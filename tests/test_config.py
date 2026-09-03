"""
tests/test_config.py — Tests unitarios para config.py
"""

import json
import os
import tempfile

from config import DEFAULTS, load_config, save_config


class TestLoadConfig:
    """Tests para load_config."""

    def test_load_defaults_when_no_file(self):
        """Carga valores por defecto cuando no existe config.json."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, "config.json")
            config = load_config(config_path)
            assert config == DEFAULTS

    def test_load_saved_config(self):
        """Carga configuración guardada correctamente."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, "config.json")
            saved = {"font_size": 60, "scroll_speed": 10, "wpm": 200}
            with open(config_path, "w") as f:
                json.dump(saved, f)
            config = load_config(config_path)
            assert config["font_size"] == 60
            assert config["scroll_speed"] == 10
            assert config["wpm"] == 200

    def test_ignores_unknown_keys(self):
        """Ignora claves desconocidas en config.json."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, "config.json")
            saved = {"unknown_key": 123, "font_size": 30}
            with open(config_path, "w") as f:
                json.dump(saved, f)
            config = load_config(config_path)
            assert "unknown_key" not in config
            assert config["font_size"] == 30

    def test_corrupt_json_returns_defaults(self):
        """JSON corrupto devuelve valores por defecto."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, "config.json")
            with open(config_path, "w") as f:
                f.write("{invalid json {{{")
            config = load_config(config_path)
            assert config == DEFAULTS

    def test_empty_json_returns_defaults(self):
        """JSON vacío devuelve valores por defecto."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, "config.json")
            with open(config_path, "w") as f:
                json.dump({}, f)
            config = load_config(config_path)
            assert config == DEFAULTS

    def test_wrong_types_fall_back_to_defaults(self):
        """Fase 0: un tipo incorrecto en el archivo cae al valor por defecto."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, "config.json")
            saved = {"font_size": "grande", "scroll_speed": None, "wpm": [1, 2]}
            with open(config_path, "w") as f:
                json.dump(saved, f)
            config = load_config(config_path)
            assert config["font_size"] == DEFAULTS["font_size"]
            assert config["scroll_speed"] == DEFAULTS["scroll_speed"]
            assert config["wpm"] == DEFAULTS["wpm"]


class TestSaveConfig:
    """Tests para save_config."""

    def test_save_and_load(self):
        """Guardar y cargar mantiene los valores."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, "config.json")
            config = dict(DEFAULTS)
            config["font_size"] = 99
            save_config(config, config_path)
            loaded = load_config(config_path)
            assert loaded["font_size"] == 99

    def test_save_creates_file(self):
        """save_config crea el archivo si no existe."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, "new_config.json")
            assert not os.path.exists(config_path)
            save_config(DEFAULTS, config_path)
            assert os.path.exists(config_path)


class TestDefaults:
    """Tests para los valores por defecto."""

    def test_all_defaults_exist(self):
        """Todos los defaults esperados están presentes."""
        required_keys = [
            "font_family", "font_size", "font_weight",
            "text_color", "bg_color", "scroll_speed",
            "margin_x", "margin_y", "wpm",
            "mirror_mode", "fullscreen", "script_dir"
        ]
        for key in required_keys:
            assert key in DEFAULTS, f"Falta la clave: {key}"

    def test_scroll_speed_positive(self):
        """La velocidad de scroll debe ser positiva."""
        assert DEFAULTS["scroll_speed"] > 0

    def test_font_size_positive(self):
        """El tamaño de fuente debe ser positivo."""
        assert DEFAULTS["font_size"] > 0

    def test_wpm_positive(self):
        """WPM debe ser positivo."""
        assert DEFAULTS["wpm"] > 0
