"""
tests/test_scroll_engine.py — Tests for ScrollEngine (Phase 3).

Uses a QApplication (no display needed) and REAL waiting for short
intervals: the engine is monotonic-clock based, so a 0.3 s run must
advance ~0.3 s — the acceptance test for refresh-rate independence.
Longer stability (minutes) is a manual test documented in PHASE-3.md.
"""

import time

import pytest
from PyQt6.QtWidgets import QApplication

from scroll_engine import ScrollEngine


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


TEXT_60S = " ".join(["word"] * 150)  # 150 words @ 150 wpm = 60 s


@pytest.fixture
def engine(qapp):
    e = ScrollEngine()
    e.set_script(TEXT_60S)
    yield e
    e.restart()


class TestBasicFlow:
    """start / pause / resume / restart without countdown."""

    def test_start_runs(self, engine, qapp):
        engine.set_countdown(0)
        engine.start()
        assert engine.state() == "running"
        end = time.monotonic() + 0.5
        while time.monotonic() < end:
            qapp.processEvents()
        engine.pause()
        pos = engine.position()
        assert 0.0 < pos < 0.05, pos  # ~0.5 s of 60 s
        engine.restart()

    def test_pause_freezes(self, engine, qapp):
        engine.set_countdown(0)
        engine.start()
        end = time.monotonic() + 0.3
        while time.monotonic() < end:
            qapp.processEvents()
        engine.pause()
        frozen = engine.position()
        time.sleep(0.2)
        qapp.processEvents()
        assert engine.position() == frozen
        assert engine.state() == "paused"

    def test_resume_continues(self, engine, qapp):
        engine.set_countdown(0)
        engine.start()
        end = time.monotonic() + 0.2
        while time.monotonic() < end:
            qapp.processEvents()
        engine.pause()
        before = engine.position()
        engine.resume()
        assert engine.state() == "running"
        end = time.monotonic() + 0.2
        while time.monotonic() < end:
            qapp.processEvents()
        assert engine.position() > before

    def test_restart_zeroes(self, engine):
        engine.set_countdown(0)
        engine.start()
        engine.restart()
        assert engine.state() == "idle"
        assert engine.position() == 0.0

    def test_empty_script_wont_start(self, engine):
        engine.set_script("")
        engine.set_countdown(0)
        engine.start()
        assert engine.state() == "idle"


class TestCountdown:
    """Configurable countdown: 0/3/5/10 seconds."""

    def test_countdown_zero_starts_immediately(self, engine):
        engine.set_countdown(0)
        engine.start()
        assert engine.state() == "running"
        engine.restart()

    def test_countdown_emits_and_delays(self, engine, qapp):
        engine.set_countdown(1)
        seen = []
        engine.countdown.connect(lambda s: seen.append(s))
        engine.start()
        assert engine.state() == "counting"
        end = time.monotonic() + 1.5
        while time.monotonic() < end and engine.state() == "counting":
            qapp.processEvents()
        assert engine.state() == "running"
        assert seen, "no countdown signals emitted"
        assert seen[0] == 1
        engine.restart()

    def test_pause_during_countdown(self, engine, qapp):
        engine.set_countdown(3)
        engine.start()
        engine.pause()
        assert engine.state() == "paused"
        engine.resume()
        assert engine.state() == "counting"
        engine.restart()


class TestSpeedAndJump:
    """WPM changes, manual nudge, jumps, finish."""

    def test_set_wpm_rescales_position(self, engine, qapp):
        engine.set_countdown(0)
        engine.start()
        end = time.monotonic() + 0.2
        while time.monotonic() < end:
            qapp.processEvents()
        pos_before = engine.position()
        engine.set_wpm(75)  # half speed → same position, doubled elapsed
        assert engine.wpm() == 75
        assert abs(engine.position() - pos_before) < 0.02  # no jump felt
        engine.restart()

    def test_nudge_forward_back(self, engine):
        engine.set_countdown(0)
        engine.nudge(0.5)
        assert 0.49 <= engine.position() <= 0.51
        engine.nudge(-0.25)
        assert 0.24 <= engine.position() <= 0.26

    def test_nudge_clamps_at_bounds(self, engine):
        engine.nudge(5.0)
        assert engine.position() == 1.0
        engine.nudge(-10.0)
        assert engine.position() == 0.0

    def test_jump_to(self, engine):
        engine.jump_to(0.25)
        assert abs(engine.position() - 0.25) < 0.01

    def test_finished_at_end(self, engine, qapp):
        engine.set_countdown(0)
        engine.jump_to(0.999)
        engine.start()
        end = time.monotonic() + 1.0
        while time.monotonic() < end and engine.state() == "running":
            qapp.processEvents()
        assert engine.state() == "finished"
        assert engine.position() == 1.0

    def test_restart_after_finish(self, engine, qapp):
        engine.set_countdown(0)
        engine.jump_to(1.0)
        engine.start()  # finished position → restarts from top
        assert engine.state() == "running"
        assert engine.position() < 0.05
        engine.restart()


class TestStability:
    """Acceptance: speed independent of the refresh rate."""

    def test_monotonic_pace(self, engine, qapp):
        """Position after ~0.6 s matches words/minute, not tick count."""
        engine.set_countdown(0)
        engine.start()
        t0 = time.monotonic()
        while time.monotonic() - t0 < 0.6:
            qapp.processEvents()
        elapsed = time.monotonic() - t0
        engine.pause()
        # Expected: elapsed/60 of the script; tolerate timer jitter
        expected = elapsed / 60.0
        assert abs(engine.position() - expected) < 0.03, (
            engine.position(), expected,
        )
        engine.restart()
