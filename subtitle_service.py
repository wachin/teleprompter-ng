"""
subtitle_service.py — Local speech-to-text for subtitles (Phase 7).

Pipeline: video .ts → mono 16 kHz WAV (ffmpeg) → Vosk word-level
recognition → subtitle_model cues. Everything is LOCAL (Roadmap:
no cloud; models are a separate, consent-required download).

Threading model: Transcriber runs on a Python thread and reports
progress through a callback (0..1); the UI adapter turns that into
Qt signals. cancel() flips a flag checked between chunks — Vosk
cannot be interrupted mid-chunk, but 4 kB chunks make cancellation
take effect almost immediately.
"""

import json
import os
import shutil
import subprocess
import threading

from logging_setup import get_logger
from paths import models_dir, resource_path
from subtitle_model import merge_short

log = get_logger("Subtitles")

CHUNK_BYTES = 4096


class SubtitleError(Exception):
    """Transcription problem with a user-facing message."""


def vosk_available():
    try:
        import vosk  # noqa: F401
        return True
    except ImportError:
        return False


def find_model(candidate=None):
    """
    Locates a Vosk model directory.

    Order: explicit candidate → models/ (resource path) → the old
    model-es/ folder next to the app (legacy read-mode layout).
    Returns None when no usable model exists.
    """
    import vosk  # noqa: F401 — presence check is done by callers

    candidates = []
    if candidate:
        candidates.append(candidate)
    base = models_dir()
    candidates.append(os.path.join(base, "model-es"))
    for name in os.listdir(base) if os.path.isdir(base) else []:
        if name.startswith("vosk-model") or name == "model":
            candidates.append(os.path.join(base, name))
    # Legacy layout (Phase 0 read mode)
    app_dir = resource_path()
    candidates.append(os.path.join(app_dir, "model-es"))
    for path in candidates:
        # In Vosk models 'conf' is a DIRECTORY (mfcc.conf, model.conf…)
        if os.path.isdir(path) and os.path.isdir(os.path.join(path, "conf")):
            return path
    return None


def extract_audio(source, wav_path):
    """Video .ts → mono 16 kHz WAV via ffmpeg (the format Vosk wants)."""
    if not shutil.which("ffmpeg"):
        raise SubtitleError(
            "FFmpeg is not installed. Install it with: sudo apt install ffmpeg"
        )
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostdin", "-y",
         "-i", source, "-vn", "-ac", "1", "-ar", "16000",
         "-f", "wav", wav_path],
        capture_output=True, timeout=120, check=False,
    )
    if result.returncode != 0 or not os.path.isfile(wav_path):
        raise SubtitleError(
            f"Could not extract the audio of {os.path.basename(source)}. The file may be "
            "corrupt or empty"
        )
    return wav_path


class Transcriber:
    """
    Background Vosk transcription of one media file.

    Callbacks (plain callables; the UI adapts to signals):
        on_progress(float) — 0..1 as WAV bytes are consumed
        on_done([Cue])    — merged cues on success
        on_error(str)     — user-facing failure
    """

    def __init__(self, on_progress=None, on_done=None, on_error=None):
        self.on_progress = on_progress
        self.on_done = on_done
        self.on_error = on_error
        self._cancel = threading.Event()
        self._thread = None

    def cancel(self):
        """Cooperative cancel; takes effect within one chunk."""
        self._cancel.set()

    def is_running(self):
        return self._thread is not None and self._thread.is_alive()

    def start(self, media_path, model_path=None):
        """Runs the transcription on a thread; returns immediately."""
        if self.is_running():
            raise SubtitleError("A transcription is already running")
        if not vosk_available():
            raise SubtitleError(
                "Vosk is not installed. Install it with: "
                "pip install --user vosk"
            )
        self._cancel.clear()
        self._thread = threading.Thread(
            target=self._run, args=(media_path, model_path),
            daemon=True, name="subtitle-transcribe",
        )
        self._thread.start()

    # ── Worker ────────────────────────────────────────────────

    def _run(self, media_path, model_path):
        try:
            cues = self._transcribe(media_path, model_path)
            if self._cancel.is_set():
                return
            if self.on_done:
                self.on_done(cues)
        except SubtitleError as e:
            if self.on_error:
                self.on_error(str(e))
        except Exception as e:  # vosk/ffmpeg internals
            log.exception("Transcription failed")
            if self.on_error:
                self.on_error(
                    f"Transcription failed: {e}. See the log for "
                    "details"
                )

    def _transcribe(self, media_path, model_path):
        import vosk

        model_dir = find_model(model_path)
        if model_dir is None:
            raise SubtitleError(
                "No speech recognition model found. Download the Spanish "
                "model from https://alphacephei.com/vosk/models and place "
                "it in the models/ folder as model-es (see README)"
            )
        if not os.path.isfile(media_path):
            raise SubtitleError(f"File not found: {media_path}")

        wav_path = media_path + ".subtitles.wav"
        try:
            extract_audio(media_path, wav_path)
            size = os.path.getsize(wav_path)
            if size < 1000:
                raise SubtitleError(
                    "The recording has no audio track to transcribe"
                )

            model = vosk.Model(model_dir)
            recognizer = vosk.KaldiRecognizer(model, 16000)
            recognizer.SetWords(True)

            words = []
            with open(wav_path, "rb") as f:
                # Skip the 44-byte canonical WAV header
                f.read(44)
                consumed = 0
                while not self._cancel.is_set():
                    chunk = f.read(CHUNK_BYTES)
                    if not chunk:
                        break
                    consumed += len(chunk)
                    if self.on_progress:
                        self.on_progress(min(1.0, consumed / max(1, size - 44)))
                    if recognizer.AcceptWaveform(chunk):
                        words.extend(
                            _words_from(recognizer.Result())
                        )
                if self._cancel.is_set():
                    return []
                words.extend(_words_from(recognizer.FinalResult()))

            cues = merge_short(_cues_from_words(words))
            log.info(
                "Transcribed %s: %d words → %d cues",
                os.path.basename(media_path), len(words), len(cues),
            )
            return cues
        finally:
            with _silence_oserror():
                os.unlink(wav_path)


def _words_from(result_json):
    """Vosk result JSON → [{'word','start','end'}]."""
    try:
        data = json.loads(result_json)
        return [
            {"word": w.get("word", ""),
             "start": float(w.get("start", 0.0)),
             "end": float(w.get("end", 0.0))}
            for w in data.get("result", [])
        ]
    except (json.JSONDecodeError, TypeError, ValueError):
        return []


def _cues_from_words(words):
    """Word tokens → cues (grouping rule lives in subtitle_model)."""
    from subtitle_model import word_timestamps_to_cues
    return word_timestamps_to_cues(words)


class _silence_oserror:
    """Context manager that swallows OSError (best-effort cleanup)."""

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return exc_type is OSError
