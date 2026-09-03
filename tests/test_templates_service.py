"""
tests/test_templates_service.py — Tests for script templates (Phase 1).

Verifies the six built-in templates ship, load, and fill correctly.
"""

import pytest

from templates_service import (
    BUILTIN,
    TemplateError,
    available_templates,
    fill_template,
    load_template,
)


class TestAvailable:
    """Template discovery."""

    def test_six_builtins(self):
        names = {t["name"] for t in available_templates()}
        assert names == set(BUILTIN)
        assert len(names) == 6

    def test_metadata_complete(self):
        for t in available_templates():
            assert t["title"], t
            assert t["description"], t
            assert isinstance(t["wpm"], int) and t["wpm"] > 0, t

    def test_sorted_by_title(self):
        titles = [t["title"] for t in available_templates()]
        assert titles == sorted(titles)

    def test_expected_titles(self):
        titles = {t["title"] for t in available_templates()}
        assert {"Tutorial", "Presentation", "Class / Lesson",
                "News segment", "Product review", "Advertisement"} == titles


class TestLoad:
    """Raw template loading."""

    def test_load_each(self):
        for name in BUILTIN:
            text = load_template(name)
            assert len(text) > 100, name  # real content, not a stub

    def test_load_unknown(self):
        with pytest.raises(TemplateError, match="Unknown"):
            load_template("does_not_exist")

    def test_load_rejects_path_tricks(self):
        with pytest.raises(TemplateError, match="Unknown"):
            load_template("../../etc/passwd")

    def test_templates_have_placeholders(self):
        for name in BUILTIN:
            assert "{" in load_template(name), name


class TestFill:
    """Placeholder substitution."""

    def test_fill_replaces(self):
        filled = fill_template("ad", {
            "title": "My Ad", "pain_point": "slow Wi-Fi",
            "product": "SpeedBox", "struggle": "stream in 4K",
            "main_benefit": "watch without buffering",
            "special_offer": "20% off", "deadline": "Sunday",
        })
        assert "SpeedBox" in filled
        assert "{product}" not in filled
        assert "20% off" in filled

    def test_fill_keeps_unknown_placeholders(self):
        filled = fill_template("tutorial", {"author": "Ana"})
        assert "{author}" not in filled
        assert "{topic}" in filled  # not provided → stays visible

    def test_fill_empty_values(self):
        filled = fill_template("tutorial", {})
        assert "{title}" in filled and "{author}" in filled

    def test_fill_with_braces_in_values(self):
        # A value containing braces must not break str.format_map
        filled = fill_template("ad", {"product": "{weird}"})
        assert "{weird}" in filled
