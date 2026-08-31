# ROADMAP — Teleprompter Pro

> Real-world usage context: **the computer is used to read the script** and **the phone is used to record the video**.
> This means that during recording, hands are occupied and the phone is not available for keyboard input.
> This single fact shapes most of the priorities below (remote control > keyboard-only controls).

---

## 🎉 Project Completed! (2026-08-30)

| Phase | Status | Date |
|-------|--------|------|
| Phase 0 — Groundwork | ✅ Completed | 2026-08-30 |
| Phase 1 — Controls & UX | ✅ Completed | 2026-08-30 |
| Phase 2 — Remote Control | ✅ Completed | 2026-08-30 |
| Phase 3 — Voice Sync | ✅ Completed | 2026-08-30 |
| Phase 4 — Packaging | ✅ Completed | 2026-08-30 |
| Phase 5 — Polish & Tests | ✅ Completed | 2026-08-30 |

---

## Phase 0 — Groundwork ✅

- [x] Split `telepromt.py` into modules: `main.py`, `ui.py`, `config.py`, `scripts/`
- [x] Move script to `scripts/current_script.txt`, loaded by path or CLI argument
- [x] Add `requirements.txt` with dependencies
- [x] Add `README.md` with usage instructions
- [x] Migrate from tkinter to PyQt6 for better Wayland/X11 compatibility

---

## Phase 1 — Controls & Reader UX ✅

- [x] **Initial countdown** (3-2-1) before scrolling starts
- [x] **Quick reset** (`Home` or `R`): return text to beginning
- [x] **Progress indicator**: progress bar with percentage and estimated remaining time
- [x] **Estimated duration calculation** based on configurable WPM
- [x] **Configuration persistence** (`config.json`)
- [x] **Script selector**: file dialog with `O`
- [x] **Horizontal guide line**: toggle with `G`
- [x] **Horizontal mirror mode** (configurable in config.json)
- [x] Shortcuts: `+`/`-` font size, `F` fullscreen, `Q` QR code

---

## Phase 2 — Phone Remote Control ✅

- [x] Flask + WebSocket server embedded in the app
- [x] Responsive HTML page for remote control
- [x] QR code generated on `Q` press
- [x] Controls: Play/Pause, Speed +/-, Reset
- [x] Touch control (swipe up/down for speed)
- [x] Real-time progress bar

---

## Phase 3 — Intelligent Voice Synchronization ✅

- [x] Local speech recognition with Vosk
- [x] Automatic speed adjustment based on speaker's WPM
- [x] Visual sync indicators (green/gray/red)
- [x] `V` key to toggle voice synchronization
- [x] Callbacks for real-time WPM updates
- [x] Integration with existing scroll system

---

## Phase 4 — Packaging & Distribution ✅

- [x] ~~Migrate from tkinter to PyQt6~~ (already completed in Phase 0)
- [x] Package with PyInstaller for single executable
- [x] `build.sh` script for directory or onefile mode
- [x] `TeleprompterPro.spec` with advanced configuration
- [x] Automatic inclusion of scripts, templates, and dependencies

---

## Phase 5 — Polish & Tests ✅

- [x] Handle text edge cases (long words, manual line breaks, UTF-8)
- [x] Unit tests for speed calculation and time estimation
- [x] Validate corrupt or incomplete `config.json`
- [x] Test with long scripts (10+ minutes)

**Test summary:**
- 27 unit tests (100% passed)
- `tests/test_config.py` — 11 configuration tests
- `tests/test_speech_sync.py` — 7 voice sync tests
- `tests/test_edge_cases.py` — 9 edge case tests

---

## Project Structure

```
teleprompter/
├── main.py                    # Entry point
├── ui.py                      # Teleprompter class (PyQt6)
├── config.py                  # Persistent configuration
├── remote_server.py           # Flask server for remote control
├── speech_sync.py             # Voice sync with Vosk
├── build.sh                   # Build script
├── TeleprompterPro.spec       # PyInstaller configuration
├── templates/
│   └── remote.html            # Remote control page
├── tests/
│   ├── test_config.py         # Configuration tests
│   ├── test_speech_sync.py    # Sync tests
│   └── test_edge_cases.py     # Edge case tests
├── scripts/
│   ├── current_script.txt     # Default script
│   └── long_script_example.txt # Long test script
├── model-es/                  # Vosk model (downloaded)
├── config.json                # User preferences (generated)
├── requirements.txt
├── .gitignore
├── ROADMAP.md                 # This file
└── README.md
```

---

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Space` | Play/Pause with countdown |
| `↑` / `↓` | Speed ±1 |
| `Ctrl + ↑/↓` | Speed ±5 |
| `Shift + ↑/↓` | Speed ±10 |
| `Home` / `R` | Reset to beginning |
| `+` / `-` | Font size |
| `F` | Toggle fullscreen |
| `O` | Open script selector |
| `G` | Show/hide guide line |
| `Q` | Show QR code |
| `V` | Toggle voice sync |
| `Escape` | Exit (saves config) |

---

## Feature Summary

| Feature | Status |
|---------|--------|
| PyQt6 UI | ✅ |
| 3-2-1 Countdown | ✅ |
| Progress bar | ✅ |
| Speed control (±1, ±5, ±10) | ✅ |
| Script selector | ✅ |
| Guide line | ✅ |
| Mirror mode | ✅ |
| Remote control (Flask + QR) | ✅ |
| Voice sync (Vosk) | ✅ |
| Configuration persistence | ✅ |
| PyInstaller packaging | ✅ |
| 27 unit tests | ✅ |
| Complete documentation | ✅ |
