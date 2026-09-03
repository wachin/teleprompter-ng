"""
main_window.py — Main application window with project navigation.

Phase 1: MainWindow with a sidebar to move between the five views of
the roadmap (Home, Script, Camera, Review, Editor). Home and Script are
functional; Camera, Review, and Editor are placeholders for Phases 2-8.

All user-visible strings are English wrapped in self.tr() so they can
be extracted by Qt Linguist later (see docs/I18N.md).
"""

import os

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QFileDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMainWindow, QMessageBox, QPushButton, QSpinBox,
    QStackedWidget, QVBoxLayout, QWidget, QPlainTextEdit,
)

from logging_setup import get_logger
from project_service import ProjectError
from text_import import import_file, word_count, estimated_duration_seconds, SUPPORTED
from templates_service import available_templates, fill_template

log = get_logger("MainWindow")


def _format_duration(seconds):
    """mm:ss (or h:mm:ss for long scripts)."""
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return "{0}:{1:02d}:{2:02d}".format(h, m, s)
    return "{0:02d}:{1:02d}".format(m, s)


class HomeView(QWidget):
    """Projects screen: create, open, duplicate, rename, delete."""

    def __init__(self, main):
        super().__init__()
        self.main = main
        layout = QVBoxLayout(self)

        # New project row
        new_row = QHBoxLayout()
        new_row.addWidget(QLabel(self.tr("New project:")))
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText(self.tr("Project name"))
        new_row.addWidget(self.name_edit, 1)
        self.create_btn = QPushButton(self.tr("Create"))
        self.create_btn.clicked.connect(self._create)
        new_row.addWidget(self.create_btn)
        layout.addLayout(new_row)

        # Template picker
        self.template_label = QLabel(self.tr("Start from template:"))
        layout.addWidget(self.template_label)

        # Recent projects
        layout.addWidget(QLabel(self.tr("Recent projects:")))
        self.project_list = QListWidget()
        self.project_list.itemDoubleClicked.connect(self._open_selected)
        layout.addWidget(self.project_list, 1)

        # Action buttons
        btn_row = QHBoxLayout()
        self.open_btn = None  # created in the loop below
        for label, handler in (
            (self.tr("Open"), self._open_selected),
            (self.tr("Duplicate"), self._duplicate_selected),
            (self.tr("Rename"), self._rename_selected),
            (self.tr("Delete"), self._delete_selected),
        ):
            btn = QPushButton(label)
            btn.clicked.connect(handler)
            btn_row.addWidget(btn)
        layout.addLayout(btn_row)

        self.open_external_btn = QPushButton(self.tr("Open other project…"))
        self.open_external_btn.clicked.connect(self._open_external)
        layout.addWidget(self.open_external_btn)

        self.refresh()

    # ── Data ──────────────────────────────────────────────────

    def refresh(self):
        """Reloads the recent projects list from the service."""
        self.project_list.clear()
        for name, path, _mtime in self.main.service.recent_projects():
            item = QListWidgetItem(name)
            item.setData(Qt.ItemDataRole.UserRole, path)
            self.project_list.addItem(item)

    # ── Actions ───────────────────────────────────────────────

    def _selected_path(self):
        item = self.project_list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _create(self):
        name = self.name_edit.text().strip() or self.tr("My Project")
        template = self.main.create_dialog_template()
        if template is None:
            # Cancelled the template dialog → abort creation
            return
        self.main.open_new_project(name, None if template == "blank" else template)
        self.name_edit.clear()

    def _open_selected(self):
        path = self._selected_path()
        if path:
            self.main.open_existing_project(path)

    def _open_external(self):
        start = self.main.service.projects_dir
        path = QFileDialog.getExistingDirectory(
            self, self.tr("Open project folder"), start,
        )
        if path:
            self.main.open_existing_project(path)

    def _duplicate_selected(self):
        path = self._selected_path()
        if not path:
            self.main.show_info(self.tr("Select a project first."))
            return
        try:
            project = self.main.service.open(path)
            copy = self.main.service.save_as(
                project, project.name + " " + self.tr("(copy)")
            )
            self.main.switch_project(copy)
            self.refresh()
        except ProjectError as e:
            self.main.show_error(str(e))

    def _rename_selected(self):
        path = self._selected_path()
        if not path:
            self.main.show_info(self.tr("Select a project first."))
            return
        new_name = self.main.ask_text(self.tr("Rename project"), self.tr("New name:"))
        if not new_name:
            return
        try:
            project = self.main.service.open(path)
            self.main.service.rename(project, new_name)
            self.main.switch_project(project)
            self.refresh()
        except ProjectError as e:
            self.main.show_error(str(e))

    def _delete_selected(self):
        path = self._selected_path()
        if not path:
            self.main.show_info(self.tr("Select a project first."))
            return
        confirm = QMessageBox.question(
            self,
            self.tr("Delete project"),
            self.tr(
                "Delete '{0}' permanently?\n"
                "All scripts, recordings, and exports inside it will be lost."
            ).format(os.path.basename(path)),
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        try:
            self.main.service.delete(path, confirm=True)
            self.main.project_closed()
            self.refresh()
        except ProjectError as e:
            self.main.show_error(str(e))


class ScriptView(QWidget):
    """Script editor: edit, counters, duration estimate, import."""

    def __init__(self, main):
        super().__init__()
        self.main = main
        layout = QVBoxLayout(self)

        # Editor
        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText(self.tr("Write or paste your script here…"))
        self.editor.textChanged.connect(self._on_text_changed)
        layout.addWidget(self.editor, 1)

        # Stats row
        stats = QHBoxLayout()
        self.words_label = QLabel(self.tr("Words: 0"))
        stats.addWidget(self.words_label)
        self.duration_label = QLabel(self.tr("Est. duration: --:--"))
        stats.addWidget(self.duration_label)
        stats.addWidget(QLabel(self.tr("WPM:")))
        self.wpm_spin = QSpinBox()
        self.wpm_spin.setRange(60, 300)
        self.wpm_spin.setValue(150)
        self.wpm_spin.valueChanged.connect(self._update_stats)
        stats.addWidget(self.wpm_spin)
        stats.addStretch()

        self.import_btn = QPushButton(self.tr("Import file…"))
        self.import_btn.clicked.connect(self._import)
        stats.addWidget(self.import_btn)

        self.template_btn = QPushButton(self.tr("Insert template…"))
        self.template_btn.clicked.connect(self._insert_template)
        stats.addWidget(self.template_btn)

        self.save_btn = QPushButton(self.tr("Save script"))
        self.save_btn.clicked.connect(self._save)
        stats.addWidget(self.save_btn)
        layout.addLayout(stats)

    # ── Wiring with the open project ──────────────────────────

    def load_project(self, project):
        """Fills the editor from the open project."""
        self.editor.setPlainText(project.script_text)
        wpm = project.get("teleprompter", {}).get("wpm", 150)
        self.wpm_spin.setValue(int(wpm))
        self._update_stats()

    def _on_text_changed(self):
        if self.main.project is not None:
            self.main.project.set_script_text(self.editor.toPlainText())
        self._update_stats()

    def _update_stats(self):
        text = self.editor.toPlainText()
        words = word_count(text)
        seconds = estimated_duration_seconds(text, self.wpm_spin.value())
        self.words_label.setText(self.tr("Words: {0}").format(words))
        self.duration_label.setText(
            self.tr("Est. duration: {0}").format(_format_duration(seconds))
        )
        self.save_btn.setEnabled(self.main.project is not None)

    def _save(self):
        if self.main.project is None:
            self.main.show_info(self.tr("Open or create a project first."))
            return
        try:
            self.main.service.save(self.main.project)
            self.main.show_info(self.tr("Script saved."))
        except ProjectError as e:
            self.main.show_error(str(e))

    def _import(self):
        if self.main.project is None:
            self.main.show_info(self.tr("Open or create a project first."))
            return
        extensions = " ".join("*{0}".format(e) for e in SUPPORTED)
        path, _ = QFileDialog.getOpenFileName(
            self,
            self.tr("Import script"),
            os.path.expanduser("~"),
            "{0} ({1});;{2} (*)".format(
                self.tr("Supported files"), extensions, self.tr("All files")
            ),
        )
        if not path:
            return
        try:
            text = import_file(path)
        except Exception as e:
            self.main.show_error(
                self.tr("Could not import:\n{0}").format(e)
            )
            return
        current = self.editor.toPlainText()
        merged = (current + "\n\n" + text) if current.strip() else text
        self.editor.setPlainText(merged)

    def _insert_template(self):
        template = self.main.create_dialog_template()
        if template is None or template == "blank":
            return
        try:
            text = fill_template(template, {})
        except Exception as e:
            self.main.show_error(str(e))
            return
        current = self.editor.toPlainText()
        merged = (current + "\n\n" + text) if current.strip() else text
        self.editor.setPlainText(merged)


class _PlaceholderView(QWidget):
    """Future view stub (Camera/Review/Editor) with a clear message."""

    def __init__(self, title, phase):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.addStretch()
        label = QLabel("<h2>{0}</h2>".format(title))
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)
        info = QLabel(
            "<i>{0}</i>".format(
                # translators: {0} is a phase name like "Phase 2"
                self.tr("Coming in {0}.").format(phase)
            )
        )
        info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(info)
        layout.addStretch()


class MainWindow(QMainWindow):
    """
    Application shell: sidebar navigation + stacked views.

    Owns the ProjectService and the currently open Project; views
    talk to it through small helpers (open/save/switch) so error
    handling and view refresh stay in one place.
    """

    def __init__(self, service, config=None):
        super().__init__()
        self.service = service
        self.config = config or {}
        self.project = None

        self.setWindowTitle(self.tr("Teleprompter Pro"))
        self.resize(1100, 700)

        central = QWidget()
        self.setCentralWidget(central)
        outer = QHBoxLayout(central)

        # ── Sidebar ────────────────────────────────────────────
        side = QVBoxLayout()
        self.nav_buttons = {}
        # (key, label, enabled without project)
        self._nav_defs = [
            ("home", self.tr("Home"), True),
            ("script", self.tr("Script"), False),
            ("camera", self.tr("Camera"), False),
            ("review", self.tr("Review"), False),
            ("editor", self.tr("Editor"), False),
        ]
        for key, label, always in self._nav_defs:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.clicked.connect(lambda _c, k=key: self.show_view(k))
            btn.setEnabled(always)
            side.addWidget(btn)
            self.nav_buttons[key] = btn
        side.addStretch()
        outer.addLayout(side)

        # ── Views ──────────────────────────────────────────────
        self.views = QStackedWidget()
        self.home_view = HomeView(self)
        self.script_view = ScriptView(self)
        self.camera_view = _PlaceholderView(
            self.tr("Camera"), self.tr("Phase 2")
        )
        self.review_view = _PlaceholderView(
            self.tr("Review"), self.tr("Phase 6")
        )
        self.editor_view = _PlaceholderView(
            self.tr("Editor"), self.tr("Phase 6")
        )
        for view in (self.home_view, self.script_view, self.camera_view,
                     self.review_view, self.editor_view):
            self.views.addWidget(view)
        outer.addWidget(self.views, 1)

        self.show_view("home")

    # ── Navigation ────────────────────────────────────────────

    def show_view(self, key):
        """Switches the stacked view and the sidebar selection."""
        index = {d[0]: i for i, d in enumerate(self._nav_defs)}[key]
        self.views.setCurrentIndex(index)
        for k, btn in self.nav_buttons.items():
            btn.setChecked(k == key)

    def _project_opened(self):
        for key, _label, always in self._nav_defs:
            self.nav_buttons[key].setEnabled(True)
        self.show_view("script")

    def project_closed(self):
        self.project = None
        for key, _label, always in self._nav_defs:
            self.nav_buttons[key].setEnabled(always)
        self.show_view("home")
        self.script_view.editor.clear()
        self.home_view.refresh()

    # ── Project helpers ───────────────────────────────────────

    def open_new_project(self, name, template):
        try:
            text = fill_template(template, {}) if template else ""
            project = self.service.create(name, script_text=text)
            if template:
                wpm = next(
                    (t["wpm"] for t in available_templates() if t["name"] == template),
                    150,
                )
                project.set("teleprompter", {"wpm": wpm})
                self.service.save(project)
            self.switch_project(project)
        except ProjectError as e:
            self.show_error(str(e))

    def open_existing_project(self, path):
        try:
            project = self.service.open(path)
            self.switch_project(project)
        except ProjectError as e:
            self.show_error(str(e))

    def switch_project(self, project):
        """Adopts an open project and refreshes every view."""
        self.project = project
        self.script_view.load_project(project)
        self._project_opened()
        log.info("Active project: %s", project.root)

    # ── Dialogs ───────────────────────────────────────────────

    def create_dialog_template(self):
        """
        Asks which template to use.

        Returns the template name, "blank" for a blank script, or
        None when the user cancels.
        """
        from PyQt6.QtWidgets import QDialog, QDialogButtonBox

        dialog = QDialog(self)
        dialog.setWindowTitle(self.tr("Choose a template"))
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel(self.tr("How do you want to start your script?")))

        list_widget = QListWidget()
        blank_item = QListWidgetItem(self.tr("Blank script"))
        blank_item.setData(Qt.ItemDataRole.UserRole, "blank")
        list_widget.addItem(blank_item)
        for t in available_templates():
            item = QListWidgetItem("{0} — {1}".format(t["title"], t["description"]))
            item.setData(Qt.ItemDataRole.UserRole, t["name"])
            list_widget.addItem(item)
        list_widget.setCurrentRow(0)
        layout.addWidget(list_widget)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        item = list_widget.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else "blank"

    def show_error(self, message):
        QMessageBox.critical(self, self.tr("Error"), message)

    def show_info(self, message):
        QMessageBox.information(self, self.tr("Teleprompter Pro"), message)

    def ask_text(self, title, label, default=""):
        """Single-line text input; returns '' when cancelled."""
        from PyQt6.QtWidgets import QInputDialog
        text, ok = QInputDialog.getText(self, title, label, text=default)
        return text if ok else ""
