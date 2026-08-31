"""
main.py — Entry point of Teleprompter Pro.

Usage:
    python main.py                          # Loads scripts/guion_actual.txt
    python main.py path/to/script.txt       # Loads a specific file
"""

import sys
import os

from PyQt6.QtCore import QLocale, QTranslator
from PyQt6.QtWidgets import QApplication, QMessageBox

from config import load_config, get_config_path
from logging_setup import setup_logging, get_logger
from paths import get_app_dir, resolve_script_path
from ui import Teleprompter

log = get_logger("Main")


def load_script(path):
    """Reads the text file and returns its content."""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def install_translators(app):
    """
    Loads .qm translations from the translations/ folder, if present.

    Source strings are English. Spanish and other translations will be
    delivered as compiled .qm files (see docs/I18N.md); when they exist
    they are loaded automatically based on the system locale.
    """
    translations_dir = os.path.join(get_app_dir(), "translations")
    if not os.path.isdir(translations_dir):
        return
    # Prefer an exact locale match (es_ES), then language-only (es).
    locale_names = [
        QLocale.system().name(),                       # e.g. "es_ES"
        QLocale.system().name().split("_")[0],         # e.g. "es"
    ]
    loaded_any = False
    for base in ("teleprompter", "qt"):
        for locale_name in locale_names:
            translator = QTranslator(app)
            if translator.load(QLocale(locale_name), base, "_", translations_dir):
                app.installTranslator(translator)
                log.info("Translation loaded: %s_%s.qm", base, locale_name)
                loaded_any = True
                break
    if not loaded_any and QLocale.system().name().split("_")[0] != "en":
        log.info(
            "No translation found for locale %s; using English source strings",
            QLocale.system().name(),
        )


def main():
    setup_logging()
    config = load_config()

    # Determine which script to load
    if len(sys.argv) > 1:
        script_path = os.path.abspath(sys.argv[1])
    else:
        script_path = resolve_script_path()

    if not script_path or not os.path.exists(script_path):
        searched = script_path or os.path.join(get_app_dir(), "scripts", "guion_actual.txt")
        log.error("Script not found: %s", searched)
        # Show the error in the UI when possible
        app = QApplication.instance() or QApplication(sys.argv)
        box = QMessageBox()
        box.setIcon(QMessageBox.Icon.Critical)
        box.setWindowTitle(QApplication.translate("MainWindow", "Teleprompter Pro"))
        box.setText(QApplication.translate("MainWindow", "Script not found"))
        box.setInformativeText(
            QApplication.translate(
                "MainWindow",
                "This file does not exist:\n{0}\n\n"
                "Usage: python main.py [path/to/script.txt]",
            ).format(searched)
        )
        box.exec()
        sys.exit(1)

    text = load_script(script_path)
    log.info("Script loaded: %s", script_path)
    log.info("Words: %s", len(text.split()))
    log.info("Config: %s", get_config_path())

    app = QApplication(sys.argv)
    install_translators(app)
    window = Teleprompter(text, config, script_path)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

