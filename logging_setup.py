"""
logging_setup.py — Structured logging with DEBUG, INFO, WARNING, ERROR levels.

Phase 0: centralizes logging configuration for the whole application.
Writes to the console and, on Linux, to the systemd journal if available.
"""

import logging
import os
import sys

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging(level=logging.INFO):
    """
    Configures the application root logger.

    Args:
        level: minimum logging level (DEBUG, INFO, WARNING, ERROR).
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
            # /dev/log puede denegar el acceso según el sistema; el
            # handler de consola ya cubre el caso normal
            root.debug("SysLog handler not available", exc_info=True)

    # Reducir ruido de bibliotecas de terceros
    for noisy in ("engineio", "socketio", "werkzeug", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    return root


def get_logger(name):
    """Returns a child logger of the application."""
    return logging.getLogger(name)
