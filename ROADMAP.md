# ROADMAP.md — Teleprompter for Linux with camera and video creation workflow

> Document for a programming AI agent.

Objective: transform the existing project `teleprompter`/`Teleprompter Pro` into a Linux desktop application, written in **Python + PyQt6**, that combines teleprompter, webcam, recording, basic editing, subtitles, and publishing/export.

## 1. Context of the existing project

The current code already contains:

- PyQt6 interface in `ui.py`.
- Entry point in `main.py`.
- Persistent configuration in `config.py`.
- UTF-8 script loading from `.txt` files.
- Automatic scrolling with adjustable speed.
- 3-2-1 countdown.
- Progress bar, estimated time, and word counter.
- Guide line and mirror mode.
- Local remote control using Flask, Socket.IO, and QR code.
- Experimental voice sync using Vosk and `sounddevice`.
- Preliminary packaging with PyInstaller.
- Existing unit tests.

Before adding features, the agent must study the actual repository code, fix bugs, and preserve compatibility with the features that already work.

## 2. Desired outcome

The user must be able to complete this full workflow:

1. Create a project.
2. Write, paste, import, or generate a script.
3. Choose a built-in or USB webcam.
4. See themselves live inside the window.
5. Read the script superimposed over the camera image, near the lens.
6. Adjust text size, color, position, opacity, speed, and mirroring.
7. Record video and audio to a local file.
8. Review the recording.
9. Cut silences and unwanted segments.
10. Generate subtitles automatically.
11. Add logo, colors, intro, outro, music, and visual assets.
12. Export in the usual formats for YouTube, Instagram, TikTok, and LinkedIn.
13. Save the project to continue editing it later.
14. Control the recording and the teleprompter with keyboard, mouse, large buttons, and phone.

## 3. Mandatory technical principles

### 3.1 Platform

- First platform: Debian 13 and compatible derivatives.
- Initial architecture: x86_64; do not block ARM64 unnecessarily.
- Support X11 and Wayland whenever the libraries allow it.
- Do not depend on web services for basic features.
- Recording, teleprompter, preview, and local saving must work without Internet.

### 3.2 Interface

- Use **PyQt6** exclusively for the native interface.
- Use signals and slots to communicate threads and widgets.
- Do not block the main Qt thread.
- Keep a clear, translatable, accessible interface.
- Add dark mode and high-contrast controls.
- Use `QSettings` or XDG-compatible configuration; keep migration from the current `config.json`.

### 3.3 Architecture

Separate the program into modules with clear responsibilities:

```text
teleprompter/
├── app/
│   ├── main.py
│   ├── main_window.py
│   ├── models/
│   ├── services/
│   │   ├── camera_service.py
│   │   ├── audio_service.py
│   │   ├── recording_service.py
│   │   ├── subtitle_service.py
│   │   ├── export_service.py
│   │   └── project_service.py
│   ├── widgets/
│   │   ├── camera_preview.py
│   │   ├── teleprompter_overlay.py
│   │   ├── recording_controls.py
│   │   ├── script_editor.py
│   │   └── editor_timeline.py
│   ├── dialogs/
│   └── resources/
├── scripts/
├── templates/
├── tests/
├── docs/
├── pyproject.toml
├── requirements.txt
├── requirements-dev.txt
├── README.md
└── ROADMAP.md
```

The agent may keep current names during a gradual migration, but must avoid having all the logic remain in `ui.py`.

## 4. Dependencies allowed on Debian 13

### 4.1 Preference for Debian packages

Use libraries available in the Debian 13 repositories first, and document their `apt` names where applicable. Do not manually compile multimedia components if a Debian-maintained solution exists.

Candidate system packages:

```text
python3
python3-pyqt6
python3-opencv
python3-numpy
python3-pil
python3-flask
python3-flask-socketio
python3-qrcode
python3-pytest
python3-venv
ffmpeg
v4l-utils
pulseaudio-utils or pipewire-pulse
portaudio19-dev
libportaudio2
```

The agent must verify the exact names available on Debian 13 before setting them as requirements. Do not assume that all Python modules have exactly the same name in `apt` and in PyPI.

### 4.2 Acceptable pip packages

Use `pip` inside a virtual environment; never irresponsibly modify the system Python. Evaluate:

- `PyQt6` if the Debian version is not enough.
- `opencv-python` only if `python3-opencv` does not offer what is needed.
- `sounddevice` or `soundcard` for audio.
- `vosk` for the existing local recognition.
- `faster-whisper` as an optional subtitle backend, if performance and size are acceptable.
- `qrcode` for remote control.
- `pytest`, `pytest-qt`, `ruff`, `mypy`, and development tools.
- `pyinstaller` only as a distribution option, not as a replacement for Debian packaging.

Each dependency must have a justification, a compatible license, and an optional alternative whenever possible.

### 4.3 Multimedia

Prefer **FFmpeg** executed as an external process for muxing, conversion, audio extraction, scaling, and export. Do not implement codecs manually.

Use OpenCV or Qt Multimedia for camera capture, according to real testing on Debian 13. The solution must:

- Detect V4L2 cameras.
- Show the available `/dev/video*` devices.
- Choose a compatible resolution and FPS.
- Clearly report when a camera is busy or has no permissions.
- Avoid claiming that a USB camera works without checking its capabilities.

## 5. Functional model of the application

### 5.1 Main screens

Implement these views:

1. **Home/Projects**: create, open, duplicate, rename, and delete projects.
2. **Script**: text editor with word counter, estimated duration, search, import, and saving.
3. **Camera**: live preview with the teleprompter superimposed.
4. **Recording**: controls, countdown, camera/microphone indicators, and status.
5. **Review**: play, re-record, or move on to the editor.
6. **Editor**: trimming, subtitles, branding, audio, and export.
7. **Settings**: camera, microphone, language, shortcuts, privacy, and storage.

### 5.2 Persistent project

Create a versioned project format, for example:

```text
MyProject.bigprompt/
├── project.json
├── scripts/
│   └── script.txt
├── media/
│   ├── raw/
│   ├── exports/
│   └── assets/
├── subtitles/
└── thumbnails/
```

`project.json` must store, at minimum:

- Schema version.
- Name and creation date.
- Relative path of the script.
- Teleprompter settings.
- Chosen camera and microphone.
- Resolution and FPS.
- Recorded clips.
- Cut segments.
- Subtitle style.
- Branding.
- Music and audio levels.
- Export history.

Never store absolute paths when a relative path is sufficient.

## 6. Implementation phases

## Phase 0 — Audit and code safety

### Objective

Establish a reliable base before adding features.

### Tasks

- Read all existing files; do not overwrite useful functions without analyzing them.
- Run the current tests and record the initial state.
- Fix obvious bugs, especially:
  - Thread and audio resource management.
  - Actual stopping of `RawInputStream`.
  - Updating PyQt6 widgets from secondary threads.
  - Path compatibility when packaging.
  - Loading templates and models from installed paths.
  - Real implementation of mirror mode; do not confuse layout direction with visual transformation.
  - Script selection that depends on the working directory.
- Remove fixed secrets such as a static `SECRET_KEY` if they are not needed.
- Add structured logging with DEBUG, INFO, WARNING, and ERROR levels.
- Add permission checks for camera, microphone, and directories.

### Acceptance criteria

- Existing tests pass.
- The application starts from the repository and from another folder.
- The application does not freeze when toggling voice or closing a recording.
- Device failures are explained in Spanish and offer a corrective action.

## Phase 1 — PyQt6 base and project management

### Tasks

- Create a `MainWindow` with navigation between Home, Script, Camera, Review, and Editor.
- Implement `ProjectService`.
- Add new/open/save/close project.
- Migrate the current configuration to the new model.
- Keep `.txt` import and UTF-8.
- Add optional import of `.md`, `.html`, and `.docx` only if a reliable dependency is available; the text must be cleaned without introducing dangerous formatting.
- Add script templates: tutorial, presentation, class, news, review, and advertisement.
- Calculate the approximate duration using WPM and display it next to the counter.

### Acceptance criteria

- A project opens in another session with all its settings.
- A script with ñ, accents, emojis, and line breaks is preserved correctly.
- Temporary files are kept separate from final files.

## Phase 2 — Live webcam

### Objective

Show the built-in or USB camera image and superimpose the script.

### Tasks

- Detect cameras through V4L2 and/or OpenCV.
- Show name, device, resolution, and FPS.
- Allow choosing the built-in or USB camera.
- Implement `CameraService` in a thread-safe way.
- Show the image in a PyQt6 widget with correct BGR/RGB conversion and scaling that preserves the aspect ratio.
- Allow selecting resolution and FPS among the modes the camera actually offers.
- Add brightness, contrast, and preview mirror controls when supported.
- Show messages for:
  - Camera not found.
  - Permission denied.
  - Camera in use by another application.
  - Unsupported format.
- Release the camera when switching devices, closing the window, or starting another application.

### Acceptance criteria

- It works with the built-in camera and with a tested USB V4L2 camera.
- The selector does not show as available resolutions that the device does not support.
- The preview remains smooth without blocking the interface.

## Phase 3 — Teleprompter superimposed on the camera

### Objective

Let the user see themselves and read the text near the lens.

### Tasks

- Create `TeleprompterOverlay` as a layer over the camera view.
- Keep the text in a configurable region close to the lens.
- Allow:
  - Font size.
  - Font family.
  - Bold.
  - Color.
  - Transparent, semi-transparent, or solid background.
  - Column width.
  - Line spacing.
  - Alignment.
  - Guide line.
  - Margins.
  - Horizontal mirroring of the text.
  - Vertical and horizontal position.
  - Interface inversion for reflective glass accessories.
- Add two modes:
  - **Reading**: large text, minimal controls.
  - **Camera**: video and teleprompter visible with controls.
- Implement smooth scrolling independent of the refresh rate.
- Use monotonic time and speed in words per minute when possible, not just arbitrary pixels.
- Add markers and jumping to paragraphs.
- Allow pausing, resuming, restarting, and manual scrolling.

### Acceptance criteria

- The text is legible over light and dark backgrounds.
- The user can place the text near the camera without completely hiding their face.
- The speed remains stable over several minutes.
- The current shortcuts still work and visible buttons also exist.

## Phase 4 — Controls, countdown, and remote control

### Tasks

- Keep Space, arrows, Ctrl/Shift, Home/R, +/-, F, O, G, Q, and V, documenting them in the interface.
- Add large buttons for Play/Pause, speed, restart, and jumping.
- Configurable countdown: 0, 3, 5, or 10 seconds.
- Add an optional USB/HID pedal if it can be implemented without depending on proprietary hardware.
- Improve the local server:
  - Bind it to the local network by default only when the user activates it.
  - Show IP and port.
  - Generate QR.
  - Add a temporary token or pairing code.
  - Shut the server down on close.
  - Do not expose it to the Internet.
  - Validate commands and limit their frequency.
- Mobile remote control:
  - Play/Pause.
  - Speed +/-.
  - Restart.
  - Progress.
  - Countdown.
  - Button to start and stop recording.
  - Connection indicator.

### Acceptance criteria

- The remote control works on the same Wi-Fi network without any cloud.
- An unauthorized phone cannot control the session if pairing is enabled.
- The application keeps working if the phone disconnects.

## Phase 5 — Audio capture and video recording

### Objective

Record camera and microphone, synchronized, into a playable file.

### Tasks

- Implement microphone selection through PipeWire/PulseAudio/ALSA depending on availability.
- Show a level meter and detect clipping.
- Allow choosing camera and microphone separately.
- Add pre-flight checks for audio and video.
- Implement `RecordingService` with a frame queue and safe shutdown.
- Record in a reliable intermediate format, preferably through FFmpeg when it simplifies synchronization.
- Keep the original recording without destroying it.
- Add automatic naming with date and time.
- Show duration, available space, and recording status.
- Allow stopping, canceling, and recovering an incomplete recording when possible.
- Do not mix the teleprompter image into the final video by default; the text is an aid during recording.
- Offer an explicit option to embed the text if the user requests it.

### Acceptance criteria

- The recording has synchronized audio and video.
- Closing the window during a recording leaves no orphan FFmpeg processes.
- The original file can be played with VLC and FFplay.
- The user is informed before recording if there is no microphone or not enough space.

## Phase 6 — Review and non-destructive editor

### Tasks

- Create a review player with playback controls.
- Show thumbnail, duration, and clip size.
- Allow marking start/end and deleting segments.
- Add head and tail trimming.
- Add optional pause/silence removal, always with a preview.
- Keep non-destructive editing through a segment list in `project.json`.
- Allow re-recording a single segment only.
- Add undo/redo.
- Do not destroy the original until the user explicitly requests it.

## Phase 7 — Automatic subtitles

### Tasks

- Keep Vosk as the optional lightweight local backend.
- Add an optional backend based on Whisper/faster-whisper if it can be reasonably installed and run on Debian 13.
- Allow choosing language and model.
- Generate subtitles with timestamps.
- Import/export `.srt` and `.vtt`.
- Manually edit text and times.
- Highlight words or phrases.
- Choose position, typography, color, background, and a simple animation.
- Allow subtitles both as an editable track and as a final burn-in.
- Process in the background and show progress, cancellation, and model size.
- Do not download models without the user's clear consent.

### Acceptance criteria

- A Spanish-language video produces a reviewable `.srt`.
- Recognition errors can be corrected before exporting.
- The program explains when the model is not installed.

## Phase 8 — Branding and visual editing

### Tasks

- Create a local Brand Kit:
  - Logo.
  - Colors.
  - Available fonts.
  - Intro.
  - Outro.
  - Name and contact details.
- Add the logo as an overlay with position and opacity.
- Add titles, subtitles, and lower thirds.
- Add local images and B-roll clips.
- Add an optional free-asset library, without downloading content without authorization.
- Add local music with volume control and fades.
- Normalize audio levels with FFmpeg where appropriate.
- Add aspect ratios:
  - Vertical 9:16.
  - Horizontal 16:9.
  - Square 1:1.
- Add a crop preview for social media.
- Add simple autozoom based on cuts or positions, without promising face tracking until a reliable solution is implemented.

## Phase 9 — Optional local AI features

### Tasks

- Script assistant:
  - Create a draft from a topic.
  - Adjust tone.
  - Summarize.
  - Change duration.
  - Create title, description, and tags.
- Design the integration through adapters:
  - Local backend.
  - HTTP backend chosen by the user.
  - No mandatory provider.
- Always show whether the text leaves the computer.
- Request consent before sending scripts, audio, video, or images.
- Do not present an avatar, voice cloning, eye correction, or video generation feature as available until it is implemented, tested, and documented.
- If voice cloning or avatars are implemented, include consent controls, model deletion, and warnings against impersonation.

## Phase 10 — Export and publishing

### Tasks

- Create export profiles:
  - YouTube: 16:9.
  - TikTok/Reels/Shorts: 9:16.
  - LinkedIn: 16:9 or 1:1.
  - High-quality master file.
- Use FFmpeg with documented parameters.
- Allow choosing container, codec, resolution, FPS, bitrate, and folder.
- Show a size estimate when possible.
- Validate that the final file exists, has a reasonable size, and can be opened.
- Generate an optional thumbnail.
- Copy title, description, and hashtags to the clipboard or save them to a `.txt`/`.json`.
- Do not integrate direct social publishing until their APIs, authentication, limits, and policy changes have been studied.
- As a first version, offer local export and opening the output folder.

## Phase 11 — Quality, testing, and accessibility

### Unit tests

- Configuration and migrations.
- WPM and duration calculation.
- Path conversion.
- Project and recovery.
- Edit segments.
- Subtitle generation.
- FFmpeg command construction.
- Camera and microphone validation.

### Integration tests

- Built-in camera.
- USB camera.
- USB microphone.
- Camera change during the session.
- Recording of 1, 5, and 30 minutes.
- Camera disconnection.
- Microphone disconnection.
- Wayland and X11.
- HiDPI screen scaling.
- Long UTF-8 scripts.
- Local network and remote phone.

### Accessibility

- Configurable shortcuts.
- Keyboard navigation.
- Accessible labels for controls.
- Verifiable contrast.
- Control sizes sufficient for use while recording.
- Understandable error messages.
- Initial interface in Spanish, prepared for translations with Qt Linguist.

### Tools

- `pytest` and `pytest-qt`.
- `ruff`.
- Gradual `mypy`.
- Optional `pre-commit`.
- Coverage on critical modules.
- Testing on a real Debian 13 machine, not only on mocks.

## Phase 12 — Linux distribution

### Tasks

- Create reproducible installation with `pyproject.toml`.
- Keep `requirements.txt` and `requirements-dev.txt` separate.
- Document installation with Debian packages and with a virtual environment.
- Create a `.desktop` file and icon.
- Evaluate a `.deb` package with `dpkg-buildpackage` or equivalent.
- Keep AppImage as an optional distribution, without hiding camera and FFmpeg dependencies.
- Include voice models as a separate, documented download.
- Do not include large unnecessary models in the executable.
- Add version checking and project migration.

## 7. Implementation rules for the AI agent

1. Work in small, compilable phases.
2. Before changing a module, read its code and its tests.
3. Do not remove an existing feature without a compatible replacement or a documented migration.
4. Do not create pseudocode presented as finished code.
5. Every task must end with tests run and the result recorded.
6. Do not use network calls for basic local features.
7. Do not add dependencies just for convenience if a suitable Debian library exists.
8. Every heavy operation must run outside the main thread.
9. Never update Qt widgets directly from a worker thread; use signals.
10. Release camera, microphone, files, and external processes on both normal and exceptional paths.
11. Validate user input and project paths.
12. Use relative paths in projects and locally installed resources.
13. Separate original, temporary, and exported files.
14. Ask for confirmation before deleting originals or overwriting exports.
15. Document real hardware and system limitations.
16. Use the project's own names, for example `Teleprompter`, `BigPrompt`, or the name the maintainer confirms.
17. Keep the MIT license if the repository owner confirms it.
18. **Package installation rule (mandatory)**: whenever development requires installing a new package (`apt`, `pip`, or any other manager), the agent must **stop the process immediately and notify the maintainer**, stating the exact package name and the installation command. The maintainer is the only person who can install packages, because the administrator password must be entered. The agent must never try to install packages on its own, or request them indirectly. Until the package is installed and confirmed by the maintainer, the agent must limit itself to tasks that do not depend on it.

## 8. Format of each agent delivery

For each phase, the agent must report:

```text
Phase:
Objective:
Files modified:
New files:
Dependencies added:
Technical decisions:
Known limitations:
Tests run:
Test results:
How to run:
Next recommended task:
```

## 9. Recommended MVP order

The MVP must stop after completing these features:

- Modular PyQt6.
- Project and UTF-8 script.
- Built-in/USB camera selection.
- Live preview.
- Superimposed, scrolling text.
- Countdown.
- Camera and microphone recording.
- Review and basic trimming.
- Local export with FFmpeg.
- Secure mobile remote control on the local network.
- Documentation in Spanish.
- Hardware and software testing.

Do not start avatars, automatic publishing, or generative AI before the MVP records and exports correctly.

## 10. Definition of done

A feature is considered finished only when:

- It is implemented with real code.
- It is integrated into the interface.
- It has error handling.
- It has at least one appropriate test.
- It is documented in Spanish.
- It works on Debian 13 in a reproducible test.
- It does not block the interface.
- It releases its resources correctly.
- It does not break existing features.
- The limitation, if any, appears explicitly in the interface or the documentation.

## 11. First order to the AI agent

Start like this:

1. Audit the repository and list its files and responsibilities.
2. Run the existing tests.
3. Check which packages are available on Debian 13.
4. Propose a minimal migration from the current structure to the indicated architecture.
5. Implement only Phase 0.
6. Run the tests and show the changes.
7. Wait for the maintainer's approval before continuing with Phase 1.

The goal is to produce a native, local, verifiable, and maintainable Linux tool that first solves the essential flow: **script → camera → superimposed reading → recording → review → export**.
