"""
text_import.py — Script import from other formats (Phase 1).

Extracts plain UTF-8 text from .md, .html, and .docx using only the
standard library, so no extra dependency is required (ROADMAP 4.x:
add dependencies only when necessary).

- .txt/.md: returned as-is (md keeps its syntax, it is readable text).
- .html: tags stripped with html.parser, entities decoded, block
  elements turned into newlines.
- .docx: a .docx is a zip with word/document.xml; the text runs
  (<w:t>) are joined and paragraph breaks (<w:p>) preserved.
"""

import os
import re
import zipfile
from html.parser import HTMLParser
from typing import ClassVar

from logging_setup import get_logger

log = get_logger("Import")

SUPPORTED = (".txt", ".md", ".html", ".htm", ".docx")


class UnsupportedFormat(Exception):
    """The file extension is not supported."""


class _HTMLTextExtractor(HTMLParser):
    """Collects visible text, adding newlines on block elements."""

    _BLOCKS: ClassVar[set[str]] = {
        "p", "div", "br", "li", "tr", "section", "article",
        "h1", "h2", "h3", "h4", "h5", "h6",
    }

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.chunks = []
        self._skip = 0  # inside script/style/head

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "head"):
            self._skip += 1
        elif tag in self._BLOCKS:
            self.chunks.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "head"):
            self._skip = max(0, self._skip - 1)
        elif tag in self._BLOCKS:
            self.chunks.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self.chunks.append(data)

    def text(self):
        out = "".join(self.chunks)
        # Collapse whitespace per line and merge consecutive blank lines
        # (block tags emit a newline on open AND close).
        lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in out.splitlines()]
        result = []
        blank = False
        for ln in lines:
            if not ln:
                blank = True
                continue
            if result and blank:
                result.append("")  # single blank line between paragraphs
            blank = False
            result.append(ln)
        return "\n".join(result).strip("\n")


def _html_to_text(raw):
    parser = _HTMLTextExtractor()
    try:
        parser.feed(raw)
        parser.close()
    except Exception as e:
        raise UnsupportedFormat(f"Malformed HTML: {e}") from e
    return parser.text()


def _docx_to_text(raw_bytes):
    """Reads word/document.xml from the .docx zip and extracts <w:t> runs."""
    try:
        with zipfile.ZipFile(__import__("io").BytesIO(raw_bytes)) as z:
            xml = z.read("word/document.xml").decode("utf-8", errors="replace")
    except (zipfile.BadZipFile, KeyError) as e:
        raise UnsupportedFormat(
            f"This does not look like a valid .docx file: {e}"
        ) from e

    # w:p → paragraph break; w:t → text run; w:tab → tab
    xml = re.sub(r"<w:tab[^>]*/>", "\t", xml)
    xml = re.sub(r"<w:br[^>]*/>", "\n", xml)
    paragraphs = re.split(r"</w:p>", xml)
    lines = []
    for para in paragraphs:
        runs = re.findall(r"<w:t[^>]*>(.*?)</w:t>", para, flags=re.DOTALL)
        line = "".join(runs)
        # Decode basic XML entities left in the runs
        line = (line.replace("&amp;", "&").replace("&lt;", "<")
                    .replace("&gt;", ">").replace("&quot;", '"')
                    .replace("&apos;", "'"))
        lines.append(line)
    # Drop trailing empty paragraphs from the split
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines).strip("\n")


def import_file(path):
    """
    Reads a script file and returns plain UTF-8 text.

    Raises UnsupportedFormat for unknown extensions and OSError for
    unreadable files. Encoding fallback: UTF-8 first, then latin-1
    (common with legacy .txt files) so users are not blocked.
    """
    ext = os.path.splitext(path)[1].lower()
    if ext not in SUPPORTED:
        raise UnsupportedFormat(
            "Unsupported format '{0}'. Supported: {1}".format(
                ext, ", ".join(SUPPORTED)
            )
        )

    if ext == ".docx":
        with open(path, "rb") as f:
            return _docx_to_text(f.read())

    raw = None
    last_err = None
    for encoding in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            with open(path, encoding=encoding) as f:
                raw = f.read()
            break
        except UnicodeDecodeError as e:
            last_err = e
    if raw is None:
        raise last_err

    if ext in (".html", ".htm"):
        return _html_to_text(raw)
    # .txt / .md
    return raw.strip("\n")


def word_count(text):
    """Number of words (whitespace-separated tokens)."""
    return len(text.split())


def estimated_duration_seconds(text, wpm=150):
    """
    Estimated speaking duration in seconds at the given WPM.

    Empty text → 0. Rounds to the nearest second.
    """
    if not text or wpm <= 0:
        return 0
    words = word_count(text)
    return round(words / wpm * 60)
