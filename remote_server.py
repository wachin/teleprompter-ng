"""
remote_server.py — Servidor Flask para control remoto del teleprompter.

Levanta un servidor local con una página web que permite controlar
el teleprompter desde el teléfono (Play/Pausa, Velocidad, Reiniciar).
"""

import socket
import qrcode
import qrcode.image.svg
from io import BytesIO
from flask import Flask, render_template, jsonify
from flask_socketio import SocketIO


def get_local_ip():
    """Obtiene la IP local de la máquina."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


class RemoteServer:
    def __init__(self, teleprompter, port=5000):
        self.teleprompter = teleprompter
        self.port = port
        self.ip = get_local_ip()
        self.url = f"http://{self.ip}:{self.port}"

        # Crear app Flask
        self.app = Flask(__name__,
                         template_folder="templates",
                         static_folder="static")
        self.app.config["SECRET_KEY"] = "teleprompter-pro-secret"

        # Socket.IO para comunicación en tiempo real
        self.socketio = SocketIO(self.app, cors_allowed_origins="*", async_mode="threading")

        self._setup_routes()
        self._setup_socket_events()

    def _setup_routes(self):
        """Configura las rutas HTTP."""

        @self.app.route("/")
        def index():
            return render_template("remote.html")

        @self.app.route("/qr")
        def qr_code():
            """Genera código QR como SVG."""
            factory = qrcode.image.svg.SvgPathImage
            img = qrcode.make(self.url, image_factory=factory)
            buffer = BytesIO()
            img.save(buffer)
            buffer.seek(0)
            return buffer.getvalue(), 200, {"Content-Type": "image/svg+xml"}

        @self.app.route("/api/status")
        def status():
            """Devuelve el estado actual del teleprompter."""
            return jsonify({
                "is_running": self.teleprompter.is_running,
                "speed": self.teleprompter.scroll_speed,
                "progress": self._get_progress(),
                "countdown_active": self.teleprompter.countdown_active
            })

    def _setup_socket_events(self):
        """Configura los eventos de WebSocket."""

        @self.socketio.on("connect")
        def handle_connect():
            print(f"[Remote] Cliente conectado desde {self.ip}:{self.port}")

        @self.socketio.on("disconnect")
        def handle_disconnect():
            print("[Remote] Cliente desconectado")

        @self.socketio.on("toggle")
        def handle_toggle():
            self.teleprompter.toggle()
            self._emit_status()

        @self.socketio.on("speed_up")
        def handle_speed_up():
            self.teleprompter.speed_up()
            self._emit_status()

        @self.socketio.on("speed_down")
        def handle_speed_down():
            self.teleprompter.speed_down()
            self._emit_status()

        @self.socketio.on("reset")
        def handle_reset():
            self.teleprompter.reset()
            self._emit_status()

        @self.socketio.on("get_status")
        def handle_get_status():
            self._emit_status()

    def _emit_status(self):
        """Emite el estado actual a todos los clientes conectados."""
        self.socketio.emit("status", {
            "is_running": self.teleprompter.is_running,
            "speed": self.teleprompter.scroll_speed,
            "progress": self._get_progress(),
            "countdown_active": self.teleprompter.countdown_active
        })

    def _get_progress(self):
        """Calcula el progreso actual del scroll."""
        try:
            scrollbar = self.teleprompter.text_widget.verticalScrollBar()
            max_scroll = scrollbar.maximum()
            if max_scroll > 0:
                return int((scrollbar.value() / max_scroll) * 100)
        except Exception:
            pass
        return 0

    def start(self):
        """Inicia el servidor en un hilo separado."""
        import threading
        thread = threading.Thread(
            target=lambda: self.socketio.run(
                self.app,
                host="0.0.0.0",
                port=self.port,
                debug=False,
                use_reloader=False,
                allow_unsafe_werkzeug=True
            ),
            daemon=True
        )
        thread.start()
        print(f"[Remote] Servidor iniciado en {self.url}")
        return thread
