"""
teleprompter_overlay.py — Script overlay painted over the camera (Phase 3).

A QWidget child of the camera area that draws the script with
QPainter, directly on top of the live preview. It is purely passive:
ScrollEngine (a QTimer with a monotonic clock) tells it what to show
via set_position(), and this widget just paints.

The overlay never occludes the whole face: the text column is a
configurable fraction of the width and can be parked near the lens
(position_x/position_y from OverlaySettings).
"""


from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QPainter,
    QPen,
    QTextLayout,
    QTextOption,
)
from PyQt6.QtWidgets import QWidget

from overlay_model import OverlaySettings, _parse_rgba, split_paragraphs


class TeleprompterOverlay(QWidget):
    """
    Transparent overlay widget showing the scrolling script.

    Parent it over the camera preview; resize it to cover the preview
    area and call raise_() after the preview to stay on top.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self._settings = OverlaySettings()
        self._paragraphs = []
        self._markers = []            # char offsets per paragraph start
        self._char_total = 1
        self._position = 0.0          # 0..1 over the whole script
        self._layout_cache = None     # (key, [QTextLayout]) for repaint speed
        self._layout_key = None

    # ── Content ──────────────────────────────────────────────

    def set_script(self, text):
        """Loads the script text; resets layout caches."""
        self._paragraphs = split_paragraphs(text or "")
        # Markers over the JOINED text (what we render)
        self._markers = _joined_markers(self._paragraphs)
        joined = "\n\n".join(self._paragraphs)
        self._char_total = max(1, len(joined))
        self._layout_cache = None
        self._layout_key = None
        self.update()

    def set_settings(self, settings: OverlaySettings):
        self._settings = settings
        self._layout_cache = None
        self._layout_key = None
        self.update()

    def settings(self):
        return self._settings

    def set_position(self, position: float):
        """Scroll position 0..1 of the whole script (from ScrollEngine)."""
        self._position = max(0.0, min(1.0, position))
        self.update()

    def position(self):
        return self._position

    def current_paragraph(self):
        """Index of the paragraph at the guide line (for the marker UI)."""
        if not self._paragraphs:
            return 0
        center = self._current_char()
        current = 0
        for i, start in enumerate(self._markers):
            if start <= center:
                current = i
        return current

    def paragraph_count(self):
        return len(self._paragraphs)

    def jump_to_paragraph(self, index: int):
        """Jumps the scroll so paragraph `index` sits on the guide line."""
        if not self._paragraphs:
            return
        index = max(0, min(index, len(self._paragraphs) - 1))
        self.set_position(self._markers[index] / self._char_total)

    # ── Painting ──────────────────────────────────────────────

    def paintEvent(self, event):
        if not self._paragraphs:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        s = self._settings
        # Column geometry (normalized settings → pixels)
        col_w = self.width() * s.column_width
        col_x = self.width() * s.position_x - col_w / 2
        col_x = max(0.0, min(col_x, self.width() - col_w))  # keep inside
        col_h = self.height()
        margin = self.width() * s.margin
        text_rect = QRectF(
            col_x + margin, 0.0, max(10.0, col_w - 2 * margin), col_h
        )

        # Background of the column
        r, g, b, a = s.bg_rgba()
        if s.bg_mode == "solid":
            bg = QColor(r, g, b, 255)
        elif s.bg_mode == "semi":
            bg = QColor(r, g, b, a if a < 255 else 160)
        else:
            bg = None
        if bg is not None:
            painter.fillRect(text_rect.adjusted(-margin, 0, margin, 0), bg)

        # Font
        font = QFont(s.font_family, s.font_size)
        font.setBold(s.bold)
        painter.setFont(font)
        painter.setPen(QColor(*s.text_rgba()))

        layouts = self._get_layouts(font, text_rect.width())

        # Vertical scroll: total height minus a partial window of slack
        total_h = self._total_height()
        scroll_y = self._position * max(0.0, total_h - text_rect.height())

        guide_y = text_rect.height() * s.position_y

        # Draw each paragraph; skip ones fully outside the view
        y = 0.0
        for para_layout, para_h in layouts:
            para_top = y - scroll_y
            y += para_h
            para_bottom = para_top + para_h
            if para_bottom < 0 or para_top > text_rect.height():
                continue
            para_layout.draw(painter, QPointF(text_rect.left(), para_top))

        # Guide line at the reading position
        if s.guide_line:
            gr, gg, gb, ga = _parse_rgba(s.guide_color)
            if ga >= 255:
                ga = 153  # 60% opacity when a solid color was given
            pen = QPen(QColor(gr, gg, gb, ga))
            pen.setWidth(2)
            painter.setPen(pen)
            painter.drawLine(
                int(text_rect.left()) - int(margin),
                int(guide_y),
                int(text_rect.right()) + int(margin),
                int(guide_y),
            )
        painter.end()

    # ── Layout engine ─────────────────────────────────────────

    def _get_layouts(self, font, width):
        """Builds (and caches) one QTextLayout per paragraph."""
        key = (font.family(), font.pointSize(), font.bold(), int(width),
               len(self._paragraphs))
        if self._layout_key == key and self._layout_cache is not None:
            return self._layout_cache

        option = QTextOption()
        option.setWrapMode(QTextOption.WrapMode.WordWrap)
        align = {
            "left": Qt.AlignmentFlag.AlignLeft,
            "center": Qt.AlignmentFlag.AlignCenter,
            "right": Qt.AlignmentFlag.AlignRight,
        }.get(self._settings.alignment, Qt.AlignmentFlag.AlignCenter)
        option.setAlignment(align)

        layouts = []
        line_spacing = self._settings.line_spacing
        metrics = QFontMetrics(font)
        line_h = metrics.height() * line_spacing
        for para in self._paragraphs:
            layout = QTextLayout(para, font)
            layout.setTextOption(option)
            layout.beginLayout()
            y = 0.0
            while True:
                line = layout.createLine()
                if not line.isValid():
                    break
                line.setLineWidth(width)
                line.setPosition(QPointF(0.0, y))
                y += line_h
            layout.endLayout()
            # Extra gap between paragraphs (0.6 of a line)
            layouts.append((layout, y + line_h * 0.6))
        self._layout_cache = layouts
        self._layout_key = key
        return layouts

    def _total_height(self):
        if not self._layout_cache:
            return 0
        return sum(h for _l, h in self._layout_cache)

    def _current_char(self):
        """Approximate char offset at the guide line for markers."""
        return int(self._position * self._char_total)


def _joined_markers(paragraphs):
    """Char offsets of paragraph starts in the joined text."""
    markers = []
    pos = 0
    for para in paragraphs:
        markers.append(pos)
        pos += len(para) + 2  # "\n\n" separator
    return markers
