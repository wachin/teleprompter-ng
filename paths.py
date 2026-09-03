"""
paths.py — Working-directory-independent path resolution.

Phase 0: ensures the application finds its resources (scripts,
templates, models) whether run from the repository, from an
installation folder, or from a PyInstaller binary.
"""

import os
import sys


def get_app_dir():
    """
    Returns the application base directory.

    - PyInstaller binary: the executable directory.
    - Normal mode: the directory containing main.py.
    """
    if getattr(sys, "frozen", False):
        # PyInstaller: los recursos van junto al ejecutable
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def resource_path(*parts):
    """Joins parts to the application resource root."""
    return os.path.join(get_app_dir(), *parts)


def script_dir():
    """Directorio de guiones predeterminado."""
    return resource_path("scripts")


def templates_dir():
    """Directorio de plantillas del control remoto."""
    return resource_path("templates")


def models_dir():
    """Directorio de modelos de voz (Vosk)."""
    return resource_path("models")


def resolve_script_path(name="guion_actual.txt"):
    """Ruta al guion predeterminado; None si no existe."""
    path = os.path.join(script_dir(), name)
    return path if os.path.exists(path) else None


def relative_to(path, base):
    """
    Converts path to a path relative to base when possible.

    Returns the original path unchanged if it is on another drive
    or outside base.
    """
    try:
        return os.path.relpath(path, base)
    except ValueError:
        return path
