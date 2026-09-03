"""
main.py — Entry point of Teleprompter Pro.

Usage:
    python main.py                      # Project mode (default, Phase 1)
    python main.py --read script.txt   # Legacy reading mode (full-screen)
    python main.py path/to/script.txt  # Read a specific script directly
"""

import os
import sys

from PyQt6.QtCore import QLocale, QTranslator
from PyQt6.QtWidgets import QApplication, QMessageBox

from config import get_config_path, load_config
from logging_setup import get_logger, setup_logging
from paths import get_app_dir, resolve_script_path
from project_service import ProjectService

log = get_logger("Main")


def load_script(path):
    """Reads the text file and returns its content."""
    with open(path, encoding="utf-8") as f:
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


def parse_args(argv):
    """
    Returns (mode, script_path): mode is 'read' or 'projects'.
    """
    mode = "projects"
    script_path = None
    rest = list(argv[1:])
    if "--read" in rest:
        mode = "read"
        rest.remove("--read")
    if rest:
        mode = "read"  # a positional script implies reading mode
        script_path = os.path.abspath(rest[0])
    return mode, script_path


def run_read_mode(app, script_path, config):
    """Legacy full-screen teleprompter over a script file."""
    from ui import Teleprompter

    if script_path is None:
        script_path = resolve_script_path()
    if not script_path or not os.path.exists(script_path):
        searched = script_path or os.path.join(get_app_dir(), "scripts", "guion_actual.txt")
        log.error("Script not found: %s", searched)
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
    window = Teleprompter(text, config, script_path)
    window.show()
    return window


def run_projects_mode(app, config):
    """Project-based mode (default): MainWindow + ProjectService."""
    from main_window import MainWindow

    service = ProjectService()
    # First run hint in the log so users can find their files
    log.info("Projects folder: %s", service.projects_dir)

    window = MainWindow(service, config=config)
    window.show()
    return window


def main():
    setup_logging()
    config = load_config()
    mode, script_path = parse_args(sys.argv)

    app = QApplication(sys.argv)
    install_translators(app)
    log.info("Config: %s", get_config_path())
    log.info("Mode: %s", mode)

    if mode == "read":
        run_read_mode(app, script_path, config)
    else:
        run_projects_mode(app, config)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
