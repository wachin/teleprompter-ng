"""
render_pipeline.py — Final composition command builder (Phase 8).

build_render_command() assembles ONE ffmpeg argv that materializes
the edited timeline (Phase 6 segments) with the brand kit applied:
letterbox/crop to the social ratio, logo overlay, subtitle burn-in,
and music mixing with fades. Intro/outro join happens around the
main render (concat of same-codec .ts parts).

All functions are pure data builders (unit-testable without media);
run_render() executes the plan and reports progress via callback.
"""

import os
import subprocess
import time

from branding_model import AspectRatio
from logging_setup import get_logger

log = get_logger("Render")

# drawtext needs a font file on some systems; use a common Debian one
FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
)
DEFAULT_FONT = next((f for f in FONT_CANDIDATES if os.path.isfile(f)), None)


class RenderError(Exception):
    """Render problem with a user-facing message."""


def _hex_to_ffmpeg(color):
    """'#FFD700' → '0xFFD700FF' (ffmpeg color syntax)."""
    return "0x{0}FF".format(color.lstrip("#"))


def subtitle_filter_args(style, output_height):
    """
    drawtext (subtitles style) — one drawtext per cue via the
    subtitles filter when an .srt file is given, or enable/style
    when burning a generated cue list.

    For simplicity and robustness we burn via the `subtitles`
    filter with force_style: libass handles timing, wrapping and
    styling in one go (validated: ffmpeg ≥ 4 has libass on Debian).
    """
    if not style or not style.enabled:
        return None
    force_style_parts = [
        f"FontSize={max(10, int(style.font_size * output_height / 1080))}",
        f"PrimaryColour={_hex_to_ffmpeg(style.primary_color)}",
        f"OutlineColour={_hex_to_ffmpeg(style.outline_color)}",
        "BorderStyle=1",
        "Outline=2",
        "Shadow=0",
        "Alignment=2" if style.position == "bottom-center" else "8",
    ]
    if style.position == "top-center":
        force_style_parts[-1] = "Alignment=8"
    elif style.position == "bottom-left":
        force_style_parts[-1] = "Alignment=1"
    elif style.position == "bottom-right":
        force_style_parts[-1] = "Alignment=3"
    if style.background:
        hex_color, alpha = style.background.split("@")
        force_style_parts += [
            "BackColour=0x{0}{1}".format(
                hex_color.lstrip("#"), alpha
            ),
            "BorderStyle=4",
        ]
    # The commas inside force_style would split filter options;
    # quoting the value makes ffmpeg treat it as ONE option.
    # Single quotes pass literally through the argv (no shell).
    return "force_style='" + ",".join(force_style_parts) + "'"


def build_video_filter(kit, source_w, source_h, srt_path=None):
    """
    The video filter chain: geometry (ratio fit) + logo overlay +
    subtitle burn-in. Pure data: returns the -vf string.
    """
    target = kit.aspect_ratio
    if kit.fit_mode == "crop":
        crop_w, crop_h, tw, th = AspectRatio.fit_crop(
            source_w, source_h, target,
        )
        chain = [
            f"crop={crop_w}:{crop_h}",
            f"scale={tw}:{th}",
        ]
    else:
        sw, sh, x, y = AspectRatio.fit_letterbox(
            source_w, source_h, target,
        )
        tw, th = AspectRatio.resolution(target)
        chain = [
            f"scale={sw}:{sh}",
            f"pad={tw}:{th}:{x}:{y}:black",
        ]

    if srt_path and kit.subtitle_style.enabled:
        chain.append(
            f"subtitles={_escape_filter_path(srt_path)}:{subtitle_filter_args(kit.subtitle_style, th)}"
        )

    if kit.logo_path:
        # Overlay math is done by the caller (logo needs its own
        # input stream); here we only leave the chain geometric.
        pass

    return ",".join(chain)


def _escape_filter_path(path):
    """Filters parse ':' and '\\' — escape both, quote it."""
    escaped = path.replace("\\", "\\\\").replace(":", "\\:")
    return f"'{escaped}'"


def logo_geometry(kit, output_w, output_h):
    """
    (scale_w, scale_h, x, y) for the logo overlay in output pixels.

    The logo keeps its own aspect; size = logo_scale x output width.
    Margin = 2% of the corresponding dimension.
    """
    scale_w = int(output_w * kit.logo_scale)
    # Height unknown here (caller scales keeping ratio); we return
    # a scale-only filter and position via overlay with expressions:
    margin_x = int(output_w * 0.02)
    margin_y = int(output_h * 0.02)
    if kit.logo_position == "top-left":
        return scale_w, margin_x, margin_y, f"overlay={margin_x}:{margin_y}"
    if kit.logo_position == "top-right":
        return scale_w, None, margin_y, f"overlay=W-w-{margin_x}:{margin_y}"
    if kit.logo_position == "bottom-left":
        return scale_w, margin_x, None, f"overlay={margin_x}:H-h-{margin_y}"
    # bottom-right
    return scale_w, None, None, f"overlay=W-w-{margin_x}:H-h-{margin_y}"


def build_render_command(segments, output, kit, probe,
                         srt_path=None, concat_list_path=None,
                         project_root=None):
    """
    The full ffmpeg argv for the final render of the timeline.

    segments: [Segment] (Phase 6 EditList) — exported to parts first.
    probe: {"duration_s", "width", "height"} of the source clip(s).
    kit: BrandKit with everything configured. Asset paths in the kit
         are PROJECT-RELATIVE; pass project_root so ffmpeg gets
         absolute paths (it does not know the project layout).
    srt_path: burned-in subtitles when style.enabled.
    concat_list_path: pre-joined timeline .ts (Phase 6 _concat).
    project_root: where the kit's relative paths resolve.

    The command reads the joined timeline and writes the branded
    master. Pure data: returned argv, never executed here.
    """
    if not segments:
        raise RenderError("Nothing to render: the timeline is empty")
    if probe.get("width", 0) <= 0 or probe.get("height", 0) <= 0:
        raise RenderError(
            "The source video has no readable dimensions — probe the "
            "original take, not a stream-copied part"
        )
    if concat_list_path is None:
        raise RenderError("A joined timeline file is required (see editor)")
    if not os.path.isfile(concat_list_path):
        raise RenderError(f"Joined timeline not found: {concat_list_path}")

    def resolve(path):
        """Project-relative kit path → absolute for ffmpeg."""
        if path is None or project_root is None or os.path.isabs(path):
            return path
        return os.path.join(project_root, path)

    music_abs = resolve(kit.music_path)
    logo_abs = resolve(kit.logo_path)
    srt_abs = resolve(srt_path) if srt_path else None

    cmd = [
        "ffmpeg", "-hide_banner", "-nostdin", "-y",
        "-i", concat_list_path,
    ]

    # Input indexes are fixed BEFORE adding them: music and logo
    # positions depend on the order, not on later counting.
    has_music = music_abs is not None
    music_index = cmd_inputs(cmd) if has_music else None
    if has_music:
        cmd += ["-stream_loop", "-1", "-i", music_abs]

    has_logo = logo_abs is not None
    logo_index = cmd_inputs(cmd) if has_logo else None
    if has_logo:
        cmd += ["-i", logo_abs]

    tw, th = AspectRatio.resolution(kit.aspect_ratio)
    video_chain = build_video_filter(kit, probe["width"], probe["height"], srt_abs)

    filters = [f"[0:v]{video_chain}[v0]"]
    vref = "[v0]"
    if has_logo:
        scale_w, _sx, _sy, overlay_pos = logo_geometry(kit, tw, th)
        filters.append(
            f"[{logo_index}:v]scale={scale_w}:-1,format=rgba,colorchannelmixer=aa={kit.logo_opacity}[logo]"
        )
        filters.append(
            f"{vref}[logo]{overlay_pos}[vf]"
        )
        vref = "[vf]"

    if has_music:
        # Duck the music, fade in/out, and stop with the video
        fade_out_start = max(0.0, probe["duration_s"] - kit.music_fade_out)
        filters.append(
            f"[{music_index}:a]volume={kit.music_volume},"
            f"afade=t=in:d={kit.music_fade_in},"
            f"afade=t=out:st={fade_out_start}:d={kit.music_fade_out}[music]"
        )
        filters.append(
            "[0:a][music]amix=inputs=2:duration=first:dropout_transition=3[aout]"
        )
        aref = "[aout]"
    else:
        aref = "[0:a]"

    cmd += ["-filter_complex", ";".join(filters)]

    map_args = ["-map", vref, "-map", aref]
    cmd += map_args
    cmd += [
        "-c:v", "libx264", "-preset", "medium", "-crf", "19",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
    ]
    if has_music:
        cmd += ["-shortest"]
    cmd += ["-movflags", "+faststart", output]
    return cmd


def cmd_inputs(cmd):
    """Number of -i inputs declared so far in the argv."""
    return sum(1 for a in cmd if a == "-i")


def run_render(cmd, on_progress=None, timeout=600):
    """
    Runs the render, piping stderr for progress parsing.

    Reports (0..1) from ffmpeg's time= output; returns when done.
    """
    start = time.monotonic()
    process = subprocess.Popen(
        cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        text=True, bufsize=1,
    )
    duration_hint = None
    try:
        for line in process.stderr:
            if "Duration:" in line and duration_hint is None:
                # e.g. "  Duration: 00:00:03.05"
                parts = line.split("Duration:")[1].split(",")[0].strip()
                h, m, s = parts.split(":")
                duration_hint = (
                    int(h) * 3600 + int(m) * 60 + float(s)
                )
            if "time=" in line and duration_hint and on_progress:
                time_part = line.split("time=")[1].split()[0]
                if "N/A" in time_part or ":" not in time_part:
                    continue  # stream not producing time yet
                try:
                    h, m, s = time_part.split(":")
                    current = int(h) * 3600 + int(m) * 60 + float(s)
                except ValueError:
                    continue
                on_progress(min(1.0, current / duration_hint))
        process.wait(timeout=timeout)
    finally:
        if process.poll() is None:
            process.kill()
    if process.returncode != 0:
        raise RenderError(
            f"The render failed (exit {process.returncode}). Check the free disk space "
            "and the branding assets."
        )
    log.info("Render finished in %.1f s", time.monotonic() - start)
    return True


def export_timeline_parts(segments, clip_paths, temp_dir):
    """
    Materializes each keep-range as a .ts part.

    Parts for the FINAL render re-encode (accurate): stream-copied
    seeks land mid-GOP and can drop ALL video frames (found with
    x264 sources: a 0.5 s input-seek left an audio-only part),
    which breaks [0:v] binding downstream. Preview-speed copies
    stay in the Editor (Phase 6) where fragments are acceptable.

    Returns the list of part paths in timeline order.
    """
    from ffmpeg_tools import segment_export_command

    parts = []
    for i, seg in enumerate(segments):
        source = clip_paths[seg.clip]
        part = os.path.join(temp_dir, f"part_{i:03d}.ts")
        cmd = segment_export_command(
            source, part, seg.in_s, seg.out_s, reencode=True,
        )
        result = subprocess.run(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=120, check=False,
        )
        if result.returncode != 0 or not os.path.getsize(part) > 0:
            raise RenderError(
                f"Could not export the segment {seg.in_s}-{seg.out_s}s of {os.path.basename(seg.clip)}"
            )
        parts.append(part)
    return parts


def join_parts(parts, temp_dir):
    """Concatenates same-codec parts into one timeline .ts."""
    from ffmpeg_tools import join_command, write_concat_list

    joined = os.path.join(temp_dir, "timeline.ts")
    cmd, _ = join_command(parts, joined)
    list_path = os.path.join(temp_dir, "concat.txt")
    write_concat_list(list_path, parts)
    cmd[cmd.index("CONCAT_LIST_PLACEHOLDER")] = list_path
    result = subprocess.run(
        cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        timeout=300, check=False,
    )
    if result.returncode != 0 or not os.path.isfile(joined):
        raise RenderError("Could not join the timeline segments")
    return joined
