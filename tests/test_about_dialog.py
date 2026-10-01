"""
tests/test_about_dialog.py — Tests for the About dialog + app metadata.

Conventions follow the rest of the suite: a module-scoped QApplication
fixture (no qtbot), monkeypatching for anything that would touch the
desktop, and no network or device access.
"""

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import QApplication, QLabel, QScrollArea

import about_dialog
import app_info
from about_dialog import (
    ICON_COLUMN_MIN_WIDTH,
    ICON_SIZE,
    SVG_WIDGET_AVAILABLE,
    AboutDialog,
    app_icon,
)
from paths import icon_path, icons_dir, resource_path

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def dialog(qapp):
    d = AboutDialog()
    yield d
    d.close()


class TestAppInfo:
    """The metadata module is the single source of truth."""

    def test_two_authors_in_order(self):
        assert len(app_info.AUTHORS) == 2
        assert app_info.AUTHORS[0] == (
            "Washington Indacochea Delgado", "linuxfrontier@proton.me")
        assert app_info.AUTHORS[1] == (
            "Juan Salazar Flores", "juancarlosalazar.jcsf@gmail.com")

    def test_license_is_gpl3(self):
        assert app_info.LICENSE_NAME == "GPL-3.0-or-later"
        assert app_info.LICENSE_SHORT == "GPL3"
        assert "gnu.org/licenses/gpl-3.0" in app_info.LICENSE_URL

    def test_license_file_present(self):
        """The About dialog points at LICENSE; it must really exist."""
        assert (REPO_ROOT / app_info.LICENSE_FILE).is_file()

    def test_version_matches_pyproject(self):
        """pyproject.toml and app_info must not drift apart."""
        tomllib = pytest.importorskip("tomllib")
        with open(REPO_ROOT / "pyproject.toml", "rb") as fh:
            data = tomllib.load(fh)
        assert data["project"]["version"] == app_info.APP_VERSION

    def test_authors_match_pyproject(self):
        tomllib = pytest.importorskip("tomllib")
        with open(REPO_ROOT / "pyproject.toml", "rb") as fh:
            data = tomllib.load(fh)
        declared = [(a["name"], a["email"]) for a in data["project"]["authors"]]
        assert declared == list(app_info.AUTHORS)

    def test_repository_url_is_current(self):
        """The old wachin/teleprompter repository must not be referenced."""
        assert app_info.REPOSITORY_URL.endswith("/teleprompter-ng")

    def test_description_mentions_teleprompter_and_camera(self):
        text = app_info.APP_DESCRIPTION.lower()
        assert "teleprompter" in text
        assert "camera" in text
        assert "export" in text

    def test_technologies_are_named_pairs(self):
        assert len(app_info.TECHNOLOGIES) >= 8
        names = [name for name, _role in app_info.TECHNOLOGIES]
        assert "PyQt6" in names
        assert "OpenCV" in names
        assert "FFmpeg" in names
        for name, role in app_info.TECHNOLOGIES:
            assert name and role

    def test_helpers(self):
        assert app_info.version_string() == (
            "Teleprompter Pro " + app_info.APP_VERSION)
        line = app_info.copyright_line("Ada Lovelace")
        assert line.startswith("Copyright: © 2026")
        assert "Ada Lovelace" in line
        assert "PyQt6 (" in app_info.technologies_text()


class TestPackagingMetadata:
    """
    The license/URL cleanup must reach every shipped file, not only the
    About dialog: README, Debian packaging and the metadata modules.
    """

    STALE_URL = "github.com/wachin/teleprompter"

    def _files(self):
        return {
            "README.md": REPO_ROOT / "README.md",
            "debian/control": REPO_ROOT / "debian" / "control",
            "debian/copyright": REPO_ROOT / "debian" / "copyright",
            "debian/watch": REPO_ROOT / "debian" / "watch",
            "debian/changelog": REPO_ROOT / "debian" / "changelog",
        }

    def test_no_stale_repository_url(self):
        for name, path in self._files().items():
            text = path.read_text(encoding="utf-8")
            # Any older URL must be the -ng one, never the bare name.
            for line in text.splitlines():
                if self.STALE_URL in line:
                    assert self.STALE_URL + "-ng" in line, f"{name}: {line}"

    def test_readme_license_is_gpl3(self):
        text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        # The license section must not still advertise plain MIT.
        for line in text.splitlines():
            assert line.strip() not in ("MIT", "MIT License"), line
        assert "GPL-3.0-or-later" in text
        assert "GNU General Public License" in text

    def test_debian_copyright_is_gpl3(self):
        text = (REPO_ROOT / "debian" / "copyright").read_text(encoding="utf-8")
        assert "License: GPL-3+" in text
        assert "common-licenses/GPL-3" in text
        assert "License: MIT" not in text

    def test_debian_control_uses_current_urls_and_authors(self):
        text = (REPO_ROOT / "debian" / "control").read_text(encoding="utf-8")
        assert app_info.REPOSITORY_URL in text
        assert app_info.AUTHORS[0][1] in text
        assert app_info.AUTHORS[1][1] in text

    def test_debian_install_ships_app_info(self):
        """A missing module here breaks the packaged program at runtime."""
        entries = (REPO_ROOT / "debian" / "install").read_text(
            encoding="utf-8").split()
        for module in ("app_info.py", "about_dialog.py"):
            assert module in entries, module

    def test_icon_shipped_by_debian_install(self):
        text = (REPO_ROOT / "debian" / "install").read_text(encoding="utf-8")
        assert "hicolor/scalable/apps" in text
        assert app_info.ICON_FILENAME in text

    def test_changelog_mentions_license_cleanup(self):
        text = (REPO_ROOT / "debian" / "changelog").read_text(encoding="utf-8")
        assert "GPL-3.0-or-later" in text
        assert "About dialog" in text


class TestTranslationCatalog:
    """The About dialog strings must be extractable by Qt Linguist."""

    TS = REPO_ROOT / "translations" / "teleprompter_es.ts"

    def test_catalog_is_valid_xml(self):
        root = ET.parse(self.TS).getroot()
        assert root.tag == "TS"

    def test_about_dialog_context_present(self):
        root = ET.parse(self.TS).getroot()
        contexts = [c.findtext("name") for c in root.findall("context")]
        assert "AboutDialog" in contexts

    def test_about_dialog_sources_extracted(self):
        text = self.TS.read_text(encoding="utf-8")
        for source in ("Technologies", "Authors", "License", "Repository"):
            assert f"<source>{source}</source>" in text, source

    def test_developer_data_is_not_translatable(self):
        """Names, addresses and URLs must not appear as tr() sources."""
        text = self.TS.read_text(encoding="utf-8")
        for value in (app_info.AUTHORS[0][0], app_info.AUTHORS[0][1],
                      app_info.REPOSITORY_URL, app_info.LICENSE_NAME):
            assert f"<source>{value}</source>" not in text, value

    def test_catalog_mentions_about_module(self):
        assert "../about_dialog.py" in self.TS.read_text(encoding="utf-8")


class TestIcon:
    """Icon file location and SVG validity (Inkscape-friendly output)."""

    def test_icon_path_points_to_svg(self):
        path = icon_path()
        assert path.endswith(app_info.ICON_FILENAME)
        assert Path(path).is_file()
        assert Path(path).parent == Path(icons_dir())

    def test_icon_dir_uses_resource_root(self):
        assert Path(icons_dir()) == Path(resource_path("resources", "icons"))

    def test_svg_is_valid_xml_with_viewbox(self):
        tree = ET.parse(icon_path())
        root = tree.getroot()
        assert root.tag.endswith("svg")
        assert root.get("viewBox") is not None
        assert root.get("width") == root.get("height")
        # Must contain actual drawing elements, not an empty shell.
        drawables = [e for e in root.iter()
                     if e.tag.split("}")[-1] in ("rect", "path", "circle")]
        assert len(drawables) >= 5

    def test_svg_has_no_embedded_raster_or_filters(self):
        """Plain SVG only: keeps the file editable in Inkscape."""
        # Re-serialise through ElementTree so XML comments (which merely
        # *describe* these restrictions) are not part of the check.
        root = ET.parse(icon_path()).getroot()
        markup = ET.tostring(root, encoding="unicode")
        for forbidden in ("<image", "base64", "filter=", "mask=", "<style"):
            assert forbidden not in markup, forbidden

    def test_svg_layers_are_labelled(self):
        """Named Inkscape layers so the icon opens as tidy objects."""
        text = Path(icon_path()).read_text(encoding="utf-8")
        assert "inkscape:groupmode=\"layer\"" in text
        assert "inkscape:label=" in text

    def test_icon_is_loadable(self, qapp):
        icon = app_icon()
        assert not icon.isNull()
        assert icon.pixmap(ICON_SIZE, ICON_SIZE).width() == ICON_SIZE


class TestDialogLayout:
    """Two-section layout: large centered icon left, details right."""

    def test_dialog_constructs(self, dialog):
        assert dialog.windowTitle() == "About " + app_info.APP_NAME
        assert dialog.isModal()

    def test_has_large_icon_widget(self, dialog):
        if SVG_WIDGET_AVAILABLE:
            from PyQt6.QtSvgWidgets import QSvgWidget
            assert isinstance(dialog.icon_widget, QSvgWidget)
        # The icon column is at least 200 px wide (large, not a bullet).
        assert dialog.icon_widget.width() >= 200
        assert dialog.icon_widget.minimumHeight() >= 200

    def test_icon_size_constant_is_large(self):
        assert ICON_SIZE >= 200
        assert ICON_COLUMN_MIN_WIDTH >= ICON_SIZE

    def test_icon_renders_the_svg_file(self, dialog):
        assert Path(dialog.icon_file()).resolve() == Path(icon_path()).resolve()

    def test_icon_widget_has_accessible_name(self, dialog):
        assert dialog.icon_widget.accessibleName()
        assert dialog.icon_widget.accessibleDescription() == app_info.APP_NAME

    def test_details_section_is_scrollable(self, dialog):
        assert isinstance(dialog.details_area, QScrollArea)
        assert dialog.details_area.widgetResizable()

    def test_dialog_width_constant(self, dialog):
        assert about_dialog.DIALOG_WIDTH >= ICON_COLUMN_MIN_WIDTH
        assert dialog.minimumSizeHint().width() <= about_dialog.DIALOG_WIDTH + 40

    def test_dialog_grows_to_fit_content(self, dialog):
        """
        The height follows the content so License/Repository are visible.

        Capped to the available screen height: on a display that is too
        small the details area scrolls instead of running off-screen.
        """
        dialog.resize(about_dialog.DIALOG_WIDTH, about_dialog.MIN_DIALOG_HEIGHT)
        dialog._fit_to_content()
        needed = (
            dialog.details_body.sizeHint().height()
            + dialog.buttons.sizeHint().height()
            + 72
        )
        screen = dialog.screen()
        available = screen.availableGeometry().height() - 80 if screen else needed
        expected = max(about_dialog.MIN_DIALOG_HEIGHT, min(needed, available))
        assert dialog.height() == expected
        assert dialog.height() >= about_dialog.MIN_DIALOG_HEIGHT
        assert dialog.height() <= available
        # The icon column stays a fixed width, only the height grows.
        assert dialog.width() == about_dialog.DIALOG_WIDTH

    def test_fit_is_applied_only_once(self, dialog):
        """A manual resize by the user must not be undone by the dialog."""
        assert dialog._fitted is False
        dialog.show()
        assert dialog._fitted is True
        dialog.resize(about_dialog.DIALOG_WIDTH, about_dialog.MIN_DIALOG_HEIGHT)
        dialog.hide()
        dialog.show()
        assert dialog.height() == about_dialog.MIN_DIALOG_HEIGHT

    def test_title_and_version(self, dialog):
        assert dialog.title_label.text() == app_info.APP_NAME
        assert app_info.APP_VERSION in dialog.version_label.text()

    def test_description_is_shown(self, dialog):
        assert dialog.description_label.text() == app_info.APP_DESCRIPTION
        assert dialog.description_label.wordWrap()

    def test_technologies_listed(self, dialog):
        html = dialog.technologies_label.text()
        for name, _role in app_info.TECHNOLOGIES:
            assert name in html

    def test_section_headings_present(self, dialog):
        texts = [w.text() for w in dialog.findChildren(QLabel)]
        for heading in ("Technologies", "Authors", "License", "Repository"):
            assert heading in texts, heading

    def test_close_button_exists(self, dialog):
        assert dialog.buttons is not None
        assert len(dialog.buttons.buttons()) == 1


class TestAuthorsAndMailto:
    """Authors block: order, copyright, clickable mailto: links."""

    def test_one_label_per_author_in_order(self, dialog):
        assert len(dialog.author_labels) == len(app_info.AUTHORS)

    def test_labels_contain_name_copyright_and_mailto(self, dialog):
        for label, (name, email) in zip(
                dialog.author_labels, app_info.AUTHORS, strict=True):
            html = label.text()
            assert name in html
            assert f"Copyright: © {app_info.COPYRIGHT_START_YEAR}" in html
            assert f'href="mailto:{email}"' in html
            # The address itself is visible, not hidden behind the link.
            assert email in html

    def test_mailto_links_are_external_links(self, dialog):
        """Qt must not open them itself: we route through _open_link()."""
        for label in dialog.author_labels:
            assert not label.openExternalLinks()
            assert label.textFormat() == label.textFormat().RichText
            assert label.textInteractionFlags() & (
                label.textInteractionFlags().TextBrowserInteraction
            )

    def test_authors_block_order_in_text(self, dialog):
        text = dialog.authors_text()
        first = text.index(app_info.AUTHORS[0][1])
        second = text.index(app_info.AUTHORS[1][1])
        assert first < second

    def test_mailto_verification(self, dialog):
        """Every author address is reachable as a valid mailto: URL."""
        for _name, email in app_info.AUTHORS:
            url = QUrl("mailto:" + email)
            assert url.isValid()
            assert url.scheme() == "mailto"
            assert url.path() == email
            assert "@" in url.path()
            assert "." in url.path().split("@")[1]

    def test_license_link_and_file(self, dialog):
        assert app_info.LICENSE_URL in dialog.license_label.text()
        assert app_info.LICENSE_NAME in dialog.license_label.text()
        assert Path(dialog.license_path()).is_file()

    def test_repository_link(self, dialog):
        assert app_info.REPOSITORY_URL in dialog.repository_label.text()

    def test_open_link_records_and_uses_desktop_services(
            self, dialog, monkeypatch):
        opened = []
        monkeypatch.setattr(
            QDesktopServices, "openUrl", lambda url: opened.append(url) or True)
        target = "mailto:" + app_info.AUTHORS[0][1]
        assert dialog._open_link(target) is True
        assert dialog.opened_links == [target]
        assert opened[0].toString() == target

    def test_open_link_falls_back_to_xdg_email(self, dialog, monkeypatch):
        """Minimal desktops without a Qt mail handler still work."""
        monkeypatch.setattr(QDesktopServices, "openUrl", lambda _url: False)
        calls = []
        monkeypatch.setattr("about_dialog.shutil.which",
                            lambda program: "/usr/bin/" + program)
        monkeypatch.setattr(
            "about_dialog.subprocess.Popen",
            lambda cmd, **_kw: calls.append(cmd),
        )
        email = app_info.AUTHORS[1][1]
        assert dialog._open_link("mailto:" + email) is True
        assert calls == [["xdg-email", email]]
        # A plain web link falls back to xdg-open with the raw URL.
        assert dialog._open_link(app_info.REPOSITORY_URL) is True
        assert calls[-1] == ["xdg-open", app_info.REPOSITORY_URL]

    def test_open_link_reports_failure_without_handler(
            self, dialog, monkeypatch):
        monkeypatch.setattr(QDesktopServices, "openUrl", lambda _url: False)
        monkeypatch.setattr("about_dialog.shutil.which", lambda _program: None)
        assert dialog._open_link("mailto:nobody@example.invalid") is False


class TestMainWindowIntegration:
    """Wire-up inside MainWindow: window icon, About button, F1."""

    @pytest.fixture
    def service(self, tmp_path):
        from project_service import ProjectService
        return ProjectService(projects_dir=str(tmp_path / "projects"))

    @pytest.fixture
    def window(self, qapp, service):
        from main_window import MainWindow
        w = MainWindow(service)
        yield w
        w.close()

    def test_window_icon_is_set(self, window):
        assert not window.windowIcon().isNull()

    def test_about_button_outside_nav(self, window):
        assert hasattr(window, "about_btn")
        assert "about" not in window.nav_buttons
        assert len(window._nav_defs) == 5
        assert window.views.count() == 5
        assert window.about_btn.isEnabled()

    def test_about_button_opens_dialog(self, window, monkeypatch):
        opened = []
        monkeypatch.setattr(
            "main_window.AboutDialog.exec",
            lambda self: opened.append(self) or 0,
        )
        window.about_btn.click()
        assert len(opened) == 1
        assert isinstance(window.about_dialog, AboutDialog)

    def test_f1_shortcut_opens_dialog(self, window, monkeypatch):
        opened = []
        monkeypatch.setattr(
            "main_window.AboutDialog.exec",
            lambda self: opened.append(self) or 0,
        )
        assert window._about_shortcut.key().toString() == "F1"
        window._about_shortcut.activated.emit()
        assert len(opened) == 1

    def test_about_available_without_project(self, window):
        """About is informational: no project needed."""
        assert window.project is None
        assert window.about_btn.isEnabled()
