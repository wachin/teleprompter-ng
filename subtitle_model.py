"""
subtitle_model.py — Subtitle cues, SRT/WebVTT I/O (Phase 7).

A Cue is one subtitle line with a time range. This module is pure
Python (no Qt, no vosk): parsing, formatting, merging short cues,
and time math — fully unit-testable and reusable by the burn-in
(Phase 8) and export (Phase 10).
"""

import re

from logging_setup import get_logger

log = get_logger("Subtitles")


class SubtitleError(Exception):
    """Subtitle problem with a user-facing message."""


class Cue:
    """One subtitle: [start_s, end_s) with text."""

    __slots__ = ("end", "start", "text")

    def __init__(self, start, end, text):
        self.start = float(start)
        self.end = float(end)
        self.text = str(text).strip()
        if self.end < self.start:
            raise SubtitleError(
                f"Cue end ({self.end:.2f}) before start ({self.start:.2f})"
            )

    def __repr__(self):  # pragma: no cover
        return f"Cue({self.start:.2f}-{self.end:.2f}, {self.text[:30]!r})"

    def __eq__(self, other):
        return (
            isinstance(other, Cue)
            and abs(self.start - other.start) < 1e-6
            and abs(self.end - other.end) < 1e-6
            and self.text == other.text
        )

    # ── Time formats ────────────────────────────────────────

    @staticmethod
    def seconds_to_srt(t):
        """1.5 → '00:00:01,500'"""
        t = max(0.0, t)
        ms = round(t * 1000)
        h, rem = divmod(ms, 3600_000)
        m, rem = divmod(rem, 60_000)
        s, ms = divmod(rem, 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    @staticmethod
    def srt_to_seconds(text):
        """
        '00:00:01,500' → 1.5. Also accepts the VTT dot form and the
        short VTT 'MM:SS.mmm' form.
        """
        t = text.strip()
        m = re.fullmatch(r"(\d{2,}):(\d{2}):(\d{2})[.,](\d{3})", t)
        if not m:
            m = re.fullmatch(r"(\d{2}):(\d{2})[.,](\d{3})", t)  # VTT short
        if not m:
            raise SubtitleError(f"Bad timestamp: {text!r}")
        parts = [int(g) for g in m.groups()]
        if len(parts) == 4:
            h, mi, s, ms = parts
        else:
            mi, s, ms = parts
            h = 0
        return h * 3600 + mi * 60 + s + ms / 1000.0

    @staticmethod
    def seconds_to_vtt(t):
        """1.5 → '00:00:01.500'"""
        return Cue.seconds_to_srt(t).replace(",", ".")


# ─────────────────────────────────────────────────────────────
# SRT
# ─────────────────────────────────────────────────────────────

_SRT_CUE_RE = re.compile(
    r"(\d+)\s*\n"                                    # index
    r"(\d{2,}:\d{2}:\d{2}[,.]\d{3})\s*-->\s*"        # start
    r"(\d{2,}:\d{2}:\d{2}[,.]\d{3})[^\n]*\n"         # end (+ optional settings)
    r"((?:.*\n?)*)",                                 # text lines
)


def parse_srt(content):
    """SRT text → [Cue]. Tolerant: BOM, blank lines, missing indices."""
    cues = []
    normalized = content.lstrip("\ufeff").replace("\r\n", "\n").strip()
    if not normalized:
        return []
    blocks = re.split(r"\n\s*\n", normalized)
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        lines = block.split("\n")
        # Skip a leading index line when present
        if re.fullmatch(r"\d+", lines[0].strip()):
            lines = lines[1:]
        if not lines:
            continue
        timing = lines[0]
        m = re.match(
            r"(\S+)\s*-->\s*(\S+)", timing,
        )
        if not m:
            log.warning("Skipping cue with bad timing: %r", timing)
            continue
        try:
            start = Cue.srt_to_seconds(m.group(1))
            end = Cue.srt_to_seconds(m.group(2))
        except SubtitleError:
            log.warning("Skipping cue with bad times: %r", timing)
            continue
        text = "\n".join(lines[1:]).strip()
        if text:
            cues.append(Cue(start, end, text))
    return cues


def format_srt(cues):
    """[Cue] → SRT text with sequential indices."""
    blocks = []
    for i, cue in enumerate(cues, start=1):
        blocks.append(
            f"{i}\n{Cue.seconds_to_srt(cue.start)} --> {Cue.seconds_to_srt(cue.end)}\n{cue.text}"
        )
    return "\n\n".join(blocks) + "\n"


# ─────────────────────────────────────────────────────────────
# WebVTT
# ─────────────────────────────────────────────────────────────

def parse_vtt(content):
    """WebVTT text → [Cue] ('WEBVTT' header and NOTE blocks skipped)."""
    normalized = content.lstrip("\ufeff").replace("\r\n", "\n")
    if normalized.startswith("WEBVTT"):
        # Drop the header line (and any header metadata before a blank)
        normalized = normalized.split("\n", 1)[1]
    cues = []
    blocks = re.split(r"\n\s*\n", normalized.strip())
    for block in blocks:
        lines = block.strip().split("\n")
        if not lines or lines[0].strip().startswith(("WEBVTT", "NOTE")):
            continue
        # Optional cue id line before the timing line
        if "-->" not in lines[0]:
            lines = lines[1:]
        if not lines:
            continue
        m = re.match(r"(\S+)\s*-->\s*(\S+)", lines[0] if lines else "")
        if not m:
            continue
        try:
            start = Cue.srt_to_seconds(m.group(1))
            end = Cue.srt_to_seconds(m.group(2))
        except SubtitleError:
            continue
        text = "\n".join(lines[1:]).strip()
        if text:
            cues.append(Cue(start, end, text))
    return cues


def format_vtt(cues):
    """[Cue] → WebVTT text."""
    blocks = ["00:00:00.000 --> 00:00:00.001\n"] if not cues else []
    header = "WEBVTT\n"
    for cue in cues:
        blocks.append(
            f"{Cue.seconds_to_vtt(cue.start)} --> {Cue.seconds_to_vtt(cue.end)}\n{cue.text}"
        )
    return header + ("\n\n".join(blocks) + "\n" if blocks else "\n")


# ─────────────────────────────────────────────────────────────
# Editing helpers
# ─────────────────────────────────────────────────────────────

def merge_short(cues, min_duration=0.8, max_gap=0.6):
    """
    Merges cues shorter than min_duration into their neighbor when
    the gap is under max_gap (Vosk emits many tiny fragments).

    The rule looks at the INCOMING cue: a tiny fragment joins the
    accumulator regardless of the accumulator's own length, so a
    chain of fragments collapses into one cue.
    """
    if not cues:
        return []
    result = [Cue(cues[0].start, cues[0].end, cues[0].text)]
    for cue in cues[1:]:
        prev = result[-1]
        gap = cue.start - prev.end
        tiny = cue.end - cue.start < min_duration
        if tiny and gap <= max_gap:
            prev.end = cue.end
            prev.text = (prev.text + " " + cue.text).strip()
        else:
            result.append(Cue(cue.start, cue.end, cue.text))
    return result


def enforce_order(cues):
    """Sorts by start and drops overlaps (end clipped to next start)."""
    ordered = sorted(cues, key=lambda c: c.start)
    for i in range(len(ordered) - 1):
        if ordered[i].end > ordered[i + 1].start:
            ordered[i].end = ordered[i + 1].start
    return [c for c in ordered if c.end > c.start]


def word_timestamps_to_cues(words):
    """
    Converts Vosk word tokens [{'word','start','end'}] into cues of
    up to ~10 words that never exceed ~4 s each.
    """
    cues = []
    current = None
    for w in words:
        token = w.get("word", "").strip()
        if not token:
            continue
        start = float(w.get("start", 0.0))
        end = float(w.get("end", start))
        if current is None:
            current = {"text": [token], "start": start, "end": end}
        elif (start - current["end"] > 1.0
                or len(current["text"]) >= 10
                or end - current["start"] > 4.0):
            cues.append(Cue(current["start"], current["end"],
                           " ".join(current["text"])))
            current = {"text": [token], "start": start, "end": end}
        else:
            current["text"].append(token)
            current["end"] = max(current["end"], end)
    if current is not None:
        cues.append(Cue(current["start"], current["end"],
                        " ".join(current["text"])))
    return cues
