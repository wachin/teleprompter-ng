"""
branding_view.py — Brand kit editor and final export (Phase 8).

Dialog over the Editor: configure logo, colors, music (volume +
fades), intro/outro paths, aspect ratio (16:9 / 9:16 / 1:1 / 4:5),
fit mode (letterbox/crop), and subtitle burn-in style. Everything
persists into project.json (`branding`) and the Export button runs
the render pipeline (timeline parts → join → branded master into
media/exports).
"""

import os
import shutil
import tempfile

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from branding_model import AspectRatio, BrandKit
from ffmpeg_tools import probe_clip
from logging_setup import get_logger
from render_pipeline import (
    RenderError,
    build_render_command,
    export_timeline_parts,
    join_parts,
    run_render,
)

log = get_logger("BrandingView")


class BrandingView(QWidget):
    """Brand kit + export UI for the project."""

    def __init__(self, main):
        super().__init__()
        self.main = main
        self.kit = BrandKit()

        layout = QVBoxLayout(self)

        # ── Brand kit form ─────────────────────────────────────
        form = QFormLayout()

        # Logo
        logo_row = QHBoxLayout()
        self.logo_edit = QLineEdit()
        self.logo_edit.setPlaceholderText(self.tr("media/assets/logo.png"))
        logo_row.addWidget(self.logo_edit, 1)
        self.logo_btn = QPushButton(self.tr("Choose…"))
        self.logo_btn.clicked.connect(lambda: self._pick_file(self.logo_edit))
        logo_row.addWidget(self.logo_btn)
        form.addRow(self.tr("Logo (PNG)"), logo_row)

        self.logo_position = QComboBox()
        for pos in ("top-left", "top-right", "bottom-left", "bottom-right"):
            self.logo_position.addItem(pos)
        self.logo_position.setCurrentText("top-right")
        form.addRow(self.tr("Logo position"), self.logo_position)

        self.logo_scale = QDoubleSpinBox()
        self.logo_scale.setRange(0.02, 0.5)
        self.logo_scale.setValue(0.15)
        self.logo_scale.setSingleStep(0.01)
        form.addRow(self.tr("Logo size (x width)"), self.logo_scale)

        self.logo_opacity = QDoubleSpinBox()
        self.logo_opacity.setRange(0.1, 1.0)
        self.logo_opacity.setValue(0.85)
        self.logo_opacity.setSingleStep(0.05)
        form.addRow(self.tr("Logo opacity"), self.logo_opacity)

        # Colors
        colors_row = QHBoxLayout()
        self.primary_btn = QPushButton()
        self.primary_btn.setFixedSize(40, 24)
        self.primary_btn.clicked.connect(
            lambda: self._pick_color(self.primary_color)
        )
        self.primary_color = "#FFD700"
        self._style_color_button(self.primary_btn, self.primary_color)
        colors_row.addWidget(self.primary_btn)
        colors_row.addWidget(QLabel(self.tr("Primary")))
        self.secondary_btn = QPushButton()
        self.secondary_btn.setFixedSize(40, 24)
        self.secondary_btn.clicked.connect(
            lambda: self._pick_color(self.secondary_color)
        )
        self.secondary_color = "#1a1a2e"
        self._style_color_button(self.secondary_btn, self.secondary_color)
        colors_row.addWidget(self.secondary_btn)
        colors_row.addWidget(QLabel(self.tr("Secondary")))
        colors_row.addStretch()
        form.addRow(self.tr("Brand colors"), colors_row)

        # Intro / outro
        intro_row = QHBoxLayout()
        self.intro_edit = QLineEdit()
        self.intro_edit.setPlaceholderText(self.tr("media/assets/intro.mp4"))
        intro_row.addWidget(self.intro_edit, 1)
        intro_btn = QPushButton(self.tr("Choose…"))
        intro_btn.clicked.connect(lambda: self._pick_file(self.intro_edit))
        intro_row.addWidget(intro_btn)
        form.addRow(self.tr("Intro clip (optional)"), intro_row)

        outro_row = QHBoxLayout()
        self.outro_edit = QLineEdit()
        self.outro_edit.setPlaceholderText(self.tr("media/assets/outro.mp4"))
        outro_row.addWidget(self.outro_edit, 1)
        outro_btn = QPushButton(self.tr("Choose…"))
        outro_btn.clicked.connect(lambda: self._pick_file(self.outro_edit))
        outro_row.addWidget(outro_btn)
        form.addRow(self.tr("Outro clip (optional)"), outro_row)

        # Music
        music_row = QHBoxLayout()
        self.music_edit = QLineEdit()
        self.music_edit.setPlaceholderText(self.tr("media/assets/theme.mp3"))
        music_row.addWidget(self.music_edit, 1)
        music_btn = QPushButton(self.tr("Choose…"))
        music_btn.clicked.connect(lambda: self._pick_file(self.music_edit))
        music_row.addWidget(music_btn)
        form.addRow(self.tr("Background music"), music_row)

        self.music_volume = QDoubleSpinBox()
        self.music_volume.setRange(0.0, 1.0)
        self.music_volume.setValue(0.35)
        self.music_volume.setSingleStep(0.05)
        form.addRow(self.tr("Music volume"), self.music_volume)

        fade_row = QHBoxLayout()
        self.fade_in = QDoubleSpinBox()
        self.fade_in.setRange(0.0, 10.0)
        self.fade_in.setValue(1.0)
        fade_row.addWidget(self.fade_in)
        fade_row.addWidget(QLabel(self.tr("s in /")))
        self.fade_out = QDoubleSpinBox()
        self.fade_out.setRange(0.0, 10.0)
        self.fade_out.setValue(2.0)
        fade_row.addWidget(self.fade_out)
        fade_row.addWidget(QLabel(self.tr("s out")))
        fade_row.addStretch()
        form.addRow(self.tr("Music fades"), fade_row)

        # Aspect ratio + fit
        ratio_row = QHBoxLayout()
        self.aspect_combo = QComboBox()
        for ratio in AspectRatio.RATIOS:
            self.aspect_combo.addItem(
                "{0} ({1}x{2})".format(
                    ratio, *AspectRatio.resolution(ratio)
                ),
                ratio,
            )
        self.aspect_combo.setCurrentIndex(0)
        ratio_row.addWidget(self.aspect_combo)
        self.fit_combo = QComboBox()
        self.fit_combo.addItem(self.tr("Letterbox (bars)"), "letterbox")
        self.fit_combo.addItem(self.tr("Crop (fill)"), "crop")
        ratio_row.addWidget(self.fit_combo)
        ratio_row.addStretch()
        form.addRow(self.tr("Aspect ratio"), ratio_row)

        # Subtitles burn-in
        self.subtitles_check = QCheckBox(
            self.tr("Burn subtitles into the video")
        )
        form.addRow(self.tr("Subtitles"), self.subtitles_check)

        self.subtitle_position = QComboBox()
        for pos in ("bottom-center", "top-center", "bottom-left", "bottom-right"):
            self.subtitle_position.addItem(pos)
        form.addRow(self.tr("Subtitle position"), self.subtitle_position)

        self.subtitle_size = QSpinBox()
        self.subtitle_size.setRange(10, 72)
        self.subtitle_size.setValue(28)
        form.addRow(self.tr("Subtitle size (1080p base)"), self.subtitle_size)

        layout.addLayout(form)

        # ── Export ──────────────────────────────────────────────
        export_row = QHBoxLayout()
        self.export_btn = QPushButton(self.tr("🎬 Export final video"))
        self.export_btn.setStyleSheet(
            "font-weight: bold; padding: 8px;"
        )
        self.export_btn.clicked.connect(self._export)
        export_row.addWidget(self.export_btn)
        export_row.addStretch()
        layout.addLayout(export_row)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        self.status = QLabel("")
        self.status.setStyleSheet("color: #888;")
        layout.addWidget(self.status)
        layout.addStretch()

        self._load_from_project()

    # ── Helpers ───────────────────────────────────────────────

    def _style_color_button(self, btn, color):
        btn.setStyleSheet(
            f"background-color: {color}; border: 1px solid #888;"
        )

    def _pick_color(self, current):
        color = QColorDialog.getColor(startup=Qt.GlobalColor.white)
        if not color.isValid():
            return
        value = color.name()  # '#RRGGBB'
        self._style_color_button(
            self.primary_btn if current == self.primary_color
            else self.secondary_btn, value,
        )
        if current == self.primary_color:
            self.primary_color = value
        else:
            self.secondary_color = value

    def _pick_file(self, edit):
        """File picker that COPIES the asset into media/assets."""
        project = self.main.project
        if project is None:
            self.status.setText(self.tr("Open a project first."))
            return
        path, _ = QFileDialog.getOpenFileName(
            self, self.tr("Choose a file"), os.path.expanduser("~"),
        )
        if not path:
            return
        assets_dir = os.path.join(project.root, "media", "assets")
        os.makedirs(assets_dir, exist_ok=True)
        dest = os.path.join(assets_dir, os.path.basename(path))
        if os.path.abspath(path) != os.path.abspath(dest):
            try:
                shutil.copy(path, dest)
            except OSError as e:
                self.status.setText(
                    self.tr("Could not copy the file into the project: {0}")
                    .format(e)
                )
                return
        # Project-relative path (Rule 12)
        edit.setText(os.path.relpath(dest, project.root))
        self.status.setText(
            self.tr("Copied into media/assets: {0}").format(
                os.path.basename(dest)
            )
        )

    # ── Kit <-> form ──────────────────────────────────────────

    def _collect_kit(self):
        """Form → BrandKit (None paths for empty fields)."""
        kit = BrandKit()
        kit.logo_path = self.logo_edit.text().strip() or None
        kit.logo_position = self.logo_position.currentText()
        kit.logo_scale = self.logo_scale.value()
        kit.logo_opacity = self.logo_opacity.value()
        kit.primary_color = self.primary_color
        kit.secondary_color = self.secondary_color
        kit.intro_path = self.intro_edit.text().strip() or None
        kit.outro_path = self.outro_edit.text().strip() or None
        kit.music_path = self.music_edit.text().strip() or None
        kit.music_volume = self.music_volume.value()
        kit.music_fade_in = self.fade_in.value()
        kit.music_fade_out = self.fade_out.value()
        kit.aspect_ratio = self.aspect_combo.currentData()
        kit.fit_mode = self.fit_combo.currentData()
        kit.subtitle_style.enabled = self.subtitles_check.isChecked()
        kit.subtitle_style.position = self.subtitle_position.currentText()
        kit.subtitle_style.font_size = self.subtitle_size.value()
        return kit

    def _apply_kit_to_form(self, kit):
        """BrandKit → form widgets."""
        self.logo_edit.setText(kit.logo_path or "")
        self.logo_position.setCurrentText(kit.logo_position)
        self.logo_scale.setValue(kit.logo_scale)
        self.logo_opacity.setValue(kit.logo_opacity)
        self.primary_color = kit.primary_color
        self.secondary_color = kit.secondary_color
        self._style_color_button(self.primary_btn, self.primary_color)
        self._style_color_button(self.secondary_btn, self.secondary_color)
        self.intro_edit.setText(kit.intro_path or "")
        self.outro_edit.setText(kit.outro_path or "")
        self.music_edit.setText(kit.music_path or "")
        self.music_volume.setValue(kit.music_volume)
        self.fade_in.setValue(kit.music_fade_in)
        self.fade_out.setValue(kit.music_fade_out)
        idx = self.aspect_combo.findData(kit.aspect_ratio)
        self.aspect_combo.setCurrentIndex(max(0, idx))
        fidx = self.fit_combo.findData(kit.fit_mode)
        self.fit_combo.setCurrentIndex(max(0, fidx))
        self.subtitles_check.setChecked(kit.subtitle_style.enabled)
        self.subtitle_position.setCurrentText(kit.subtitle_style.position)
        self.subtitle_size.setValue(kit.subtitle_style.font_size)

    def _load_from_project(self):
        project = self.main.project
        if project is None:
            return
        data = project.get("branding")
        if data:
            self.kit = BrandKit.from_dict(data)
            self._apply_kit_to_form(self.kit)

    def _save_to_project(self, kit):
        project = self.main.project
        project.set("branding", kit.to_dict())

    # ── Export (the big one) ─────────────────────────────────

    def _export(self):
        project = self.main.project
        editor = self.main.editor_view
        if project is None:
            self.status.setText(self.tr("Open a project first."))
            return
        if editor.clip_rel is None:
            self.status.setText(
                self.tr("Load a take in the Editor first.")
            )
            return

        kit = self._collect_kit()
        problems = kit.validate(project.root)
        if problems:
            self.status.setText(self.tr("❌ {0}").format(problems[0]))
            return

        self._save_to_project(kit)

        # 1. Timeline: segments (or the whole clip)
        edit = editor.edit
        segments = edit.segments or None
        clip_paths = {editor.clip_rel: editor.clip_path}
        probe = probe_clip(editor.clip_path)

        # 2. Subtitles: the editor's cue list when burn-in is on
        srt_path = None
        if kit.subtitle_style.enabled:
            # Reuse the cue list edited in the subtitle view is not
            # wired here; the exported .srt is picked instead.
            candidates = sorted(
                f for f in os.listdir(
                    os.path.join(project.root, "subtitles")
                ) if f.endswith(".srt")
            ) if os.path.isdir(os.path.join(project.root, "subtitles")) else []
            if candidates:
                srt_path = os.path.join(
                    project.root, "subtitles", candidates[0]
                )
            else:
                self.status.setText(
                    self.tr("Burn-in needs subtitles: generate or import "
                            "them in the Editor first.")
                )
                return

        self.progress.setVisible(True)
        self.progress.setValue(2)
        self.status.setText(self.tr("Exporting timeline…"))

        try:
            temp_dir = tempfile.mkdtemp(prefix="bigprompt_render_")
            # Timeline parts → joined
            if segments:
                parts = export_timeline_parts(segments, clip_paths, temp_dir)
                joined = join_parts(parts, temp_dir)
            else:
                joined = editor.clip_path

            # Output name with date
            import time as _time
            output = os.path.join(
                project.root, "media", "exports",
                "export_{0}_{1}.mp4".format(
                    os.path.splitext(os.path.basename(editor.clip_rel))[0],
                    _time.strftime("%Y%m%d_%H%M%S"),
                ),
            )
            os.makedirs(os.path.dirname(output), exist_ok=True)

            self.status.setText(self.tr("Rendering with branding…"))
            cmd = build_render_command(
                segments if segments else [],
                output, kit, probe,
                srt_path=srt_path,
                concat_list_path=joined,
            )
            run_render(
                cmd,
                on_progress=self._set_progress,
            )
            project.add_export({
                "file": os.path.relpath(output, project.root),
                "aspect_ratio": kit.aspect_ratio,
                "burned_subtitles": kit.subtitle_style.enabled,
                "music": bool(kit.music_path),
                "logo": bool(kit.logo_path),
            })
            self.main.service.save(project)
            self.progress.setValue(100)
            self.status.setText(
                self.tr("✅ Exported: {0}").format(os.path.basename(output))
            )
        except (RenderError, OSError, ValueError) as e:
            self.progress.setVisible(False)
            self.status.setText(self.tr("❌ {0}").format(e))
            log.exception("Export failed")

    def _set_progress(self, fraction):
        self.progress.setValue(int(fraction * 100))

    def shutdown(self):
        pass

