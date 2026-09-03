"""
camera_preview.py — Live camera preview widget (Phase 2).

Paints OpenCV BGR frames inside a QWidget with:
- BGR → RGB conversion,
- aspect-ratio-preserving scaling (letterboxed, never stretched),
- optional horizontal mirror (for presenters checking their posture).

The widget never blocks: frames arrive via a Qt signal from
CameraWorker and are painted in paintEvent from the scaled pixmap.
"""

import numpy as np
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImage, QPainter, QPixmap
from PyQt6.QtWidgets import QSizePolicy, QWidget

from logging_setup import get_logger

log = get_logger("CameraPreview")


def ndarray_to_pixmap(frame):
    """
    Converts an OpenCV BGR numpy frame to a QPixmap.

    Returns None for empty/invalid frames instead of raising, so the
    preview can simply skip bad frames.
    """
    if frame is None or frame.size == 0 or frame.ndim != 3:
        return None
    height, width, channels = frame.shape
    if channels != 3:
        return None
    # BGR → RGB by reversing the channel axis; QImage needs contiguous data
    rgb = np.ascontiguousarray(frame[:, :, ::-1])
    image = QImage(
        rgb.data, width, height, 3 * width,
        QImage.Format.Format_RGB888,
    )
    return QPixmap.fromImage(image.copy())  # copy: rgb buffer is temporary


class CameraPreview(QWidget):
    """Widget that displays the latest camera frame, letterboxed."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.setMinimumSize(320, 180)
        self._pixmap = None
        self._mirror = False
        self._frame_count = 0
        self.setStyleSheet("background-color: #111;")

    # ── Frame intake ─────────────────────────────────────────

    def set_frame(self, frame):
        """Stores the newest frame and schedules a repaint."""
        pixmap = ndarray_to_pixmap(frame)
        if pixmap is None:
            return
        self._pixmap = pixmap
        self._frame_count += 1
        self.update()

    def set_mirror(self, enabled):
        self._mirror = bool(enabled)
        self.update()

    def is_mirrored(self):
        return self._mirror

    def frame_count(self):
        """Frames painted since creation (for tests/diagnostics)."""
        return self._frame_count

    # ── Painting ──────────────────────────────────────────────

    def paintEvent(self, event):
        if self._pixmap is None:
            self._paint_placeholder()
            return
        painter = QPainter(self)
        # Aspect-preserving fit, centered (letterbox)
        scaled = self._pixmap.scaled(
            self.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        x = (self.width() - scaled.width()) // 2
        y = (self.height() - scaled.height()) // 2
        if self._mirror:
            painter.translate(self.width(), 0)
            painter.scale(-1, 1)
            x = (self.width() - scaled.width()) // 2  # symmetric anyway
        painter.drawPixmap(x, y, scaled)
        painter.end()

    def _paint_placeholder(self):
        painter = QPainter(self)
        painter.setPen(Qt.GlobalColor.gray)
        painter.drawText(
            self.rect(),
            Qt.AlignmentFlag.AlignCenter,
            self.tr("Camera off"),
        )
        painter.end()
