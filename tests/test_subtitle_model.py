"""
tests/test_subtitle_model.py — Tests for subtitle_model (Phase 7).

Pure-Python: time formats, SRT/VTT parsing/formatting round-trips,
merge_short, ordering, word→cue grouping.
"""

import pytest

from subtitle_model import (
    Cue,
    SubtitleError,
    enforce_order,
    format_srt,
    format_vtt,
    merge_short,
    parse_srt,
    parse_vtt,
    word_timestamps_to_cues,
)


class TestCue:
    def test_valid(self):
        c = Cue(1.0, 2.5, "Hello")
        assert c.start == 1.0 and c.end == 2.5 and c.text == "Hello"

    def test_strips_text(self):
        assert Cue(0, 1, "  hi  ").text == "hi"

    def test_rejects_inverted(self):
        with pytest.raises(SubtitleError, match="before start"):
            Cue(2.0, 1.0, "x")

    def test_equality(self):
        assert Cue(1, 2, "a") == Cue(1, 2, "a")
        assert Cue(1, 2, "a") != Cue(1, 2, "b")


class TestTimeFormats:
    def test_seconds_to_srt(self):
        assert Cue.seconds_to_srt(0.0) == "00:00:00,000"
        assert Cue.seconds_to_srt(1.5) == "00:00:01,500"
        assert Cue.seconds_to_srt(3661.25) == "01:01:01,250"

    def test_srt_to_seconds(self):
        assert Cue.srt_to_seconds("00:00:01,500") == 1.5
        assert Cue.srt_to_seconds("01:01:01,250") == 3661.25

    def test_vtt_dot_form_accepted(self):
        assert Cue.srt_to_seconds("00:00:01.500") == 1.5

    def test_bad_timestamp_raises(self):
        with pytest.raises(SubtitleError, match="Bad timestamp"):
            Cue.srt_to_seconds("1:2:3")

    def test_seconds_to_vtt(self):
        assert Cue.seconds_to_vtt(1.5) == "00:00:01.500"


class TestSrt:
    def test_format_parse_roundtrip(self):
        cues = [
            Cue(0.0, 1.5, "First line"),
            Cue(2.0, 3.75, "Second\nmulti-line"),
            Cue(10.0, 12.0, "Last"),
        ]
        content = format_srt(cues)
        parsed = parse_srt(content)
        assert parsed == cues

    def test_parse_bom_and_crlf(self):
        content = (
            "1\r\n00:00:01,000 --> 00:00:02,000\r\nHola\r\n\r\n"
        )
        parsed = parse_srt("\ufeff" + content)
        assert len(parsed) == 1
        assert parsed[0].text == "Hola"

    def test_parse_skips_bad_blocks(self):
        content = (
            "garbage line\n\n"
            "1\n00:00:01,000 --> 00:00:02,000\nGood\n\n"
        )
        parsed = parse_srt(content)
        assert len(parsed) == 1
        assert parsed[0].text == "Good"

    def test_parse_empty(self):
        assert parse_srt("") == []

    def test_indices_sequential_on_format(self):
        content = format_srt([Cue(0, 1, "a"), Cue(2, 3, "b")])
        assert "1\n" in content and "2\n" in content
        assert "3\n" not in content.split("00:00")[0]


class TestVtt:
    def test_format_parse_roundtrip(self):
        cues = [Cue(1.0, 2.5, "Vídeo con acentos")]
        content = format_vtt(cues)
        assert content.startswith("WEBVTT")
        parsed = parse_vtt(content)
        assert parsed == cues

    def test_parse_skips_header_and_notes(self):
        content = (
            "WEBVTT\n\nNOTE this is a comment\n\n"
            "00:01.000 --> 00:02.000\nReal cue\n"
        )
        parsed = parse_vtt(content)
        assert len(parsed) == 1
        assert parsed[0].text == "Real cue"


class TestMergeShort:
    def test_merges_tiny_fragments(self):
        cues = [
            Cue(0.0, 0.3, "Hel"),
            Cue(0.35, 0.6, "lo"),
            Cue(0.7, 3.0, "world"),
        ]
        merged = merge_short(cues)
        assert len(merged) == 2
        assert merged[0].text == "Hel lo"
        assert merged[0].end == 0.6
        assert merged[1].text == "world"

    def test_keeps_long_cues(self):
        cues = [Cue(0, 2.0, "long enough"), Cue(2.5, 4.0, "also long")]
        assert len(merge_short(cues)) == 2

    def test_gap_too_big_no_merge(self):
        cues = [Cue(0, 0.3, "a"), Cue(5.0, 6.0, "b")]
        assert len(merge_short(cues)) == 2

    def test_non_destructive(self):
        cues = [Cue(0, 0.3, "a"), Cue(0.4, 0.6, "b")]
        merge_short(cues)
        assert cues[0].end == 0.3  # input untouched
        assert cues[0].text == "a"


class TestEnforceOrder:
    def test_sorts_and_clips_overlaps(self):
        cues = [
            Cue(2.0, 4.0, "b"),
            Cue(0.0, 2.5, "a"),  # overlaps b
        ]
        fixed = enforce_order(cues)
        assert fixed[0].text == "a"
        assert fixed[0].end == 2.0
        assert fixed[1].text == "b"

    def test_drops_empty_after_clip(self):
        # A duplicated start makes the earlier cue clip to zero
        cues = [
            Cue(0.0, 3.0, "a"),
            Cue(0.0, 1.0, "b"),  # same start → 'a' clipped to 0.0-0.0
        ]
        fixed = enforce_order(cues)
        assert fixed == [Cue(0.0, 1.0, "b")]  # 'a' dropped as empty


class TestWordsToCues:
    def test_groups_up_to_ten_words(self):
        words = [
            {"word": f"w{i}", "start": i * 0.3, "end": i * 0.3 + 0.2}
            for i in range(25)
        ]
        cues = word_timestamps_to_cues(words)
        assert all(len(c.text.split()) <= 10 for c in cues)
        assert len(cues) == 3  # 25 words → 10 + 10 + 5

    def test_breaks_on_long_pause(self):
        words = [
            {"word": "a", "start": 0.0, "end": 0.2},
            {"word": "b", "start": 5.0, "end": 5.2},
        ]
        cues = word_timestamps_to_cues(words)
        assert len(cues) == 2

    def test_breaks_on_duration(self):
        words = [
            {"word": f"w{i}", "start": i * 0.3, "end": i * 0.3 + 0.2}
            for i in range(20)
        ]
        cues = word_timestamps_to_cues(words)
        assert all(c.end - c.start <= 4.0 for c in cues)

    def test_skips_empty_tokens(self):
        words = [{"word": "", "start": 0, "end": 0}]
        assert word_timestamps_to_cues(words) == []
