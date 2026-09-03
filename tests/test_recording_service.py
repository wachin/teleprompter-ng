"""
tests/test_recording_service.py — Unit tests for Phase 5 (no hardware).

Covers: ffmpeg command construction (pure data), pre-flight checks,
crash recovery listing, filename suggestion, and the pipe writer's
drop behavior with a fake process. Real end-to-end recording with
the actual camera + microphone is in test_recording_integration.py
(skipped without hardware).
"""

import os
import subprocess
import time

import pytest

from recording_service import (
    BYTES_PER_MINUTE,
    MIN_FREE_BYTES,
    RecordingError,
    RecordingService,
    _PipeWriter,
    build_ffmpeg_command,
    check_prerequisites,
    ffmpeg_available,
    recover_incomplete,
    suggest_filename,
)


class TestBuildCommand:
    """FFmpeg argv is pure data — asserted without running ffmpeg."""

    def test_basic_shape(self, tmp_path):
        cmd = build_ffmpeg_command(
            str(tmp_path / "take.ts"), 1280, 720, 30, "alsa_input.mic",
        )
        assert cmd[0] == "ffmpeg"
        joined = " ".join(cmd)
        assert "libx264" in joined and "aac" in joined
        assert "-f mpegts" in joined or ("-f" in joined and "mpegts" in joined)
        assert str(tmp_path / "take.ts") == cmd[-1]

    def test_video_input_format(self, tmp_path):
        cmd = build_ffmpeg_command(
            str(tmp_path / "t.ts"), 640, 480, 25, "src",
        )
        # rawvideo bgr24 at the right size/fps on stdin
        i = cmd.index("-f")
        assert cmd[i + 1] == "rawvideo"
        assert cmd[cmd.index("-pix_fmt") + 1] == "bgr24"
        assert "640x480" in cmd
        assert "25" in cmd[cmd.index("-r") + 1]

    def test_audio_pulse_source(self, tmp_path):
        cmd = build_ffmpeg_command(
            str(tmp_path / "t.ts"), 640, 480, 30, "alsa_input.pci-mic",
        )
        assert "-f" in cmd
        assert "pulse" in cmd
        assert "alsa_input.pci-mic" in cmd
        # Both streams mapped explicitly
        assert cmd[cmd.index("-map") + 1] == "0:v"
        assert "-shortest" in cmd

    def test_requires_ts_extension(self, tmp_path):
        with pytest.raises(RecordingError, match=r"\.ts"):
            build_ffmpeg_command(
                str(tmp_path / "take.mp4"), 640, 480, 30, "src",
            )

    def test_burn_in_not_yet(self, tmp_path):
        with pytest.raises(RecordingError, match="burn-in"):
            build_ffmpeg_command(
                str(tmp_path / "t.ts"), 640, 480, 30, "src", burn_in=True,
            )


class TestPrerequisites:
    """Pre-flight informs BEFORE the user hits a wall."""

    def test_missing_ffmpeg_detected(self, monkeypatch, tmp_path):
        monkeypatch.setattr("recording_service.ffmpeg_available",
                            lambda: False)
        problems = check_prerequisites(str(tmp_path))
        assert any("ffmpeg" in p.lower() for p in problems)

    def test_all_good(self, tmp_path):
        if not ffmpeg_available():
            pytest.skip("ffmpeg not installed")
        assert check_prerequisites(str(tmp_path)) == []

    def test_creates_directory(self, tmp_path):
        target = tmp_path / "new" / "raw"
        check_prerequisites(str(target))
        assert target.is_dir()

    def test_low_disk_flagged(self, monkeypatch, tmp_path):
        monkeypatch.setattr(
            "shutil.disk_usage",
            lambda p: type("D", (), {"free": 10 * 1024 * 1024})(),  # 10 MB
        )
        problems = check_prerequisites(str(tmp_path))
        assert any("free" in p.lower() for p in problems)

    def test_constants_sane(self):
        assert MIN_FREE_BYTES > 100 * 1024 * 1024
        assert 5 * 1024 * 1024 < BYTES_PER_MINUTE < 100 * 1024 * 1024


class TestRecovery:
    """SIGKILL leftovers are listed, oldest first, for user choice."""

    def test_finds_part_files(self, tmp_path):
        for name in ("b.ts.part", "a.ts.part"):
            (tmp_path / name).write_bytes(b"x" * 500)
        time.sleep(0.01)
        (tmp_path / "c.ts.part").write_bytes(b"y" * 700)
        found = recover_incomplete(str(tmp_path))
        names = [os.path.basename(p) for p, _ in found]
        assert set(names) == {"a.ts.part", "b.ts.part", "c.ts.part"}
        assert found[0][1] == 500

    def test_ignores_finished(self, tmp_path):
        (tmp_path / "done.ts").write_bytes(b"x" * 100)
        assert recover_incomplete(str(tmp_path)) == []

    def test_missing_dir(self):
        assert recover_incomplete("/nonexistent/dir") == []

    def test_suggest_filename(self, tmp_path):
        path = suggest_filename(str(tmp_path))
        assert path.startswith(str(tmp_path))
        assert "take_" in path and path.endswith(".ts")


class TestServiceLifecycle:
    """State machine with a fake ffmpeg process."""

    def _fake_proc(self):
        """A Popen-like object that accepts writes and exits on q."""

        class FakeProc:
            def __init__(self):
                class Stdin:
                    buffer = b""

                    def write(self, data):
                        Stdin.buffer += data

                    def flush(self):
                        pass

                    def close(self):
                        pass
                self.stdin = Stdin()
                self._exited = False

            def poll(self):
                return 0 if self._exited else None

            def wait(self, timeout=None):
                self._exited = True
                return 0

            def kill(self):
                self._exited = True

        return FakeProc()

    def test_not_recording_initially(self):
        svc = RecordingService()
        assert not svc.is_recording()
        assert svc.stop() is None  # idempotent

    def test_start_requires_ffmpeg(self, tmp_path, monkeypatch):
        monkeypatch.setattr("recording_service.ffmpeg_available",
                            lambda: False)
        svc = RecordingService()
        with pytest.raises(RecordingError, match="ffmpeg"):
            svc.start(str(tmp_path / "t.ts"), 640, 480, 30, "src")

    def test_start_then_stop(self, tmp_path, monkeypatch):
        monkeypatch.setattr("recording_service.ffmpeg_available",
                            lambda: True)
        svc = RecordingService()
        monkeypatch.setattr(
            "recording_service.check_prerequisites", lambda d: [],
        )
        fake = self._fake_proc()
        monkeypatch.setattr(
            subprocess, "Popen", lambda *a, **k: fake,
        )
        path = str(tmp_path / "t.ts")
        svc.start(path, 640, 480, 30, "src")
        assert svc.is_recording()
        assert svc.elapsed_seconds() >= 0.0

        # Fake a valid output file so stop() reports success
        with open(path, "wb") as f:
            f.write(b"0" * 5000)

        result = svc.stop()
        assert result == path
        assert not svc.is_recording()

    def test_double_start_rejected(self, tmp_path, monkeypatch):
        monkeypatch.setattr("recording_service.ffmpeg_available",
                            lambda: True)
        monkeypatch.setattr(
            "recording_service.check_prerequisites", lambda d: [],
        )
        fake = self._fake_proc()
        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: fake)
        svc = RecordingService()
        svc.start(str(tmp_path / "t.ts"), 640, 480, 30, "src")
        with pytest.raises(RecordingError, match="already"):
            svc.start(str(tmp_path / "t2.ts"), 640, 480, 30, "src")
        svc._cleanup()

    def test_feed_frame_when_not_recording_is_noop(self):
        svc = RecordingService()
        svc.feed_frame(None)  # must not raise


class TestPipeWriter:
    """Backpressure drops frames instead of blocking the UI."""

    def test_drops_when_full(self):
        class FakeProc:
            class stdin:
                buffer = b""

                @staticmethod
                def write(data):
                    time.sleep(0.05)  # slow consumer

                @staticmethod
                def close():
                    pass

        writer = _PipeWriter(FakeProc(), max_queue=2)
        writer.start()
        # Fill the queue + overflow: push faster than consumption
        pushed = 0
        dropped = 0
        for _ in range(10):
            if writer.push(b"x" * 100):
                pushed += 1
            else:
                dropped += 1
        writer.stop()
        assert pushed >= 2
        assert dropped >= 1
        assert writer.dropped == dropped
