# Phase 11 — Quality and accessibility

Status: **in progress** (quality groundwork landed together with the
About dialog and the i18n pass).

## What was built

A consistency and hardening pass over the whole codebase before the
release. It groups three kinds of work: developer-facing quality
(rules, linting, docs), user-facing accessibility (keyboard, HiDPI,
translatability), and the reproducible test baseline that guards every
future change.

### New modules

| Module | Responsibility |
|---|---|
| `app_info.py` | Single source of truth for metadata: version, both authors + e-mail, license, repository URL, technology list, icon file name. Consumed by `about_dialog.py`, `setup.py`, tests and (via `paths.py`) the window icon. |
| `about_dialog.py` | `QDialog` with a two-column layout: left = large centered `QSvgWidget` (256×256, the app icon); right = title + version, short description, *Technologies*, *Authors* (copyright lines with **clickable** `mailto:` e-mails) and *License* with a GNU link. E-mails open the system mail client (`QDesktopServices`, falling back to `xdg-email`). |
| `tests/test_about_dialog.py` | 56 tests: both authors + exact e-mails, version synced with `pyproject.toml` via `tomllib`, valid SVG (parses + has expected `inkscape:label` layers), `QSvgWidget` sized ≥ 200 px and centered, each `mailto:` anchor points at the right address. |

### Integration

- `main_window.py` and the legacy `ui.py` both set the window icon
  (`resources/icons/teleprompter-pro.svg`) and open the About dialog
  from a sidebar **About** button plus the `F1` shortcut (kept outside
  `_nav_defs`/`nav_buttons` so `test_five_views` still holds).
- The icon `resources/icons/teleprompter-pro.svg` was redesigned to a
  512×512 SVG with `inkscape:label`/`id` per object and no
  `<style>`/filters/masks, so it stays editable in Inkscape while
  rendering crisply at any size through `QtSvg`.

## Key decisions

- **English-first source strings** (`docs/I18N.md`): every translatable
  string goes through `tr()`; the Spanish text the user wants in the
  About dialog therefore arrives as a `.qm` translation, not hardcoded.
- **Mail opening** intentionally prefers `QDesktopServices.openUrl`
  and only falls back to a `xdg-email` subprocess, so a desktop without
  a `mailto:` handler still opens a composer.
- The About button lives OUTSIDE the navigation model to preserve the
  exact five-view invariant tested by `test_five_views`.
- Packaging now ships `resources/` and `translations/` (previously the
  icon and any `.qm` never reached the binary or the `.deb`).

## Acceptance criteria (ROADMAP Phase 11)

- ✅ `ruff check .` → All checks passed.
- ✅ `python3 -m pytest tests/ -q` → suite green (`443 total` in the
  README; camera tests skip without hardware).
- ✅ HiDPI: the window and About icons are `.svg` (resolution
  independent) rendered via `QtSvg`.
- ✅ Keyboard navigation: About reachable via `F1` and a real button.
- ✅ Full suite translatable (`translation/teleprompter_es.ts` passes
  `pylupdate6`/`lrelease` without dropping messages).
- ✅ Spanish-language code residue in `config.py`/`paths.py`/docstrings
  cleaned to match the English-first policy.
- ✅ Release checklist documented (5-minute soaks, USB webcam unplug,
  VLC playback verification).

## Tests

- `tests/test_about_dialog.py` (56) — see module table above.
- Full-suite status: all existing + new tests pass under
  `QT_QPA_PLATFORM=offscreen`.
- `ruff check .` → All checks passed.
- `translations/teleprompter_es.ts` message count kept in sync via
  `pylupdate6` (no orphaned/unreferenced message losses).

## Known limitations

- Voice model (`Vosk`) and `sounddevice` are OPTIONAL at runtime
  (`try/except ImportError` in `speech_sync.py`), so the About
  technology list shows them as used technologies even when the user
  has not installed the model.
- `mailto:` always uses `mailto:` — a webmail-first workflow (e.g.
  Gmail) is out of scope; the OS mail client wins.

## Next phase

Phase 12 — Linux distribution: finalize the Debian packaging,
PyInstaller binary build and the icons/manpages so `dpkg-buildpackage`
produces an installable `.deb` from a clean tree.
