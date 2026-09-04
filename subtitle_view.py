"""
subtitle_view.py — Subtitle generation and editing (Phase 7).

Docked into the Editor: generate from the loaded take (Vosk, local),
edit cue texts/times in a table, import/export .srt and .vtt.
Progress and cancellation are first-class (Roadmap Phase 7); a
missing model produces the exact download hint, never a crash.
"""

import os

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from logging_setup import get_logger
from subtitle_model import (
    Cue,
    SubtitleError,
    format_srt,
    format_vtt,
    parse_srt,
    parse_vtt,
)
from subtitle_service import Transcriber, find_model, vosk_available

log = get_logger("SubtitleView")


class SubtitleView(QWidget):
    """Subtitle editor for the clip loaded in the Editor view."""

    def __init__(self, main):
        super().__init__()
        self.main = main
        self.cues = []
        self.transcriber = None

        layout = QVBoxLayout(self)

        # ── Actions ──────────────────────────────────────────
        actions = QHBoxLayout()
        self.generate_btn = QPushButton(self.tr("✨ Generate from audio"))
        self.generate_btn.clicked.connect(self._generate)
        actions.addWidget(self.generate_btn)

        self.import_btn = QPushButton(self.tr("📂 Import .srt/.vtt"))
        self.import_btn.clicked.connect(self._import)
        actions.addWidget(self.import_btn)

        self.export_srt_btn = QPushButton(self.tr("💾 Save .srt"))
        self.export_srt_btn.clicked.connect(self._export_srt)
        actions.addWidget(self.export_srt_btn)

        self.export_vtt_btn = QPushButton(self.tr("💾 Save .vtt"))
        self.export_vtt_btn.clicked.connect(self._export_vtt)
        actions.addWidget(self.export_vtt_btn)
        actions.addStretch()
        layout.addLayout(actions)

        # ── Status / progress ────────────────────────────────
        self.status = QLabel("")
        self.status.setStyleSheet("color: #888;")
        layout.addWidget(self.status)

        # ── Cue table ─────────────────────────────────────────
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels([
            self.tr("Start"), self.tr("End"), self.tr("Text"),
        ])
        self.table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch,
        )
        layout.addWidget(self.table, 1)

        self._refresh_status()

    # ── Generate (Vosk, background) ──────────────────────────

    def _generate(self):
        editor = self.main.editor_view
        clip = editor.clip_path
        if clip is None:
            self.status.setText(
                self.tr("Load a take in the Editor first.")
            )
            return
        if not vosk_available():
            self.status.setText(
                self.tr("Vosk is not installed. Install it with: "
                        "pip install --user vosk")
            )
            return
        if find_model() is None:
            self.status.setText(
                self.tr(
                    "No speech model found. Download the Spanish model "
                    "from https://alphacephei.com/vosk/models and place "
                    "it in models/model-es (see README)."
                )
            )
            return
        if self.transcriber is not None and self.transcriber.is_running():
            self.transcriber.cancel()
            self.generate_btn.setText(self.tr("✨ Generate from audio"))
            self.status.setText(self.tr("Transcription cancelled."))
            return

        self.generate_btn.setText(self.tr("⏹ Cancel"))
        self.status.setText(self.tr("Extracting audio…"))
        self.transcriber = Transcriber(
            on_progress=self._on_progress,
            on_done=self._on_done,
            on_error=self._on_error,
        )
        self.transcriber.start(clip)

    def _on_progress(self, fraction):
        # Called from the worker thread: schedule UI work on Qt
        from PyQt6.QtCore import QMetaObject
        from PyQt6.QtCore import Qt as _Qt

        QMetaObject.invokeMethod(
            self, "_set_progress_ui", _Qt.ConnectionType.QueuedConnection,
            fraction,
        )

    def _set_progress_ui(self, fraction):
        self.status.setText(
            self.tr("Transcribing… {0}%").format(int(fraction * 100))
        )

    def _on_done(self, cues):
        from PyQt6.QtCore import QMetaObject
        from PyQt6.QtCore import Qt as _Qt
        QMetaObject.invokeMethod(
            self, "_load_cues_ui", _Qt.ConnectionType.QueuedConnection,
        )
        # Cues cross threads as plain Python objects — safe to stash
        self._pending_cues = cues

    def _load_cues_ui(self):
        cues = getattr(self, "_pending_cues", [])
        self._pending_cues = []
        self.cues = cues
        self._refresh_table()
        self.generate_btn.setText(self.tr("✨ Generate from audio"))
        if cues:
            self.status.setText(
                self.tr("{0} cues generated — edit and export below.")
                .format(len(cues))
            )
        else:
            self.status.setText(
                self.tr("No speech detected in this take.")
            )

    def _on_error(self, message):
        from PyQt6.QtCore import QMetaObject
        from PyQt6.QtCore import Qt as _Qt
        self._pending_error = message
        QMetaObject.invokeMethod(
            self, "_show_error_ui", _Qt.ConnectionType.QueuedConnection,
        )

    def _show_error_ui(self):
        message = getattr(self, "_pending_error", "")
        self._pending_error = ""
        self.status.setText(self.tr("❌ {0}").format(message))
        self.generate_btn.setText(self.tr("✨ Generate from audio"))

    # Qt slot bridge (declared for invokeMethod by name)
    from PyQt6.QtCore import pyqtSlot

    # ── Import / export ──────────────────────────────────────

    def _import(self):
        path, _ = QFileDialog.getOpenFileName(
            self, self.tr("Import subtitles"), os.path.expanduser("~"),
            self.tr("Subtitles (*.srt *.vtt);;All files (*)"),
        )
        if not path:
            return
        try:
            with open(path, encoding="utf-8-sig") as f:
                content = f.read()
            cues = parse_vtt(content) if path.lower().endswith(".vtt") \
                else parse_srt(content)
        except (OSError, SubtitleError) as e:
            self.status.setText(self.tr("❌ {0}").format(e))
            return
        self.cues = cues
        self._refresh_table()
        self.status.setText(
            self.tr("Imported {0} cues.").format(len(cues))
        )

    def _export_srt(self):
        self._export(format_srt, ".srt")

    def _export_vtt(self):
        self._export(format_vtt, ".vtt")

    def _export(self, formatter, extension):
        if not self._collect_from_table():
            return
        project = self.main.project
        start_dir = (
            os.path.join(project.root, "subtitles") if project
            else os.path.expanduser("~")
        )
        suggested = f"subtitles{extension}"
        path, _ = QFileDialog.getSaveFileName(
            self, self.tr("Save subtitles"),
            os.path.join(start_dir, suggested),
        )
        if not path:
            return
        try:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(formatter(self.cues))
        except OSError as e:
            self.status.setText(self.tr("❌ {0}").format(e))
            return
        self.status.setText(
            self.tr("Saved {0} cues to {1}.").format(
                len(self.cues), os.path.basename(path)
            )
        )

    # ── Table plumbing ────────────────────────────────────────

    def _refresh_table(self):
        self.table.setRowCount(len(self.cues))
        for row, cue in enumerate(self.cues):
            start = QTableWidgetItem(f"{cue.start:.2f}")
            end = QTableWidgetItem(f"{cue.end:.2f}")
            text = QTableWidgetItem(cue.text)
            for col, item in enumerate((start, end, text)):
                if col < 2:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item.setFlags(
                    item.flags() | Qt.ItemFlag.ItemIsEditable
                )
                self.table.setItem(row, col, item)
        self._refresh_status()

    def _collect_from_table(self):
        """Edits in the table become the source of truth on export."""
        cues = []
        for row in range(self.table.rowCount()):
            start_item = self.table.item(row, 0)
            end_item = self.table.item(row, 1)
            text_item = self.table.item(row, 2)
            if not (start_item and end_item and text_item):
                continue
            try:
                cue = Cue(
                    float(start_item.text()),
                    float(end_item.text()),
                    text_item.text(),
                )
            except (ValueError, SubtitleError) as e:
                self.status.setText(
                    self.tr("❌ Row {0}: {1}").format(row + 1, e)
                )
                return False
            cues.append(cue)
        self.cues = cues
        self._refresh_status()
        return True

    def _refresh_status(self):
        if not self.cues and self.status.text() == "":
            self.status.setText(self.tr("No cues yet."))

    def shutdown(self):
        """Cancels any running transcription on close."""
        if self.transcriber is not None and self.transcriber.is_running():
            self.transcriber.cancel()
