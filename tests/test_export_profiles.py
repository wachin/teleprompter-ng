"""
tests/test_export_profiles.py — Tests for Phase 10.

Profile ladders and metadata are pure data; the real multi-take
render (body + intro/outro, profile command, thumbnail, validation)
runs against generated media.
"""

import os
import shutil
import subprocess

import pytest

import render_pipeline as rp
from branding_model import BrandKit
from edit_model import EditList
from export_profiles import (
    PROFILES,
    ExportProfile,
    ProfileError,
    get_profile,
    suggest_metadata,
)
from ffmpeg_tools import probe_clip

pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="requires ffmpeg and ffprobe",
)


class TestProfiles:
    """Built-in profile data + ladders."""

    def test_five_profiles(self):
        assert set(PROFILES) == {"youtube", "shorts", "linkedin",
                                 "draft", "master"}

    def test_ratios(self):
        assert PROFILES["youtube"].aspect_ratio == "16:9"
        assert PROFILES["shorts"].aspect_ratio == "9:16"
        assert PROFILES["linkedin"].aspect_ratio == "1:1"

    def test_get_profile(self):
        assert get_profile("shorts") is PROFILES["shorts"]
        with pytest.raises(ProfileError, match="Available"):
            get_profile("vimeo")

    def test_video_ladders(self):
        draft = PROFILES["draft"].video_args()
        balanced = PROFILES["youtube"].video_args()
        master = PROFILES["master"].video_args()
        assert "26" in draft and "veryfast" in draft
        assert "21" in balanced and "medium" in balanced
        assert "18" in master and "slow" in master

    def test_audio_bitrates(self):
        assert "128k" in PROFILES["draft"].audio_args()
        assert "192k" in PROFILES["youtube"].audio_args()
        assert "256k" in PROFILES["master"].audio_args()

    def test_container_faststart(self):
        args = PROFILES["youtube"].container_args("/tmp/o.mp4")
        assert "+faststart" in args and args[-1] == "/tmp/o.mp4"

    def test_bad_tier_or_ratio(self):
        with pytest.raises(ProfileError, match="tier"):
            ExportProfile("x", "X", "16:9", "ultra", "d")
        with pytest.raises(ProfileError, match="ratio"):
            ExportProfile("x", "X", "21:9", "draft", "d")

    def test_size_estimate_scales(self):
        prof = PROFILES["youtube"]
        big = prof.estimate_size_bytes(60, 1080)
        small = prof.estimate_size_bytes(60, 540)
        assert big > small > 0
        assert prof.estimate_size_bytes(0, 1080) >= 0

    def test_descriptions_document_ffmpeg(self):
        # Roadmap: documented parameters — every profile mentions codec
        for prof in PROFILES.values():
            assert "H.264" in prof.description
            assert "AAC" in prof.description


class TestMetadata:
    def test_title_only(self):
        assert suggest_metadata("Hello") == "Hello"

    def test_full_block(self):
        text = suggest_metadata(
            "My video", "A description", ["linux", "#tools"],
        )
        lines = text.splitlines()
        assert lines[0] == "My video"
        assert "A description" in lines
        assert "#linux #tools" in lines

    def test_tags_cleaned(self):
        text = suggest_metadata("T", "", ["Big Topic", "#ok"])
        assert "#BigTopic #ok" in text


class TestProfileCommand:
    """build_profile_command swaps the ladder correctly."""

    def _kit(self, ratio="9:16"):
        kit = BrandKit(aspect_ratio=ratio)
        return kit

    def _segments(self):
        edit = EditList({"a.ts": 3.0})
        edit.load_clips(["a.ts"])
        return edit.segments

    def test_ladder_applied(self, tmp_path):
        joined = tmp_path / "t.ts"
        joined.write_bytes(b"x" * 100)
        kit = BrandKit(aspect_ratio="16:9")  # matches the draft profile
        cmd = rp.build_profile_command(
            self._segments(), str(tmp_path / "o.mp4"), kit,
            {"duration_s": 3, "width": 320, "height": 240},
            PROFILES["draft"],
            concat_list_path=str(joined),
        )
        assert "veryfast" in cmd and "26" in cmd
        assert "128k" in cmd

    def test_ratio_mismatch_refused(self, tmp_path):
        joined = tmp_path / "t.ts"
        joined.write_bytes(b"x" * 100)
        with pytest.raises(rp.RenderError, match="profile"):
            rp.build_profile_command(
                self._segments(), str(tmp_path / "o.mp4"),
                BrandKit(aspect_ratio="16:9"),
                {"duration_s": 3, "width": 320, "height": 240},
                PROFILES["shorts"],  # 9:16 vs 16:9 kit
                concat_list_path=str(joined),
            )


class TestThumbnailValidation:
    def test_thumbnail_and_validate(self, tmp_path):
        take = tmp_path / "take.ts"
        subprocess.run(
            ["ffmpeg", "-hide_banner", "-nostdin", "-y",
             "-f", "lavfi", "-i", "testsrc=duration=3:size=320x240:rate=15",
             "-f", "lavfi",
             "-i", "sine=frequency=440:sample_rate=48000:duration=3",
             "-c:v", "libx264", "-preset", "veryfast", "-c:a", "aac",
             "-shortest", "-f", "mpegts", str(take)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=60, check=True,
        )
        thumb = str(tmp_path / "thumb.jpg")
        rp.extract_thumbnail(str(take), thumb)
        assert os.path.getsize(thumb) > 5000  # real JPEG

        ok, problem = rp.validate_output(str(take))
        assert ok, problem

    def test_validate_missing(self, tmp_path):
        ok, problem = rp.validate_output(str(tmp_path / "ghost.mp4"))
        assert not ok and "does not exist" in problem

    def test_validate_tiny(self, tmp_path):
        tiny = tmp_path / "tiny.mp4"
        tiny.write_bytes(b"x" * 100)
        ok, problem = rp.validate_output(str(tiny))
        assert not ok and "small" in problem

    def test_validate_garbage(self, tmp_path):
        bad = tmp_path / "bad.mp4"
        bad.write_bytes(os.urandom(200_000))
        ok, _problem = rp.validate_output(str(bad))
        assert not ok


class TestRealMultiTake:
    """Body + intro + outro assembled, exported with a profile."""

    def test_assembly_with_bookends(self, tmp_path):
        def make(path, seconds, freq):
            subprocess.run(
                ["ffmpeg", "-hide_banner", "-nostdin", "-y",
                 "-f", "lavfi",
                 "-i", f"testsrc=duration={seconds}:size=320x240:rate=15",
                 "-f", "lavfi",
                 "-i", f"sine=frequency={freq}:sample_rate=48000:duration={seconds}",
                 "-c:v", "libx264", "-preset", "veryfast", "-c:a", "aac",
                 "-shortest", "-f", "mpegts", path],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=60, check=True,
            )

        make(str(tmp_path / "intro.ts"), 1, 220)
        make(str(tmp_path / "body.ts"), 3, 440)
        make(str(tmp_path / "outro.ts"), 1, 330)

        edit = EditList({"body.ts": 3.0})
        edit.load_clips(["body.ts"])
        edit.trim_head(0, 0.5)
        edit.trim_tail(0, 2.5)   # body keeps 0.5-2.5 -> 2.0 s

        joined = rp.assemble_timeline(
            edit.segments,
            {"body.ts": str(tmp_path / "body.ts")},
            str(tmp_path),
            intro_path=str(tmp_path / "intro.ts"),
            outro_path=str(tmp_path / "outro.ts"),
        )
        info = probe_clip(joined)
        # 1 s intro + 2 s body + 1 s outro ≈ 4 s (stream-copy joins
        # may snap; allow slack but require all three present)
        assert 3.5 <= info["duration_s"] <= 4.6, info["duration_s"]

        # Full profiled export on the assembled timeline
        kit = BrandKit(aspect_ratio="9:16")
        probe = probe_clip(str(tmp_path / "body.ts"))
        probe["duration_s"] = info["duration_s"]
        output = str(tmp_path / "final.mp4")
        cmd = rp.build_profile_command(
            edit.segments, output, kit, probe, PROFILES["shorts"],
            concat_list_path=joined,
        )
        rp.run_render(cmd)
        ok, problem = rp.validate_output(output)
        assert ok, problem
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-print_format", "json",
             "-show_streams", output],
            capture_output=True, text=True, timeout=15, check=True,
        )
        import json
        v = next(s for s in json.loads(result.stdout)["streams"]
                 if s["codec_type"] == "video")
        assert (v["width"], v["height"]) == (1080, 1920)
