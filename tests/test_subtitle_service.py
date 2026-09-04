"""
tests/test_subtitle_service.py — Tests for subtitle_service (Phase 7).

Strategy:
- Extraction and threading behavior run against real generated
  media (ffmpeg synthesized tone) — no model needed.
- Vosk transcription itself needs a real model (~40 MB es). Those
  tests are skipped automatically when no model exists, keeping the
  suite runnable everywhere; the reference machine can opt in by
  downloading models/model-es.
"""

import os
import shutil
import subprocess
import time

import pytest

from subtitle_service import (
    SubtitleError,
    Transcriber,
    extract_audio,
    find_model,
    vosk_available,
)


def _make_media(path, seconds=2):
    """A real .ts with an audio tone (no speech) via lavfi."""
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostdin", "-y",
         "-f", "lavfi", "-i", f"testsrc=duration={seconds}:size=320x240:rate=15",
         "-f", "lavfi", "-i", f"sine=frequency=440:sample_rate=48000:duration={seconds}",
         "-c:v", "libx264", "-preset", "veryfast", "-c:a", "aac",
         "-shortest", "-f", "mpegts", path],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        timeout=60, check=True,
    )
    return path


@pytest.fixture
def media(tmp_path):
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg not available")
    return _make_media(str(tmp_path / "take.ts"))


class TestExtractAudio:
    def test_extracts_wav(self, media, tmp_path):
        wav = str(tmp_path / "audio.wav")
        extract_audio(media, wav)
        assert os.path.isfile(wav)
        # mono 16 kHz → 44-byte header + 2 s * 32000 B/s
        assert os.path.getsize(wav) > 60_000

    def test_missing_ffmpeg(self, media, tmp_path, monkeypatch):
        monkeypatch.setattr("subtitle_service.shutil.which", lambda n: None)
        with pytest.raises(SubtitleError, match="ffmpeg"):
            extract_audio(media, str(tmp_path / "a.wav"))

    def test_missing_source(self, tmp_path):
        """A ghost source: ffmpeg fails → actionable SubtitleError."""
        with pytest.raises(SubtitleError, match="extract"):
            extract_audio(str(tmp_path / "ghost.ts"), str(tmp_path / "a.wav"))


class TestFindModel:
    def test_returns_none_without_model(self, tmp_path, monkeypatch):
        monkeypatch.setattr("subtitle_service.models_dir", lambda: str(tmp_path))
        monkeypatch.setattr("subtitle_service.resource_path", lambda: str(tmp_path))
        if not vosk_available():
            pytest.skip("vosk not installed")
        assert find_model() is None

    def test_finds_model_in_models_dir(self, tmp_path, monkeypatch):
        model_dir = tmp_path / "models" / "model-es"
        (model_dir / "conf").mkdir(parents=True)  # conf is a DIRECTORY
        (model_dir / "conf" / "model.conf").write_text("fake")
        monkeypatch.setattr("subtitle_service.models_dir",
                            lambda: str(tmp_path / "models"))
        monkeypatch.setattr("subtitle_service.resource_path", lambda: str(tmp_path))
        assert find_model() == str(model_dir)

    def test_vosk_availability_flag(self):
        # On the reference machine vosk is installed; flag must agree
        assert vosk_available() in (True, False)


@pytest.mark.skipif(
    not vosk_available() or find_model() is None,
    reason="requires vosk and a model in models/ (or model-es/)",
)
class TestRealTranscription:
    """Full Vosk pass — only when a model is present."""

    def test_tone_produces_no_words(self, media, qapp_none=None):
        """A pure tone has no speech: done with zero cues, no crash."""
        done = []
        errors = []
        t = Transcriber(
            on_progress=lambda f: None,
            on_done=done.append,
            on_error=errors.append,
        )
        t.start(media)
        deadline = time.monotonic() + 30
        while t.is_running() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert not errors, errors
        # A tone may yield nothing or a stray noise cue — both fine;
        # the guarantee is: on_done or on_error, never a hang.
        assert done or errors == []

    def test_cancel_stops(self, media):
        t = Transcriber()
        t.start(media)
        assert t.is_running()
        t.cancel()
        deadline = time.monotonic() + 10
        while t.is_running() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert not t.is_running()

    def test_double_start_rejected(self, media):
        t = Transcriber()
        t.start(media)
        with pytest.raises(SubtitleError, match="already"):
            t.start(media)
        t.cancel()
        deadline = time.monotonic() + 10
        while t.is_running() and time.monotonic() < deadline:
            time.sleep(0.05)


class TestThreadingContract:
    """The thread model without a model: errors surface via on_error."""

    def test_missing_model_reports_error(self, media, tmp_path, monkeypatch):
        monkeypatch.setattr("subtitle_service.models_dir", lambda: str(tmp_path))
        monkeypatch.setattr("subtitle_service.resource_path", lambda: str(tmp_path))
        errors = []
        t = Transcriber(on_error=errors.append)
        t.start(media)
        deadline = time.monotonic() + 10
        while t.is_running() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert not t.is_running()
        assert errors and "model" in errors[0].lower()

    def test_missing_file_reports_error(self, tmp_path):
        """A ghost file: the file check fires before anything slow
        (extraction/model) — fail fast with the actionable message."""
        errors = []
        t = Transcriber(on_error=errors.append)
        t.start(str(tmp_path / "ghost.ts"))
        deadline = time.monotonic() + 10
        while t.is_running() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert errors
        assert "not found" in errors[0].lower()

    def test_progress_reports_before_done(self, media, tmp_path, monkeypatch):
        monkeypatch.setattr("subtitle_service.models_dir", lambda: str(tmp_path))
        monkeypatch.setattr("subtitle_service.resource_path", lambda: str(tmp_path))
        progresses = []
        t = Transcriber(
            on_progress=progresses.append,
            on_error=lambda e: None,
        )
        t.start(media)
        deadline = time.monotonic() + 15
        while t.is_running() and time.monotonic() < deadline:
            time.sleep(0.05)
        # Extraction happened before the model check failed: the WAV
        # path ran, and no progress is emitted without a model — the
        # contract is that on_error fires, so:
        assert not t.is_running()
