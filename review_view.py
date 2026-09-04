"""
review_view.py — Take review screen (Phase 6).

Lists the project's recorded takes (media/raw) with size/duration,
plays the selected one, and lets the user jump to the Editor to cut.

Playback strategy:
- QMediaPlayer + QVideoWidget when PyQt6.QtMultimedia is available
  (embedded, scrub-capable, recommended).
- Otherwise 'Open in external player' via ffplay (still useful: the
  acceptance criterion 'plays with VLC/FFplay' is manual anyway).
The view degrades gracefully and says which mode it is in.
"""

import os

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from ffmpeg_tools import FFmpegToolError, probe_clip
from logging_setup import get_logger

log = get_logger("Review")

try:
    from PyQt6.QtMultimedia import QMediaPlayer
    from PyQt6.QtMultimediaWidgets import QVideoWidget
    HAS_QTMM = True
except ImportError:
    HAS_QTMM = False


class ReviewView(QWidget):
    """Review takes: list + player + 'send to editor'."""

    def __init__(self, main):
        super().__init__()
        self.main = main
        layout = QVBoxLayout(self)

        # ── Takes list ──────────────────────────────────────
        layout.addWidget(QLabel(self.tr("Recorded takes")))
        self.take_list = QListWidget()
        self.take_list.itemSelectionChanged.connect(self._on_take_selected)
        layout.addWidget(self.take_list, 1)

        # ── Player area ──────────────────────────────────────
        self.player_widget = None
        self.position_slider = None
        self.status = QLabel("")
        self.status.setStyleSheet("color: #888;")
        layout.addWidget(self.status)

        if HAS_QTMM:
            self._build_embedded_player(layout)
        else:
            self._build_external_player(layout)

        # ── Actions ──────────────────────────────────────────
        actions = QHBoxLayout()
        self.refresh_btn = QPushButton(self.tr("Refresh takes"))
        self.refresh_btn.clicked.connect(self.refresh)
        actions.addWidget(self.refresh_btn)

        self.to_editor_btn = QPushButton(self.tr("✂ Edit this take"))
        self.to_editor_btn.setEnabled(False)
        self.to_editor_btn.clicked.connect(self._to_editor)
        actions.addWidget(self.to_editor_btn)
        actions.addStretch()
        layout.addLayout(actions)

        self.refresh()

    # ── Player construction ──────────────────────────────────

    def _build_embedded_player(self, layout):
        self.video_widget = QVideoWidget()
        self.video_widget.setMinimumHeight(260)
        layout.addWidget(self.video_widget, 2)

        controls = QHBoxLayout()
        self.play_btn = QPushButton(self.tr("▶"))
        self.play_btn.clicked.connect(self._toggle_play)
        controls.addWidget(self.play_btn)

        self.position_slider = QSlider(Qt.Orientation.Horizontal)
        self.position_slider.setRange(0, 1000)
        self.position_slider.sliderMoved.connect(self._on_seek)
        controls.addWidget(self.position_slider, 1)

        self.duration_label = QLabel("0:00")
        controls.addWidget(self.duration_label)
        layout.addLayout(controls)

        self.player = QMediaPlayer(self)
        self.player.setVideoOutput(self.video_widget)
        self.player.positionChanged.connect(self._on_position)
        self.player.durationChanged.connect(self._on_duration)
        self.status.setText(self.tr("Embedded player (drag to seek)"))

    def _build_external_player(self, layout):
        self.play_btn = QPushButton(self.tr("▶ Play in system player"))
        self.play_btn.setEnabled(False)
        self.play_btn.clicked.connect(self._play_external)
        layout.addWidget(self.play_btn)
        self.status.setText(
            self.tr(
                "Embedded playback needs python3-pyqt6.qtmultimedia; "
                "using the system player for now"
            )
        )

    # ── Data ──────────────────────────────────────────────────

    def refresh(self):
        """Reloads takes from the open project's media/raw."""
        self.take_list.clear()
        project = getattr(self.main, "project", None)
        if project is None:
            self.status.setText(self.tr("Open a project to see its takes."))
            self.play_btn.setEnabled(False)
            self.to_editor_btn.setEnabled(False)
            return
        raw_dir = os.path.join(project.root, "media", "raw")
        self.status.setText(self.tr("No takes yet — record one in Camera."))
        if os.path.isdir(raw_dir):
            names = sorted(n for n in os.listdir(raw_dir)
                           if n.endswith(".ts"))
            for name in names:
                path = os.path.join(raw_dir, name)
                try:
                    info = probe_clip(path)
                    label = "{0} — {1:.1f}s — {2:.1f} MB".format(
                        name, info["duration_s"],
                        os.path.getsize(path) / 1e6,
                    )
                except FFmpegToolError as e:
                    label = f"{name} — {e}"
                item = QListWidgetItem(label)
                item.setData(Qt.ItemDataRole.UserRole, path)
                self.take_list.addItem(item)
                self.status.setText("")
        if self.take_list.count() == 0 and self.status.text() == "":
            self.status.setText(self.tr("No takes yet — record one in Camera."))
        self.play_btn.setEnabled(False)
        self.to_editor_btn.setEnabled(False)

    def _selected_path(self):
        item = self.take_list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    # ── Selection / playback ─────────────────────────────────

    def _on_take_selected(self):
        path = self._selected_path()
        if not path:
            return
        self.play_btn.setEnabled(True)
        self.to_editor_btn.setEnabled(True)
        if HAS_QTMM:
            self.player.setSource(__import__("PyQt6.QtCore",
                                             fromlist=["QUrl"]).QUrl.fromLocalFile(path))
            self.status.setText(self.tr("Ready: {0}").format(
                os.path.basename(path)
            ))

    def _toggle_play(self):
        if not HAS_QTMM or self._selected_path() is None:
            return
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
            self.play_btn.setText(self.tr("▶"))
        else:
            self.player.play()
            self.play_btn.setText(self.tr("⏸"))

    def _on_position(self, ms):
        if self.position_slider is not None:
            duration = self.player.duration()
            if duration > 0:
                self.position_slider.setValue(int(ms / duration * 1000))

    def _on_duration(self, ms):
        seconds = ms // 1000
        self.duration_label.setText(
            f"{seconds // 60}:{seconds % 60:02d}"
        )

    def _on_seek(self, value):
        if self.player.duration() > 0:
            self.player.setPosition(int(value / 1000 * self.player.duration()))

    def _play_external(self):
        """Fallback: opens the take with ffplay (system player)."""
        path = self._selected_path()
        if not path:
            return
        import shutil
        import subprocess
        player = shutil.which("ffplay")
        if player:
            subprocess.Popen(
                [player, "-autoexit", path],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            self.status.setText(
                self.tr("Playing {0} in the system player…").format(
                    os.path.basename(path)
                )
            )
        else:
            self.status.setText(
                self.tr("Neither the embedded player nor ffplay is "
                        "available. Install ffmpeg or "
                        "python3-pyqt6.qtmultimedia.")
            )

    # ── To the editor ────────────────────────────────────────

    def _to_editor(self):
        path = self._selected_path()
        if path:
            project = self.main.project
            rel = os.path.relpath(path, project.root)
            self.main.show_view("editor")
            self.main.editor_view.load_clip(rel)

    def shutdown(self):
        """Stops playback when leaving/closing."""
        if HAS_QTMM:
            self.player.stop()
