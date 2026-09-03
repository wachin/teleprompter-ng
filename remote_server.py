"""
remote_server.py — Secure local remote control server (Phase 4).

A Flask + Socket.IO server bound to the LAN **only when the user
activates it**. Security model (Roadmap Phase 4):

- Pairing token: a 6-digit code shown in the app; a client that does
  not present it (via /pair/<token> deep link or a socket 'pair'
  event) cannot send commands. Unpaired clients only get read-only
  status.
- Command rate limit: per-client sliding window (10 commands / 5 s);
  floods are rejected with an error event, never crash the app.
- Server binds to the LAN interface only when started; stop() is
  called on window close so the port is always freed.
"""

import os
import secrets
import socket
import threading
import time
from collections import defaultdict
from io import BytesIO

import qrcode
import qrcode.image.svg
from flask import Flask, jsonify, render_template, request
from flask_socketio import SocketIO

from logging_setup import get_logger
from paths import templates_dir

log = get_logger("Remote")

RATE_LIMIT_COMMANDS = 10      # commands allowed per window…
RATE_LIMIT_WINDOW = 5.0       # …of this many seconds


def get_local_ip():
    """Returns the local IP without sending actual traffic."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


class _RateLimiter:
    """Per-client sliding window over command timestamps."""

    def __init__(self, max_calls, window_s):
        self.max_calls = max_calls
        self.window_s = window_s
        self._calls = defaultdict(list)

    def allow(self, client_id):
        now = time.monotonic()
        calls = self._calls[client_id]
        self._calls[client_id] = [t for t in calls if now - t < self.window_s]
        if len(self._calls[client_id]) >= self.max_calls:
            return False
        self._calls[client_id].append(now)
        return True

    def forget(self, client_id):
        self._calls.pop(client_id, None)


class RemoteServer:
    """
    Local remote-control server for the teleprompter.

    `teleprompter` is any object exposing:
      - engine (ScrollEngine): toggle/restart/set_wpm/wpm/jump_to/
        state/position
      - status() fallbacks exist for the legacy read-mode window.
    """

    def __init__(self, teleprompter, port=5000, host="0.0.0.0",
                 pairing_enabled=True):
        self.teleprompter = teleprompter
        self.port = port
        self.host = host
        self.ip = get_local_ip()
        self.pairing_enabled = pairing_enabled
        self.pairing_token = self._new_token() if pairing_enabled else None

        # Paired session IDs (added by the socket 'pair' event)
        self._paired_sessions = set()
        self._limiter = _RateLimiter(RATE_LIMIT_COMMANDS, RATE_LIMIT_WINDOW)

        self._thread = None
        self._running = False
        self._wsgi_server = None

        self.app = Flask(
            __name__,
            template_folder=templates_dir(),
            static_folder=os.path.join(templates_dir(), "static"),
        )
        self.app.config["SECRET_KEY"] = secrets.token_hex(32)
        self.socketio = SocketIO(
            self.app, cors_allowed_origins="*", async_mode="threading"
        )

        self._setup_routes()
        self._setup_socket_events()

    # ── Pairing ──────────────────────────────────────────────

    @staticmethod
    def _new_token():
        """6-digit pairing code."""
        return f"{secrets.randbelow(1000000):06d}"

    def regenerate_token(self):
        """New code; invalidates all paired phones."""
        self._paired_sessions.clear()
        self.pairing_token = self._new_token() if self.pairing_enabled else None
        return self.pairing_token

    @property
    def url(self):
        """Base URL (LAN)."""
        return f"http://{self.ip}:{self.port}"

    def qr_data(self):
        """URL embedded in the QR (includes the pairing token)."""
        if self.pairing_token:
            return f"{self.url}/pair/{self.pairing_token}"
        return self.url

    def _is_paired(self, session_id):
        return not self.pairing_enabled or session_id in self._paired_sessions

    # ── Teleprompter bridge ─────────────────────────────────

    def status(self):
        """Snapshot dict (read-only for every client)."""
        tp = self.teleprompter
        engine = getattr(tp, "engine", None)
        if engine is not None:
            recording = getattr(tp, "recording", None)
            return {
                "is_running": engine.state() == "running",
                "state": engine.state(),
                "position": round(engine.position(), 4),
                "wpm": engine.wpm(),
                "countdown_active": engine.state() == "counting",
                "recording": bool(recording is not None and recording.is_recording()),
                "pairing_required": self.pairing_enabled,
            }
        # Legacy full-screen Teleprompter (read mode)
        running = bool(getattr(tp, "is_running", False))
        return {
            "is_running": running,
            "state": "running" if running else "idle",
            "position": 0,
            "wpm": getattr(tp, "wpm", 150),
            "countdown_active": getattr(tp, "countdown_active", False),
            "recording": False,
            "pairing_required": self.pairing_enabled,
        }

    # ── HTTP routes ──────────────────────────────────────────

    def _setup_routes(self):
        @self.app.route("/")
        def index():
            return render_template("remote.html")

        @self.app.route("/qr")
        def qr_code():
            factory = qrcode.image.svg.SvgPathImage
            img = qrcode.make(self.qr_data(), image_factory=factory)
            buffer = BytesIO()
            img.save(buffer)
            buffer.seek(0)
            return buffer.getvalue(), 200, {"Content-Type": "image/svg+xml"}

        @self.app.route("/api/status")
        def status():
            return jsonify(self.status())

        @self.app.route("/pair/<token>")
        def pair_via_url(token):
            """QR deep-link: opens the control page for a paired phone.
            Command authorization happens over the socket 'pair' event;
            this route only serves the page (HTTP cannot send commands
            by design)."""
            valid = (
                not self.pairing_enabled
                or secrets.compare_digest(str(token), str(self.pairing_token))
            )
            # The page itself is served either way; it asks the user for
            # the code via the socket when not yet paired.
            response = self.app.make_response(render_template("remote.html"))
            if valid:
                response.set_cookie("paired", "1", httponly=True, samesite="Lax")
            else:
                response.status_code = 401
            return response

    # ── Socket.IO events ──────────────────────────────────────

    def _setup_socket_events(self):
        server = self

        @self.socketio.on("connect")
        def handle_connect():
            log.info("Remote client connected (sid %s)", request.sid)
            server._limiter.forget(request.sid)
            server.socketio.emit("status", server.status(), to=request.sid)

        @self.socketio.on("disconnect")
        def handle_disconnect():
            log.info("Remote client disconnected (sid %s)", request.sid)
            server._paired_sessions.discard(request.sid)
            server._limiter.forget(request.sid)

        @self.socketio.on("pair")
        def handle_pair(token):
            ok = (
                not server.pairing_enabled
                or secrets.compare_digest(str(token), str(server.pairing_token))
            )
            if ok:
                server._paired_sessions.add(request.sid)
            server.socketio.emit("paired", {"ok": ok}, to=request.sid)
            if ok:
                server._emit_status()

        @self.socketio.on("get_status")
        def handle_get_status():
            server.socketio.emit("status", server.status(), to=request.sid)

        # Commands: registered through the guard, which checks pairing
        # and the per-client rate limit before touching the engine.
        def guarded(handler):
            def wrapped(*args):
                sid = request.sid
                if not server._is_paired(sid):
                    server.socketio.emit(
                        "error", "Pair first: enter the code shown in the app",
                        to=sid,
                    )
                    return
                if not server._limiter.allow(sid):
                    server.socketio.emit(
                        "error", "Too many commands; wait a moment", to=sid,
                    )
                    return
                handler(*args)
                server._emit_status()
            wrapped.__name__ = handler.__name__  # keeps flask-socketio happy
            return self.socketio.on(handler.__name__)(wrapped)

        @guarded
        def toggle():
            server.teleprompter.engine.toggle()

        @guarded
        def restart():
            server.teleprompter.engine.restart()

        @guarded
        def wpm_up():
            engine = server.teleprompter.engine
            engine.set_wpm(min(500, engine.wpm() + 10))

        @guarded
        def wpm_down():
            engine = server.teleprompter.engine
            engine.set_wpm(max(30, engine.wpm() - 10))

        @guarded
        def jump(position):
            try:
                pos = float(position)
            except (TypeError, ValueError):
                return
            server.teleprompter.engine.jump_to(max(0.0, min(1.0, pos)))

        @guarded
        def rec_start():
            """Starts a recording take (Phase 5)."""
            tp = server.teleprompter
            if hasattr(tp, "request_recording_start"):
                tp.request_recording_start()

        @guarded
        def rec_stop():
            """Stops the recording take (Phase 5)."""
            tp = server.teleprompter
            if hasattr(tp, "request_recording_stop"):
                tp.request_recording_stop()

    def _emit_status(self):
        self.socketio.emit("status", self.status())

    # ── Lifecycle ──────────────────────────────────────────────

    def start(self):
        if self._running:
            log.info("The remote server is already running at %s", self.url)
            return self._thread
        self._running = True
        self._thread = threading.Thread(
            target=self._run_server, daemon=True, name="remote-server",
        )
        self._thread.start()
        log.info(
            "Server started at %s (pairing %s)",
            self.url, "ON" if self.pairing_enabled else "off",
        )
        return self._thread

    def _run_server(self):
        try:
            from werkzeug.serving import make_server

            self._wsgi_server = make_server(
                self.host, self.port, self.app, threaded=True
            )
            self._wsgi_server.serve_forever()
        except Exception as e:
            log.error("The remote server stopped: %s", e)
        finally:
            self._running = False

    def stop(self):
        if not self._running and self._wsgi_server is None:
            return
        log.info("Stopping the remote server…")
        try:
            if self._wsgi_server is not None:
                self._wsgi_server.shutdown()
                self._wsgi_server = None
        except Exception as e:
            log.warning("Error stopping the remote server: %s", e)
        self._running = False
        self._paired_sessions.clear()

    def is_running(self):
        return self._running
