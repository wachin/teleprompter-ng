# Teleprompter Pro

A desktop teleprompter for presentations and recordings. Designed for a real-world workflow: **the computer reads the script** and **the phone records the video**.

**Cross-platform:** Works on Windows, Linux, and macOS.

---

## 📦 Requirements

- Python 3.10+
- PyQt6 (installed via pip)
- Same WiFi network (for phone remote control)
- Microphone (for voice sync, optional)

---

## 🛠️ Installation and dependencies

Everything needed to run and test this program on **Debian 13 (trixie)**
and derivatives (Ubuntu included). Two ways to try it:

- **Option A — system packages, no venv** (recommended): the way the
  program is developed and tested on the reference machine. Run it
  directly with `python3 main.py` after installing the apt packages.
- **Option B — venv**: an isolated environment for developers who
  prefer pip-managed dependencies.

### Option A — Debian/Ubuntu packages, no venv (recommended)

```bash
# 1. Install the dependencies (Debian 13 / Ubuntu 22.04+)
sudo apt install \
    python3 python3-venv python3-pip \
    python3-pyqt6 python3-pyqt6.qtmultimedia \
    python3-opencv \
    python3-flask python3-flask-socketio python3-qrcode \
    python3-numpy python3-pil \
    python3-pytest python3-pytestqt \
    ffmpeg \
    v4l-utils \
    pulseaudio-utils \
    libportaudio2 portaudio19-dev

# 2. Vosk and sounddevice have no Debian package: install them
#    for your user (no sudo needed).
#    Debian 13 and recent Ubuntu mark the system Python as
#    externally managed; --break-system-packages only lets pip
#    write into your user site (~/.local), it does NOT touch the
#    system packages.
pip install --user --break-system-packages vosk sounddevice

# 3. Run — no virtual environment required
python3 main.py
```

The optional voice/subtitle model goes in `models/model-es`
(see [Install voice model](#install-voice-model-optional) below).

### Option B — venv (alternative for developers)

Some developers prefer an isolated environment. Everything works the
same; only the Python packages come from PyPI instead of Debian:

```bash
python3 -m venv venv
source venv/bin/activate          # Linux/macOS
# venv\Scripts\activate          # Windows
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

ffmpeg, v4l-utils and the other system tools are still needed
(option A installs them too); inside the venv the system-wide
`vosk`/`sounddevice` (installed with `pip install --user`) are not
visible — install them inside the venv as well:

```bash
pip install vosk sounddevice
```

To run inside the venv, activate it first in every session:

```bash
source venv/bin/activate
python3 main.py
```

### Package reference table

| Package (apt name) | PyPI name | Purpose | Phase |
|---|---|---|---|
| `python3` | — | Interpreter (≥ 3.10) | All |
| `python3-pyqt6` | `PyQt6` | Native user interface | All |
| `python3-pyqt6.qtmultimedia` | `PyQt6-Multimedia` | Embedded review player (QMediaPlayer); ffplay fallback without it | Review / Editor |
| `python3-opencv` | `opencv-python` | Camera capture (V4L2) | Camera |
| `python3-flask` | `flask` | Local remote-control server | Remote |
| `python3-flask-socketio` | `flask-socketio` | Real-time WebSocket events | Remote |
| `python3-qrcode` | `qrcode[pil]` | QR code generation | Remote |
| `python3-numpy` | `numpy` | Numeric operations (audio/video) | Voice / Camera |
| `python3-pil` | `Pillow` | Image handling | Branding |
| `ffmpeg` | — | Recording muxing, probing, silence detection, segment export | Recording / Editor / Subtitles |
| `v4l-utils` | — | Camera detection and diagnostics (`v4l2-ctl`) | Camera |
| `pulseaudio-utils` | — | Audio device diagnostics (`pactl`) | Audio |
| `libportaudio2` + `portaudio19-dev` | — | PortAudio backend for `sounddevice` | Voice |
| — | `vosk` | Local speech recognition (no apt package; install via pip) | Voice / Subtitles |
| — | `sounddevice` | Microphone capture via PortAudio (no apt package; install via pip) | Voice |
| `python3-pytest` | `pytest` | Test framework | Development |
| `python3-pytestqt` | `pytest-qt` | Qt widget testing | Development |
| — | `ruff` | Linter and formatter (install via pip) | Development |
| `mypy` | `mypy` | Gradual type checking | Development |
| — | `pyinstaller` | Binary packaging, optional | Distribution |

Notes:

- `vosk` and `sounddevice` have **no Debian package**; they are installed
  with `pip install --user vosk sounddevice` (they are already present on
  the reference machine).
- `pytest-qt` exists in Debian under the name `python3-pytestqt`.
- The Vosk Spanish voice model is a separate download (see
  [README](#install-voice-model-optional)); place it in `models/model-es`.

### Quick verification

After installing (either option), verify the environment — this
command works the same inside and outside a venv:

```bash
python3 -c "import PyQt6, flask, flask_socketio, qrcode, numpy, vosk, sounddevice; print('OK')"
ffmpeg -version | head -1
v4l2-ctl --list-devices
python3 -m pytest tests/ -q   # 387 tests; camera tests need hardware
```

---

## 🚀 Running

**Without venv (option A):**

```bash
# 1. Clone the repository
git clone https://github.com/wachin/teleprompter.git
cd teleprompter

# 2. Run (project mode — default)
python3 main.py

# 2b. Legacy full-screen reading mode
python3 main.py --read
python3 main.py scripts/mission_speech.txt   # a positional file also works
```

**Inside the venv (option B):** activate it first, then the same
commands:

```bash
source venv/bin/activate   # once per session
python3 main.py
```

### Install voice model (optional)

Voice sync and automatic subtitles need the Spanish Vosk model.
Two options:

```bash
# Small model (~40 MB download; takes ~30-35 minutes on slow
# connections, ~2 s on fast ones). Enough for word-timing sync and
# draft subtitles.
mkdir -p models
wget https://alphacephei.com/vosk/models/vosk-model-small-es-0.42.zip
unzip vosk-model-small-es-0.42.zip
mv vosk-model-small-es-0.42 models/model-es
rm vosk-model-small-es-0.42.zip

# Full model (1.3 GB): better accuracy for final subtitles. Only
# needed if the small one misrecognizes your speech.
wget https://alphacephei.com/vosk/models/vosk-model-es-0.42.zip
unzip vosk-model-es-0.42.zip
mv vosk-model-es-0.42 models/model-es
rm vosk-model-es-0.42.zip
```

> Download time note: on a slow connection the small model can take
> **~35 minutes**; the full model can take hours. The app never
> downloads models by itself — you decide (Roadmap rule: no model
> downloads without consent).

---

## 🗂️ Project mode (Phase 1)

By default the app now opens in **project mode**: a sidebar navigates
between Home, Script, Camera, Review, and Editor (the last three are
placeholders for upcoming phases).

Projects live in `~/TeleprompterProjects` as self-contained
`.bigprompt` folders:

```text
MyProject.bigprompt/
├── project.json        # settings: only relative paths
├── scripts/script.txt  # the script (UTF-8)
├── media/raw/          # original recordings (never overwritten)
├── media/exports/      # exported files
├── media/assets/       # logos, intro/outro, b-roll
├── subtitles/
└── thumbnails/
```

From Home you can **create, open, duplicate, rename, and delete**
projects. The Script view offers a text editor with live word count,
estimated duration (adjustable WPM), file import (`.txt`, `.md`,
`.html`, `.docx`), and six starter templates: tutorial, presentation,
class/lesson, news segment, product review, and 30-second ad.

The classic full-screen teleprompter is still available:

```bash
python3 main.py --read
```

---

## 📖 Step-by-step User Manual

### 1. Prepare your script

Write or paste your speech in a plain text file (`.txt`) inside the `scripts/` folder:

```
teleprompter/scripts/
├── guion_actual.txt      ← default script (loaded by --read mode)
├── mission_speech.txt    ← your own scripts
└── presentation.txt
```

**Script tips:**
- Use short paragraphs (2-3 sentences max)
- Separate ideas with blank lines
- No rich formatting (bold, italic) — plain text only
- Save with UTF-8 encoding for accents and special characters

### 2. Run the teleprompter

**Load the default script:**
```bash
python3 main.py
```

**Load a specific script:**
```bash
python3 main.py scripts/mission_speech.txt
```

### 3. Control playback

| Key | Action | Description |
|-----|--------|-------------|
| `Space` | ▶ / ⏸ | Start with 3-2-1 countdown, or pause |
| `↑` | 🔼 | Increase speed (+1) |
| `↓` | 🔽 | Decrease speed (-1) |
| `Ctrl + ↑/↓` | ⚡ | Fast speed change (±5) |
| `Shift + ↑/↓` | ⚡⚡ | Very fast speed change (±10) |
| `Home` / `R` | 🔄 | Return to beginning of text |
| `+` / `-` | 🔤 | Increase/decrease font size |
| `F` | 🖥️ | Toggle fullscreen / windowed |
| `O` | 📄 | Open script selector |
| `G` | 📏 | Show/hide guide line |
| `Q` | 📱 | Show QR code for remote control |
| `V` | 🎤 | Toggle voice synchronization |
| `Escape` | ❌ | Close app (saves configuration) |

### 4. Phone remote control 📱

You can control the teleprompter from your phone without touching the computer.

**Steps:**
1. Make sure your computer and phone are on the **same WiFi network**
2. Press `Q` on the computer to show the QR code
3. Scan the QR code with your phone's camera
4. The remote control page will open in your phone's browser

**Remote control features:**
- ▶ **Play/Pause** with countdown
- 🔼 **Speed +/-** with large buttons
- 🔄 **Reset** to return to the beginning
- 📊 **Progress bar** in real-time
- 👆 **Touch control** (swipe up/down to change speed)

### 5. Voice synchronization 🎤

The teleprompter can listen to your voice and automatically adjust the speed.

**How it works:**
1. Press `V` to activate voice synchronization
2. The teleprompter listens to what you say through the microphone
3. It compares your speaking speed against the target WPM (configurable in `config.json`)
4. It automatically adjusts the scroll speed:
   - If you speak **fast** → increases speed
   - If you speak **slow** → decreases speed

**Visual indicators:**
- 🟢 Green = sync active
- ⚪ Gray = sync disabled
- 🔴 Red = voice model not available

### 6. Cross-platform configuration ⚙️

Preferences are automatically saved to `config.json` when you close the app. The location depends on your operating system:

| Platform | Configuration path |
|----------|-------------------|
| **Windows** | `%AppData%\TeleprompterPro\config.json` |
| **Linux** | `~/.config/TeleprompterPro/config.json` |
| **macOS** | `~/Library/Application Support/TeleprompterPro/config.json` |

**On Windows**, the full path is usually:
```
C:\Users\YourUsername\AppData\Roaming\TeleprompterPro\config.json
```

**On Linux:**
```
/home/yourusername/.config/TeleprompterPro/config.json
```

**On macOS:**
```
/Users/yourusername/Library/Application Support/TeleprompterPro/config.json
```

### 7. Configuration options

```json
{
  "font_size": 42,
  "text_color": "#FFD700",
  "bg_color": "black",
  "scroll_speed": 3,
  "margin_x": 200,
  "margin_y": 50,
  "mirror_mode": false,
  "fullscreen": true,
  "wpm": 150
}
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `font_size` | int | 42 | Font size |
| `font_family` | string | "Helvetica" | Font family |
| `text_color` | string | "#FFD700" | Text color (gold) |
| `bg_color` | string | "black" | Background color |
| `scroll_speed` | int | 3 | Scroll speed (remembered on close) |
| `margin_x` | int | 200 | Horizontal margin in pixels |
| `margin_y` | int | 50 | Vertical margin in pixels |
| `mirror_mode` | bool | false | Mirror text horizontally |
| `fullscreen` | bool | true | Open in fullscreen |
| `wpm` | int | 150 | Target WPM for voice sync |

---

## 🎨 Quick Customization

### Change colors

**Classic mode (gold on black):**
```json
"text_color": "#FFD700",
"bg_color": "black"
```

**High contrast (white on black):**
```json
"text_color": "#FFFFFF",
"bg_color": "black"
```

**Green on black (terminal style):**
```json
"text_color": "#00FF00",
"bg_color": "black"
```

### Mirror mode

If you mount a reflective glass in front of the phone camera:

```json
"mirror_mode": true
```

---

## 📁 Project Structure

```
teleprompter/
├── main.py              # Entry point (projects mode / --read mode)
├── main_window.py       # MainWindow + Home and Script views
├── project_service.py   # .bigprompt project format and lifecycle
├── text_import.py       # .txt/.md/.html/.docx import + WPM duration
├── templates_service.py # Script templates loader
├── ui.py                # Legacy full-screen Teleprompter (PyQt6)
├── config.py            # Cross-platform configuration
├── remote_server.py     # Flask server for remote control
├── speech_sync.py       # Voice sync with Vosk
├── paths.py             # Resource resolution (repo/PyInstaller)
├── logging_setup.py     # Structured logging
├── build.sh             # Build script
├── TeleprompterPro.spec # PyInstaller config
├── templates/
│   └── remote.html      # Remote control page
├── resources/
│   └── script_templates/  # 6 starter scripts (.txt + .json)
├── translations/
│   └── teleprompter_es.ts # Qt Linguist source (66 messages)
├── tests/               # 130 tests (pytest + pytest-qt)
├── scripts/
│   ├── guion_actual.txt
│   └── long_script_example.txt
├── docs/                # Phase reports + I18N guide
├── model-es/            # Vosk model (downloaded)
├── requirements.txt
├── requirements-dev.txt
├── .gitignore
├── ROADMAP.md
└── README.md
```

---

## ❓ Frequently Asked Questions

**Can I use a script in another language?**
Yes. The teleprompter fully supports UTF-8: accents, ñ, emojis, and any language.

**Where is my configuration saved?**
It depends on your operating system. See the "Cross-platform configuration" section above.

**Does it remember my last speed?**
Yes. Speed is automatically saved when you close the app and restored on startup.

**Does it work on Wayland?**
Yes. PyQt6 has better support than tkinter. If you have issues, press `F` to toggle windowed mode.

**How does remote control work?**
The teleprompter runs a local Flask server on port 5000. Scanning the QR opens a web page that communicates via WebSocket. Everything is local, no internet required.

**How does voice synchronization work?**
It uses Vosk (local speech recognition) to listen to your voice and compare it against the script. It automatically adjusts scroll speed based on your speaking pace. No internet required.

---

## 🗺️ Roadmap

See [ROADMAP.md](ROADMAP.md) for the full plan and
[docs/](docs/) for per-phase reports.

**Status of the new application plan:**
- ✅ Phase 0: Audit and code safety (41 tests) — see [docs/FASE-0.md](docs/FASE-0.md)
- ✅ Phase 1: PyQt6 base and project management (130 tests) — see [docs/PHASE-1.md](docs/PHASE-1.md)
- ⏭️ Phase 2: Live webcam (next)
- Phases 3-12: teleprompter overlay, controls/recording, audio+video
  capture, review/editor, subtitles, branding, optional local AI,
  export, quality, distribution

**Legacy features (pre-existing, kept working via `--read` mode):**
countdown, progress bar, script selector, guide line, mirror mode,
phone remote control (Flask + QR), voice sync (Vosk).

---

## 📄 License

MIT
