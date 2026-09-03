# Phase 3 — Teleprompter overlay on the camera

Status: **completed** on 2026-09-03.

## What was built

The user can now see themselves on camera and read the script
superimposed over the image, near the lens, with a scroll whose
speed is defined in words per minute — not pixels — so it stays
stable regardless of the display refresh rate.

### New modules

| Module | Responsibility |
|---|---|
| `overlay_model.py` | `OverlaySettings` dataclass (font, colors, background mode, column geometry normalized 0-1, alignment, guide line, mirror, WPM, countdown), color parsing (#RGB/#RRGGBB/#RRGGBBAA), paragraph splitting, WPM↔position math, settings ↔ project.json serialization |
| `teleprompter_overlay.py` | `TeleprompterOverlay` widget: paints the script over the camera preview with QTextLayout per paragraph (cached), transparent/semi/solid column background, guide line at the reading position, paragraph markers and jumps; mouse-transparent so the camera controls stay usable |
| `scroll_engine.py` | `ScrollEngine`: QTimer (~30 Hz) + **monotonic clock**; position = elapsed / total (WPM-based), so the pace is independent of tick count or refresh rate. Countdown 0/3/5/10 s, pause freezes elapsed exactly, resume continues, restart, manual nudge, `jump_to` for markers, WPM change mid-read (or paused) rescales the time base with no perceived jump |

### UI integration (CameraView)

- Reading controls row: **Play/Pause**, **Restart**, **WPM** spinbox,
  **⏮ Paragraph / Paragraph ⏭** markers, position **slider**
  (manual scrub + live feedback), **Reading mode** toggle.
- **Reading mode**: font ≥44 pt, wider column, semi background,
  camera pickers hidden — only reading controls stay (Roadmap:
  "large text, minimal controls").
- The overlay reloads the script whenever the active project changes
  (`switch_project` → `_sync_script_from_project`), inheriting the
  project's WPM.
- The overlay covers the preview exactly (eventFilter on Resize).

## Key decisions

- **Time-based scroll, not pixel-based**: `position = elapsed/total`
  with `time.monotonic()`; the acceptance test (`test_monotonic_pace`)
  proves the position matches wall-clock, not timer ticks.
- **WPM rescale in pause too**: `_elapsed` is always expressed in
  seconds of the current WPM; changing WPM while paused rebases it,
  otherwise the position jumped on resume (bug found by the smoke
  test and fixed in this phase).
- **Overlay is a child of the preview**: shares its geometry, stays on
  top with `raise_()`, and is transparent to mouse events.
- **Layout cache keyed by (font, width, paragraph count)**: repaints
  at 30 Hz cost only the draw calls, not the text layout.
- **QFontMetrics, not QTextLayout.fontMetrics()**: the latter does
  not exist in PyQt6 — using it crashed the painter (found by the
  rendering tests, fixed).

## Acceptance criteria (ROADMAP Phase 3)

- ✅ Overlay layer over the camera view
- ✅ Configurable region near the lens (position_x/position_y,
  column width — normalized, survives resizes)
- ✅ Font size/family/bold, text color, transparent/semi/solid
  background, column width, line spacing, alignment, guide line,
  margins, mirror (data model + painting; UI panels for fine
  tuning come with the Phase 5 settings view)
- ✅ Reading mode (large text, minimal controls) + Camera mode
- ✅ Smooth scroll independent of refresh rate (monotonic + WPM)
- ✅ Markers and paragraph jumps (⏮/⏭ + slider)
- ✅ Pause, resume, restart, manual scroll (slider/nudge)
- ✅ Legible on light and dark backgrounds (semi bg + gold default)

Remaining from the phase list, deferred deliberately:
- Text mirror over the camera (data flag exists; painting toggle
  arrives with the Phase 5 settings UI).
- Interface inversion for glass accessories (Phase 5 settings).
- Font/color UI panels (Phase 5); today they are data + defaults.

## Tests

- **193 total pass** (149 previous + 44 new):
  - `test_overlay_model.py` (16): colors, paragraph split, WPM math,
    serialization round-trip, invalid-type guards.
  - `test_scroll_engine.py` (16): start/pause/resume/restart,
    countdown 0/3/5/10 (emissions + delay + pause during count),
    WPM rescale without jump, nudge clamps, finish + restart,
    monotonic pace acceptance.
  - `test_teleprompter_overlay.py` (12): script load, empty script,
    position clamps, markers (current/jump/clamp), rendering
    (transparent/semi/solid), engine→overlay wiring.
- Smoke test with the real camera (9 steps): script in overlay,
  live frames, composite grab, monotonic scroll vs wall clock,
  pause freeze, marker jump, WPM change paused AND resume coherence,
  Reading mode controls hidden, clean shutdown.
- `ruff check .` → All checks passed.
- `teleprompter_es.ts` regenerated: 80 → 88 messages.

## How to run

```bash
python3 main.py          # open a project → Camera tab → Play
QT_QPA_PLATFORM=offscreen python3 -m pytest tests/ -q
```

## Known limitations

- Multi-minute pace stability is designed for (monotonic clock) but
  the automated test covers ~0.6 s; a 5-minute manual soak is
  documented as the release checklist item (Phase 11).
- Fine-tuning panels (sliders for size/position/opacity) are Phase 5
  work; today the settings are defaults + data model.
- The guide line is horizontal only (matches the legacy behavior).

## Next phase

Phase 4 — Controls, countdown, and remote control: keep legacy
shortcuts available in camera mode, big buttons (already present for
Play/WPM/markers), configurable countdown selector, and the improved
remote server (pairing token, rate limiting) with the mobile page
gaining Play/Pause, speed, progress, and camera controls.
