"""
main.py — Punto de entrada del Teleprompter Pro.

Uso:
    python main.py                          # Carga scripts/guion_actual.txt
    python main.py ruta/al/guion.txt        # Carga un archivo específico
"""

import sys
import os

from PyQt6.QtWidgets import QApplication, QMessageBox

from config import load_config, get_config_path
from logging_setup import setup_logging, get_logger
from paths import get_app_dir, resolve_script_path
from ui import Teleprompter

log = get_logger("Main")


def load_script(path):
    """Lee el archivo de texto y devuelve su contenido."""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def main():
    setup_logging()
    config = load_config()

    # Determinar qué guion cargar
    if len(sys.argv) > 1:
        script_path = os.path.abspath(sys.argv[1])
    else:
        script_path = resolve_script_path()

    if not script_path or not os.path.exists(script_path):
        searched = script_path or os.path.join(get_app_dir(), "scripts", "guion_actual.txt")
        log.error("No se encontró el guion: %s", searched)
        # Mostrar el error también en la interfaz si es posible
        app = QApplication.instance() or QApplication(sys.argv)
        box = QMessageBox()
        box.setIcon(QMessageBox.Icon.Critical)
        box.setWindowTitle("Teleprompter Pro")
        box.setText("No se encontró el guion")
        box.setInformativeText(
            f"No existe el archivo:\n{searched}\n\n"
            "Uso: python main.py [ruta/al/guion.txt]"
        )
        box.exec()
        sys.exit(1)

    text = load_script(script_path)
    log.info("Guion cargado: %s", script_path)
    log.info("Palabras: %s", len(text.split()))
    log.info("Config: %s", get_config_path())

    app = QApplication(sys.argv)
    window = Teleprompter(text, config, script_path)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
