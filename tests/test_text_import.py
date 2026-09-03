"""
tests/test_text_import.py — Tests for text_import.py (Phase 1).

Covers .txt/.md passthrough, .html stripping, .docx extraction,
encoding fallbacks, and WPM/duration helpers.
"""

import pytest

from text_import import (
    SUPPORTED,
    UnsupportedFormat,
    estimated_duration_seconds,
    import_file,
    word_count,
)


class TestTxt:
    """Plain text passthrough."""

    def test_txt(self, tmp_path):
        f = tmp_path / "s.txt"
        f.write_text("hello\nworld\n", encoding="utf-8")
        assert import_file(str(f)) == "hello\nworld"

    def test_txt_utf8(self, tmp_path):
        f = tmp_path / "s.txt"
        f.write_text("¡ñandú comía allí! 🎉", encoding="utf-8")
        assert import_file(str(f)) == "¡ñandú comía allí! 🎉"

    def test_latin1_fallback(self, tmp_path):
        f = tmp_path / "s.txt"
        f.write_bytes("café ño".encode("latin-1"))
        assert import_file(str(f)) == "café ño"

    def test_md_passthrough(self, tmp_path):
        f = tmp_path / "s.md"
        f.write_text("# Title\n\n- bullet\n", encoding="utf-8")
        assert import_file(str(f)) == "# Title\n\n- bullet"


class TestHtml:
    """HTML → plain text."""

    def test_simple(self, tmp_path):
        f = tmp_path / "s.html"
        f.write_text("<html><body><p>Hello</p><p>World</p></body></html>",
                     encoding="utf-8")
        # Paragraphs become blank-line-separated (script convention)
        assert import_file(str(f)) == "Hello\n\nWorld"

    def test_skips_script_and_style(self, tmp_path):
        f = tmp_path / "s.html"
        f.write_text(
            "<html><head><style>p{color:red}</style></head>"
            "<body><script>alert(1)</script><p>Visible</p></body></html>",
            encoding="utf-8",
        )
        text = import_file(str(f))
        assert "Visible" in text
        assert "color" not in text
        assert "alert" not in text

    def test_entities_decoded(self, tmp_path):
        f = tmp_path / "s.html"
        f.write_text("<p>caf&eacute; &amp; &lt;tag&gt;</p>", encoding="utf-8")
        assert import_file(str(f)) == "café & <tag>"

    def test_headings_break_lines(self, tmp_path):
        f = tmp_path / "s.htm"
        f.write_text("<h1>One</h1><h2>Two</h2>", encoding="utf-8")
        assert import_file(str(f)) == "One\n\nTwo"


class TestDocx:
    """DOCX → plain text (stdlib zip + regex extraction)."""

    def _make_docx(self, path, paragraphs):
        """Builds a minimal but valid .docx with the given paragraphs."""
        import zipfile
        ns = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"')
        body = "".join(
            f"<w:p><w:r><w:t xml:space=\"preserve\">{t}</w:t></w:r></w:p>"
            for t in paragraphs
        )
        doc = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<w:document {ns}><w:body>{body}<w:p/></w:body></w:document>'
        )
        with zipfile.ZipFile(path, "w") as z:
            z.writestr("[Content_Types].xml", "<?xml version=\"1.0\"?><Types/>")
            z.writestr("word/document.xml", doc)

    def test_paragraphs(self, tmp_path):
        f = tmp_path / "s.docx"
        self._make_docx(f, ["First paragraph.", "Second one!"])
        assert import_file(str(f)) == "First paragraph.\nSecond one!"

    def test_accents(self, tmp_path):
        f = tmp_path / "s.docx"
        self._make_docx(f, ["Días — ñandú"])
        assert import_file(str(f)) == "Días — ñandú"

    def test_entities_in_docx(self, tmp_path):
        f = tmp_path / "s.docx"
        self._make_docx(f, ["A &amp; B &lt;tag&gt;"])
        assert import_file(str(f)) == "A & B <tag>"

    def test_invalid_docx(self, tmp_path):
        f = tmp_path / "s.docx"
        f.write_bytes(b"not a zip file at all")
        with pytest.raises(UnsupportedFormat, match=r"valid \.docx"):
            import_file(str(f))


class TestUnsupported:
    """Unknown formats rejected with a clear message."""

    def test_pdf_rejected(self, tmp_path):
        f = tmp_path / "s.pdf"
        f.write_bytes(b"%PDF-1.4")
        with pytest.raises(UnsupportedFormat, match="Supported"):
            import_file(str(f))

    def test_supported_list(self):
        for ext in SUPPORTED:
            assert ext.startswith(".")


class TestWpm:
    """Word count and duration estimation."""

    def test_word_count(self):
        assert word_count("") == 0
        assert word_count("one two three") == 3
        assert word_count("  spaced   out  ") == 2

    def test_duration_zero(self):
        assert estimated_duration_seconds("", 150) == 0
        assert estimated_duration_seconds("text", 0) == 0

    def test_duration_basic(self):
        # 150 words at 150 wpm = 60 s
        text = " ".join(["w"] * 150)
        assert estimated_duration_seconds(text, 150) == 60

    def test_duration_other_wpm(self):
        # 300 words at 200 wpm = 90 s
        text = " ".join(["w"] * 300)
        assert estimated_duration_seconds(text, 200) == 90
