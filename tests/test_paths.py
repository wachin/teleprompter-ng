"""
tests/test_paths.py — Tests for path resolution (Phase 0).

Verifies that the application finds its resources regardless of the
working directory.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import paths


class TestAppDir:
    """Tests de get_app_dir."""

    def test_app_dir_contains_main(self):
        """El directorio de la app contiene main.py (o el binario)."""
        app_dir = paths.get_app_dir()
        if not getattr(sys, "frozen", False):
            assert os.path.isfile(os.path.join(app_dir, "main.py"))

    def test_app_dir_is_absolute(self):
        """La ruta devuelta es absoluta."""
        assert os.path.isabs(paths.get_app_dir())


class TestResourceDirs:
    """Tests de los directorios de recursos."""

    def test_script_dir_exists(self):
        """El directorio de guiones existe en el repositorio."""
        assert os.path.isdir(paths.script_dir())

    def test_templates_dir_exists(self):
        """El directorio de plantillas existe en el repositorio."""
        assert os.path.isdir(paths.templates_dir())

    def test_default_script_resolves(self):
        """El guion predeterminado se encuentra desde cualquier cwd."""
        path = paths.resolve_script_path()
        assert path is not None
        assert os.path.isfile(path)

    def test_resolution_independent_of_cwd(self):
        """resolve_script_path works from another directory."""
        import subprocess
        result = subprocess.run(
            [sys.executable, "-c",
             "import sys; sys.path.insert(0, %r); "
             "import paths; print(paths.resolve_script_path())" % paths.get_app_dir()],
            capture_output=True, text=True, cwd="/tmp", check=True,
        )
        assert "guion_actual.txt" in result.stdout


class TestRelativeTo:
    """Tests of relative-path conversion."""

    def test_relative_inside_base(self):
        assert paths.relative_to("/a/b/c.txt", "/a/b") == "c.txt"

    def test_relative_outside_base(self):
        rel = paths.relative_to("/x/y.txt", "/a/b")
        assert rel.startswith("..")
        assert rel.endswith("y.txt")

    def test_relative_same_path(self):
        assert paths.relative_to("/a/b", "/a/b") == "."
