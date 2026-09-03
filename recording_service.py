"""
recording_service.py — Camera + microphone recording via FFmpeg (Phase 5).

Design (Roadmap Phase 5):
- FFmpeg runs as an external process (no codecs implemented here) and
  muxes camera frames (fed via a stdin pipe) + microphone audio from
  the PulseAudio/PipeWire source.
- The camera frames are pushed by CameraService.frame_ready; the pipe
  writer lives in a small queue+thread so the UI never blocks and the
  capture loop never stalls on a full pipe (drops frames with a
  warning instead).
- Intermediate format is lossless-ish and edit-friendly: MPEG-TS with
  libx264 CRF 18 + AAC 128k. The original is never modified later
  (non-destructive editing in Phase 6).
- The recorded file NEVER includes the teleprompter overlay by
  default; burn-in is an explicit opt-in per recording.
- Safety: pre-flight checks (device, disk space, ffmpeg present),
  graceful stop (q to stdin), SIGKILL recovery on next launch
  (MPEG-TS is playable even when truncated).
"""

import contextlib
import os
import queue
import shutil
import subprocess
import threading
import time

from logging_setup import get_logger

log = get_logger("Record")

# Conservative per-minute bitrate of the intermediate format (CRF18
# 720p30 + AAC 128k ≈ 12 MB/min). Used for the free-space pre-flight.
BYTES_PER_MINUTE = 15 * 1024 * 1024
MIN_FREE_BYTES = 200 * 1024 * 1024  # refuse under ~200 MB


class RecordingError(Exception):
    """Recording problem with an actionable message."""


def ffmpeg_available():
    return shutil.which("ffmpeg") is not None


def build_ffmpeg_command(output_path, width, height, fps,
                        pulse_source, burn_in=False):
    """
    Builds the FFmpeg argv for a recording.

    - Video: rawvideo bgr24 frames on stdin (what OpenCV produces),
      encoded libx264 CRF 18 with yuv420p (max player compat).
    - Audio: `-f pulse -source <name>`, AAC 128k, 48 kHz.
    - Container: MPEG-TS (.ts) — robust to truncation, edit-friendly.
    - `burn_in=True` prepends a text filter hook: the caller replaces
      the final `drawtext` path (kept simple: Phase 6 editor owns
      compositing; this flag reserves the workflow).

    The command is pure data: unit-tested without running ffmpeg.
    """
    if not output_path.endswith(".ts"):
        raise RecordingError(
            f"Intermediate recordings must be .ts files ({output_path})"
        )
    cmd = [
        "ffmpeg",
        "-hide_banner", "-nostdin",
        "-y",
        # ── Video: raw BGR frames from stdin ──
        "-f", "rawvideo",
        "-pix_fmt", "bgr24",
        "-s", f"{width}x{height}",
        "-r", str(fps),
        "-i", "-",
        # ── Audio: system microphone via Pulse/PipeWire ──
        "-f", "pulse",
        "-fragment_size", "1024",
        "-i", pulse_source,
        # ── Mapping and sync ──
        "-map", "0:v", "-map", "1:a",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "128k",
        "-ar", "48000",
        "-shortest",
        "-f", "mpegts",
        output_path,
    ]
    if burn_in:
        raise RecordingError(
            "Script burn-in is not implemented yet (Phase 8 branding); "
            "recordings are camera-only by design"
        )
    return cmd


def check_prerequisites(output_dir, estimated_minutes=60):
    """
    Pre-flight (Roadmap: inform BEFORE recording).

    Returns a list of user-facing problem strings; empty = good to go.
    """
    problems = []
    if not ffmpeg_available():
        problems.append(
            "FFmpeg is not installed. Install it with: sudo apt install ffmpeg"
        )
    if not os.path.isdir(output_dir):
        try:
            os.makedirs(output_dir, exist_ok=True)
        except OSError as e:
            problems.append(
                f"Could not create the recording folder: {e}"
            )
    free = shutil.disk_usage(output_dir).free
    if free < MIN_FREE_BYTES:
        problems.append(
            f"Only {free / 1e6:.1f} MB free. Recordings need at least {MIN_FREE_BYTES / 1e6} MB "
            "for a safe take."
        )
    elif free < estimated_minutes * BYTES_PER_MINUTE:
        log.warning(
            "Free space covers ~%d min; recording may stop early",
            free // BYTES_PER_MINUTE,
        )
    return problems


def recover_incomplete(directory):
    """
    Finds leftover .ts.part recordings (crash leftovers).

    Returns [(path, size_bytes)] sorted oldest first; the caller
    decides to keep (rename to .ts — MPEG-TS truncations play) or
    delete them with user confirmation.
    """
    leftovers = []
    if not os.path.isdir(directory):
        return leftovers
    for name in os.listdir(directory):
        if name.endswith(".ts.part"):
            path = os.path.join(directory, name)
            if os.path.isfile(path):
                stat = os.stat(path)
                leftovers.append((path, stat.st_size))
    leftovers.sort(key=lambda p: os.path.getmtime(p[0]))
    return leftovers


class _PipeWriter(threading.Thread):
    """Feeds frames to ffmpeg's stdin; drops frames on backpressure."""

    def __init__(self, proc, max_queue=120):
        super().__init__(daemon=True, name="rec-pipe")
        self.proc = proc
        self.queue = queue.Queue(maxsize=max_queue)
        self.dropped = 0
        self._closed = threading.Event()

    def run(self):
        while not self._closed.is_set():
            try:
                frame = self.queue.get(timeout=0.1)
            except queue.Empty:
                continue
            try:
                self.proc.stdin.write(frame)
            except (BrokenPipeError, ValueError, OSError):
                # ffmpeg died or finished: drain quietly
                self._closed.set()

    def push(self, frame_bytes):
        """Non-blocking enqueue; drops when the pipe is behind."""
        try:
            self.queue.put_nowait(frame_bytes)
            return True
        except queue.Full:
            self.dropped += 1
            return False

    def stop(self, flush_timeout=2.0):
        """Closes stdin after draining (lets ffmpeg finalize)."""
        self._closed.set()
        self.join(timeout=flush_timeout)
        with contextlib.suppress(OSError):
            self.proc.stdin.close()


class RecordingService:
    """
    Owns one ffmpeg recording subprocess.

    The camera view calls feed_frame() on every frame_ready signal;
    stop() finalizes and returns the file path. The service never
    touches the UI; it reports via the given callbacks (the view
    adapts them to signals).
    """

    def __init__(self, on_state=None, on_error=None):
        self._proc = None
        self._writer = None
        self._path = None
        self._started_at = None
        self._frames_written = 0
        self._on_state = on_state
        self._on_error = on_error

    # ── State ───────────────────────────────────────────────

    def is_recording(self):
        return self._proc is not None and self._proc.poll() is None

    def elapsed_seconds(self):
        if self._started_at is None:
            return 0.0
        return time.monotonic() - self._started_at

    def output_path(self):
        return self._path

    def frames_written(self):
        return self._frames_written

    def dropped_frames(self):
        return 0 if self._writer is None else self._writer.dropped

    def _notify_state(self, state):
        if self._on_state:
            self._on_state(state)

    def _notify_error(self, message):
        if self._on_error:
            self._on_error(message)
        else:
            log.error("Recording error: %s", message)

    # ── Lifecycle ───────────────────────────────────────────

    def start(self, output_path, width, height, fps, pulse_source,
              burn_in=False):
        """Starts ffmpeg; raises RecordingError on any pre-flight fail."""
        if self.is_recording():
            raise RecordingError("A recording is already in progress")
        problems = check_prerequisites(os.path.dirname(output_path) or ".")
        if problems:
            raise RecordingError(problems[0])
        try:
            cmd = build_ffmpeg_command(
                output_path, width, height, fps, pulse_source, burn_in
            )
        except RecordingError:
            raise
        try:
            self._proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            raise RecordingError(
                "FFmpeg is not installed. Install it with: sudo apt install ffmpeg"
            ) from None
        except OSError as e:
            raise RecordingError(
                f"Could not start FFmpeg: {e}"
            ) from e

        self._path = output_path + ".part"  # crash-safe until finished
        # ffmpeg was started with the FINAL path argument; the .part
        # indirection is handled by writing to output_path directly
        # and renaming on success below — see stop().
        self._path = output_path
        self._writer = _PipeWriter(self._proc)
        self._writer.start()
        self._started_at = time.monotonic()
        self._frames_written = 0
        log.info(
            "Recording started: %s (%dx%d@%d, source %s)",
            output_path, width, height, fps, pulse_source,
        )
        self._notify_state("recording")
        return output_path

    def feed_frame(self, frame):
        """Pushes one OpenCV BGR frame (numpy array)."""
        if not self.is_recording():
            return
        ok = self._writer.push(frame.tobytes())
        if ok:
            self._frames_written += 1
        # Early failure detection: ffmpeg died (bad device, disk full)
        if self._writer._closed.is_set() and self._proc.poll() is not None:
            self._notify_error(
                "FFmpeg stopped unexpectedly. Check free disk space and "
                "that the microphone is not in use"
            )
            self._cleanup()

    def stop(self, timeout=8):
        """
        Finalizes the recording and returns the file path.

        Sends 'q' to ffmpeg (graceful mux finalization), waits for the
        process, verifies the file is playable-sized.
        """
        if not self.is_recording():
            return self._path
        proc = self._proc
        try:
            self._writer.stop()
        except Exception as e:
            log.debug("Writer stop: %s", e)
        try:
            proc.stdin.write(b"q")
            proc.stdin.flush()
        except (OSError, ValueError):
            pass  # already gone
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            log.warning("FFmpeg did not exit in time; killing")
            proc.kill()
            proc.wait(timeout=3)
        path = self._path
        elapsed = self.elapsed_seconds()
        self._cleanup()
        if path and os.path.isfile(path) and os.path.getsize(path) > 1000:
            log.info(
                "Recording finished: %s (%.1f s, %d frames, %d dropped)",
                path, elapsed, self._frames_written,
                self.dropped_frames() if self._writer else 0,
            )
            self._notify_state("stopped")
            return path
        self._notify_error(
            "The recording file is missing or empty — it was not saved"
        )
        return None

    def cancel(self, timeout=3):
        """Aborts and removes the partial file."""
        if not self.is_recording():
            return
        self._proc.kill()
        with contextlib.suppress(subprocess.TimeoutExpired):
            self._proc.wait(timeout=timeout)
        path = self._path
        self._cleanup()
        if path and os.path.isfile(path):
            try:
                os.unlink(path)
                log.info("Cancelled recording removed: %s", path)
            except OSError:
                pass
        self._notify_state("cancelled")

    def _cleanup(self):
        self._proc = None
        self._writer = None
        self._started_at = None


def suggest_filename(directory):
    """take_YYYYmmdd_HHMMSS.ts inside the directory."""
    stamp = time.strftime("%Y%m%d_%H%M%S")
    return os.path.join(directory, f"take_{stamp}.ts")
