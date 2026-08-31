"""
config.py — Configuración del Teleprompter Pro.

Carga y guarda preferencias en config.json.
Si el archivo no existe o está corrupto, usa valores por defecto.

Soporta Windows (%AppData%), Linux (~/.config) y macOS (~/Library/Application Support).
"""

import json
import os
import sys
import platform


def get_config_dir():
    """Retorna el directorio de configuración según la plataforma."""
    app_name = "TeleprompterPro"

    if sys.platform == "win32":
        # Windows: %AppData%\TeleprompterPro
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
        return os.path.join(base, app_name)
    elif sys.platform == "darwin":
        # macOS: ~/Library/Application Support/TeleprompterPro
        return os.path.join(os.path.expanduser("~"), "Library", "Application Support", app_name)
    else:
        # Linux/Unix: ~/.config/TeleprompterPro
        xdg_config = os.environ.get("XDG_CONFIG_HOME", os.path.join(os.path.expanduser("~"), ".config"))
        return os.path.join(xdg_config, app_name)


def get_config_path():
    """Retorna la ruta completa del archivo de configuración."""
    return os.path.join(get_config_dir(), "config.json")


DEFAULTS = {
    "font_family": "Helvetica",
    "font_size": 42,
    "font_weight": "bold",
    "text_color": "#FFD700",
    "bg_color": "black",
    "scroll_speed": 3,
    "margin_x": 200,
    "margin_y": 50,
    "wpm": 150,
    "mirror_mode": False,
    "fullscreen": True,
    "script_dir": "scripts",
    "remote_enabled": False,
}

# Tipos esperados por clave; si el archivo guardado no coincide, se
# usa el valor por defecto en lugar de propagar un tipo inválido.
_TYPES = {
    "font_family": str,
    "font_size": int,
    "font_weight": str,
    "text_color": str,
    "bg_color": str,
    "scroll_speed": int,
    "margin_x": int,
    "margin_y": int,
    "wpm": int,
    "mirror_mode": bool,
    "fullscreen": bool,
    "script_dir": str,
    "remote_enabled": bool,
}


def load_config(path=None):
    """
    Carga config.json. Si falla, devuelve los valores por defecto.

    Args:
        path: Ruta al archivo de config. Si es None, usa la ruta por plataforma.
    """
    if path is None:
        path = get_config_path()

    config = dict(DEFAULTS)

    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                saved = json.load(f)
            # Solo tomamos claves que existen en DEFAULTS y con el
            # tipo correcto (Fase 0: evita config corrupta que rompe la UI)
            for key in DEFAULTS:
                if key in saved and isinstance(saved[key], _TYPES[key]):
                    config[key] = saved[key]
        except (json.JSONDecodeError, IOError):
            pass  # Archivo corrupto → usar defaults

    return config


def save_config(config, path=None):
    """
    Guarda la configuración actual en config.json.

    Args:
        config: Diccionario con la configuración.
        path: Ruta al archivo de config. Si es None, usa la ruta por plataforma.
    """
    if path is None:
        path = get_config_path()

    # Crear directorio si no existe
    config_dir = os.path.dirname(path)
    if not os.path.exists(config_dir):
        os.makedirs(config_dir, exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
