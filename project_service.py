"""
project_service.py — Project management for Teleprompter Pro.

Phase 1: versioned project format (*.bigprompt), with services to
create, open, save, close, duplicate, rename, and delete projects.

A project is a directory with this structure (see ROADMAP section 5.2):

    MyProject.bigprompt/
    ├── project.json
    ├── scripts/
    │   └── script.txt
    ├── media/
    │   ├── raw/
    │   ├── exports/
    │   └── assets/
    ├── subtitles/
    └── thumbnails/

Rules from the ROADMAP:
- project.json stores only RELATIVE paths.
- Raw, temporary, and exported files live in separate folders.
"""

import json
import os
import re
import shutil
from datetime import datetime, timezone

from logging_setup import get_logger

log = get_logger("Project")

SCHEMA_VERSION = 1
PROJECT_EXTENSION = ".bigprompt"

# Keys allowed in project.json, with their expected types.
# Everything else is preserved as-is (forward compatibility).
_META_TYPES = {
    "schema_version": int,
    "name": str,
    "created": str,
    "modified": str,
    "script": str,          # relative path inside the project
    "teleprompter": dict,   # font, colors, speed, mirror, wpm, etc.
    "devices": dict,        # camera, microphone, resolution, fps
    "clips": list,          # recorded clips (media/raw filenames)
    "segments": list,       # edit segments (non-destructive)
    "subtitle_style": dict,
    "branding": dict,
    "audio": dict,          # music, levels
    "exports": list,        # export history
}

# Characters not allowed in a directory name on common filesystems.
_UNSAFE_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def _utc_now():
    """ISO-8601 UTC timestamp, second precision."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _sanitize(name):
    """
    Turns an arbitrary string into a safe project directory name.

    Keeps letters (including accents), digits, spaces, dash, underscore,
    and dot; removes filesystem-unsafe characters. Empty result becomes
    "Project".
    """
    cleaned = _UNSAFE_CHARS.sub("", name).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    if not cleaned or cleaned in (".", ".."):
        return "Project"
    return cleaned[:80]


def _validate_relative(path):
    """Returns a normalized relative path or None if unsafe."""
    if not path:
        return None
    norm = os.path.normpath(path)
    if norm.startswith(("..", "/")) or os.path.isabs(norm):
        return None
    return norm


class ProjectError(Exception):
    """Raised for invalid or corrupt projects."""


class Project:
    """
    An open project: metadata + script text.

    The in-memory representation keeps the script text so the editor
    can work on it; save() writes both script.txt and project.json.
    """

    def __init__(self, root, meta):
        self.root = root
        self.meta = meta
        self.script_text = ""
        self.script_dirty = False
        self.meta_dirty = False

    # ── Properties ────────────────────────────────────────────

    @property
    def name(self):
        return self.meta.get("name", os.path.basename(self.root))

    @property
    def script_rel_path(self):
        return self.meta.get("script", "scripts/script.txt")

    @property
    def script_abs_path(self):
        return os.path.join(self.root, self.script_rel_path)

    # ── Mutation helpers ──────────────────────────────────────

    def set_script_text(self, text):
        self.script_text = text
        self.script_dirty = True

    def set(self, key, value):
        """Sets a metadata key, validating known types."""
        expected = _META_TYPES.get(key)
        if expected is not None and value is not None and not isinstance(value, expected):
            raise ProjectError(
                f"Invalid type for '{key}': expected {expected.__name__}, got {type(value).__name__}"
            )
        self.meta[key] = value
        self.meta_dirty = True

    def get(self, key, default=None):
        return self.meta.get(key, default)

    def add_export(self, entry):
        """Appends an entry to the export history."""
        exports = self.meta.setdefault("exports", [])
        exports.append(entry)
        self.meta_dirty = True

    def add_clip(self, filename):
        """Registers a recorded clip (relative filename in media/raw)."""
        clips = self.meta.setdefault("clips", [])
        rel = _validate_relative(filename)
        if rel is None:
            raise ProjectError(f"Clip path must be relative: {filename}")
        if rel not in clips:
            clips.append(rel)
            self.meta_dirty = True


class ProjectService:
    """
    Creates, opens, and manages projects on disk.

    All public methods raise ProjectError with an English, user-facing
    message on failure (Phase 0 rule: failures must be explained and
    offer a corrective action).
    """

    def __init__(self, projects_dir=None):
        if projects_dir is None:
            projects_dir = os.path.join(os.path.expanduser("~"), "TeleprompterProjects")
        self.projects_dir = projects_dir

    # ── Discovery ─────────────────────────────────────────────

    def list_projects(self):
        """Returns [(name, path, modified)] sorted by most recent use."""
        if not os.path.isdir(self.projects_dir):
            return []
        out = []
        for entry in os.listdir(self.projects_dir):
            path = os.path.join(self.projects_dir, entry)
            if entry.endswith(PROJECT_EXTENSION) and os.path.isfile(
                os.path.join(path, "project.json")
            ):
                out.append((entry[: -len(PROJECT_EXTENSION)], path,
                            os.path.getmtime(path)))
        out.sort(key=lambda t: t[2], reverse=True)
        return out

    def recent_projects(self, limit=10):
        return self.list_projects()[:limit]

    # ── Lifecycle ──────────────────────────────────────────────

    def create(self, name, script_text="", template=None):
        """
        Creates a new project directory and returns the open Project.

        The directory name is '<safe-name>.bigprompt'; if it already
        exists, a numeric suffix ('-2', '-3'…) is appended.
        """
        base = _sanitize(name)
        root = os.path.join(self.projects_dir, base + PROJECT_EXTENSION)
        suffix = 2
        while os.path.exists(root):
            root = os.path.join(
                self.projects_dir,
                f"{base}-{suffix}{PROJECT_EXTENSION}",
            )
            suffix += 1

        try:
            self._make_layout(root)
        except OSError as e:
            raise ProjectError(
                f"Could not create the project folder: {e}. "
                f"Check permissions on {self.projects_dir}"
            ) from e

        meta = {
            "schema_version": SCHEMA_VERSION,
            "name": base,
            "created": _utc_now(),
            "modified": _utc_now(),
            "script": "scripts/script.txt",
            "teleprompter": {},
            "devices": {},
            "clips": [],
            "segments": [],
            "subtitle_style": {},
            "branding": {},
            "audio": {},
            "exports": [],
        }
        project = Project(root, meta)
        project.set_script_text(script_text)
        self.save(project)
        log.info("Project created: %s", root)
        return project

    def open(self, path):
        """Opens an existing project; raises ProjectError if invalid."""
        if not os.path.isdir(path):
            raise ProjectError(f"Project not found: {path}")
        meta_path = os.path.join(path, "project.json")
        if not os.path.isfile(meta_path):
            raise ProjectError(
                f"'{path}' is not a project folder (missing project.json)"
            )
        try:
            with open(meta_path, encoding="utf-8") as f:
                meta = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            raise ProjectError(
                f"The project file is corrupt or unreadable: {e}. "
                "Restore it from a backup or recreate the project"
            ) from e

        if not isinstance(meta, dict) or "schema_version" not in meta:
            raise ProjectError(
                f"The project file is not valid: {meta_path}"
            )
        if meta["schema_version"] > SCHEMA_VERSION:
            raise ProjectError(
                "This project was created with a newer version ({0}). "
                "Update Teleprompter Pro to open it".format(meta["schema_version"])
            )

        project = Project(path, meta)

        script_path = os.path.join(path, project.script_rel_path)
        if os.path.isfile(script_path):
            try:
                with open(script_path, encoding="utf-8") as f:
                    project.script_text = f.read()
            except OSError as e:
                raise ProjectError(
                    f"Could not read the script: {e}"
                ) from e
        else:
            project.script_text = ""
            project.script_dirty = True  # will be created on save

        log.info("Project opened: %s", path)
        return project

    def save(self, project):
        """
        Persists metadata and (if dirty) the script.

        Only relative paths are written; absolute paths in meta are
        rejected.
        """
        project.meta["modified"] = _utc_now()
        if "script" in project.meta:
            rel = _validate_relative(project.meta["script"])
            if rel is None:
                raise ProjectError(
                    "Script path must be relative to the project: {0}".format(
                        project.meta["script"]
                    )
                )
            project.meta["script"] = rel

        try:
            if project.script_dirty:
                script_path = project.script_abs_path
                os.makedirs(os.path.dirname(script_path), exist_ok=True)
                with open(script_path, "w", encoding="utf-8") as f:
                    f.write(project.script_text)
                project.script_dirty = False

            meta_path = os.path.join(project.root, "project.json")
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(project.meta, f, indent=2, ensure_ascii=False)
            project.meta_dirty = False
        except OSError as e:
            raise ProjectError(f"Could not save the project: {e}") from e

        log.info("Project saved: %s", project.root)
        return True

    def save_as(self, project, new_name):
        """Duplicates the project under a new name and opens the copy."""
        source = project.root
        # First save pending changes so the copy includes them
        self.save(project)
        new_project = self.create(new_name)
        shutil.rmtree(new_project.root)
        try:
            shutil.copytree(source, new_project.root)
        except OSError as e:
            raise ProjectError(f"Could not duplicate the project: {e}") from e
        reopened = self.open(new_project.root)
        reopened.meta["name"] = _sanitize(new_name)
        self.save(reopened)
        log.info("Project duplicated: %s -> %s", source, reopened.root)
        return reopened

    def rename(self, project, new_name):
        """Renames the project directory and metadata name."""
        old_root = project.root
        new_dirname = _sanitize(new_name) + PROJECT_EXTENSION
        new_root = os.path.join(os.path.dirname(old_root), new_dirname)
        if os.path.exists(new_root):
            raise ProjectError(
                f"A project named '{new_name}' already exists"
            )
        try:
            os.rename(old_root, new_root)
        except OSError as e:
            raise ProjectError(f"Could not rename the project: {e}") from e
        project.root = new_root
        project.meta["name"] = _sanitize(new_name)
        self.save(project)
        log.info("Project renamed: %s -> %s", old_root, new_root)
        return project

    def delete(self, project_or_path, confirm=False):
        """
        Deletes a project permanently. Requires confirm=True.

        The original recorded media goes with the folder; callers must
        warn the user (ROADMAP rule 14).
        """
        path = (
            project_or_path.root
            if isinstance(project_or_path, Project)
            else project_or_path
        )
        if not confirm:
            raise ProjectError(
                "Deletion requires explicit confirmation "
                "(pass confirm=True after asking the user)"
            )
        if not os.path.isdir(path):
            raise ProjectError(f"Project not found: {path}")
        try:
            shutil.rmtree(path)
        except OSError as e:
            raise ProjectError(f"Could not delete the project: {e}") from e
        log.info("Project deleted: %s", path)
        return True

    # ── Helpers ───────────────────────────────────────────────

    def _make_layout(self, root):
        """Creates the standard project folder layout."""
        for sub in (
            "scripts",
            os.path.join("media", "raw"),
            os.path.join("media", "exports"),
            os.path.join("media", "assets"),
            "subtitles",
            "thumbnails",
        ):
            os.makedirs(os.path.join(root, sub), exist_ok=True)

    def media_path(self, project, kind, filename=None):
        """
        Absolute path inside media/<kind>/.

        kind must be one of raw/exports/assets; filename, when given,
        must be a bare filename (no directories).
        """
        if kind not in ("raw", "exports", "assets"):
            raise ProjectError(f"Unknown media kind: {kind}")
        base = os.path.join(project.root, "media", kind)
        if filename is None:
            return base
        if os.path.basename(filename) != filename:
            raise ProjectError("Media filenames must not contain paths")
        return os.path.join(base, filename)

    def migrate_legacy_config(self, config):
        """
        Converts the old global config.json into teleprompter settings
        for a fresh project (Phase 1 migration path).
        """
        return {
            "font_family": config.get("font_family", "Helvetica"),
            "font_size": config.get("font_size", 42),
            "text_color": config.get("text_color", "#FFD700"),
            "bg_color": config.get("bg_color", "black"),
            "scroll_speed": config.get("scroll_speed", 3),
            "margin_x": config.get("margin_x", 200),
            "wpm": config.get("wpm", 150),
            "mirror_mode": config.get("mirror_mode", False),
        }
