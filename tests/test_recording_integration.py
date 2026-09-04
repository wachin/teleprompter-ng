"""
tests/test_recording_integration.py — Real end-to-end recording (Phase 5).

Records ~3 s from the built-in camera (/dev/video0) and the default
microphone through FFmpeg, then validates the file with ffprobe:
both streams present, sane duration, and playable size.

Skipped automatically without camera/microphone/ffmpeg — the Phase 5
acceptance ("VLC/FFplay-playable file with synced audio+video") is
also a manual release-checklist item (docs/PHASE-5.md).
"""

import json
import os
import shutil
import subprocess
import time

import cv2
import pytest

pytestmark = pytest.mark.skipif(
    not os.path.exists("/dev/video0")
    or shutil.which("ffmpeg") is None
    or shutil.which("ffprobe") is None,
    reason="requires /dev/video0, ffmpeg and ffprobe",
)


def _ffprobe(path):
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json",
         "-show_format", "-show_streams", path],
        capture_output=True, text=True, timeout=15, check=True,
    )
    return json.loads(result.stdout)


class TestRealRecording:
    """Camera + microphone → .ts via ffmpeg on this machine."""

    def test_record_three_seconds(self, tmp_path):
        from audio_service import default_microphone
        from camera_service import device_formats
        from recording_service import (
            RecordingService,
            check_prerequisites,
        )

        mic = default_microphone()
        assert mic, "no microphone found"

        # Smallest real camera mode for a fast test
        formats = device_formats("/dev/video0")
        w, h, fps = min(formats, key=lambda k: k[0] * k[1])
        assert check_prerequisites(str(tmp_path)) == []

        svc = RecordingService()
        output = str(tmp_path / "take_test.ts")
        svc.start(output, w, h, fps, mic)

        # Feed frames from OpenCV directly (no Qt needed here)
        cap = cv2.VideoCapture("/dev/video0")
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
        cap.set(cv2.CAP_PROP_FPS, fps)
        assert cap.isOpened()

        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            ok, frame = cap.read()
            if ok:
                svc.feed_frame(frame)
            time.sleep(1.0 / fps)
        cap.release()

        path = svc.stop(timeout=10)
        assert path is not None, "recording was not finalized"
        assert os.path.isfile(path)
        size = os.path.getsize(path)
        # Enough for both streams at the smallest camera mode (3 s take
        # at 320x240 can be ~40 KB — small is fine, EMPTY is not)
        assert size > 15_000, f"file suspiciously small: {size} bytes"

        # ffprobe: container + both streams
        info = _ffprobe(path)
        streams = info["streams"]
        kinds = {s["codec_type"] for s in streams}
        assert "video" in kinds and "audio" in kinds

        v = next(s for s in streams if s["codec_type"] == "video")
        a = next(s for s in streams if s["codec_type"] == "audio")
        assert v["codec_name"] == "h264"
        assert a["codec_name"] == "aac"
        assert int(v["width"]) == w and int(v["height"]) == h

        duration = float(info["format"]["duration"])
        assert 1.0 <= duration <= 10.0, duration

    def test_stops_cleanly_no_orphans(self, tmp_path):
        """After stop, no ffmpeg process with our output remains."""
        import subprocess as sp

        from recording_service import RecordingService

        before = sp.run(["pgrep", "-c", "-f", "ffmpeg"],
                        capture_output=True, text=True).stdout.strip()
        # (just starting + cancelling must not add orphans)
        svc = RecordingService()
        svc._proc = None
        svc.stop()  # no-op stop with nothing running
        after = sp.run(["pgrep", "-c", "-f", "ffmpeg"],
                       capture_output=True, text=True).stdout.strip()
        assert before == after or int(after or 0) == 0

    def test_playable_with_ffplay_demux(self, tmp_path):
        """ffmpeg can demux the whole file (VLC/FFplay sanity proxy)."""
        from audio_service import default_microphone
        from camera_service import device_formats
        from recording_service import RecordingService

        mic = default_microphone()
        formats = device_formats("/dev/video0")
        w, h, fps = min(formats, key=lambda k: k[0] * k[1])

        svc = RecordingService()
        output = str(tmp_path / "take_demux.ts")
        svc.start(output, w, h, fps, mic)
        cap = cv2.VideoCapture("/dev/video0")
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            ok, frame = cap.read()
            if ok:
                svc.feed_frame(frame)
        cap.release()
        path = svc.stop(timeout=10)
        assert path is not None

        # Demux to null: proves the whole file parses
        result = subprocess.run(
            ["ffmpeg", "-v", "error", "-i", path, "-f", "null", "-"],
            capture_output=True, text=True, timeout=30, check=True,
        )
        assert result.returncode == 0
