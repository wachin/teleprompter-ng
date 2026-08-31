"""
remote_server.py — Servidor Flask para control remoto del teleprompter.

Levanta un servidor local con una página web que permite controlar
el teleprompter desde el teléfono (Play/Pausa, Velocidad, Reiniciar).

Fase 0: la SECRET_KEY se genera aleatoriamente en cada ejecución,
el servidor queda desactivado por defecto (el usuario lo activa con Q
o desde la interfaz) y expone shutdown() para liberar el puerto al
cerrar la aplicación.
"""

import os
import secrets
import socket
import threading
from io import BytesIO

import qrcode
import qrcode.image.svg
from flask import Flask, jsonify, render_template
from flask_socketio import SocketIO

from logging_setup import get_logger
from paths import templates_dir

log = get_logger("Remote")


def get_local_ip():
    """Obtiene la IP local de la máquina sin enviar tráfico real."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # UDP connect no envía paquetes; solo consulta la tabla de rutas
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


class RemoteServer:
    def __init__(self, teleprompter, port=5000, host="0.0.0.0"):
        self.teleprompter = teleprompter
        self.port = port
        self.host = host
        self.ip = get_local_ip()
        self.url = f"http://{self.ip}:{self.port}"
        self._thread = None
        self._running = False
        self._wsgi_server = None

        # Flask
        self.app = Flask(
            __name__,
            template_folder=templates_dir(),
            static_folder=os.path.join(templates_dir(), "static"),
        )
        # Clave efímera: no hay sesiones persistentes que preservar
        self.app.config["SECRET_KEY"] = secrets.token_hex(32)

        self.socketio = SocketIO(
            self.app, cors_allowed_origins="*", async_mode="threading"
        )

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
                "countdown_active": self.teleprompter.countdown_active,
            })

    def _setup_socket_events(self):
        """Configura los eventos de WebSocket."""

        @self.socketio.on("connect")
        def handle_connect():
            log.info("Cliente remoto conectado")

        @self.socketio.on("disconnect")
        def handle_disconnect():
            log.info("Cliente remoto desconectado")

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
            "countdown_active": self.teleprompter.countdown_active,
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
        if self._running:
            log.info("The remote server is already running at %s", self.url)
            return self._thread

        self._running = True
        self._thread = threading.Thread(
            target=self._run_server,
            daemon=True,
            name="remote-server",
        )
        self._thread.start()
        log.info("Server started at %s", self.url)
        return self._thread

    def _run_server(self):
        """Bucle del servidor; captura errores sin matar la app."""
        try:
            from werkzeug.serving import make_server

            # WSGIServer de Werkzeug: igual que socketio.run en modo
            # threading, pero expone shutdown() para detenerlo de forma
            # limpia al cerrar la aplicación.
            self._wsgi_server = make_server(
                self.host, self.port, self.app, threaded=True
            )
            self._wsgi_server.serve_forever()
        except Exception as e:
            log.error("The remote server stopped: %s", e)
        finally:
            self._running = False

    def stop(self):
        """Detiene el servidor remoto."""
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

    def is_running(self):
        """Indica si el servidor está activo."""
        return self._running
