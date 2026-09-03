"""
tests/test_remote_server.py — Tests for the Phase 4 remote server.

Covers: pairing token (correct/wrong code, unpaired rejection),
per-client rate limiting, command effects on a real ScrollEngine,
status snapshots, and QR/pairing URL formats — all via the
flask-socketio test client (no real sockets).
"""

import pytest
from PyQt6.QtWidgets import QApplication

from remote_server import RemoteServer, _RateLimiter
from scroll_engine import ScrollEngine

SCRIPT = " ".join(["word"] * 150)  # 60 s @ 150 wpm


class FakeTeleprompter:
    """The minimum surface RemoteServer expects (CameraView-like)."""

    def __init__(self):
        self.engine = ScrollEngine()
        self.engine.set_script(SCRIPT)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def tp(qapp):
    return FakeTeleprompter()


@pytest.fixture
def server(tp):
    srv = RemoteServer(tp, port=5099)
    yield srv
    srv.stop()


@pytest.fixture
def client(server):
    return server.socketio.test_client(server.app)


def _received(client, name):
    return [r for r in client.get_received() if r["name"] == name]


class TestRateLimiter:
    """Unit tests of the sliding-window limiter."""

    def test_allows_up_to_limit(self):
        lim = _RateLimiter(3, 60.0)
        assert all(lim.allow("a") for _ in range(3))
        assert not lim.allow("a")

    def test_other_clients_unaffected(self):
        lim = _RateLimiter(1, 60.0)
        assert lim.allow("a")
        assert not lim.allow("a")
        assert lim.allow("b")

    def test_window_slides(self):
        lim = _RateLimiter(1, 0.05)  # 50 ms window
        assert lim.allow("a")
        assert not lim.allow("a")
        import time
        time.sleep(0.06)
        assert lim.allow("a")


class TestPairing:
    """6-digit code security model."""

    def test_token_is_six_digits(self, server):
        assert server.pairing_token.isdigit()
        assert len(server.pairing_token) == 6

    def test_unpaired_cannot_command(self, server, client, tp):
        client.emit("toggle")
        received = client.get_received()
        errors = [r for r in received if r["name"] == "error"]
        assert errors, "no rejection for unpaired command"
        assert tp.engine.state() == "idle"

    def test_wrong_code_rejected(self, server, client):
        client.emit("pair", "000000")  # 1/1e6 chance of matching
        received = client.get_received()
        paired = [r for r in received if r["name"] == "paired"]
        assert paired and paired[0]["args"][0]["ok"] is False

    def test_correct_code_pairs(self, server, client, tp):
        client.get_received()  # drain
        client.emit("pair", server.pairing_token)
        paired = [r for r in client.get_received() if r["name"] == "paired"]
        assert paired and paired[0]["args"][0]["ok"] is True

        # Now commands work
        client.emit("toggle")
        tp.engine.set_countdown(0)
        received = client.get_received()
        # No error events
        assert not [r for r in received if r["name"] == "error"]

    def test_pairing_disabled_allows_all(self, tp):
        srv = RemoteServer(tp, port=5098, pairing_enabled=False)
        try:
            assert srv.pairing_token is None
            client = srv.socketio.test_client(srv.app)
            client.get_received()
            client.emit("restart")
            assert not [r for r in client.get_received() if r["name"] == "error"]
        finally:
            srv.stop()

    def test_regenerate_invalidates_sessions(self, server, client):
        client.emit("pair", server.pairing_token)
        paired = [r for r in client.get_received() if r["name"] == "paired"]
        assert paired[0]["args"][0]["ok"] is True
        server.regenerate_token()
        client.emit("toggle")
        assert [r for r in client.get_received() if r["name"] == "error"]


class TestCommands:
    """Paired command effects on the real engine."""

    @pytest.fixture(autouse=True)
    def paired(self, server, client):
        client.get_received()
        client.emit("pair", server.pairing_token)
        client.get_received()
        yield

    def test_toggle_starts_and_pauses(self, server, client, tp):
        tp.engine.set_countdown(0)
        client.emit("toggle")
        client.get_received()
        assert tp.engine.state() == "running"
        client.emit("toggle")
        client.get_received()
        assert tp.engine.state() == "paused"

    def test_wpm_up_down(self, server, client, tp):
        assert tp.engine.wpm() == 150
        client.emit("wpm_up")
        client.get_received()
        assert tp.engine.wpm() == 160
        client.emit("wpm_down")
        client.emit("wpm_down")
        client.get_received()
        assert tp.engine.wpm() == 140

    def test_wpm_bounds(self, server, client, tp):
        tp.engine.set_wpm(500)
        client.emit("wpm_up")
        client.get_received()
        assert tp.engine.wpm() == 500
        tp.engine.set_wpm(30)
        client.emit("wpm_down")
        client.get_received()
        assert tp.engine.wpm() == 30

    def test_restart(self, server, client, tp):
        tp.engine.jump_to(0.5)
        client.emit("restart")
        client.get_received()
        assert tp.engine.position() == 0.0

    def test_jump_clamps(self, server, client, tp):
        client.emit("jump", 0.25)
        client.get_received()
        assert abs(tp.engine.position() - 0.25) < 0.01
        client.emit("jump", 5)      # clamped to 1.0
        client.emit("jump", "junk")  # ignored, no crash
        client.get_received()
        assert tp.engine.position() == 1.0


class TestRateLimitOnCommands:
    """The guard enforces the limit after pairing."""

    def test_flood_rejected(self, server, client, tp):
        client.get_received()
        client.emit("pair", server.pairing_token)
        client.get_received()
        tp.engine.set_countdown(0)

        errors = 0
        for _ in range(15):  # limit is 10 / 5 s
            client.emit("restart")
            received = client.get_received()
            errors += len([r for r in received if r["name"] == "error"])
        assert errors >= 5, "flood was not rate limited"


class TestStatusAndQr:
    """Read-only surfaces."""

    def test_status_snapshot(self, server, tp):
        tp.engine.set_countdown(0)
        tp.engine.jump_to(0.5)
        status = server.status()
        assert status["position"] == 0.5
        assert status["wpm"] == 150
        assert status["pairing_required"] is True
        assert status["state"] == "idle"

    def test_status_legacy_teleprompter(self):
        """The legacy read-mode object still yields a snapshot."""
        class Legacy:
            is_running = True
            wpm = 130
            countdown_active = False
        srv = RemoteServer(Legacy(), port=5097)
        try:
            status = srv.status()
            assert status["is_running"] is True
            assert status["wpm"] == 130
        finally:
            srv.stop()

    def test_qr_data_contains_token(self, server):
        assert server.pairing_token in server.qr_data()
        assert server.qr_data().startswith("http://")

    def test_status_broadcast_on_command(self, server, client, tp):
        client.get_received()
        client.emit("pair", server.pairing_token)
        client.get_received()
        tp.engine.set_countdown(0)
        client.emit("restart")
        received = client.get_received()
        statuses = [r for r in received if r["name"] == "status"]
        assert statuses, "no broadcast after command"
