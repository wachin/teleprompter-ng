"""
overlay_model.py — Data model for the teleprompter overlay (Phase 3).

Plain Python (no Qt): fonts, colors, region near the lens, WPM math,
and paragraph-marker indexing. Keeping it Qt-free makes it unit-
testable without a display and reusable by the future recording
settings view (Phase 5).
"""

import re
from dataclasses import asdict, dataclass


@dataclass
class OverlaySettings:
    """
    Visual and behavioral settings of the teleprompter overlay.

    Position is normalized (0.0-1.0) relative to the preview area so it
    survives window resizes; sizes are in points; colors are #RRGGBB
    or #RRGGBBAA strings.
    """

    # Text appearance
    font_family: str = "DejaVu Sans"
    font_size: int = 32
    bold: bool = True
    text_color: str = "#FFD700"

    # Background of the text column
    bg_mode: str = "semi"          # transparent | semi | solid
    bg_color: str = "#00000080"     # used when semi/solid

    # Geometry (normalized 0-1)
    position_x: float = 0.5         # 0=left, 1=right (column center)
    position_y: float = 0.5         # 0=top, 1=bottom
    column_width: float = 0.46     # fraction of preview width
    line_spacing: float = 1.25
    alignment: str = "center"       # left | center | right
    margin: float = 0.02            # inner padding (fraction of width)

    # Reading aids
    guide_line: bool = True
    guide_color: str = "#FFD70099"
    mirror: bool = False

    # Motion
    wpm: int = 150
    countdown: int = 3              # 0 | 3 | 5 | 10 seconds

    def bg_rgba(self) -> tuple[int, int, int, int]:
        """Parses bg_color into an (r, g, b, a) 0-255 tuple."""
        return _parse_rgba(self.bg_color)

    def text_rgba(self) -> tuple[int, int, int, int]:
        return _parse_rgba(self.text_color)


def _parse_rgba(color: str) -> tuple[int, int, int, int]:
    """
    Parses #RGB, #RRGGBB, or #RRGGBBAA into (r, g, b, a).

    Raises ValueError for anything else.
    """
    text = color.strip()
    if re.fullmatch(r"#[0-9a-fA-F]{3}", text):
        r, g, b = (int(c * 2, 16) for c in text[1:])
        return (r, g, b, 255)
    if re.fullmatch(r"#[0-9a-fA-F]{6}", text):
        r, g, b = int(text[1:3], 16), int(text[3:5], 16), int(text[5:7], 16)
        return (r, g, b, 255)
    if re.fullmatch(r"#[0-9a-fA-F]{8}", text):
        r = int(text[1:3], 16)
        g = int(text[3:5], 16)
        b = int(text[5:7], 16)
        a = int(text[7:9], 16)
        return (r, g, b, a)
    raise ValueError(f"Invalid color: {color}")


# ─────────────────────────────────────────────────────────────
# Script layout and paragraph markers
# ─────────────────────────────────────────────────────────────

def split_paragraphs(text: str) -> list[str]:
    """
    Splits a script into paragraphs: non-empty blocks separated by
    blank lines. Consecutive whitespace inside a paragraph collapses
    to single spaces (scripts are prose).
    """
    blocks = re.split(r"\n\s*\n", text.strip())
    result = []
    for block in blocks:
        if not block.strip():
            continue
        collapsed = re.sub(r"[ \t]+", " ", block.strip())
        collapsed = re.sub(r"\s*\n\s*", " ", collapsed)
        result.append(collapsed)
    return result


def word_count(text: str) -> int:
    return len(text.split())


def paragraph_markers(text: str) -> list[int]:
    """
    Character offsets where each paragraph starts (len includes them
    for the trailing end used by 'jump to next paragraph').
    """
    markers = []
    pos = 0
    for para in split_paragraphs(text):
        # Find the real offset in the original text
        idx = text.find(para.split(" ", 1)[0], pos)
        if idx == -1:
            idx = pos
        markers.append(idx)
        pos = idx + len(para)
    markers.append(len(text))
    return markers


# ─────────────────────────────────────────────────────────────
# WPM engine math
# ─────────────────────────────────────────────────────────────

def duration_seconds(text: str, wpm: int) -> float:
    """Estimated speaking time at wpm words per minute."""
    if wpm <= 0 or not text.strip():
        return 0.0
    return word_count(text) / wpm * 60.0


def progress_to_position(text: str, elapsed_s: float, wpm: int) -> float:
    """
    Converts monotonic elapsed time into a scroll position 0.0-1.0.

    Linear in words-per-minute: position = elapsed / total_duration.
    Clamps to [0, 1] so the overlay stops exactly at the end.
    """
    total = duration_seconds(text, wpm)
    if total <= 0:
        return 0.0
    return max(0.0, min(1.0, elapsed_s / total))


def position_to_elapsed(position: float, text: str, wpm: int) -> float:
    """Inverse of progress_to_position (for restoring a session)."""
    total = duration_seconds(text, wpm)
    return max(0.0, min(1.0, position)) * total


def settings_to_dict(settings: OverlaySettings) -> dict:
    """Serializable form for project.json (Phase 5 persistence)."""
    return asdict(settings)


def settings_from_dict(data: dict) -> OverlaySettings:
    """Builds OverlaySettings from project.json, ignoring unknown keys."""
    valid = {f: getattr(OverlaySettings(), f) for f in OverlaySettings.__dataclass_fields__}
    merged = dict(valid)
    for key in valid:
        if key in data and isinstance(data[key], type(valid[key])):
            merged[key] = data[key]
    return OverlaySettings(**merged)
