"""
logging_setup.py — Registro estructurado con niveles DEBUG, INFO, WARNING, ERROR.

Fase 0: centraliza la configuración de logging para toda la aplicación.
Escribe a la consola y, en Linux, también al journal de systemd si existe.
"""

import logging
import os
import sys

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging(level=logging.INFO):
    """
    Configura el logger raíz de la aplicación.

    Args:
        level: nivel mínimo de registro (DEBUG, INFO, WARNING, ERROR).
    """
    root = logging.getLogger()
    if root.handlers:
        # Ya configurado (p. ej. por una segunda llamada)
        root.setLevel(level)
        return root

    root.setLevel(level)

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
    root.addHandler(handler)

    # Journal de systemd en Linux, si está disponible
    if sys.platform.startswith("linux"):
        try:
            from logging.handlers import SysLogHandler

            if os.path.exists("/dev/log"):
                syslog = SysLogHandler(address="/dev/log")
                syslog.setFormatter(logging.Formatter("teleprompter-pro: " + LOG_FORMAT, DATE_FORMAT))
                root.addHandler(syslog)
        except Exception:
            pass

    # Reducir ruido de bibliotecas de terceros
    for noisy in ("engineio", "socketio", "werkzeug", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    return root


def get_logger(name):
    """Devuelve un logger hijo de la aplicación."""
    return logging.getLogger(name)
