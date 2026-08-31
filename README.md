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

## 🚀 Installation

```bash
# 1. Clone the repository
git clone https://github.com/wachin/teleprompter.git
cd teleprompter

# 2. (Optional) Create virtual environment
python3 -m venv venv
source venv/bin/activate  # Linux/macOS
# venv\Scripts\activate   # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run
python3 main.py
```

### Install voice model (optional)

To use voice synchronization, download the Spanish model:

```bash
wget https://alphacephei.com/vosk/models/vosk-model-es-0.42.zip
unzip vosk-model-es-0.42.zip
mv vosk-model-es-0.42 model-es
```

---

## 📖 Step-by-step User Manual

### 1. Prepare your script

Write or paste your speech in a plain text file (`.txt`) inside the `scripts/` folder:

```
teleprompter/scripts/
├── current_script.txt    ← default script
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
├── main.py              # Entry point
├── ui.py                # Teleprompter class (PyQt6 UI)
├── config.py            # Cross-platform configuration
├── remote_server.py     # Flask server for remote control
├── speech_sync.py       # Voice sync with Vosk
├── build.sh             # Build script
├── TeleprompterPro.spec # PyInstaller config
├── templates/
│   └── remote.html      # Remote control page
├── tests/
│   ├── test_config.py
│   ├── test_speech_sync.py
│   └── test_edge_cases.py
├── scripts/
│   ├── current_script.txt
│   └── long_script_example.txt
├── model-es/            # Vosk model (downloaded)
├── requirements.txt
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

See [ROADMAP.md](ROADMAP.md) for planned improvements.

**All phases completed:**
- ✅ Phase 0: Base refactor and modularization
- ✅ Phase 1: Countdown, progress, script selector, guide line
- ✅ Phase 2: Phone remote control with Flask and QR
- ✅ Phase 3: Intelligent voice synchronization (Vosk)
- ✅ Phase 4: Packaging with PyInstaller
- ✅ Phase 5: Polish and 27 unit tests

---

## 📄 License

MIT
