"""
ffmpeg_tools.py — FFmpeg/ffprobe helpers for review and edit (Phase 6).

- probe_clip(): duration/resolution/fps of a recorded take.
- detect_silences(): ranges of near-silence via ffmpeg silencedetect.
- segment_export_command(): the ffmpeg argv that materializes ONE
  keep-range from an original .ts without re-encoding quality loss
  (stream copy when in/out land on safe points; re-encode otherwise).
- join_command(): concatenates exported segments losslessly
  (same codec) — used by export previews and Phase 10.

All commands are pure data (unit-tested without running ffmpeg).
"""

import json
import re
import shutil
import subprocess

from logging_setup import get_logger

log = get_logger("FFmpeg")

SILENCE_DB = "-35dB"       # anything quieter counts as silence
SILENCE_MIN_S = 0.4        # ignore gaps shorter than this


class FFmpegToolError(Exception):
    """Helper failure with a user-facing message."""


def ffmpeg_available():
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def probe_clip(path):
    """
    Returns {"duration_s", "width", "height", "fps", "has_audio"}.

    Raises FFmpegToolError for missing/broken files (actionable text).
    """
    if not shutil.which("ffprobe"):
        raise FFmpegToolError(
            "ffprobe is not installed. Install it with: sudo apt install ffmpeg"
        )
    if not shutil.os.path.isfile(path):
        raise FFmpegToolError(f"File not found: {path}")
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-print_format", "json",
             "-show_format", "-show_streams", path],
            capture_output=True, text=True, timeout=15, check=True,
        )
    except subprocess.SubprocessError as e:
        raise FFmpegToolError(
            f"Could not read {path}: {e}"
        ) from e
    info = json.loads(result.stdout)
    try:
        duration = float(info["format"]["duration"])
    except (KeyError, ValueError) as e:
        raise FFmpegToolError(
            f"{path} has no readable duration — it may be corrupt"
        ) from e
    streams = info.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), {})
    fps = 30.0
    rate = video.get("avg_frame_rate", "30/1")
    with __import__("contextlib").suppress(ZeroDivisionError, ValueError):
        num, den = rate.split("/")
        fps = float(num) / float(den) if float(den) else 30.0
    return {
        "duration_s": duration,
        "width": int(video.get("width", 0)),
        "height": int(video.get("height", 0)),
        "fps": round(fps, 3),
        "has_audio": any(s.get("codec_type") == "audio" for s in streams),
    }


def detect_silences(path, noise_db=SILENCE_DB, min_s=SILENCE_MIN_S):
    """
    Returns [(start_s, end_s)] of silences, parsed from
    `ffmpeg -af silencedetect` stderr.

    Only gaps of at least min_s are returned (short pauses are
    natural speech rhythm). Errors return [] — silence removal is
    always optional, never fatal.
    """
    if not shutil.which("ffmpeg"):
        return []
    try:
        result = subprocess.run(
            ["ffmpeg", "-hide_banner", "-nostdin", "-i", path,
             "-af", f"silencedetect=noise={noise_db}:d={min_s}",
             "-f", "null", "-"],
            capture_output=True, text=True, timeout=60, check=False,
        )
    except subprocess.SubprocessError as e:
        log.warning("Silence detection failed: %s", e)
        return []
    silences = []
    start = None
    for line in result.stderr.splitlines():
        m = re.search(
            r"silence_(start|end):\s*([-\d.]+)", line,
        )
        if not m:
            continue
        kind, value = m.group(1), float(m.group(2))
        if kind == "start":
            start = value
        elif kind == "end" and start is not None:
            if value - start >= min_s:
                silences.append((start, value))
            start = None
    return silences


def segment_export_command(source, output, in_s, out_s, reencode=False):
    """
    ffmpeg argv materializing [in_s, out_s) of `source` into `output`.

    Default is stream copy (-c copy): instant and lossless for rough
    cuts (the editor preview). Re-encode (accurate frames) is used by
    the final export (Phase 10) or when the caller needs frame-exact
    boundaries.
    """
    if out_s <= in_s:
        raise FFmpegToolError("Segment end must be after its start")
    cmd = [
        "ffmpeg", "-hide_banner", "-nostdin", "-y",
        "-i", source,
    ]
    if reencode:
        # OUTPUT seeking (after -i): decodes from the start and cuts
        # exactly. Input-seeking on mpegts landed mid-GOP and produced
        # AUDIO-ONLY parts (ffmpeg 7.1.5, x264 sources) — found live.
        cmd += [
            "-ss", f"{in_s:.3f}",
            "-to", f"{out_s:.3f}",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k",
        ]
    else:
        # Stream copy keeps INPUT seeking (fast preview cuts)
        cmd = [
            "ffmpeg", "-hide_banner", "-nostdin", "-y",
            "-ss", f"{in_s:.3f}",
            "-to", f"{out_s:.3f}",
            "-i", source,
            "-c", "copy",
        ]
    cmd += ["-f", "mpegts", output]
    return cmd


def join_command(parts, output):
    """
    ffmpeg argv concatenating same-codec .ts parts losslessly.

    parts: list of exported segment .ts paths, in timeline order.
    Uses the concat demuxer via a file list on stdin.
    """
    if not parts:
        raise FFmpegToolError("No segments to join")
    # list file via process substitution is not portable: use -f concat
    # with concat: protocol requires a list file; we return the argv
    # expecting the caller to pass the list path as the concat input.
    return [
        "ffmpeg", "-hide_banner", "-nostdin", "-y",
        "-f", "concat", "-safe", "0",
        "-i", "CONCAT_LIST_PLACEHOLDER",
        "-c", "copy",
        "-f", "mpegts", output,
    ], parts  # caller writes parts list to CONCAT_LIST_PLACEHOLDER


def write_concat_list(list_path, parts):
    """Writes the concat demuxer list file."""
    with open(list_path, "w", encoding="utf-8") as f:
        for part in parts:
            f.write("file '{0}'\n".format(part.replace("'", "'\\''")))
    return list_path
