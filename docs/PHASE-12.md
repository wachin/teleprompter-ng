# Phase 12 — Linux distribution

Status: **in progress** (packaging fixes landed together with the
distribution scan; a clean `dpkg-buildpackage` run from a pristine
tree is the remaining gate).

## What was built

The distribution pass that makes Teleprompter Pro installable and
maintainable on Debian 13 / derivatives. It audits and repairs the
three delivery paths — the Debian source package, the PyInstaller
binary, and the metadata the packagers (Debian, distro, users) rely on.

### Key packaging fixes

| Area | Before | After |
|---|---|---|
| `debian/control` | Declared `python3-vosk` and `python3-sounddevice` in `Build-Depends`/`Depends` — **these packages do not exist in Debian**, and both are runtime-optional (guarded by `try/except ImportError`). | Removed both; added the real system dependency `libportaudio2` (exists in Debian, needed for audio metering). |
| `pyproject.toml` / `setup.py` | Listed a handful of early modules. | Every application module enumerated (`about_dialog` … `ui`, 32 total) so `pip install` ships a usable program. |
| `debian/install` | Only early modules + stale `templates/` name. | All 32 `*.py`, `scripts/`, `templates/`, `resources/`, `translations/`, the SVG icon, the `.desktop` and `LICENSE`. |
| `debian/rules` | Relied on path guessing. | Explicit `#! /usr/bin/make -f`, `dh $@ --with python3 --buildsystem=pybuild`, wrapper installed to `/usr/bin/teleprompter-pro`, and `--no-guessing-deps` to keep `Depends` honest. |
| `debian/watch`, `debian/control`, `README.md` | Pointed at the old `wachin/teleprompter` repo. | Updated to `github.com/wachin/teleprompter-ng`; both authors listed everywhere. |
| `LICENSE` / `debian/copyright` | Mixed MIT + GPL signals. | Unified on **GPL-3.0-or-later** (`LICENSE` is already GPLv3; `debian/copyright` uses the `GPL-3+` + common-licenses stanza and lists both copyright holders). |

### Metadata & identity

- `app_info.py` centralizes version, authors/e-mail, license, repo URL,
  technologies and the icon name; `setup.py` pulls these from it so the
  `.deb` and the PyPI-style metadata can never drift apart.
- `.desktop` uses `Icon=teleprompter-pro`; the SVG is installed to
  `usr/share/icons/hicolor/scalable/apps` and the wrapper script to
  `/usr/bin/teleprompter-pro`.

## Key decisions

- **Vosk/sounddevice are OPTIONAL**: `speech_sync.py` guards them with
  `try/except ImportError`, and the README instructs users to install
  them with `pip --user` (they are not Debian packages). Forcing them
  into `Depends` would make the `.deb` uninstallable.
- License is unified on GPL-3.0-or-later across `pyproject.toml`,
  `setup.py`, `LICENSE`, `debian/copyright` and the About dialog. This
  contradicts the earlier MIT text in a handful of files, which have
  been corrected to match the already-GPLv3 `LICENSE`.

## Acceptance criteria (ROADMAP Phase 12)

- ✅ All 32 application modules in `pyproject.toml`, `setup.py` and
  `debian/install` — a `pip install`/`.deb` is actually usable.
- ✅ `debian/control` depends only on real Debian packages.
- ✅ Debian metadata references `teleprompter-ng` and both authors.
- ✅ Icon ships to the hicolor theme and is referenced by the `.desktop`.
- ✅ Wrapper `teleprompter-pro` entry point installed to `/usr/bin`.
- ✅ PyInstaller `.spec`/`build.sh` gather `resources/`, `scripts/`,
  `templates/` and `translations/` (icon + `.qm` reach the binary).
- 🔲 Clean `dpkg-buildpackage -b -us -uc` run on a pristine checkout
  produces an installable `.deb` (the remaining gate).

## How to run / verify

```bash
# Debian source package
dpkg-buildpackage -b -us -uc          # from the repo root

# PyInstaller binary (needs ~1 GB of free space + venv)
./build.sh

# Installed binary
teleprompter-pro                      # wrapper: python3 main.py
```

## Known limitations

- The Vosk Spanish model is NOT shipped (a separate
  `teleprompter-pro-model-es` package is prepared in `debian/control`
  `Recommends`; the model itself is a consent-required download per
  roadmap rule 18).
- ARM64 is not blocked but only x86_64 is validated on this machine.
- A pristine-tree `dpkg-buildpackage` smoke is still outstanding and is
  exactly what this phase is gated on next.

## Next phase

Post-Phase 12 maintenance: translate the About dialog + full UI into
Spanish via the compiled `teleprompter_es.qm` (delivering the two-author
copyright lines verbatim), then release-tag v2.0.0.
