"""
main_window.py — Main application window with project navigation.

Phase 1: MainWindow with a sidebar to move between the five views of
the roadmap (Home, Script, Camera, Review, Editor). Home and Script are
functional; Camera, Review, and Editor are placeholders for Phases 2-8.

All user-visible strings are English wrapped in self.tr() so they can
be extracted by Qt Linguist later (see docs/I18N.md).
"""

import os

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSlider,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from camera_preview import CameraPreview
from camera_service import CameraError, CameraService, device_formats, grouped_modes, list_devices
from logging_setup import get_logger
from project_service import ProjectError
from scroll_engine import ScrollEngine
from teleprompter_overlay import TeleprompterOverlay
from templates_service import available_templates, fill_template
from text_import import SUPPORTED, estimated_duration_seconds, import_file, word_count

log = get_logger("MainWindow")


def _format_duration(seconds):
    """mm:ss (or h:mm:ss for long scripts)."""
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


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
        extensions = " ".join(f"*{e}" for e in SUPPORTED)
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
        label = QLabel(f"<h2>{title}</h2>")
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


class CameraView(QWidget):
    """Live camera view (Phase 2): device/mode pickers + preview."""

    def __init__(self, main):
        super().__init__()
        self.main = main
        layout = QVBoxLayout(self)

        # ── Controls row ─────────────────────────────────────
        controls = QHBoxLayout()
        controls.addWidget(QLabel(self.tr("Camera:")))
        self.device_combo = QComboBox()
        self.device_combo.setMinimumWidth(180)
        controls.addWidget(self.device_combo)

        controls.addWidget(QLabel(self.tr("Mode:")))
        self.mode_combo = QComboBox()
        self.mode_combo.setMinimumWidth(160)
        controls.addWidget(self.mode_combo)

        self.start_btn = QPushButton(self.tr("Start"))
        self.start_btn.clicked.connect(self._toggle)
        controls.addWidget(self.start_btn)

        self.mirror_btn = QPushButton(self.tr("Mirror"))
        self.mirror_btn.setCheckable(True)
        self.mirror_btn.clicked.connect(self._toggle_mirror)
        controls.addWidget(self.mirror_btn)

        self.refresh_btn = QPushButton(self.tr("Refresh"))
        self.refresh_btn.clicked.connect(self.refresh_devices)
        controls.addWidget(self.refresh_btn)
        controls.addStretch()
        layout.addLayout(controls)

        # ── Preview + teleprompter overlay (Phase 3) ───────────
        self.preview = CameraPreview()
        layout.addWidget(self.preview, 1)

        # The overlay lives inside the preview so it shares its bounds;
        # raise_() keeps it above the painted frames.
        self.overlay = TeleprompterOverlay(self.preview)
        self.overlay.raise_()
        self.overlay.setGeometry(self.preview.rect())
        self.preview.installEventFilter(self)

        self.engine = ScrollEngine(self)
        self.engine.position_changed.connect(self.overlay.set_position)
        self.engine.state_changed.connect(self._on_engine_state)
        self.engine.countdown.connect(self._on_countdown)

        # ── Reading controls (Phase 3) ─────────────────────────
        reading = QHBoxLayout()
        self.play_btn = QPushButton(self.tr("▶ Play"))
        self.play_btn.clicked.connect(self._toggle_reading)
        reading.addWidget(self.play_btn)

        self.restart_btn = QPushButton(self.tr("⟲ Restart"))
        self.restart_btn.clicked.connect(self.engine.restart)
        reading.addWidget(self.restart_btn)

        reading.addWidget(QLabel(self.tr("WPM:")))
        self.wpm_spin = QSpinBox()
        self.wpm_spin.setRange(30, 500)
        self.wpm_spin.setValue(150)
        self.wpm_spin.valueChanged.connect(self.engine.set_wpm)
        reading.addWidget(self.wpm_spin)

        self.prev_par_btn = QPushButton(self.tr("⏮ Paragraph"))
        self.prev_par_btn.clicked.connect(
            lambda: self.overlay.jump_to_paragraph(
                max(0, self.overlay.current_paragraph() - 1)
            )
        )
        reading.addWidget(self.prev_par_btn)

        self.next_par_btn = QPushButton(self.tr("Paragraph ⏭"))
        self.next_par_btn.clicked.connect(
            lambda: self.overlay.jump_to_paragraph(
                min(self.overlay.paragraph_count() - 1,
                    self.overlay.current_paragraph() + 1)
            )
        )
        reading.addWidget(self.next_par_btn)

        # Position slider: manual nudge and visual feedback
        self.position_slider = QSlider(Qt.Orientation.Horizontal)
        self.position_slider.setRange(0, 1000)
        self.position_slider.setValue(0)
        self.position_slider.sliderMoved.connect(
            lambda v: self.engine.jump_to(v / 1000.0)
        )
        self.engine.position_changed.connect(
            lambda p: self.position_slider.setValue(int(p * 1000))
            if not self.position_slider.isSliderDown() else None
        )
        reading.addWidget(self.position_slider, 1)

        self.reading_mode_btn = QPushButton(self.tr("Reading mode"))
        self.reading_mode_btn.setCheckable(True)
        self.reading_mode_btn.toggled.connect(self._toggle_reading_mode)
        reading.addWidget(self.reading_mode_btn)

        reading.addWidget(QLabel(self.tr("Countdown:")))
        self.countdown_combo = QComboBox()
        for seconds in (0, 3, 5, 10):
            self.countdown_combo.addItem(
                self.tr("{0} s").format(seconds) if seconds else self.tr("None"),
                seconds,
            )
        self.countdown_combo.setCurrentIndex(1)  # 3 s default
        self.countdown_combo.currentIndexChanged.connect(self._set_countdown)
        reading.addWidget(self.countdown_combo)

        self.remote_btn = QPushButton(self.tr("📱 Remote"))
        self.remote_btn.setCheckable(True)
        self.remote_btn.toggled.connect(self._toggle_remote)
        reading.addWidget(self.remote_btn)
        layout.addLayout(reading)

        # ── Status bar ────────────────────────────────────────
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #888;")
        layout.addWidget(self.status_label)

        # Camera service and remote server live lazily (Phase 2/4)
        self.service = None
        self.remote_server = None
        self.refresh_devices()
        self._sync_script_from_project()

    # ── Overlay plumbing ──────────────────────────────────────

    def eventFilter(self, obj, event):
        """Keeps the overlay covering the preview as it resizes."""
        if obj is self.preview and event.type() == event.Type.Resize:
            self.overlay.setGeometry(self.preview.rect())
        return super().eventFilter(obj, event)

    def _sync_script_from_project(self):
        """Loads the open project's script into the overlay."""
        project = getattr(self.main, "project", None)
        text = project.script_text if project is not None else ""
        self.overlay.set_script(text)
        self.engine.set_script(text)
        wpm = 150
        if project is not None:
            wpm = project.get("teleprompter", {}).get("wpm", 150)
        self.wpm_spin.setValue(int(wpm))
        self.engine.set_wpm(int(wpm))

    def _toggle_reading(self):
        self.engine.toggle()

    def _on_engine_state(self, state):
        labels = {
            "idle": "▶ Play",
            "counting": "⏸ Pause",
            "running": "⏸ Pause",
            "paused": "▶ Resume",
            "finished": "▶ Play",
        }
        self.play_btn.setText(self.tr(labels.get(state, "▶ Play")))

    def _on_countdown(self, seconds_left):
        self._set_status(self.tr("Starting in {0}…").format(seconds_left))

    def _toggle_reading_mode(self, checked):
        """Reading mode: big text, minimal controls (Roadmap Phase 3)."""
        settings = self.overlay.settings()
        if checked:
            settings.font_size = max(44, settings.font_size)
            settings.column_width = min(0.7, settings.column_width + 0.2)
            settings.bg_mode = "semi"
        self.overlay.set_settings(settings)
        # Hide the camera pickers; keep reading controls visible
        for btn in (self.device_combo, self.mode_combo, self.start_btn,
                    self.refresh_btn, self.mirror_btn):
            btn.setVisible(not checked)
        self._set_status(
            self.tr("Reading mode") if checked else self.tr("Camera mode")
        )

    # ── Countdown / remote / keyboard (Phase 4) ────────────────

    def _set_countdown(self, index):
        seconds = self.countdown_combo.itemData(index)
        self.engine.set_countdown(int(seconds) if seconds is not None else 0)

    def _toggle_remote(self, enabled):
        """Starts/stops the LAN remote-control server on demand."""
        if enabled:
            if self.remote_server is None:
                from remote_server import RemoteServer
                self.remote_server = RemoteServer(self, port=5000)
                self.remote_server.start()
            self._show_pairing_info()
        else:
            if self.remote_server is not None:
                self.remote_server.stop()
            self._set_status(self.tr("Remote control off"))

    def _show_pairing_info(self):
        """Shows URL + pairing code and offers a QR dialog."""
        if self.remote_server is None:
            return
        url = self.remote_server.url
        token = self.remote_server.pairing_token
        text = self.tr(
            "Remote control active at:\n{0}\n\n"
            "Pairing code: {1}\n\n"
            "Phones must enter this code once to send commands."
        ).format(url, token)
        box = QMessageBox(self)
        box.setWindowTitle(self.tr("Remote control"))
        box.setIcon(QMessageBox.Icon.Information)
        box.setText(text)
        qr_btn = box.addButton(self.tr("Show QR"), QMessageBox.ButtonRole.ActionRole)
        box.addButton(QMessageBox.StandardButton.Close)
        box.exec()
        if box.clickedButton() is qr_btn:
            self._show_remote_qr()

    def _show_remote_qr(self):
        """QR dialog with the pairing URL (Phase 4)."""
        if self.remote_server is None:
            return
        from io import BytesIO

        import qrcode
        from PyQt6.QtCore import Qt as _Qt
        from PyQt6.QtGui import QPixmap
        from PyQt6.QtWidgets import QDialog
        from PyQt6.QtWidgets import QVBoxLayout as DialogLayout

        dialog = QDialog(self)
        dialog.setWindowTitle(self.tr("Pair your phone"))
        dialog.setMinimumSize(350, 470)
        dialog.setStyleSheet("background-color: #1a1a2e;")
        layout = DialogLayout(dialog)

        title = QLabel(self.tr("📱 Scan and enter the code"))
        title.setStyleSheet("color: #FFD700; font-size: 17px; font-weight: bold;")
        title.setAlignment(_Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        code = QLabel(self.remote_server.pairing_token or "")
        code.setStyleSheet(
            "color: #44FF44; font-size: 34px; font-weight: bold;"
        )
        code.setAlignment(_Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(code)

        qr_label = QLabel()
        qr_label.setAlignment(_Qt.AlignmentFlag.AlignCenter)
        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(self.remote_server.qr_data())
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)
        pixmap = QPixmap()
        pixmap.loadFromData(buffer.read())
        qr_label.setPixmap(pixmap.scaled(240, 240, _Qt.AspectRatioMode.KeepAspectRatio))
        layout.addWidget(qr_label)

        url_label = QLabel(self.remote_server.qr_data())
        url_label.setStyleSheet("color: #888; font-size: 11px;")
        url_label.setWordWrap(True)
        url_label.setAlignment(_Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(url_label)

        instructions = QLabel(self.tr(
            "1. Connect to the same Wi-Fi\n"
            "2. Scan with the phone camera\n"
            "3. Enter the code above"
        ))
        instructions.setStyleSheet("color: #aaa; font-size: 13px;")
        instructions.setAlignment(_Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(instructions)

        close_btn = QPushButton(self.tr("Close"))
        close_btn.clicked.connect(dialog.close)
        layout.addWidget(close_btn)
        dialog.exec()

    # ── Keyboard shortcuts (Phase 4: documented in the UI) ────

    def keyPressEvent(self, event):
        """
        Camera-mode shortcuts, matching the legacy reading mode:

        Space play/pause - Up/Down WPM ±10 - Home/R restart -
        +/- font size - G guide line - M mirror preview - Q remote QR
        """
        key = event.key()
        modifiers = event.modifiers()
        if key == Qt.Key.Key_Space:
            self.engine.toggle()
        elif key == Qt.Key.Key_Up:
            step = 50 if modifiers & Qt.KeyboardModifier.ShiftModifier else 10
            self.wpm_spin.setValue(self.wpm_spin.value() + step)
        elif key == Qt.Key.Key_Down:
            step = 50 if modifiers & Qt.KeyboardModifier.ShiftModifier else 10
            self.wpm_spin.setValue(max(30, self.wpm_spin.value() - step))
        elif key in (Qt.Key.Key_Home, Qt.Key.Key_R):
            self.engine.restart()
        elif key == Qt.Key.Key_G:
            settings = self.overlay.settings()
            settings.guide_line = not settings.guide_line
            self.overlay.set_settings(settings)
        elif key == Qt.Key.Key_M:
            self.mirror_btn.setChecked(not self.mirror_btn.isChecked())
        elif key == Qt.Key.Key_Q:
            self.remote_btn.setChecked(True)
            self._show_remote_qr()
        else:
            super().keyPressEvent(event)

    def shutdown(self):
        """Releases camera and remote server when closing."""
        if self.service is not None:
            self.service.stop()
        if self.remote_server is not None:
            self.remote_server.stop()

    # ── Devices ──────────────────────────────────────────────

    def refresh_devices(self):
        """Reloads the device list from the system (v4l2)."""
        self.device_combo.clear()
        try:
            devices = list_devices()
        except Exception as e:
            self._set_status(self.tr("Could not list cameras: {0}").format(e))
            return
        if not devices:
            self._set_status(self.tr("No cameras found. Connect one and press Refresh."))
            self.start_btn.setEnabled(False)
            self.mode_combo.clear()
            return
        for d in devices:
            self.device_combo.addItem(
                "{0} — {1}".format(d["name"], d["device"]), d["device"]
            )
        self.start_btn.setEnabled(True)
        self._load_modes()
        self._set_status("")

    def _load_modes(self):
        """Fills the mode combo with the REAL modes of the chosen camera."""
        device = self.device_combo.currentData()
        self.mode_combo.clear()
        if not device:
            return
        try:
            formats = device_formats(device)
        except CameraError as e:
            self.mode_combo.addItem(self.tr("Default"), None)
            self._set_status(str(e))
            return
        modes = grouped_modes(formats)
        if not modes:
            self.mode_combo.addItem(self.tr("Default"), None)
            return
        # Prefer a sane default: highest area at 30 fps, MJPG when possible
        for i, mode in enumerate(modes):
            label = "{0}x{1} @ {2} fps ({3})".format(
                mode["width"], mode["height"],
                "/".join(str(int(f)) for f in mode["fps"][:3]),
                mode["format"],
            )
            self.mode_combo.addItem(label, (mode["width"], mode["height"],
                                            mode["fps"][0]))
            if mode["width"] == 1280 and mode["height"] == 720 and i == 0:
                self.mode_combo.setCurrentIndex(self.mode_combo.count() - 1)
        # Default: first entry is the largest mode
        self.mode_combo.setCurrentIndex(0)

    # ── Start / stop ─────────────────────────────────────────

    def _toggle(self):
        if self._service_active():
            self._stop()
        else:
            self._start()

    def _service_active(self):
        return self.service is not None and self.service.is_active()

    def _ensure_service(self):
        if self.service is None:
            self.service = CameraService(self)
            self.service.frame_ready.connect(self.preview.set_frame)
            self.service.error.connect(self._on_camera_error)
            self.service.started_ok.connect(
                lambda: self._set_status(self.tr("Camera active"))
            )
        return self.service

    def _start(self):
        device = self.device_combo.currentData()
        if not device:
            self._set_status(self.tr("Select a camera first."))
            return
        mode = self.mode_combo.currentData()  # (w, h, fps) or None
        width, height, fps = mode if mode else (None, None, None)
        self._set_status(self.tr("Starting camera…"))
        self._ensure_service().start(device, width, height, fps)
        self.start_btn.setText(self.tr("Stop"))
        self.start_btn.setChecked(True)

    def _stop(self):
        if self.service is not None:
            self.service.stop()
        self.start_btn.setText(self.tr("Start"))
        self.start_btn.setChecked(False)
        self._set_status(self.tr("Camera stopped"))

    def _toggle_mirror(self, checked):
        self.preview.set_mirror(checked)

    def _on_camera_error(self, message):
        self.start_btn.setText(self.tr("Start"))
        self.start_btn.setChecked(False)
        self._set_status(self.tr("❌ {0}").format(message))

    def _set_status(self, text):
        self.status_label.setText(text)


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
        self.camera_view = CameraView(self)
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
        for key, _label, _always in self._nav_defs:
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
        self.camera_view._sync_script_from_project()
        self._project_opened()
        log.info("Active project: %s", project.root)

    def closeEvent(self, event):
        """Releases the camera before the window disappears."""
        self.camera_view.shutdown()
        event.accept()

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
