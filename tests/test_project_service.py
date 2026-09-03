"""
tests/test_project_service.py — Tests for ProjectService (Phase 1).

Covers the .bigprompt format: create/open/save/rename/duplicate/delete,
relative-path enforcement, schema validation, and UTF-8 round-trips.
"""

import json
import os
import pytest

from project_service import (
    ProjectService, Project, ProjectError, SCHEMA_VERSION,
    PROJECT_EXTENSION, _sanitize, _validate_relative,
)


@pytest.fixture
def service(tmp_path):
    return ProjectService(projects_dir=str(tmp_path / "projects"))


class TestSanitize:
    """Name sanitization for project directories."""

    def test_keeps_normal_names(self):
        assert _sanitize("My Video 2026") == "My Video 2026"

    def test_strips_unsafe_chars(self):
        assert _sanitize("a/b:c*d?e") == "abcde"

    def test_empty_becomes_project(self):
        assert _sanitize("///") == "Project"
        assert _sanitize("") == "Project"

    def test_dots_are_rejected(self):
        assert _sanitize(".") == "Project"
        assert _sanitize("..") == "Project"

    def test_long_names_truncated(self):
        assert len(_sanitize("x" * 200)) == 80

    def test_accents_preserved(self):
        assert _sanitize("Presentación ñandú") == "Presentación ñandú"


class TestValidateRelative:
    """Relative-path safety inside projects."""

    def test_simple(self):
        assert _validate_relative("scripts/script.txt") == "scripts/script.txt"

    def test_rejects_parent(self):
        assert _validate_relative("../secret.txt") is None

    def test_rejects_absolute(self):
        assert _validate_relative("/etc/passwd") is None

    def test_rejects_empty(self):
        assert _validate_relative("") is None

    def test_normalizes(self):
        assert _validate_relative("./scripts//x.txt") == os.path.normpath("scripts/x.txt")


class TestCreate:
    """Project creation and layout."""

    def test_creates_layout(self, service):
        p = service.create("Test")
        assert os.path.isfile(os.path.join(p.root, "project.json"))
        for sub in ("scripts", "media/raw", "media/exports",
                    "media/assets", "subtitles", "thumbnails"):
            assert os.path.isdir(os.path.join(p.root, sub)), sub

    def test_meta_defaults(self, service):
        p = service.create("Test")
        assert p.meta["schema_version"] == SCHEMA_VERSION
        assert p.meta["name"] == "Test"
        assert p.meta["script"] == "scripts/script.txt"
        assert p.meta["clips"] == []
        assert p.meta["exports"] == []
        assert "created" in p.meta and "modified" in p.meta

    def test_directory_extension(self, service):
        p = service.create("Test")
        assert p.root.endswith(PROJECT_EXTENSION)

    def test_unique_names(self, service):
        p1 = service.create("Same")
        p2 = service.create("Same")
        assert p1.root != p2.root
        assert os.path.isdir(p1.root) and os.path.isdir(p2.root)

    def test_initial_script_saved(self, service):
        p = service.create("Test", script_text="Hello world")
        assert os.path.isfile(os.path.join(p.root, "scripts", "script.txt"))
        with open(os.path.join(p.root, "scripts", "script.txt"), encoding="utf-8") as f:
            assert f.read() == "Hello world"


class TestOpenSave:
    """Round-trips and validation."""

    def test_open_round_trip(self, service):
        p = service.create("Test", script_text="one two three")
        p2 = service.open(p.root)
        assert p2.script_text == "one two three"
        assert p2.name == "Test"

    def test_save_script_preserves_utf8(self, service):
        text = "¡Ñandú comía allí! 🎉 días — ¿ok?"
        p = service.create("UTF8", script_text=text)
        p2 = service.open(p.root)
        assert p2.script_text == text

    def test_save_updates_modified(self, service):
        p = service.create("Test")
        first = p.meta["modified"]
        p.set_script_text("changed")
        # Ensure a different timestamp
        import time
        time.sleep(1.1)
        service.save(p)
        p2 = service.open(p.root)
        assert p2.meta["modified"] > first

    def test_open_missing(self, service):
        with pytest.raises(ProjectError, match="not found"):
            service.open("/nonexistent/path")

    def test_open_not_a_project(self, service, tmp_path):
        d = tmp_path / "empty"
        d.mkdir()
        with pytest.raises(ProjectError, match="project.json"):
            service.open(str(d))

    def test_open_corrupt_json(self, service, tmp_path):
        d = tmp_path / ("bad" + PROJECT_EXTENSION)
        d.mkdir()
        (d / "project.json").write_text("{invalid")
        with pytest.raises(ProjectError, match="corrupt"):
            service.open(str(d))

    def test_open_future_version(self, service):
        p = service.create("Future")
        with open(os.path.join(p.root, "project.json"), encoding="utf-8") as f:
            meta = json.load(f)
        meta["schema_version"] = SCHEMA_VERSION + 1
        with open(os.path.join(p.root, "project.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f)
        with pytest.raises(ProjectError, match="newer version"):
            service.open(p.root)

    def test_set_validates_types(self, service):
        p = service.create("Test")
        with pytest.raises(ProjectError, match="Invalid type"):
            p.set("name", 123)  # name must be str
        p.set("wpm_anything_unknown", {"free": "form"})  # unknown keys pass

    def test_save_rejects_absolute_script(self, service):
        p = service.create("Test")
        p.meta["script"] = "/abs/path/script.txt"
        with pytest.raises(ProjectError, match="relative"):
            service.save(p)

    def test_no_absolute_paths_in_json(self, service):
        p = service.create("Test")
        service.save(p)
        with open(os.path.join(p.root, "project.json"), encoding="utf-8") as f:
            raw = f.read()
        assert service.projects_dir not in raw
        assert p.root not in raw


class TestRenameDuplicateDelete:
    """Destructive operations and copies."""

    def test_rename(self, service):
        p = service.create("Old")
        service.rename(p, "New")
        assert not os.path.exists(os.path.join(service.projects_dir, "Old.bigprompt"))
        assert os.path.isdir(os.path.join(service.projects_dir, "New.bigprompt"))
        assert p.meta["name"] == "New"

    def test_rename_conflict(self, service):
        service.create("A")
        p = service.create("B")
        with pytest.raises(ProjectError, match="already exists"):
            service.rename(p, "A")

    def test_duplicate(self, service):
        p = service.create("Original", script_text="keep me")
        p.set("branding", {"color": "gold"})
        service.save(p)
        copy = service.save_as(p, "Copy")
        assert copy.script_text == "keep me"
        assert copy.get("branding") == {"color": "gold"}
        assert os.path.isdir(p.root)  # original untouched
        assert copy.root != p.root

    def test_delete_requires_confirmation(self, service):
        p = service.create("Doomed")
        with pytest.raises(ProjectError, match="confirmation"):
            service.delete(p)
        assert os.path.isdir(p.root)  # still alive

    def test_delete_with_confirmation(self, service):
        p = service.create("Doomed")
        assert service.delete(p, confirm=True) is True
        assert not os.path.exists(p.root)


class TestListing:
    """Project discovery."""

    def test_list_empty(self, service):
        assert service.list_projects() == []

    def test_list_sorted_by_recency(self, service):
        service.create("Old")
        import time
        time.sleep(1.05)
        service.create("New")
        names = [n for n, _, _ in service.list_projects()]
        assert names[0] == "New"

    def test_ignores_non_projects(self, service, tmp_path):
        service.create("Real")
        (tmp_path / "projects" / "stray.bigprompt").mkdir()
        names = [n for n, _, _ in service.list_projects()]
        assert names == ["Real"]


class TestMediaPaths:
    """Media folder routing."""

    def test_media_base(self, service):
        p = service.create("Test")
        assert service.media_path(p, "raw").endswith(os.path.join("media", "raw"))

    def test_media_file(self, service):
        p = service.create("Test")
        path = service.media_path(p, "exports", "video.mp4")
        assert path.endswith(os.path.join("media", "exports", "video.mp4"))

    def test_media_rejects_paths(self, service):
        p = service.create("Test")
        with pytest.raises(ProjectError, match="paths"):
            service.media_path(p, "raw", "../escape.txt")

    def test_media_rejects_unknown_kind(self, service):
        p = service.create("Test")
        with pytest.raises(ProjectError, match="kind"):
            service.media_path(p, "tmp")

    def test_add_clip_validates(self, service):
        p = service.create("Test")
        p.add_clip("take_001.mp4")
        with pytest.raises(ProjectError, match="relative"):
            p.add_clip("/abs/take.mp4")
        assert p.meta["clips"] == ["take_001.mp4"]


class TestLegacyMigration:
    """Old config.json → project teleprompter settings."""

    def test_migrate(self, service):
        legacy = {
            "font_family": "DejaVu Sans", "font_size": 55,
            "text_color": "#FFFFFF", "bg_color": "black",
            "scroll_speed": 7, "margin_x": 120, "wpm": 160,
            "mirror_mode": True,
        }
        tele = service.migrate_legacy_config(legacy)
        assert tele["font_size"] == 55
        assert tele["scroll_speed"] == 7
        assert tele["mirror_mode"] is True
        assert tele["wpm"] == 160

    def test_migrate_defaults_on_missing(self, service):
        tele = service.migrate_legacy_config({})
        assert tele["font_size"] == 42
        assert tele["wpm"] == 150
