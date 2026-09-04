"""
tests/test_main_window.py — Tests for MainWindow (Phase 1).

Uses pytest-qt (already available on the machine) to verify
navigation, project lifecycle, and the Script editor wiring.
"""

import pytest
from PyQt6.QtWidgets import QApplication

from editor_view import EditorView
from main_window import CameraView, MainWindow
from project_service import ProjectService
from review_view import ReviewView


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def service(tmp_path):
    return ProjectService(projects_dir=str(tmp_path / "projects"))


@pytest.fixture
def window(qapp, service, monkeypatch):
    """MainWindow with message boxes silenced by default."""
    w = MainWindow(service)
    shown = []
    monkeypatch.setattr(w, "show_error", lambda msg: shown.append(("error", msg)))
    monkeypatch.setattr(w, "show_info", lambda msg: shown.append(("info", msg)))
    w._test_shown = shown
    yield w
    w.close()


class TestNavigation:
    """Sidebar and stacked views."""

    def test_five_views(self, window):
        assert window.views.count() == 5
        keys = [d[0] for d in window._nav_defs]
        assert keys == ["home", "script", "camera", "review", "editor"]

    def test_starts_on_home(self, window):
        assert window.views.currentWidget() is window.home_view

    def test_project_views_disabled_initially(self, window):
        for key, _enabled in (("script", False), ("camera", False),
                              ("review", False), ("editor", False)):
            assert not window.nav_buttons[key].isEnabled(), key

    def test_show_view_switches(self, window):
        window._project_opened()
        window.show_view("camera")
        assert window.views.currentWidget() is window.camera_view
        assert window.nav_buttons["camera"].isChecked()
        assert not window.nav_buttons["home"].isChecked()

    def test_placeholders(self, window):
        # Camera (Phase 2), Review (Phase 6) and Editor (Phase 6) are
        # real views; the placeholder class remains for future tabs.
        assert isinstance(window.camera_view, CameraView)
        assert isinstance(window.review_view, ReviewView)
        assert isinstance(window.editor_view, EditorView)


class TestProjectLifecycle:
    """Create → open → close through the UI helpers."""

    def test_open_new_project(self, window, service):
        window.open_new_project("From UI", None)
        assert window.project is not None
        assert window.project.name == "From UI"
        assert window.views.currentWidget() is window.script_view
        for key in window.nav_buttons:
            assert window.nav_buttons[key].isEnabled()

    def test_open_new_with_template(self, window):
        window.open_new_project("Templated", "tutorial")
        assert "{topic}" in window.script_view.editor.toPlainText()
        # Template WPM lands in project metadata
        assert window.project.get("teleprompter", {}).get("wpm") == 140

    def test_open_existing(self, window, service):
        p = service.create("Disk")
        p.set_script_text("saved text")
        service.save(p)
        window.open_existing_project(p.root)
        assert window.project.script_text == "saved text"

    def test_open_missing_shows_error(self, window):
        window.open_existing_project("/nonexistent/thing")
        kinds = [k for k, _ in window._test_shown]
        assert "error" in kinds

    def test_project_closed_resets(self, window):
        window.open_new_project("Temp", None)
        window.project_closed()
        assert window.project is None
        assert window.views.currentWidget() is window.home_view
        assert not window.nav_buttons["script"].isEnabled()


class TestScriptView:
    """Editor wiring: counters, duration, dirty tracking."""

    def test_stats_update(self, window):
        window.open_new_project("Stats", None)
        sv = window.script_view
        sv.editor.setPlainText("one two three four five")
        assert sv.words_label.text().endswith("5")

    def test_duration_wpm(self, window):
        window.open_new_project("Dur", None)
        sv = window.script_view
        sv.wpm_spin.setValue(60)
        sv.editor.setPlainText(" ".join(["w"] * 60))
        # 60 words @ 60 wpm = 60s
        assert "01:00" in sv.duration_label.text()

    def test_edit_marks_project_dirty(self, window, service):
        window.open_new_project("Dirty", None)
        before = service.open(window.project.root).script_text
        window.script_view.editor.setPlainText("changed in editor")
        assert window.project.script_dirty is True
        service.save(window.project)
        after = service.open(window.project.root).script_text
        assert after == "changed in editor"
        assert before == ""  # created empty

    def test_save_button_disabled_without_project(self, window):
        window.project_closed()
        assert not window.script_view.save_btn.isEnabled()


class TestTemplateDialog:
    """Template chooser behavior (with the dialog auto-answered)."""

    def _auto_answer(self, monkeypatch, accepted=True, row=None):
        """Patches the dialog: OK/Cancel and an optional selected row."""
        from PyQt6.QtWidgets import QDialog, QListWidget

        code = (QDialog.DialogCode.Accepted if accepted
                else QDialog.DialogCode.Rejected)

        def fake_exec(self):
            if row is not None:
                self.findChild(QListWidget).setCurrentRow(row)
            return code

        monkeypatch.setattr(QDialog, "exec", fake_exec)

    def test_dialog_returns_selection(self, window, monkeypatch):
        # Row 0 = blank, row 1 = first template (sorted by title: "Advertisement")
        from templates_service import available_templates
        second = available_templates()[0]["name"]
        self._auto_answer(monkeypatch, accepted=True, row=1)
        assert window.create_dialog_template() == second

    def test_dialog_blank(self, window, monkeypatch):
        self._auto_answer(monkeypatch, accepted=True, row=0)
        assert window.create_dialog_template() == "blank"

    def test_dialog_cancel(self, window, monkeypatch):
        self._auto_answer(monkeypatch, accepted=False)
        assert window.create_dialog_template() is None


class TestHelpers:
    """Small formatting helper."""

    def test_format_duration(self):
        from main_window import _format_duration
        assert _format_duration(0) == "00:00"
        assert _format_duration(65) == "01:05"
        assert _format_duration(3600) == "1:00:00"
        assert _format_duration(7325) == "2:02:05"
