"""
main.py — Punto de entrada del Teleprompter Pro.

Uso:
    python main.py                          # Carga scripts/guion_actual.txt
    python main.py ruta/al/guion.txt        # Carga un archivo específico
"""

import sys
import os
from PyQt6.QtWidgets import QApplication

from config import load_config, get_config_path
from ui import Teleprompter


def load_script(path):
    """Lee el archivo de texto y devuelve su contenido."""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def main():
    config = load_config()

    # Determinar qué guion cargar
    if len(sys.argv) > 1:
        script_path = sys.argv[1]
    else:
        script_dir = config["script_dir"]
        script_path = os.path.join(script_dir, "guion_actual.txt")

    if not os.path.exists(script_path):
        print(f"Error: No se encontró el archivo '{script_path}'")
        print("Uso: python main.py [ruta/al/guion.txt]")
        sys.exit(1)

    text = load_script(script_path)
    print(f"Guion cargado: {script_path}")
    print(f"Palabras: {len(text.split())}")
    print(f"Config: {get_config_path()}")

    app = QApplication(sys.argv)
    window = Teleprompter(text, config, script_path)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
