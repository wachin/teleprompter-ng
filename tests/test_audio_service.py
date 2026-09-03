"""
tests/test_audio_service.py — Unit tests for Phase 5 audio.

Pactl parsing and limiter math run without hardware; LevelMeter tests
open the REAL default microphone briefly and are skipped when none
is present (headless CI).
"""

import shutil

import pytest

from audio_service import default_microphone, list_microphones


class TestListMicrophones:
    """Enumeration via pactl (or sounddevice fallback)."""

    def test_returns_list_type(self):
        mics = list_microphones()
        assert isinstance(mics, list)
        for mic in mics:
            assert "id" in mic and "name" in mic

    def test_real_machine_has_mic(self):
        # Reference machine: PipeWire with a built-in analog mic
        if shutil.which("pactl") is None:
            pytest.skip("pactl not available")
        mics = list_microphones()
        assert mics, "no microphone found on a machine that has one"
        # No desktop monitors in the list
        for mic in mics:
            assert not mic["id"].endswith(".monitor")

    def test_pactl_parse(self, monkeypatch):
        import audio_service
        short = (
            "55\talsa_output.xx.monitor\tPipeWire\ts32le 2ch 48000Hz\tSUSPENDED\n"
            "56\talsa_input.pci-0000_00_1f.3.analog-stereo\tPipeWire\ts32le 2ch 48000Hz\tRUNNING\n"
        )
        detailed = (
            "Source #56\n"
            "\tState: RUNNING\n"
            "\tName: alsa_input.pci-0000_00_1f.3.analog-stereo\n"
            "\tdevice.description = \"Internal Audio Analog Stereo\"\n"
        )
        monkeypatch.setattr(
            audio_service, "_run_pactl",
            lambda args: short if args == ["list", "sources", "short"] else detailed,
        )
        mics = list_microphones()
        assert len(mics) == 1
        assert mics[0]["id"] == "alsa_input.pci-0000_00_1f.3.analog-stereo"
        assert mics[0]["name"] == "Internal Audio Analog Stereo"


class TestDefaultMicrophone:
    def test_default_is_first(self, monkeypatch):
        import audio_service
        monkeypatch.setattr(
            audio_service, "list_microphones",
            lambda: [{"id": "a", "name": "A"}],
        )
        assert default_microphone() == "a"

    def test_none_when_empty(self, monkeypatch):
        import audio_service
        monkeypatch.setattr(audio_service, "list_microphones", lambda: [])
        assert default_microphone() is None


class TestLevelMeter:
    """Real-stream tests; skipped without a microphone."""

    @pytest.fixture
    def qapp(self):
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])
        return app

    @pytest.fixture
    def meter(self, qapp):
        import audio_service
        mics = audio_service.list_microphones()
        if not mics:
            pytest.skip("no microphone")
        from audio_service import LevelMeter
        m = LevelMeter()
        yield m
        m.stop()

    def test_start_and_levels(self, meter, qapp):
        assert meter.start() is True
        assert meter.running
        # Collect some level updates from the real mic (room noise > 0)
        levels = []
        meter.level.connect(levels.append)
        end = qapp.processEvents() or __import__("time").monotonic() + 2.0
        import time
        while time.monotonic() < end and len(levels) < 5:
            qapp.processEvents()
            time.sleep(0.02)
        assert len(levels) >= 1
        assert all(0.0 <= v <= 1.0 for v in levels)

    def test_stop_is_idempotent(self, meter):
        meter.start()
        meter.stop()
        meter.stop()  # no crash
        assert not meter.running
