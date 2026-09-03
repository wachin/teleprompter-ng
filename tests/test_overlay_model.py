"""
tests/test_overlay_model.py — Tests for overlay_model.py (Phase 3).

Pure-Python tests (no Qt): paragraph splitting, colors, WPM math,
settings serialization.
"""

import pytest

from overlay_model import (
    OverlaySettings,
    _parse_rgba,
    duration_seconds,
    position_to_elapsed,
    progress_to_position,
    settings_from_dict,
    settings_to_dict,
    split_paragraphs,
    word_count,
)


class TestOverlaySettings:
    """Settings dataclass + serialization."""

    def test_defaults(self):
        s = OverlaySettings()
        assert s.font_size == 32
        assert s.wpm == 150
        assert s.bg_mode == "semi"
        assert s.position_x == 0.5

    def test_parse_rgba_3_digit(self):
        assert _parse_rgba("#F00") == (255, 0, 0, 255)

    def test_parse_rgba_6_digit(self):
        assert _parse_rgba("#FFD700") == (255, 215, 0, 255)

    def test_parse_rgba_8_digit(self):
        assert _parse_rgba("#00000080") == (0, 0, 0, 128)

    def test_parse_rgba_invalid(self):
        with pytest.raises(ValueError, match="Invalid color"):
            _parse_rgba("gold")
        with pytest.raises(ValueError, match="Invalid color"):
            _parse_rgba("#12345")

    def test_settings_colors(self):
        s = OverlaySettings()
        assert s.bg_rgba() == (0, 0, 0, 128)
        assert s.text_rgba()[:3] == (255, 215, 0)

    def test_roundtrip_dict(self):
        s = OverlaySettings(font_size=48, wpm=120, alignment="left")
        data = settings_to_dict(s)
        s2 = settings_from_dict(data)
        assert s2 == s

    def test_from_dict_ignores_unknown_and_bad_types(self):
        data = settings_to_dict(OverlaySettings())
        data["font_size"] = "huge"      # wrong type → default
        data["unknown_key"] = 1          # unknown → ignored
        s = settings_from_dict(data)
        assert s.font_size == OverlaySettings().font_size


class TestSplitParagraphs:
    """Script → paragraph blocks."""

    def test_basic_split(self):
        paras = split_paragraphs("One.\n\nTwo.\n\nThree.")
        assert paras == ["One.", "Two.", "Three."]

    def test_collapses_inner_whitespace(self):
        paras = split_paragraphs("Hello  world\nnext line")
        assert paras == ["Hello world next line"]

    def test_empty_and_blank(self):
        assert split_paragraphs("") == []
        assert split_paragraphs("\n\n\n") == []

    def test_keeps_accents(self):
        paras = split_paragraphs("¡Ñandú!\n\nDías — bien")
        assert paras == ["¡Ñandú!", "Días — bien"]


class TestWpmMath:
    """Duration and position conversions."""

    def test_duration(self):
        text = " ".join(["w"] * 150)
        assert duration_seconds(text, 150) == 60.0

    def test_duration_zero_cases(self):
        assert duration_seconds("", 150) == 0.0
        assert duration_seconds("words here", 0) == 0.0

    def test_progress_clamps(self):
        text = " ".join(["w"] * 150)  # 60 s at 150 wpm
        assert progress_to_position(text, -5, 150) == 0.0
        assert progress_to_position(text, 30, 150) == 0.5
        assert progress_to_position(text, 999, 150) == 1.0

    def test_position_elapsed_inverse(self):
        text = " ".join(["w"] * 150)
        pos = progress_to_position(text, 20, 150)
        elapsed = position_to_elapsed(pos, text, 150)
        assert abs(elapsed - 20) < 0.001

    def test_word_count(self):
        assert word_count("a b c") == 3
        assert word_count("") == 0
