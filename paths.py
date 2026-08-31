"""
paths.py — Resolución de rutas independiente del directorio de trabajo.

Fase 0: garantiza que la aplicación encuentre sus recursos (guiones,
plantillas, modelos) tanto al ejecutarse desde el repositorio como desde
una instalación en otra carpeta o desde un binario de PyInstaller.
"""

import os
import sys


def get_app_dir():
    """
    Retorna el directorio base de la aplicación.

    - En un binario de PyInstaller: directorio del ejecutable.
    - En modo normal: directorio que contiene main.py.
    """
    if getattr(sys, "frozen", False):
        # PyInstaller: los recursos van junto al ejecutable
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def resource_path(*parts):
    """Une partes a la raíz de recursos de la aplicación."""
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
    Convierte path en relativo a base si es posible.

    Devuelve la ruta original sin cambios si está en otra unidad o
    fuera de base.
    """
    try:
        return os.path.relpath(path, base)
    except ValueError:
        return path
