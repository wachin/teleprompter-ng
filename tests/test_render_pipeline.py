"""
tests/test_render_pipeline.py — Tests for render_pipeline (Phase 8).

Command construction is pure data; the REAL render test takes a
generated take + a generated logo + generated music through the full
pipeline (parts → join → branded 9:16 master with burn-in) and
validates the output with ffprobe.
"""

import os
import shutil
import subprocess

import pytest

from branding_model import BrandKit, SubtitleStyle
from edit_model import EditList
from ffmpeg_tools import probe_clip
from render_pipeline import (
    RenderError,
    build_render_command,
    build_video_filter,
    export_timeline_parts,
    join_parts,
    logo_geometry,
    run_render,
    subtitle_filter_args,
)

pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="requires ffmpeg and ffprobe",
)


@pytest.fixture(scope="module")
def take(tmp_path_factory):
    """A real 3 s take (video + tone audio)."""
    path = tmp_path_factory.mktemp("media") / "take.ts"
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostdin", "-y",
         "-f", "lavfi", "-i", "testsrc=duration=3:size=320x240:rate=15",
         "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=3",
         "-c:v", "libx264", "-preset", "veryfast", "-c:a", "aac",
         "-shortest", "-f", "mpegts", str(path)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        timeout=60, check=True,
    )
    return str(path)


@pytest.fixture(scope="module")
def logo_png(tmp_path_factory):
    """A real 200x80 PNG logo."""
    path = tmp_path_factory.mktemp("brand") / "logo.png"
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostdin", "-y",
         "-f", "lavfi", "-i", "color=c=gold:s=200x80:d=0.1",
         "-frames:v", "1", str(path)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        timeout=30, check=True,
    )
    return str(path)


@pytest.fixture(scope="module")
def music_mp3(tmp_path_factory):
    """A real 10 s MP3 (440 Hz)."""
    path = tmp_path_factory.mktemp("brand") / "theme.mp3"
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostdin", "-y",
         "-f", "lavfi", "-i", "sine=frequency=330:sample_rate=44100:duration=10",
         "-b:a", "64k", str(path)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        timeout=30, check=True,
    )
    return str(path)


class TestVideoFilter:
    """build_video_filter: geometry + burn-in chaining."""

    def test_letterbox_16x9_passthrough(self):
        kit = BrandKit()
        chain = build_video_filter(kit, 1920, 1080)
        assert chain == "scale=1920:1080,pad=1920:1080:0:0:black"

    def test_letterbox_to_9x16(self):
        kit = BrandKit(aspect_ratio="9:16")
        chain = build_video_filter(kit, 1920, 1080)
        assert "pad=1080:1920" in chain
        assert "scale=1080:606" in chain

    def test_crop_to_1x1(self):
        kit = BrandKit(aspect_ratio="1:1", fit_mode="crop")
        chain = build_video_filter(kit, 1920, 1080)
        assert chain.startswith("crop=1080:1080")
        assert "scale=1080:1080" in chain

    def test_subtitle_burnin_in_chain(self, tmp_path):
        kit = BrandKit()
        kit.subtitle_style.enabled = True
        srt = str(tmp_path / "subs.srt")
        with open(srt, "w") as f:
            f.write("1\n00:00:00,000 --> 00:00:01,000\nHi\n")
        chain = build_video_filter(kit, 1920, 1080, srt_path=srt)
        assert "subtitles=" in chain
        assert "force_style='FontSize=" in chain


class TestSubtitleStyleArgs:
    def test_disabled_returns_none(self):
        assert subtitle_filter_args(SubtitleStyle(), 1080) is None

    def test_enabled_args(self):
        style = SubtitleStyle(
            enabled=True, font_size=28, position="bottom-center",
        )
        args = subtitle_filter_args(style, 1920)
        assert "FontSize=" in args
        assert "Alignment=2" in args

    def test_size_scales_with_height(self):
        style = SubtitleStyle(enabled=True, font_size=28)
        hd = subtitle_filter_args(style, 1080)
        uhd = subtitle_filter_args(style, 2160)
        assert uhd != hd  # bigger canvas → bigger font

    def test_background_box(self):
        style = SubtitleStyle(enabled=True, background="#000000@80")
        args = subtitle_filter_args(style, 1080)
        assert "BackColour=0x00000080" in args
        assert "BorderStyle=4" in args


class TestLogoGeometry:
    def test_bottom_right(self):
        kit = BrandKit(logo_scale=0.15, logo_position="bottom-right")
        scale_w, _sx, _sy, overlay = logo_geometry(kit, 1920, 1080)
        assert scale_w == 288
        assert overlay == "overlay=W-w-38:H-h-21"  # 2% margins

    def test_top_left(self):
        kit = BrandKit(logo_position="top-left")
        _sw, _x, _y, overlay = logo_geometry(kit, 1080, 1920)
        assert overlay == "overlay=21:38"


class TestBuildRenderCommand:
    def _segments(self):
        edit = EditList({"a.ts": 3.0})
        edit.load_clips(["a.ts"])
        return edit.segments

    def test_minimal_command(self, take, tmp_path):
        kit = BrandKit()
        joined = os.path.join(tmp_path, "timeline.ts")
        shutil.copy(take, joined)
        probe = {"duration_s": 3.0, "width": 320, "height": 240}
        cmd = build_render_command(
            self._segments(), str(tmp_path / "out.mp4"), kit, probe,
            concat_list_path=joined,
        )
        assert cmd[0] == "ffmpeg"
        assert str(tmp_path / "out.mp4") == cmd[-1]
        joined_args = " ".join(cmd)
        assert "libx264" in joined_args and "aac" in joined_args
        assert "faststart" in joined_args

    def test_empty_timeline_rejected(self, take, tmp_path):
        kit = BrandKit()
        probe = {"duration_s": 3.0, "width": 320, "height": 240}
        with pytest.raises(RenderError, match="empty"):
            build_render_command(
                [], str(tmp_path / "o.mp4"), kit, probe,
                concat_list_path=take,
            )

    def test_missing_joined_rejected(self, tmp_path):
        kit = BrandKit()
        probe = {"duration_s": 3, "width": 320, "height": 240}
        edit = EditList({"a.ts": 3.0})
        edit.load_clips(["a.ts"])
        with pytest.raises(RenderError, match="not found"):
            build_render_command(
                edit.segments, str(tmp_path / "o.mp4"), kit, probe,
                concat_list_path=str(tmp_path / "ghost.ts"),
            )

    def test_music_adds_amix(self, take, tmp_path, music_mp3):
        kit = BrandKit(music_path=music_mp3, music_volume=0.4)
        joined = os.path.join(tmp_path, "timeline.ts")
        shutil.copy(take, joined)
        probe = {"duration_s": 3.0, "width": 320, "height": 240}
        cmd = build_render_command(
            self._segments(), str(tmp_path / "o.mp4"), kit, probe,
            concat_list_path=joined,
        )
        assert "amix=inputs=2" in " ".join(cmd)
        assert "afade=t=out" in " ".join(cmd)

    def test_logo_adds_overlay(self, take, tmp_path, logo_png):
        kit = BrandKit(logo_path=logo_png)
        joined = os.path.join(tmp_path, "timeline.ts")
        shutil.copy(take, joined)
        probe = {"duration_s": 3.0, "width": 320, "height": 240}
        cmd = build_render_command(
            self._segments(), str(tmp_path / "o.mp4"), kit, probe,
            concat_list_path=joined,
        )
        assert "overlay=" in " ".join(cmd)
        assert "colorchannelmixer=aa=0.85" in " ".join(cmd)


class TestRealPipeline:
    """Full render with real media on this machine."""

    def _edit(self, in_s=0.0, out_s=3.0):
        edit = EditList({"a.ts": 3.0})
        edit.load_clips(["a.ts"])
        edit.trim_head(0, in_s)
        edit.trim_tail(0, out_s)
        return edit

    def test_render_9x16_with_all_branding(
        self, take, logo_png, music_mp3, tmp_path,
    ):
        # Assets inside a project-like root with RELATIVE paths
        root = tmp_path / "project"
        (root / "media" / "assets").mkdir(parents=True)
        shutil.copy(logo_png, root / "media" / "assets" / "logo.png")
        shutil.copy(music_mp3, root / "media" / "assets" / "theme.mp3")
        shutil.copy(take, root / "take.ts")

        kit = BrandKit(
            logo_path="media/assets/logo.png",
            logo_scale=0.2,
            music_path="media/assets/theme.mp3",
            music_volume=0.3,
            aspect_ratio="9:16",
        )
        kit.subtitle_style.enabled = True

        # Subtitles
        srt = root / "subs.srt"
        srt.write_text(
            "1\n00:00:00,500 --> 00:00:02,000\nHello branding\n",
            encoding="utf-8",
        )

        edit = self._edit(0.5, 2.5)  # keep 0.5-2.5 s
        parts = export_timeline_parts(
            edit.segments, {"a.ts": str(root / "take.ts")}, str(tmp_path),
        )
        joined = join_parts(parts, str(tmp_path))

        output = str(root / "export.mp4")
        # Probe the ORIGINAL clip: stream-copied parts report 0x0
        # (mpegts quirk), and the branding view uses the source's
        # geometry exactly like this.
        probe = probe_clip(str(root / "take.ts"))
        probe["duration_s"] = 2.0
        cmd = build_render_command(
            edit.segments, output, kit, probe,
            srt_path=str(srt), concat_list_path=joined,
            project_root=str(root),
        )
        progress_values = []
        run_render(cmd, on_progress=progress_values.append)

        # Validate the master
        assert os.path.isfile(output)
        assert os.path.getsize(output) > 30_000
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-print_format", "json",
             "-show_streams", "-show_format", output],
            capture_output=True, text=True, timeout=15, check=True,
        )
        import json
        info = json.loads(result.stdout)
        v = next(s for s in info["streams"] if s["codec_type"] == "video")
        # 9:16 target
        assert (v["width"], v["height"]) == (1080, 1920)
        assert v["codec_name"] == "h264"
        duration = float(info["format"]["duration"])
        assert 1.5 <= duration <= 3.5
        # Progress was reported
        assert progress_values and progress_values[-1] >= 0.9
