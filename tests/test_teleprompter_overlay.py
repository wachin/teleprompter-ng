"""
tests/test_teleprompter_overlay.py — Tests for the overlay widget (Phase 3).

Qt widget tests with pytest-qt (offscreen): rendering sanity, script
loading, markers/jumps, settings effects. Integration with the real
camera (script over live preview) is covered at the end plus the
manual smoke documented in docs/PHASE-3.md.
"""

import pytest
from PyQt6.QtWidgets import QApplication

from teleprompter_overlay import TeleprompterOverlay


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


SCRIPT = (
    "First paragraph with several words to render nicely.\n\n"
    "Second paragraph, also with content.\n\n"
    "Third and final paragraph of the test script."
)


@pytest.fixture
def overlay(qapp):
    w = TeleprompterOverlay()
    w.resize(640, 480)
    w.set_script(SCRIPT)
    yield w
    w.hide()
    w.deleteLater()


class TestScriptLoading:
    """set_script and paragraph bookkeeping."""

    def test_paragraph_count(self, overlay):
        assert overlay.paragraph_count() == 3

    def test_empty_script(self, qapp):
        w = TeleprompterOverlay()
        w.set_script("")
        assert w.paragraph_count() == 0
        w.jump_to_paragraph(2)  # no-op, no crash
        assert w.position() == 0.0

    def test_position_clamps(self, overlay):
        overlay.set_position(-0.5)
        assert overlay.position() == 0.0
        overlay.set_position(2.0)
        assert overlay.position() == 1.0


class TestMarkers:
    """Paragraph markers and jumping."""

    def test_current_paragraph_starts_at_zero(self, overlay):
        overlay.set_position(0.0)
        assert overlay.current_paragraph() == 0

    def test_current_paragraph_at_end(self, overlay):
        overlay.set_position(1.0)
        assert overlay.current_paragraph() == 2

    def test_jump_moves_position(self, overlay):
        overlay.jump_to_paragraph(1)
        assert 0.2 < overlay.position() < 0.7
        assert overlay.current_paragraph() == 1

    def test_jump_clamps(self, overlay):
        # Out-of-range indexes clamp to the first/last paragraph START,
        # not to the end of the text.
        overlay.jump_to_paragraph(99)
        assert overlay.current_paragraph() == 2
        assert 0.5 < overlay.position() < 1.0
        overlay.jump_to_paragraph(-3)
        assert overlay.current_paragraph() == 0
        assert overlay.position() == 0.0


class TestRendering:
    """The widget paints without exceptions and honors settings."""

    def test_renders_script(self, overlay, qapp):
        overlay.show()
        qapp.processEvents()
        img = overlay.grab()
        assert not img.isNull()
        assert img.width() == 640 and img.height() == 480

    def test_settings_change_repaints(self, overlay, qapp):
        overlay.show()
        qapp.processEvents()
        s = overlay.settings()
        s.font_size = 48
        s.text_color = "#00FF00"
        overlay.set_settings(s)
        qapp.processEvents()
        assert overlay.settings().font_size == 48

    def test_transparent_mode_still_paints(self, overlay, qapp):
        s = overlay.settings()
        s.bg_mode = "transparent"
        overlay.set_settings(s)
        overlay.show()
        qapp.processEvents()
        assert not overlay.grab().isNull()

    def test_solid_bg_mode(self, overlay, qapp):
        s = overlay.settings()
        s.bg_mode = "solid"
        s.bg_color = "#101010FF"
        overlay.set_settings(s)
        overlay.show()
        qapp.processEvents()
        assert not overlay.grab().isNull()


class TestEngineWiring:
    """ScrollEngine drives the overlay through signals."""

    def test_engine_updates_overlay(self, overlay, qapp):
        from scroll_engine import ScrollEngine
        engine = ScrollEngine()
        engine.position_changed.connect(overlay.set_position)
        engine.set_script(SCRIPT)
        engine.jump_to(0.5)
        qapp.processEvents()
        assert abs(overlay.position() - 0.5) < 0.01
