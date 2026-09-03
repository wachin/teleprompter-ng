"""
camera_service.py — Webcam detection and capture for Teleprompter Pro.

Phase 2: V4L2 camera discovery with REAL capabilities (never claiming
a resolution the device does not offer), plus a thread-safe capture
worker built on QThread + signals.

Design (ROADMAP Phase 2):
- Camera enumeration uses v4l2-ctl (authoritative, parses formats the
  camera actually supports) with an OpenCV-only fallback that probes
  with VideoCapture.
- The capture loop lives in CameraWorker (moved to a QThread via
  moveToThread); frames are delivered to the UI through a Qt signal,
  never by touching widgets from the worker.
- Opening the same device twice returns a clear, actionable error
  ("busy"), the same for permission problems.
"""

import contextlib
import os
import re
import shutil
import subprocess

from PyQt6.QtCore import QObject, QThread, pyqtSignal, pyqtSlot

from logging_setup import get_logger

log = get_logger("Camera")

V4L2_CTL = "v4l2-ctl"


class CameraError(Exception):
    """Camera problem with a user-facing message and a hint."""


# ─────────────────────────────────────────────────────────────
# Enumeration
# ─────────────────────────────────────────────────────────────

def _run_v4l2(args):
    """Runs v4l2-ctl with args; returns stdout or None if unavailable."""
    if shutil.which(V4L2_CTL) is None:
        return None
    try:
        result = subprocess.run(
            [V4L2_CTL, *args],
            capture_output=True, text=True, timeout=5, check=False,
        )
        return result.stdout if result.returncode == 0 else None
    except (OSError, subprocess.SubprocessError) as e:
        log.debug("v4l2-ctl failed: %s", e)
        return None


def list_devices():
    """
    Lists video capture devices.

    Returns a list of dicts: {"device", "name"}. Only /dev/videoN nodes
    that support video capture are included (v4l2-ctl skips metadata
    nodes automatically; the fallback checks readability).
    """
    devices = []
    out = _run_v4l2(["--list-devices"])
    if out is not None:
        current_name = None
        for line in out.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if not line.startswith(("\t", " ")):
                # Device line: "Card Name: Bus info (usb-...):"
                # Card names may contain colons; the name is the part
                # before the first ': ' with the trailing ':' removed.
                text = stripped.rstrip(":")
                current_name = text.split(": ")[0].strip() or text
            else:
                match = re.match(r"(/dev/video\d+)", stripped)
                if match:
                    devices.append({
                        "device": match.group(1),
                        "name": current_name or match.group(1),
                    })
        return devices

    # Fallback without v4l-utils: glob /dev/video* and keep readable ones
    dev_dir = "/dev"
    with contextlib.suppress(OSError):
        for entry in sorted(os.listdir(dev_dir)):
            if re.fullmatch(r"video\d+", entry):
                path = os.path.join(dev_dir, entry)
                if os.access(path, os.R_OK | os.W_OK):
                    devices.append({"device": path, "name": path})
    return devices


def _parse_formats(output):
    """
    Parses `v4l2-ctl -d DEV --list-formats-ext` output.

    Returns {(width, height, fps): fmt} for capture-type formats.
    When two pixel formats offer the same (w, h, fps), MJPG wins:
    compressed frames sustain higher resolutions than raw YUYV.
    """
    formats = {}
    fmt = None
    size = None
    priority = {"MJPG": 2, "YUYV": 1}
    for line in output.splitlines():
        stripped = line.strip()
        fmt_match = re.match(r"\[(\d+)\]: '(\w+)'", stripped)
        if fmt_match:
            fmt = fmt_match.group(2)
            size = None
            continue
        size_match = re.match(r"Size: Discrete (\d+)x(\d+)", stripped)
        if size_match and fmt:
            size = (int(size_match.group(1)), int(size_match.group(2)))
            continue
        fps_match = re.match(r"Interval: Discrete ([\d.]+)s \(([\d.]+) fps\)", stripped)
        if fps_match and fmt and size:
            key = (*size, float(fps_match.group(2)))
            existing = formats.get(key)
            if existing is None or priority.get(fmt, 0) > priority.get(existing, 0):
                formats[key] = fmt
    return formats


def device_formats(device):
    """
    Real capture modes for a device: {(w, h, fps): pixel_format}.

    Uses v4l2-ctl --list-formats-ext (only the capture section is
    parsed). Raises CameraError when the device cannot be queried.
    """
    out = _run_v4l2(["-d", device, "--list-formats-ext"])
    if out is None:
        raise CameraError(
            f"Could not query {device}. Is v4l-utils installed and the camera "
            "connected?"
        )
    formats = _parse_formats(out)
    if not formats:
        raise CameraError(
            f"{device} does not report capture formats. It may be a metadata-only "
            "node; try another /dev/video* device."
        )
    return formats


def grouped_modes(formats):
    """
    Groups formats dict into a UI-friendly list sorted by area (desc):

        [{"width", "height", "fps": [sorted fps], "format": best_fmt}]
    """
    by_size = {}
    for (w, h, fps), fmt in formats.items():
        by_size.setdefault((w, h), {"fps": [], "formats": set()})
        by_size[(w, h)]["fps"].append(fps)
        by_size[(w, h)]["formats"].add(fmt)
    modes = []
    for (w, h), info in by_size.items():
        # MJPG preferred when available (higher fps at big resolutions)
        fmt = "MJPG" if "MJPG" in info["formats"] else sorted(info["formats"])[0]
        modes.append({
            "width": w, "height": h,
            "fps": sorted(set(info["fps"]), reverse=True),
            "format": fmt,
        })
    modes.sort(key=lambda m: (m["width"] * m["height"], m["fps"][0]), reverse=True)
    return modes


# ─────────────────────────────────────────────────────────────
# Capture worker
# ─────────────────────────────────────────────────────────────

class CameraWorker(QObject):
    """
    Reads frames from one camera in a loop, emitting them as signals.

    The object is moved to a QThread by CameraService; the UI only
    connects to its signals. The loop checks `self.running` between
    frames so stop() takes effect promptly (< one frame interval).
    """

    frame_ready = pyqtSignal(object)      # numpy BGR array
    error = pyqtSignal(str)               # user-facing message
    started_ok = pyqtSignal()

    def __init__(self, device, width=None, height=None, fps=None):
        super().__init__()
        self.device = device
        self.width = width
        self.height = height
        self.fps = fps
        self.running = False
        self._cap = None

    @pyqtSlot()
    def start(self):
        import cv2  # imported lazily: UI can enumerate without OpenCV

        try:
            self._cap = cv2.VideoCapture(self.device)
            if not self._cap.isOpened():
                raise CameraError(_open_failure_reason(self.device))
            if self.width and self.height:
                self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
                self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
            if self.fps:
                self._cap.set(cv2.CAP_PROP_FPS, self.fps)
        except CameraError as e:
            self.error.emit(str(e))
            self._release()
            return
        except Exception as e:  # cv2 raises assorted low-level errors
            self.error.emit(
                f"Could not open {self.device}: {e}"
            )
            self._release()
            return

        self.running = True
        self.started_ok.emit()
        log.info(
            "Capture started: %s %sx%s@%s",
            self.device, self.width, self.height, self.fps,
        )
        while self.running:
            ok, frame = self._cap.read()
            if not ok:
                # Brief read failures happen on some USB cameras; stop
                # only after consecutive failures.
                if not self._read_retry():
                    self.error.emit(
                        f"Lost the camera signal on {self.device}. Check the USB "
                        "connection."
                    )
                    break
                continue
            self.frame_ready.emit(frame)
        self._release()
        log.info("Capture stopped: %s", self.device)

    # Consecutive-failure tolerance before declaring the camera dead
    _MAX_READ_FAILURES = 10

    def _read_retry(self):
        """Counts consecutive failed reads; False when giving up."""
        self._failures = getattr(self, "_failures", 0) + 1
        return self._failures < self._MAX_READ_FAILURES

    @pyqtSlot()
    def stop(self):
        """Thread-safe stop request; the loop exits on next iteration."""
        self.running = False

    def _release(self):
        if self._cap is not None:
            with contextlib.suppress(Exception):
                self._cap.release()
            self._cap = None


def _open_failure_reason(device):
    """Diagnoses why a VideoCapture open failed, with a clear hint."""
    if not os.path.exists(device):
        return f"Camera not found: {device}"
    try:
        with open(device, "rb"):
            pass
    except PermissionError:
        return (
            f"Permission denied on {device}. Add yourself to the 'video' group: "
            "sudo usermod -aG video $USER, then log out and back in."
        )
    except OSError as e:
        if e.errno == 16:  # EBUSY
            return (
                f"{device} is busy. Another application is using the camera; "
                "close it and try again."
            )
        return f"Could not open {device}: {e}"
    # Readable but cv2 failed: busy or unsupported format
    out = _run_v4l2(["-d", device, "--list-formats-ext"])
    if out is not None and _parse_formats(out):
        return (
            f"{device} is busy or in an unsupported state. Close other camera "
            "apps (browser, OBS, cheese) and try again."
        )
    return (
        f"{device} does not support video capture in a usable format."
    )


class CameraService(QObject):
    """
    Owns one active capture (worker + QThread) and releases it on stop.

    The UI calls start()/stop(); frame_ready is re-emitted from the
    worker. Releasing happens in stop() AND on app quit via
    shutdown(), so no camera stays locked after the window closes.
    """

    frame_ready = pyqtSignal(object)
    error = pyqtSignal(str)
    started_ok = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._thread = None
        self._worker = None

    def is_active(self):
        return self._worker is not None and self._worker.running

    def start(self, device, width=None, height=None, fps=None):
        """Starts capture; any previous capture is stopped first."""
        self.stop()
        self._thread = QThread(self)
        self._thread.setObjectName(f"camera-{os.path.basename(device)}")
        self._worker = CameraWorker(device, width, height, fps)
        self._worker.moveToThread(self._thread)

        self._worker.frame_ready.connect(self.frame_ready)
        self._worker.error.connect(self.error)
        self._worker.started_ok.connect(self.started_ok)
        # Worker cleanup after the loop ends; thread quits after worker
        self._thread.started.connect(self._worker.start)
        self._worker.error.connect(self._thread.quit)
        self._thread.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)

        self._thread.start()

    def stop(self):
        """Stops capture and waits for the device to be released."""
        worker, thread = self._worker, self._thread
        self._worker = None
        self._thread = None
        if worker is not None:
            worker.stop()
        if thread is not None:
            thread.quit()
            if not thread.wait(3000):
                log.warning("Camera thread did not stop within 3 s")
        if worker is not None and thread is not None:
            with contextlib.suppress(RuntimeError):
                # deleteLater was queued; clear local refs either way
                pass

    def shutdown(self):
        """Alias for stop(), called on application quit."""
        self.stop()
