"""
audio_service.py — Microphone selection and level metering (Phase 5).

Roadmap Phase 5:
- Microphone selection through PipeWire/PulseAudio when available,
  with a sounddevice fallback listing.
- A level meter that runs on its own PortAudio stream and reports
  RMS + clipping via Qt signals (never touching widgets directly).
- Pre-flight checks (usable device, sane channels) with actionable
  Spanish-free English errors.
"""

import re
import shutil
import subprocess

from PyQt6.QtCore import QObject, pyqtSignal

from logging_setup import get_logger

log = get_logger("Audio")

SAMPLE_RATE = 16000


class AudioError(Exception):
    """Microphone problem with an actionable message."""


def list_microphones():
    """
    Lists input devices the app can record from.

    Order: PipeWire/PulseAudio sources via pactl (name + description)
    first — they are what ffmpeg's `pulse` device consumes — then a
    sounddevice fallback for systems without pactl.

    Returns [{"id", "name"}]. The pulse id is the source NAME (not
    index) because that is what FFmpeg's -device / source expects.
    """
    microphones = []
    out = _run_pactl(["list", "sources", "short"])
    if out is not None:
        for line in out.splitlines():
            parts = line.split("\t")
            if len(parts) >= 2 and parts[1].endswith(".monitor") is False:
                if parts[1].endswith(".monitor"):
                    continue  # desktop audio, not a mic
                microphones.append({
                    "id": parts[1],
                    "name": parts[1],
                })
        # Richer names from the full listing
        detailed = _run_pactl(["list", "sources"])
        if detailed:
            current = None
            desc = None
            for line in detailed.splitlines():
                name_m = re.match(r"\s*Name:\s+(\S+)", line)
                if name_m:
                    current = name_m.group(1)
                desc_m = re.match(r'\s*device\.description\s*=\s*"(.+)"', line)
                if desc_m and current:
                    for mic in microphones:
                        if mic["id"] == current:
                            mic["name"] = desc_m.group(1)
            _ = desc
    if microphones:
        return microphones

    # Fallback: sounddevice devices (ALSA-level)
    try:
        import sounddevice as sd
        for i, dev in enumerate(sd.query_devices()):
            if dev.get("max_input_channels", 0) > 0:
                microphones.append({"id": str(i), "name": dev["name"]})
    except Exception as e:  # pragma: no cover - depends on hardware
        log.warning("Could not list audio devices: %s", e)
    return microphones


def _run_pactl(args):
    if shutil.which("pactl") is None:
        return None
    try:
        result = subprocess.run(
            ["pactl", *args], capture_output=True, text=True,
            timeout=5, check=False,
        )
        return result.stdout if result.returncode == 0 else None
    except (OSError, subprocess.SubprocessError) as e:
        log.debug("pactl failed: %s", e)
        return None


def default_microphone():
    """Best-guess default input (first non-monitor pactl source)."""
    mics = list_microphones()
    return mics[0]["id"] if mics else None


class LevelMeter(QObject):
    """
    Measures the microphone RMS level on a background PortAudio stream.

    Signals:
        level(float)  - 0.0-1.0 normalized RMS, ~20 Hz
        clipping()    — emitted when |sample| >= 0.99
    """

    level = pyqtSignal(float)
    clipping = pyqtSignal()

    BLOCK_SIZE = 800  # 50 ms at 16 kHz

    def __init__(self, parent=None):
        super().__init__(parent)
        self._stream = None
        self.running = False

    def start(self, device=None):
        """Opens the input stream; returns False on failure."""
        try:
            import sounddevice as sd
        except ImportError:
            log.warning("sounddevice not installed; meter disabled")
            return False
        try:
            self._stream = sd.RawInputStream(
                samplerate=SAMPLE_RATE,
                blocksize=self.BLOCK_SIZE,
                channels=1,
                dtype="float32",
                device=device,
                callback=self._audio_callback,
            )
            self._stream.start()
            self.running = True
            log.info("Level meter active (device=%s)", device)
            return True
        except Exception as e:
            self.running = False
            self._stream = None
            log.warning("Could not open the microphone meter: %s", e)
            return False

    def stop(self):
        """Closes the stream (idempotent)."""
        self.running = False
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception as e:
                log.debug("Error closing meter stream: %s", e)
            finally:
                self._stream = None
        log.info("Level meter stopped")

    def _audio_callback(self, indata, frames, time_info, status):
        """PortAudio callback: computes RMS, emits signals."""
        if status:
            log.debug("Meter status: %s", status)
        samples = memoryview(indata).cast("f")
        count = len(samples)
        if count == 0:
            return
        peak = 0.0
        sum_squares = 0.0
        for s in samples:
            v = s if s >= 0 else -s
            if v > peak:
                peak = v
            sum_squares += s * s
        rms = (sum_squares / count) ** 0.5
        # Normalize: -20 dBFS full scale ≈ 0.1 RMS → 1.0 on the meter
        level = min(1.0, rms * 10.0)
        self.level.emit(level)
        if peak >= 0.99:
            self.clipping.emit()
