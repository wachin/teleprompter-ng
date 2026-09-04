"""
editor_view.py — Non-destructive segment editor (Phase 6).

One clip at a time: the take loads as a whole-clip keep range, and
the user trims heads/tails, cuts holes (or silence gaps), deletes
ranges, and reorders — every operation checkpoints the EditList for
undo/redo. The original file is NEVER touched (Rule 13/14).

The view is intentionally audio-less: it edits TIME RANGES. Visual
confirmation of a cut comes from the Review player; 'Preview cut'
exports the current timeline to a temp .ts and plays it externally
(ffplay) until QtMultimedia lands.
"""

import os
import subprocess
import tempfile

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDoubleSpinBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from edit_model import EditError, EditList
from ffmpeg_tools import (
    FFmpegToolError,
    detect_silences,
    probe_clip,
    segment_export_command,
)
from logging_setup import get_logger

log = get_logger("Editor")


class EditorView(QWidget):
    """Segment table + trim controls + undo/redo over one clip."""

    def __init__(self, main):
        super().__init__()
        self.main = main
        self.clip_path = None          # absolute path of the loaded take
        self.edit = EditList()
        self._silences = []

        layout = QVBoxLayout(self)

        # ── Header ────────────────────────────────────────────
        header = QHBoxLayout()
        self.clip_label = QLabel(self.tr("No take loaded."))
        header.addWidget(self.clip_label, 1)
        self.total_label = QLabel("")
        self.total_label.setStyleSheet("color: #888;")
        header.addWidget(self.total_label)
        layout.addLayout(header)

        # ── Segment table ─────────────────────────────────────
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels([
            self.tr("Keep range"), self.tr("In (s)"), self.tr("Out (s)"),
            self.tr("Duration"),
        ])
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch,
        )
        self.table.setSelectionBehavior(
            self.table.SelectionBehavior.SelectRows,
        )
        layout.addWidget(self.table, 2)

        # ── Edit controls ─────────────────────────────────────
        row1 = QHBoxLayout()
        row1.addWidget(QLabel(self.tr("Position:")))
        self.position_spin = QDoubleSpinBox()
        self.position_spin.setDecimals(2)
        self.position_spin.setRange(0.0, 999.0)
        self.position_spin.setSuffix(" s")
        row1.addWidget(self.position_spin)

        self.trim_head_btn = QPushButton(self.tr("Set start here"))
        self.trim_head_btn.clicked.connect(self._trim_head)
        row1.addWidget(self.trim_head_btn)

        self.trim_tail_btn = QPushButton(self.tr("Set end here"))
        self.trim_tail_btn.clicked.connect(self._trim_tail)
        row1.addWidget(self.trim_tail_btn)

        self.cut_btn = QPushButton(self.tr("✂ Cut hole here"))
        self.cut_btn.clicked.connect(self._cut)
        row1.addWidget(self.cut_btn)

        self.delete_btn = QPushButton(self.tr("🗑 Delete range"))
        self.delete_btn.clicked.connect(self._delete)
        row1.addWidget(self.delete_btn)
        layout.addLayout(row1)

        row2 = QHBoxLayout()
        self.silence_btn = QPushButton(self.tr("🔇 Remove silences…"))
        self.silence_btn.clicked.connect(self._remove_silences)
        row2.addWidget(self.silence_btn)

        self.silence_info = QLabel("")
        self.silence_info.setStyleSheet("color: #888;")
        row2.addWidget(self.silence_info, 1)
        layout.addLayout(row2)

        row3 = QHBoxLayout()
        self.undo_btn = QPushButton(self.tr("↩ Undo"))
        self.undo_btn.clicked.connect(self._undo)
        row3.addWidget(self.undo_btn)

        self.redo_btn = QPushButton(self.tr("↪ Redo"))
        self.redo_btn.clicked.connect(self._redo)
        row3.addWidget(self.redo_btn)

        self.preview_btn = QPushButton(self.tr("▶ Preview cut"))
        self.preview_btn.clicked.connect(self._preview)
        row3.addWidget(self.preview_btn)

        self.rerecord_btn = QPushButton(self.tr("⏺ Re-record this take"))
        self.rerecord_btn.clicked.connect(self._rerecord)
        row3.addWidget(self.rerecord_btn)

        # Subtitles entry (Phase 7)
        self.subtitles_btn = QPushButton(self.tr("💬 Subtitles…"))
        self.subtitles_btn.clicked.connect(self._open_subtitles)
        row3.addWidget(self.subtitles_btn)
        layout.addLayout(row3)

        self.status = QLabel("")
        self.status.setStyleSheet("color: #888;")
        layout.addWidget(self.status)

        self._set_enabled(False)

    # ── Subtitles dialog (Phase 7) ─────────────────────────────

    def _open_subtitles(self):
        """Opens the SubtitleView as a child dialog for this take."""
        from PyQt6.QtWidgets import QDialog, QVBoxLayout

        from subtitle_view import SubtitleView

        if self.clip_path is None:
            self.status.setText(self.tr("Load a take first."))
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(self.tr("Subtitles"))
        dialog.resize(720, 480)
        layout = QVBoxLayout(dialog)
        view = SubtitleView(self.main)
        layout.addWidget(view)
        # Clean shutdown of a running transcription on close
        def _closing():
            view.shutdown()
        dialog.finished.connect(_closing)
        dialog.exec()

    # ── Loading ──────────────────────────────────────────────

    def load_clip(self, rel_path):
        """Loads a take (project-relative) as the editable timeline."""
        project = self.main.project
        if project is None:
            self.main.show_info(self.tr("Open a project first."))
            return
        abs_path = os.path.join(project.root, rel_path)
        try:
            info = probe_clip(abs_path)
        except FFmpegToolError as e:
            self.main.show_error(str(e))
            return

        self.clip_path = abs_path
        self.clip_rel = rel_path
        self.edit.set_clip_durations({rel_path: info["duration_s"]})
        # Start from the project's saved segments for this clip, or whole
        saved = [s for s in project.get("segments", [])
                 if s.get("clip") == rel_path]
        if saved:
            self.edit.load_project_json(saved)
        else:
            self.edit.load_clips([rel_path])

        self.position_spin.setRange(0.0, info["duration_s"])
        self.clip_label.setText(
            self.tr("Take: {0} ({1:.1f}s, {2}x{3})").format(
                os.path.basename(rel_path), info["duration_s"],
                info["width"], info["height"],
            )
        )
        self._silences = []
        self.silence_info.setText(
            self.tr("Silences not analyzed yet — click to analyze")
        )
        self._set_enabled(True)
        self._refresh_table()

    # ── Table ────────────────────────────────────────────────

    def _refresh_table(self):
        self.table.setRowCount(len(self.edit.segments))
        for row, seg in enumerate(self.edit.segments):
            items = [
                "{0} #{1}".format(self.tr("Range"), row + 1),
                f"{seg.in_s:.2f}",
                f"{seg.out_s:.2f}",
                f"{seg.duration:.2f}s",
            ]
            for col, text in enumerate(items):
                item = QTableWidgetItem(text)
                if col:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(row, col, item)
        self.total_label.setText(
            self.tr("Total kept: {0:.1f}s").format(self.edit.total_duration())
        )
        self.undo_btn.setEnabled(self.edit.can_undo())
        self.redo_btn.setEnabled(self.edit.can_redo())

    def _selected_index(self):
        row = self.table.currentRow()
        if row < 0 and self.edit.segments:
            row = 0
        return row

    def _set_enabled(self, enabled):
        for btn in (self.trim_head_btn, self.trim_tail_btn, self.cut_btn,
                    self.delete_btn, self.silence_btn, self.undo_btn,
                    self.redo_btn, self.preview_btn, self.rerecord_btn):
            btn.setEnabled(enabled)
        if not enabled:
            self.clip_label.setText(self.tr("No take loaded."))
            self.total_label.setText("")
            self.table.setRowCount(0)

    # ── Operations ───────────────────────────────────────────

    def _trim_head(self):
        index = self._selected_index()
        if index is None:
            return
        self._apply(self.edit.trim_head, index, self.position_spin.value())

    def _trim_tail(self):
        index = self._selected_index()
        if index is None:
            return
        self._apply(self.edit.trim_tail, index, self.position_spin.value())

    def _cut(self):
        index = self._selected_index()
        if index is None:
            return
        self._apply(self.edit.cut_hole, index, self.position_spin.value())

    def _delete(self):
        index = self._selected_index()
        if index is None:
            return
        self._apply(self.edit.delete, index)

    def _apply(self, operation, *args):
        """Runs an edit, surfaces errors, saves to the project."""
        try:
            operation(*args)
        except EditError as e:
            self.status.setText(self.tr("❌ {0}").format(e))
            return
        self._persist()
        self._refresh_table()
        self.status.setText("")

    def _persist(self):
        """Stores this clip's segments into project.json (non-destructive)."""
        project = self.main.project
        others = [s for s in project.get("segments", [])
                  if s.get("clip") != self.clip_rel]
        project.set("segments", others + self.edit.to_project_json())

    def _undo(self):
        try:
            self.edit.undo()
        except EditError:
            return
        self._persist()
        self._refresh_table()

    def _redo(self):
        try:
            self.edit.redo()
        except EditError:
            return
        self._persist()
        self._refresh_table()

    # ── Silences ─────────────────────────────────────────────

    def _remove_silences(self):
        """
        Analyzes silences once; second click cuts them (previewed).

        First click: detect + show summary (Roadmap: always with a
        preview). Second click: cut each silence as a hole.
        """
        if not self._silences:
            self._silences = detect_silences(self.clip_path)
            if not self._silences:
                self.silence_info.setText(
                    self.tr("No silences ≥ {0}s found").format(0.4)
                )
                return
            total = sum(e - s for s, e in self._silences)
            self.silence_info.setText(
                self.tr("{0} silences, {1:.1f}s total — click again to "
                        "remove").format(len(self._silences), total)
            )
            self.silence_btn.setText(self.tr("🔇 Remove them"))
            return

        # Second click: cut each silence (iterate over a copy: indexes shift)
        for start, end in list(self._silences):
            # Find the segment containing this silence
            for i, seg in enumerate(self.edit.segments):
                if seg.clip == self.clip_rel and seg.in_s <= start < seg.out_s:
                    try:
                        self.edit.cut_hole(i, start, end - start)
                    except EditError as e:
                        log.debug("Silence cut skipped: %s", e)
                    break
        self._silences = []
        self.silence_btn.setText(self.tr("🔇 Remove silences…"))
        self.silence_info.setText("")
        self._persist()
        self._refresh_table()
        self.status.setText(self.tr("Silences removed from the timeline"))

    # ── Preview / re-record ──────────────────────────────────

    def _preview(self):
        """Exports the kept ranges to a temp file and plays with ffplay."""
        if not self.edit.segments:
            self.status.setText(self.tr("Nothing to preview"))
            return
        import shutil
        player = shutil.which("ffplay")
        if not player:
            self.status.setText(
                self.tr("ffplay not found — install ffmpeg")
            )
            return
        try:
            tmpdir = tempfile.mkdtemp(prefix="bigprompt_preview_")
            parts = []
            for i, seg in enumerate(self.edit.segments):
                part = os.path.join(tmpdir, f"part_{i:03d}.ts")
                cmd = segment_export_command(
                    self.clip_path, part, seg.in_s, seg.out_s,
                )
                result = subprocess.run(
                    cmd, stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL, timeout=30, check=False,
                )
                if result.returncode == 0 and os.path.getsize(part) > 0:
                    parts.append(part)
            if not parts:
                self.status.setText(self.tr("Preview export failed"))
                return
            preview = os.path.join(tmpdir, "preview.ts")
            if len(parts) == 1:
                os.replace(parts[0], preview)
            else:
                ok = self._concat(parts, preview)
                if not ok:
                    self.status.setText(self.tr("Preview join failed"))
                    return
            subprocess.Popen(
                [player, "-autoexit", preview],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            self.status.setText(self.tr("Previewing the kept ranges…"))
        except (OSError, subprocess.SubprocessError) as e:
            self.status.setText(self.tr("Preview error: {0}").format(e))

    @staticmethod
    def _concat(parts, output):
        """Concatenates same-codec .ts parts (demuxer concat list)."""
        from ffmpeg_tools import join_command, write_concat_list
        cmd, _ = join_command(parts, output)
        list_path = os.path.join(os.path.dirname(output), "concat.txt")
        write_concat_list(list_path, parts)
        cmd[cmd.index("CONCAT_LIST_PLACEHOLDER")] = list_path
        result = subprocess.run(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=60, check=False,
        )
        return result.returncode == 0 and os.path.getsize(output) > 0

    def _rerecord(self):
        """Jumps to Camera to record a replacement take."""
        self.main.show_view("camera")
        self.main.camera_view._set_status(
            self.tr("Re-recording {0} — the old take stays untouched")
            .format(os.path.basename(self.clip_rel or ""))
        )
