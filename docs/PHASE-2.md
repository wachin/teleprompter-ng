# Phase 2 — Live webcam

Status: **completed** on 2026-09-03.

## What was built

The Camera view is now live: the user sees themselves inside the app,
chooses among the cameras really connected to the machine, and picks
only modes the device actually supports.

### New modules

| Module | Responsibility |
|---|---|
| `camera_service.py` | V4L2 enumeration via `v4l2-ctl` (with a glob fallback), real format parsing (`--list-formats-ext`), grouped UI modes, and a thread-safe `CameraWorker` (QThread + signals) with clear diagnostics for: missing device, permission denied (with the `usermod -aG video` hint), busy device, and unsupported/metadata-only nodes |
| `camera_preview.py` | `CameraPreview` widget: OpenCV BGR → RGB conversion, aspect-ratio-preserving letterboxed scaling (never stretched), optional preview mirror, "Camera off" placeholder |

### UI integration

- `CameraView` replaces the Phase-1 placeholder in `MainWindow`:
  camera selector (name + `/dev/videoN`), mode selector showing real
  capabilities (`1280x720 @ 30/10 fps (MJPG)`), Start/Stop, Mirror
  toggle, Refresh, and a status line.
- `MainWindow.closeEvent` releases the camera before the window dies —
  no device stays locked after quitting.
- `CameraService.stop()` waits up to 3 s for the capture thread; a
  failed `cap.read()` streak (10 consecutive) reports "lost signal"
  instead of hanging silently.

## Key decisions

- **v4l2-ctl is the source of truth** for enumeration and formats:
  the selector never shows a mode the device does not offer
  (acceptance criterion). OpenCV is used only for capture.
- **MJPG beats YUYV** on equal `(w, h, fps)` — compressed frames
  sustain higher resolutions; the rule lives in `_parse_formats`.
- **Device names with colons** ("Integrated_Webcam_HD: Integrate") are
  parsed correctly — first `": "` separates card name from bus info.
- **Worker → UI only via signals**: `frame_ready`/`error`/`started_ok`;
  no widget is touched from the capture thread (ROADMAP rule 9).
- **Lazy OpenCV import** inside `CameraWorker.start`: enumeration and
  the rest of the app work even where cv2 is absent.

## Acceptance criteria (ROADMAP Phase 2)

- ✅ Detects cameras through V4L2, shows name, device, resolution, FPS
- ✅ Choose between built-in/USB cameras (combo + Refresh)
- ✅ Thread-safe `CameraService`
- ✅ PyQt6 widget with correct BGR/RGB conversion and aspect-preserving scale
- ✅ Select resolution/FPS among modes the camera really offers
- ✅ Mirror control for the preview (brightness/contrast deferred to
  Phase 3 overlay settings — noted as limitation)
- ✅ Messages for: not found / permission denied / busy / unsupported
- ✅ Camera released on stop, device switch, and window close

Verified on the reference machine (Debian 13.6, Integrated_Webcam_HD):
MJPG 1280x720@30 and 9 grouped modes enumerated; 5+ frames/s painted
offscreen; `v4l2-ctl` re-queries the device after stop (no EBUSY).

## Tests

- **149 total pass** (130 previous + 19 new):
  - `tests/test_camera_service.py` (14): v4l2 output parsing (names,
    formats, MJPG/YUYV priority), error diagnostics for missing /
    permission / busy / metadata-only devices with mocks.
  - `tests/test_camera_integration.py` (5): real `/dev/video0` —
    enumeration, real formats, frames emitted (≥5 in 5 s), device
    released after stop (re-query works), restart within session.
    Auto-skipped on machines without a camera or v4l-utils.
- Smoke test through the full UI: project → Camera view → Start →
  frames painted → Stop → release → window close.
- `ruff check .` → All checks passed.
- `translations/teleprompter_es.ts` regenerated: 66 → 80 messages.

## How to run

```bash
python3 main.py                # create/open project → Camera tab
QT_QPA_PLATFORM=offscreen python3 -m pytest tests/ -q
```

## Known limitations

- Brightness/contrast v4l2 controls are not exposed yet (planned with
  the Phase 3 overlay settings; `v4l2-ctl -l` lists them per device).
- Physical unplug mid-capture is handled (error emitted after the read
  streak) but not unit-tested — documented manual test:
  start preview, pull the USB camera, expect the "Lost the camera
  signal" status within ~1 s at 30 fps.
- Wayland session untested on the reference machine (X11 verified);
  QtMultimedia is not used, so no portal permission issues expected.

## Next phase

Phase 3 — Teleprompter overlay on the camera: `TeleprompterOverlay`
layer with configurable font/color/position/opacity, Reading and
Camera modes, time-based smooth scrolling (monotonic clock, WPM).
