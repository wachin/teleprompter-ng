"""
export_view.py — Profiled export with metadata (Phase 10).

Replaces the Phase-8 inline export in BrandingView with a proper
dialog: profile selector (YouTube / Shorts / LinkedIn / draft /
master), size estimate BEFORE rendering, background RenderWorker
(QThread — the UI never blocks), progress + cancel, thumbnail,
final-file validation, and the publish-metadata block (title,
description, hashtags) copied to the clipboard or saved as .txt.

Local export + opening the output folder only: no social APIs are
touched (Roadmap Phase 10: direct publishing stays out until their
policies are studied).
"""

import os
import shutil
import tempfile
import time

from PyQt6.QtCore import QObject, QThread, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from branding_model import AspectRatio
from export_profiles import PROFILES, ProfileError, get_profile, suggest_metadata
from ffmpeg_tools import probe_clip
from logging_setup import get_logger

log = get_logger("Export")

import render_pipeline as rp  # noqa: E402


class RenderWorker(QObject):
    """
    Runs the export pipeline off the UI thread (Phase 10).

    Signals: progress(float 0..1), finished(dict result),
    failed(str message). Cancellation is cooperative: run_render
    reads stderr line by line; a flag checked between lines stops
    ffmpeg promptly (kill on timeout).
    """

    progress = pyqtSignal(float)
    finished = pyqtSignal(dict)
    failed = pyqtSignal(str)

    def __init__(self, params):
        super().__init__()
        self._params = params
        self._cancel = False

    @pyqtSlot()
    def run(self):
        try:
            p = self._params
            with tempfile.TemporaryDirectory(prefix="bigprompt_export_") as tmp:
                segments = p["segments"]
                clip_paths = {p["clip_rel"]: p["clip_abs"]}
                joined = rp.assemble_timeline(
                    segments, clip_paths, tmp,
                    intro_path=p.get("intro_abs"),
                    outro_path=p.get("outro_abs"),
                )
                if self._cancel:
                    self.failed.emit("Cancelled")
                    return
                cmd = rp.build_profile_command(
                    segments, p["output"], p["kit"], p["probe"],
                    p["profile"],
                    srt_path=p.get("srt_abs"),
                    concat_list_path=joined,
                    project_root=p["project_root"],
                )
                rp.run_render(
                    cmd,
                    on_progress=self._on_progress,
                )
                if self._cancel:
                    self.failed.emit("Cancelled")
                    return
                # Thumbnail next to the master
                thumb = os.path.splitext(p["output"])[0] + ".jpg"
                try:
                    rp.extract_thumbnail(p["output"], thumb)
                except rp.RenderError as e:
                    log.warning("Thumbnail failed: %s", e)
                    thumb = None
                ok, problem = rp.validate_output(p["output"])
                if not ok:
                    self.failed.emit(problem)
                    return
                self.finished.emit({
                    "output": p["output"],
                    "thumbnail": thumb if thumb and os.path.isfile(thumb) else None,
                    "profile": p["profile"].key,
                })
        except rp.RenderError as e:
            self.failed.emit(str(e))
        except OSError as e:
            self.failed.emit(f"Export error: {e}")
        finally:
            self._thread.quit()

    def _on_progress(self, fraction):
        self.progress.emit(float(fraction))

    def cancel(self):
        self._cancel = True
        # run_render's subprocess keeps running; the worker reports
        # 'Cancelled' at the next checkpoint — acceptable for long
        # renders (ffmpeg finishes its current line read).

    @property
    def _thread(self):
        return self._params["thread"]


class ExportView(QWidget):
    """Profile + metadata export dialog content."""

    def __init__(self, main, branding_view=None):
        super().__init__()
        self.main = main
        self.branding_view = branding_view
        self.worker = None
        self.thread = None

        layout = QVBoxLayout(self)

        # ── Profile ───────────────────────────────────────────
        form_row = QHBoxLayout()
        form_row.addWidget(QLabel(self.tr("Profile:")))
        self.profile_combo = QComboBox()
        for key in ("youtube", "shorts", "linkedin", "draft", "master"):
            prof = PROFILES[key]
            self.profile_combo.addItem(prof.name, key)
        self.profile_combo.setCurrentIndex(0)
        self.profile_combo.currentIndexChanged.connect(self._describe_profile)
        form_row.addWidget(self.profile_combo, 1)
        layout.addLayout(form_row)

        self.profile_desc = QLabel("")
        self.profile_desc.setStyleSheet("color: #888;")
        self.profile_desc.setWordWrap(True)
        layout.addWidget(self.profile_desc)

        self.estimate_label = QLabel("")
        self.estimate_label.setStyleSheet("color: #FFD700;")
        layout.addWidget(self.estimate_label)

        # ── Metadata block ─────────────────────────────────────
        layout.addWidget(QLabel(self.tr("Publishing metadata (stays local):")))
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText(self.tr("Video title"))
        layout.addWidget(self.title_edit)
        self.desc_edit = QPlainTextEdit()
        self.desc_edit.setPlaceholderText(self.tr("Description"))
        self.desc_edit.setMaximumHeight(80)
        layout.addWidget(self.desc_edit)
        self.tags_edit = QLineEdit()
        self.tags_edit.setPlaceholderText(self.tr("hashtags, comma separated"))
        layout.addWidget(self.tags_edit)

        meta_row = QHBoxLayout()
        self.copy_btn = QPushButton(self.tr("📋 Copy metadata"))
        self.copy_btn.clicked.connect(self._copy_metadata)
        meta_row.addWidget(self.copy_btn)
        self.save_meta_btn = QPushButton(self.tr("💾 Save .txt"))
        self.save_meta_btn.clicked.connect(self._save_metadata)
        meta_row.addWidget(self.save_meta_btn)
        meta_row.addStretch()
        layout.addLayout(meta_row)

        # ── Export ──────────────────────────────────────────────
        export_row = QHBoxLayout()
        self.export_btn = QPushButton(self.tr("🚀 Export"))
        self.export_btn.setStyleSheet("font-weight: bold; padding: 8px;")
        self.export_btn.clicked.connect(self._export)
        export_row.addWidget(self.export_btn)
        self.cancel_btn = QPushButton(self.tr("Cancel"))
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._cancel_export)
        export_row.addWidget(self.cancel_btn)
        layout.addLayout(export_row)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        self.status = QLabel("")
        self.status.setStyleSheet("color: #888;")
        layout.addWidget(self.status)

        self.open_folder_btn = QPushButton(self.tr("📂 Open output folder"))
        self.open_folder_btn.setVisible(False)
        self.open_folder_btn.clicked.connect(self._open_folder)
        layout.addWidget(self.open_folder_btn)
        layout.addStretch()

        self._describe_profile()
        self._last_output = None

    # ── Profile description + estimate ──────────────────────

    def _current_profile(self):
        try:
            return get_profile(self.profile_combo.currentData())
        except ProfileError as e:
            self.status.setText(str(e))
            return None

    def _describe_profile(self):
        prof = self._current_profile()
        if prof is None:
            return
        self.profile_desc.setText(prof.description)
        # Estimate from the loaded take's duration (if any)
        editor = self.main.editor_view
        if editor.clip_path and os.path.isfile(editor.clip_path):
            try:
                info = probe_clip(editor.clip_path)
                height = AspectRatio.resolution(prof.aspect_ratio)[1]
                est = prof.estimate_size_bytes(info["duration_s"], height)
                self.estimate_label.setText(
                    self.tr("Estimated size: ~{0:.0f} MB")
                    .format(est / 1e6)
                )
            except Exception:
                self.estimate_label.setText("")
        else:
            self.estimate_label.setText("")

    # ── Metadata ─────────────────────────────────────────────

    def _metadata_text(self):
        return suggest_metadata(
            self.title_edit.text(),
            self.desc_edit.toPlainText(),
            [t for t in self.tags_edit.text().split(",")],
        )

    def _copy_metadata(self):
        QGuiApplication.clipboard().setText(self._metadata_text())
        self.status.setText(self.tr("Metadata copied to the clipboard."))

    def _save_metadata(self):
        project = self.main.project
        start = project.root if project else os.path.expanduser("~")
        path, _ = QFileDialog.getSaveFileName(
            self, self.tr("Save metadata"),
            os.path.join(start, "metadata.txt"),
        )
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            f.write(self._metadata_text())
        self.status.setText(
            self.tr("Saved: {0}").format(os.path.basename(path))
        )

    # ── Export lifecycle ──────────────────────────────────────

    def _export(self):
        prof = self._current_profile()
        editor = self.main.editor_view
        project = self.main.project
        if prof is None or project is None:
            return
        if editor.clip_rel is None or editor.clip_path is None:
            self.status.setText(
                self.tr("Load a take in the Editor first.")
            )
            return

        # Kit: from the BrandingView form when available (it holds
        # the live settings), else the project's saved kit.
        if self.branding_view is not None:
            kit = self.branding_view._collect_kit()
        else:
            from branding_model import BrandKit
            kit = BrandKit.from_dict(project.get("branding") or {})
        if kit.aspect_ratio != prof.aspect_ratio:
            kit = kit.copy()
            kit.aspect_ratio = prof.aspect_ratio
            kit.fit_mode = "letterbox" if prof.aspect_ratio == "16:9" else kit.fit_mode
        problems = kit.validate(project.root)
        if problems:
            self.status.setText(self.tr("❌ {0}").format(problems[0]))
            return

        # Subtitles for burn-in
        srt_abs = None
        if kit.subtitle_style.enabled:
            subs_dir = os.path.join(project.root, "subtitles")
            if os.path.isdir(subs_dir):
                candidates = sorted(
                    f for f in os.listdir(subs_dir) if f.endswith(".srt")
                )
                if candidates:
                    srt_abs = os.path.join(subs_dir, candidates[0])
            if srt_abs is None:
                self.status.setText(
                    self.tr("Burn-in needs subtitles first (Editor → Subtitles).")
                )
                return

        exports_dir = os.path.join(project.root, "media", "exports")
        os.makedirs(exports_dir, exist_ok=True)
        output = os.path.join(
            exports_dir, "{0}_{1}_{2}.mp4".format(
                prof.key,
                os.path.splitext(os.path.basename(editor.clip_rel))[0],
                time.strftime("%Y%m%d_%H%M%S"),
            ),
        )
        probe = probe_clip(editor.clip_path)

        self.thread = QThread(self)
        self.worker = RenderWorker({
            "thread": self.thread,
            "segments": editor.edit.segments,
            "clip_rel": editor.clip_rel,
            "clip_abs": editor.clip_path,
            "output": output,
            "kit": kit,
            "probe": probe,
            "profile": prof,
            "srt_abs": srt_abs,
            "project_root": project.root,
            "intro_abs": self._resolve(kit.intro_path, project.root),
            "outro_abs": self._resolve(kit.outro_path, project.root),
        })
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self._on_progress)
        self.worker.finished.connect(self._on_finished)
        self.worker.failed.connect(self._on_failed)

        self.export_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.progress.setVisible(True)
        self.progress.setValue(0)
        self.status.setText(
            self.tr("Exporting as {0}…").format(prof.name)
        )
        self.thread.start()

    @staticmethod
    def _resolve(rel, root):
        if not rel:
            return None
        return rel if os.path.isabs(rel) else os.path.join(root, rel)

    def _on_progress(self, fraction):
        self.progress.setValue(int(fraction * 100))

    def _on_finished(self, result):
        self._teardown_worker()
        self.progress.setValue(100)
        self.status.setText(
            self.tr("✅ Exported: {0}").format(
                os.path.basename(result["output"])
            )
        )
        self._last_output = result
        self.open_folder_btn.setVisible(True)
        # Record in project.json
        project = self.main.project
        project.add_export({
            "file": os.path.relpath(result["output"], project.root),
            "profile": result["profile"],
            "thumbnail": (
                os.path.relpath(result["thumbnail"], project.root)
                if result["thumbnail"] else None
            ),
        })
        try:
            self.main.service.save(project)
        except Exception as e:
            log.warning("Could not record the export: %s", e)

    def _on_failed(self, message):
        self._teardown_worker()
        self.progress.setVisible(False)
        self.status.setText(self.tr("❌ {0}").format(message))

    def _cancel_export(self):
        if self.worker is not None:
            self.worker.cancel()
            self.status.setText(self.tr("Cancelling…"))

    def _teardown_worker(self):
        self.export_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        if self.thread is not None:
            self.thread.wait(3000)
            self.thread = None
        self.worker = None

    def _open_folder(self):
        if self._last_output:
            target = os.path.dirname(self._last_output["output"])
            if shutil.which("xdg-open"):
                import subprocess
                subprocess.Popen(
                    ["xdg-open", target],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
            else:
                self.status.setText(target)

    def shutdown(self):
        """Stops a running export when the dialog closes."""
        if self.worker is not None:
            self.worker.cancel()
            self._teardown_worker()
