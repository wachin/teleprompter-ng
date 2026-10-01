"""
app_info.py — Single source of truth for application metadata.

Phase 11 (quality): the About dialog, the packaging files and the tests
all read their data from here so the version, the authors and the
license are declared exactly once. This removes the previous
duplication between pyproject.toml, setup.py and the About text.

Author and license details are developer data: they are intentionally
NOT wrapped in tr() (see docs/I18N.md, rule about non-translatable
strings).
"""

APP_ID = "teleprompter-pro"

APP_NAME = "Teleprompter Pro"

# Keep in sync with pyproject.toml; tests/test_about_dialog.py verifies
# that both files agree so they cannot drift apart.
APP_VERSION = "2.0.0.dev1"

# Short description: what the program does, in one sentence.
APP_DESCRIPTION = (
    "Desktop teleprompter for presentations and recordings. It shows "
    "your script over the live camera image while you record, then you "
    "can review the take, trim the silences, add subtitles and a brand "
    "watermark, and export the final video."
)

# (display name, contact e-mail) in the order shown in the About dialog.
AUTHORS = (
    ("Washington Indacochea Delgado", "linuxfrontier@proton.me"),
    ("Juan Salazar Flores", "juancarlosalazar.jcsf@gmail.com"),
)

COPYRIGHT_START_YEAR = 2026

LICENSE_NAME = "GPL-3.0-or-later"
LICENSE_SHORT = "GPL3"
LICENSE_URL = "https://www.gnu.org/licenses/gpl-3.0.html"
# Path (relative to the repository root) of the full license text.
LICENSE_FILE = "LICENSE"

REPOSITORY_URL = "https://github.com/wachin/teleprompter-ng"
ISSUES_URL = REPOSITORY_URL + "/issues"

# (name, what it is used for in this application)
TECHNOLOGIES = (
    ("Python 3", "application language"),
    ("PyQt6", "graphical interface (Qt 6)"),
    ("OpenCV", "camera capture and video processing"),
    ("NumPy", "frame and audio buffers"),
    ("FFmpeg", "video/audio encoding, trimming and export"),
    ("Flask", "remote control server for the phone"),
    ("Flask-SocketIO", "real-time remote control channel"),
    ("qrcode", "QR code to pair the phone remote"),
    ("Vosk", "offline speech recognition / voice sync"),
    ("PortAudio (sounddevice)", "microphone capture and audio meter"),
    ("Pillow", "image handling for exports"),
    ("PyInstaller", "standalone binary packaging"),
)

ICON_FILENAME = "teleprompter-pro.svg"
ICON_DIR = ("resources", "icons")


def version_string():
    """Version as shown in the About dialog, e.g. 'Version 2.0.0.dev1'."""
    return f"{APP_NAME} {APP_VERSION}"


def copyright_line(author_name):
    """Copyright notice for one author, e.g. 'Copyright: © 2026 Name'."""
    return f"Copyright: © {COPYRIGHT_START_YEAR} {author_name}"


def technologies_text():
    """Technologies rendered as 'Name (role)' lines."""
    return "\n".join(
        f"{name} ({role})" for name, role in TECHNOLOGIES
    )
