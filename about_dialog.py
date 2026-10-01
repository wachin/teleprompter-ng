"""
about_dialog.py — "About" dialog (Phase 11).

Two-section layout requested by the maintainer:

    +---------------------+-----------------------------------------+
    |   large icon        |  Teleprompter Pro                       |
    |   (SVG, centered)   |  Version 2.0.0.dev1                     |
    |                     |  short description, technologies,       |
    |                     |  authors, license, repository           |
    +---------------------+-----------------------------------------+

The icon on the left is rendered from the SVG source so it stays sharp
at any size (QSvgWidget paints the vector, no bitmap scaling). It is
centered both horizontally and vertically inside its column.

Author names and e-mail addresses are rendered as clickable mailto:
links; clicking one delegates to the operating system mail client. The
application metadata (version, authors, license, technologies) comes
from app_info.py, the single source of truth.

All UI strings are English and wrapped in self.tr() (docs/I18N.md).
Developer data (names, addresses, license id) is intentionally not
translatable.
"""

import shutil
import subprocess

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices, QIcon
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app_info import (
    APP_DESCRIPTION,
    APP_NAME,
    APP_VERSION,
    AUTHORS,
    ICON_FILENAME,
    LICENSE_FILE,
    LICENSE_NAME,
    LICENSE_URL,
    REPOSITORY_URL,
    TECHNOLOGIES,
    copyright_line,
)
from logging_setup import get_logger
from paths import icon_path, resource_path

try:  # QtSvgWidgets ships with PyQt6; the fallback keeps minimal
    # builds (or a partial PyQt6 install) from crashing.
    from PyQt6.QtSvgWidgets import QSvgWidget
    SVG_WIDGET_AVAILABLE = True
except ImportError:  # pragma: no cover - depends on the PyQt6 build
    QSvgWidget = None
    SVG_WIDGET_AVAILABLE = False

log = get_logger("AboutDialog")

# Icon column geometry.
ICON_SIZE = 256
ICON_COLUMN_MIN_WIDTH = 300

# Dialog geometry: width is fixed (icon + text pair), the height is
# derived from the content so nothing hides behind a scrollbar.
DIALOG_WIDTH = 880
MIN_DIALOG_HEIGHT = 560

_BRAND_GOLD = "#FFD700"
_MUTED = "#9A9AB0"


def app_icon():
    """
    QIcon built from the SVG application icon.

    Returns a null QIcon when the file is missing so callers can fall
    back to the platform default without special-casing.
    """
    return QIcon(icon_path())


class AboutDialog(QDialog):
    """Modal information dialog: icon on the left, details on the right."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("About {0}").format(APP_NAME))
        self.setWindowIcon(app_icon())
        self.setModal(True)
        self.resize(DIALOG_WIDTH, MIN_DIALOG_HEIGHT)

        # Links the dialog opened so far (used by tests and logging).
        self.opened_links = []
        # The dialog is resized to fit its content on first show.
        self._fitted = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 16)
        outer.setSpacing(16)

        # ── Two sections side by side ──────────────────────────
        row = QHBoxLayout()
        row.setSpacing(28)
        row.addWidget(self._build_icon_section())
        row.addWidget(self._build_details_section(), 1)
        outer.addLayout(row, 1)

        # ── Close button, bottom right ─────────────────────────
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self.buttons.rejected.connect(self.reject)
        button_row = QHBoxLayout()
        button_row.addStretch(1)
        button_row.addWidget(self.buttons)
        outer.addLayout(button_row)

    # ── Sizing ────────────────────────────────────────────────

    def showEvent(self, event):
        """Grows the dialog once so the whole text fits without scrolling."""
        super().showEvent(event)
        if not self._fitted:
            self._fitted = True
            self._fit_to_content()

    def _fit_to_content(self):
        """
        Sizes the dialog to its content, capped to the available screen.

        The details column is a QScrollArea, so on small displays the
        text still scrolls instead of overflowing off-screen.
        """
        body = self.details_body.sizeHint().height()
        needed = body + self.buttons.sizeHint().height() + 72
        screen = self.screen()
        if screen is not None:
            available = screen.availableGeometry().height() - 80
            needed = min(needed, available)
        self.resize(DIALOG_WIDTH, max(MIN_DIALOG_HEIGHT, needed))

    # ── Left section: large centered icon ─────────────────────

    def _build_icon_section(self):
        """Widget column with the icon centered on both axes."""
        column = QWidget()
        layout = QVBoxLayout(column)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        # Stretches above and below keep the icon vertically centered
        # at any dialog height.
        layout.addStretch(1)

        if SVG_WIDGET_AVAILABLE:
            self.icon_widget = QSvgWidget(icon_path())
            self.icon_widget.setFixedSize(ICON_SIZE, ICON_SIZE)
        else:  # pragma: no cover - depends on the PyQt6 build
            self.icon_widget = QLabel()
            self.icon_widget.setFixedSize(ICON_SIZE, ICON_SIZE)
            self.icon_widget.setPixmap(app_icon().pixmap(ICON_SIZE, ICON_SIZE))
        self.icon_widget.setAccessibleName(
            self.tr("Teleprompter Pro application icon")
        )
        self.icon_widget.setAccessibleDescription(APP_NAME)
        layout.addWidget(self.icon_widget, 0, Qt.AlignmentFlag.AlignHCenter)

        caption = QLabel(APP_NAME)
        caption.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        caption.setStyleSheet(
            f"color: {_BRAND_GOLD}; font-size: 15px; font-weight: bold;"
        )
        layout.addSpacing(14)
        layout.addWidget(caption, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addStretch(1)

        column.setMinimumWidth(ICON_COLUMN_MIN_WIDTH)
        column.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred
        )
        self.icon_holder = column
        return column

    # ── Right section: texts, technologies, authors, license ──

    def _build_details_section(self):
        """Scrollable text column shown to the right of the icon."""
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 8, 0)
        layout.setSpacing(10)

        self.title_label = QLabel(APP_NAME)
        self.title_label.setStyleSheet(
            f"font-size: 26px; font-weight: bold; color: {_BRAND_GOLD};"
        )
        layout.addWidget(self.title_label)

        self.version_label = QLabel(self.tr("Version {0}").format(APP_VERSION))
        self.version_label.setStyleSheet(f"color: {_MUTED};")
        layout.addWidget(self.version_label)

        self.description_label = QLabel(APP_DESCRIPTION)
        self.description_label.setWordWrap(True)
        self.description_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        layout.addWidget(self.description_label)
        layout.addSpacing(6)

        # Technologies
        layout.addWidget(self._section_heading(self.tr("Technologies")))
        self.technologies_label = self._rich_label(
            "<br/>".join(
                f"<b>{name}</b> — {role}"
                for name, role in TECHNOLOGIES
            )
        )
        layout.addWidget(self.technologies_label)
        layout.addSpacing(6)

        # Authors (clickable e-mail addresses)
        layout.addWidget(self._section_heading(self.tr("Authors")))
        self.author_labels = []
        for name, email in AUTHORS:
            label = self._rich_label(
                "{0}<br/>{1} <a href=\"mailto:{2}\">{2}</a>".format(
                    copyright_line(name), self.tr("Email:"), email
                )
            )
            label.setAccessibleName(self.tr("Author: {0}").format(name))
            label.setAccessibleDescription(email)
            self.author_labels.append(label)
            layout.addWidget(label)
        layout.addSpacing(6)

        # License
        layout.addWidget(self._section_heading(self.tr("License")))
        self.license_label = self._rich_label(
            "{0} <a href=\"{1}\">{2}</a>".format(
                self.tr("License:"), LICENSE_URL, LICENSE_NAME
            )
        )
        layout.addWidget(self.license_label)
        layout.addSpacing(6)

        # Repository
        layout.addWidget(self._section_heading(self.tr("Repository")))
        self.repository_label = self._rich_label(
            f"<a href=\"{REPOSITORY_URL}\">{REPOSITORY_URL}</a>"
        )
        layout.addWidget(self.repository_label)

        # GPL3 requires shipping the license text with the program.
        self.license_file_label = QLabel(
            self.tr("Full license text: {0}").format(LICENSE_FILE)
        )
        self.license_file_label.setStyleSheet(f"color: {_MUTED};")
        layout.addWidget(self.license_file_label)
        layout.addStretch(1)

        self.details_body = body
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(body)
        self.details_area = scroll
        return scroll

    def _section_heading(self, text):
        label = QLabel(text)
        label.setStyleSheet("font-size: 15px; font-weight: bold;")
        return label

    def _rich_label(self, html):
        """Read-only rich-text label whose links are handled by us."""
        label = QLabel(html)
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setWordWrap(True)
        label.setOpenExternalLinks(False)
        label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextBrowserInteraction
        )
        label.linkActivated.connect(self._open_link)
        return label

    # ── Link handling ─────────────────────────────────────────

    def _open_link(self, url):
        """
        Opens a link with the desktop's default handler.

        Tries Qt first (QDesktopServices honours the xdg-open / mailto
        association of the session). When Qt reports no handler
        (returns False), falls back to the xdg utilities so a minimal
        desktop still gets a working link.
        """
        self.opened_links.append(url)
        if QDesktopServices.openUrl(QUrl(url)):
            return True

        program = "xdg-email" if url.startswith("mailto:") else "xdg-open"
        target = url[len("mailto:"):] if program == "xdg-email" else url
        if shutil.which(program):
            try:
                subprocess.Popen(
                    [program, target],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return True
            except OSError as e:  # pragma: no cover - environment specific
                log.warning("Could not open %s with %s: %s", url, program, e)
        log.warning("No handler available for link: %s", url)
        return False

    # ── Convenience ───────────────────────────────────────────

    def authors_text(self):
        """Plain-text dump of the authors block (used by tests/logs)."""
        return "\n".join(
            "{0}\n{1} {2}".format(copyright_line(name), self.tr("Email:"), email)
            for name, email in AUTHORS
        )

    def license_path(self):
        """Absolute path of the shipped LICENSE file."""
        return resource_path(LICENSE_FILE)

    def icon_file(self):
        """Absolute path of the SVG the icon section renders."""
        return icon_path(ICON_FILENAME)


def show_about(parent=None):
    """Opens the About dialog modally and returns the dialog instance."""
    dialog = AboutDialog(parent)
    dialog.exec()
    return dialog
