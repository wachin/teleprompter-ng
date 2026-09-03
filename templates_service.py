"""
templates_service.py — Script templates for new projects (Phase 1).

Templates are plain UTF-8 .txt files with a {placeholders} convention,
stored in resources/script_templates/. Each ships a small JSON sidecar
(<name>.json) with title, description, and default WPM so the UI can
present them without parsing the text.
"""

import json
import os

from paths import resource_path
from logging_setup import get_logger

log = get_logger("Templates")

TEMPLATES_DIR = resource_path("resources", "script_templates")

# Built-in template identifiers (files shipped with the application).
BUILTIN = ("tutorial", "presentation", "class", "news", "review", "ad")


class TemplateError(Exception):
    """Raised when a template cannot be found or loaded."""


def templates_dir():
    """Directory where templates are looked up."""
    return TEMPLATES_DIR


def _template_path(name):
    return os.path.join(TEMPLATES_DIR, name + ".txt")


def available_templates():
    """
    Lists the templates shipped with the app.

    Returns a list of dicts sorted by title:
        {"name", "title", "description", "wpm"}
    """
    out = []
    for name in BUILTIN:
        txt = _template_path(name)
        meta_path = os.path.join(TEMPLATES_DIR, name + ".json")
        if not os.path.isfile(txt):
            log.warning("Template missing: %s", txt)
            continue
        meta = {"name": name, "title": name.replace("_", " ").title(),
                "description": "", "wpm": 150}
        if os.path.isfile(meta_path):
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict):
                    meta.update({k: loaded[k] for k in
                                 ("title", "description", "wpm") if k in loaded})
            except (json.JSONDecodeError, IOError) as e:
                log.warning("Bad template metadata %s: %s", meta_path, e)
        out.append(meta)
    out.sort(key=lambda m: m["title"])
    return out


def load_template(name):
    """
    Returns the raw template text (with {placeholders} intact).

    Raises TemplateError for unknown names. Only built-in identifiers
    are accepted; arbitrary names never touch the filesystem.
    """
    if name not in BUILTIN:
        raise TemplateError("Unknown template: {0}".format(name))
    path = _template_path(name)
    if not os.path.isfile(path):
        raise TemplateError("Template file not found: {0}".format(path))
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except IOError as e:
        raise TemplateError("Could not read template: {0}".format(e)) from e


def fill_template(name, values):
    """
    Loads a template and substitutes {placeholders} using str.format.

    Unknown placeholders stay visible ({topic}) so the author notices
    them; pass only the keys you want replaced.
    """
    text = load_template(name)
    class _SafeDict(dict):
        def __missing__(self, key):
            return "{" + key + "}"
    return text.format_map(_SafeDict(values or {}))
