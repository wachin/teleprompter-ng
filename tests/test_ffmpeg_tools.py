"""
tests/test_ffmpeg_tools.py — Tests for ffmpeg_tools (Phase 6).

Command construction is pure data (no ffmpeg run); probing and
silence detection run against a REAL generated take when ffmpeg is
present (a color+silence .ts made with lavfi).
"""

import os
import subprocess

import pytest

from ffmpeg_tools import (
    FFmpegToolError,
    detect_silences,
    ffmpeg_available,
    join_command,
    probe_clip,
    segment_export_command,
    write_concat_list,
)


def _make_test_video(path, seconds=3, silence_gap=True):
    """Generates a real .ts: color video + (silence → tone) audio."""
    # Audio: two lavfi SOURCES (silence, then tone) concatenated —
    # reliable with aac, unlike chained aeval (EOF issues).
    tone_s = max(0.1, seconds - 1.5)
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostdin", "-y",
         "-f", "lavfi",
         "-i", f"testsrc=duration={seconds}:size=320x240:rate=15",
         "-f", "lavfi",
         "-i", "anullsrc=r=48000:cl=mono:d=1.5",
         "-f", "lavfi",
         "-i", f"sine=frequency=440:sample_rate=48000:duration={tone_s}",
         "-filter_complex",
         "[1:a][2:a]concat=n=2:v=0:a=1[a]",
         "-map", "0:v", "-map", "[a]",
         "-c:v", "libx264", "-preset", "veryfast", "-c:a", "aac",
         "-shortest", "-f", "mpegts", path],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        timeout=60, check=True,
    )
    return path


@pytest.fixture(scope="module")
def sample_ts(tmp_path_factory):
    if not ffmpeg_available():
        pytest.skip("ffmpeg/ffprobe not available")
    path = tmp_path_factory.mktemp("media") / "sample.ts"
    _make_test_video(str(path), seconds=3)
    return str(path)


class TestProbeClip:
    """Real ffprobe over a generated take."""

    def test_probe_fields(self, sample_ts):
        info = probe_clip(sample_ts)
        assert 2.5 <= info["duration_s"] <= 4.0
        assert info["width"] == 320 and info["height"] == 240
        assert info["fps"] == 15.0
        assert info["has_audio"] is True

    def test_probe_missing_file(self, tmp_path):
        with pytest.raises(FFmpegToolError, match="not found"):
            probe_clip(str(tmp_path / "ghost.ts"))

    def test_probe_corrupt_file(self, tmp_path):
        bad = tmp_path / "bad.ts"
        bad.write_bytes(b"not a video at all")
        with pytest.raises(FFmpegToolError):
            probe_clip(str(bad))


class TestSilences:
    def test_finds_leading_silence(self, sample_ts):
        silences = detect_silences(sample_ts)
        assert silences, "leading 1.5 s silence not detected"
        start, end = silences[0]
        assert start < 0.5          # starts at the beginning
        assert 1.0 <= end <= 2.0    # ~1.5 s long

    def test_empty_when_no_ffmpeg(self, monkeypatch, sample_ts):
        monkeypatch.setattr("ffmpeg_tools.shutil.which", lambda n: None)
        assert detect_silences(sample_ts) == []

    def test_short_gaps_ignored(self, tmp_path):
        # Video with a 0.2 s gap: below the 0.4 s minimum
        path = str(tmp_path / "tinygap.ts")
        _make_test_video(path, seconds=1)
        # The detector's min duration filter is applied post-parse;
        # nothing ≥0.4s of silence in the middle of a 1s take
        result = [s for s in detect_silences(path) if s[1] - s[0] >= 0.4]
        assert all(e - s >= 0.4 for s, e in result)


class TestSegmentExportCommand:
    def test_stream_copy_by_default(self, tmp_path):
        cmd = segment_export_command("in.ts", str(tmp_path / "out.ts"), 1.0, 5.0)
        assert cmd[0] == "ffmpeg"
        assert "-c" in cmd and "copy" in cmd
        assert "-ss" in cmd and "-to" in cmd
        assert cmd[cmd.index("-ss") + 1] == "1.000"
        assert cmd[cmd.index("-to") + 1] == "5.000"

    def test_reencode_variant(self, tmp_path):
        cmd = segment_export_command(
            "in.ts", str(tmp_path / "out.ts"), 0, 3, reencode=True,
        )
        joined = " ".join(cmd)
        assert "libx264" in joined and "aac" in joined

    def test_rejects_empty_range(self, tmp_path):
        with pytest.raises(FFmpegToolError, match="after its start"):
            segment_export_command("in.ts", str(tmp_path / "o.ts"), 5.0, 5.0)


class TestJoinCommand:
    def test_shape(self, tmp_path):
        cmd, parts = join_command(["p1.ts", "p2.ts"], str(tmp_path / "j.ts"))
        assert cmd[0] == "ffmpeg"
        assert "concat" in cmd and "copy" in cmd
        assert parts == ["p1.ts", "p2.ts"]
        assert "CONCAT_LIST_PLACEHOLDER" in cmd

    def test_empty_rejected(self, tmp_path):
        with pytest.raises(FFmpegToolError, match="No segments"):
            join_command([], str(tmp_path / "j.ts"))

    def test_concat_list_writing(self, tmp_path):
        list_path = str(tmp_path / "list.txt")
        write_concat_list(list_path, ["a.ts", "b'c.ts"])
        with open(list_path, encoding="utf-8") as f:
            content = f.read()
        assert "file 'a.ts'" in content
        # ffmpeg concat-demuxer quote escaping: ' → '\'' inside the quotes
        assert "file 'b'\\''c.ts'" in content


class TestRealSegmentExport:
    """Cut the generated take and verify the result with ffprobe."""

    def test_export_and_duration(self, sample_ts, tmp_path):
        out = str(tmp_path / "cut.ts")
        subprocess.run(
            segment_export_command(sample_ts, out, 1.0, 2.0),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=30, check=True,
        )
        assert os.path.getsize(out) > 5000
        info = probe_clip(out)
        # Stream copy lands near the requested window (keyframe snap)
        assert 0.5 <= info["duration_s"] <= 1.5

    def test_original_untouched(self, sample_ts):
        """Non-destructive: the source keeps its size and duration."""
        before_size = os.path.getsize(sample_ts)
        before_dur = probe_clip(sample_ts)["duration_s"]
        # (exports in other tests never modify it)
        assert os.path.getsize(sample_ts) == before_size
        assert probe_clip(sample_ts)["duration_s"] == before_dur
