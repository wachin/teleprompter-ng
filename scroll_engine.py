"""
scroll_engine.py — Time-based script scrolling (Phase 3).

Drives TeleprompterOverlay from a QTimer + monotonic clock:

- position = elapsed / total (words-per-minute), NOT pixels per tick,
  so the scroll speed is independent of the refresh rate and stable
  over minutes (acceptance criterion).
- Supports countdown (0/3/5/10 s), pause/resume (clock accumulation),
  restart, manual nudge, and WPM changes mid-read.
- Emits Qt signals; the overlay never asks, it just receives
  position updates (loose coupling, testable without a display).
"""

import time

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from overlay_model import duration_seconds, progress_to_position


class ScrollEngine(QObject):
    """
    Computes scroll positions on a monotonic clock.

    Signals:
        position_changed(float) — new 0..1 position (emit ~30/s)
        countdown(int)           — remaining seconds during countdown
        state_changed(str)       — "idle" | "counting" | "running"
                                   | "paused" | "finished"
    """

    position_changed = pyqtSignal(float)
    countdown = pyqtSignal(int)
    state_changed = pyqtSignal(str)

    TICK_MS = 33  # ~30 Hz: smooth without flooding the painter

    def __init__(self, parent=None):
        super().__init__(parent)
        self._text = ""
        self._wpm = 150
        self._countdown_seconds = 3
        self._timer = QTimer(self)
        self._timer.setInterval(self.TICK_MS)
        self._timer.timeout.connect(self._tick)
        self._state = "idle"
        # Monotonic accumulators (seconds)
        self._elapsed = 0.0
        self._last_tick = None
        self._countdown_left = 0.0

    # ── Configuration ────────────────────────────────────────

    def set_script(self, text):
        """Loads the script; keeps position only if still valid."""
        self._text = text or ""
        if self._state == "running":
            # Re-derive elapsed so the pace stays honest at new length
            pass  # elapsed stays; position clamps via progress math
        self._emit_position()

    def set_wpm(self, wpm):
        """
        Changes speed mid-read: converts the current position to the
        new time base so no jump is perceived.

        The rescale applies while running AND while paused: _elapsed
        is always expressed in seconds of the CURRENT wpm, so changing
        it in pause must rebase elapsed or the position would jump on
        the next resume.
        """
        wpm = max(30, min(500, int(wpm)))
        old_total = duration_seconds(self._text, self._wpm)
        new_total = duration_seconds(self._text, wpm)
        if self._elapsed > 0 and old_total > 0 and new_total > 0:
            # Keep the same reading position, rescale elapsed
            self._elapsed = self._elapsed * new_total / old_total
        self._wpm = wpm
        self._emit_position()

    def set_countdown(self, seconds):
        self._countdown_seconds = max(0, int(seconds))

    def wpm(self):
        return self._wpm

    # ── State ─────────────────────────────────────────────────

    def state(self):
        return self._state

    def position(self):
        return progress_to_position(self._text, self._elapsed, self._wpm)

    def total_seconds(self):
        return duration_seconds(self._text, self._wpm)

    # ── Controls ──────────────────────────────────────────────

    def start(self):
        """Starts reading (with countdown when configured)."""
        if self._state in ("running", "counting"):
            return
        if not self._text.strip():
            return
        if self.position() >= 1.0:
            # Finished scripts restart from the top (Roadmap: restart)
            self._elapsed = 0.0
        if self._countdown_seconds > 0:
            self._state = "counting"
            self._countdown_left = float(self._countdown_seconds)
            self._last_tick = time.monotonic()
            self.countdown.emit(int(self._countdown_left))
            self.state_changed.emit(self._state)
            self._timer.start()
        else:
            self._begin_running()

    def pause(self):
        """Pauses; elapsed time is frozen exactly."""
        if self._state in ("running", "counting"):
            self._accumulate()
            self._state = "paused"
            self._timer.stop()
            self.state_changed.emit(self._state)

    def resume(self):
        """Resumes from pause, resuming the countdown if it was active."""
        if self._state != "paused":
            return
        self._last_tick = time.monotonic()
        if self._countdown_left > 0:
            self._state = "counting"
            self._timer.start()
        else:
            self._begin_running()
        self.state_changed.emit(self._state)

    def toggle(self):
        if self._state in ("running", "counting"):
            self.pause()
        else:
            self.resume() if self._state == "paused" else self.start()

    def restart(self):
        """Back to the top, stopped (matches legacy R/Home behavior)."""
        self._timer.stop()
        self._state = "idle"
        self._elapsed = 0.0
        self._countdown_left = 0.0
        self.state_changed.emit(self._state)
        self._emit_position()

    def nudge(self, delta_position):
        """
        Manual scroll by a fraction of the script (mouse wheel/arrows).

        Works in any state; converts to seconds so resume keeps pace.
        """
        if not self._text.strip():
            return
        total = self.total_seconds()
        if total <= 0:
            return
        self._elapsed = max(
            0.0, min(total, self._elapsed + delta_position * total)
        )
        self._emit_position()

    def jump_to(self, position):
        """Sets the position directly (paragraph markers)."""
        if not self._text.strip():
            return
        total = self.total_seconds()
        self._elapsed = max(0.0, min(total, position * total))
        self._emit_position()

    # ── Internals ─────────────────────────────────────────────

    def _begin_running(self):
        self._state = "running"
        self._countdown_left = 0.0
        self._last_tick = time.monotonic()
        self.state_changed.emit(self._state)
        self._timer.start()

    def _accumulate(self):
        """Adds wall time since the last tick to _elapsed (monotonic)."""
        if self._last_tick is not None:
            self._elapsed += time.monotonic() - self._last_tick
            self._last_tick = None

    def _tick(self):
        now = time.monotonic()
        delta = now - self._last_tick if self._last_tick is not None else 0.0
        self._last_tick = now

        if self._state == "counting":
            self._countdown_left -= delta
            if self._countdown_left <= 0:
                self._begin_running()
            else:
                self.countdown.emit(int(self._countdown_left + 0.999))
            return

        if self._state == "running":
            self._elapsed += delta
            if self._elapsed >= self.total_seconds():
                self._elapsed = self.total_seconds()
                self._state = "finished"
                self._timer.stop()
                self.state_changed.emit(self._state)
            self._emit_position()

    def _emit_position(self):
        self.position_changed.emit(self.position())
