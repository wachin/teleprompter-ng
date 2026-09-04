# Phase 8 — Branding and visual editing

Status: **completed** on 2026-09-03.

## What was built

The brand kit and the final export: one ffmpeg composition that
takes the edited timeline and produces a social-ready master with
logo, music, subtitles burned in, and the chosen aspect ratio.

### New modules

| Module | Responsibility |
|---|---|
| `branding_model.py` | `AspectRatio` (16:9 / 9:16 / 1:1 / 4:5 with canonical resolutions, letterbox AND crop geometry math), `BrandKit` (logo position/scale/opacity, brand colors, intro/outro paths, music + volume + fades, subtitle burn-in style, ratio + fit mode; full validation with actionable messages), `SubtitleStyle` (position, font size, colors, optional background box). Everything serializes into project.json `branding` with project-RELATIVE asset paths. |
| `render_pipeline.py` | `build_render_command` — the one ffmpeg argv: video chain (scale/pad letterbox or crop/scale) + subtitles burn-in (libass `subtitles` filter with quoted `force_style`) + logo overlay (rgba, alpha, 2% margins) + music (volume, fade in/out, amix duration=first); input indexes fixed BEFORE adding inputs (music=1, logo=2 — order bugs found and fixed). `export_timeline_parts` (RE-ENCODED parts: stream-copied input-seeks on mpegts produced AUDIO-ONLY parts on this machine — documented below), `join_parts`, `run_render` with time= progress parsing (N/A-safe). |
| `branding_view.py` | Brand kit form (logo/music/intro/outro pickers that COPY assets into media/assets, color buttons, ratio + fit combos, subtitle burn-in controls) + Export button running the pipeline into media/exports with progress bar; kit persists to project.json; every export is recorded in `exports` history. |

### Integration

- Editor gains **🎨 Brand & Export…** next to Subtitles.
- Exports land in `media/exports/export_<take>_<timestamp>.mp4`
  (+faststart for web upload) and are registered in project.json.

## Key decisions & bugs found live

1. **force_style quoting**: commas inside `force_style=` split
   filter options; the value must be single-quoted
   (`force_style='A,B,C'`) inside the argv.
2. **Music filter never declared**: the `[music]` label was used in
   amix but its filter was appended to a dead list — renders with
   music produced an unbindable graph. Fixed by building the whole
   chain in one list.
3. **Input index drift**: computing `cmd_inputs()` after adding the
   logo shifted music/logo references (both pointed at input 3).
   Indexes are now fixed before each input is appended.
4. **Stream-copied parts lose video**: with ffmpeg 7.1.5, `-ss`
   BEFORE `-i` on x264-in-mpegts sources produced parts with ZERO
   video frames (audio-only). The final render's parts re-encode
   with output seeking (`-ss` AFTER `-i`) — exact and video-safe;
   stream copy stays for the Editor's fast previews. Verified:
   output-seek part = 22 frames + probe 320x240.
5. **Kit paths are project-relative** (project.json stays portable)
   but ffmpeg needs absolutes: `build_render_command` takes
   `project_root` and resolves.
6. **Letterbox parity**: even-dimension scaling (606, not 607) keeps
   x264 happy with yuv420p.

## Acceptance criteria (ROADMAP Phase 8)

- ✅ Local brand kit: logo, colors, intro/outro paths, music
- ✅ Logo overlay with position + opacity + scale
- ⏭️ Titles/lower thirds and B-roll images: deferred to Phase 10
  polish (the overlay pipeline now exists to hang them on)
- ✅ Local music with volume control and fades
- ✅ Aspect ratios 16:9 / 9:16 / 1:1 (+4:5) with letterbox/crop
- ✅ Crop/fit preview: geometry math is tested; live preview widget
  is Phase 10 polish
- ⏭️ Free-asset library: deferred (nothing downloads without
  authorization — rule kept)
- ✅ Subtitle styling (position, size, colors, background) + burn-in
  via libass
- ⏭️ Intro/outro in the render: paths are stored/validated; the
  concat prelude arrives with Phase 10 multi-take assembly

## Tests

- **368 total pass** (323 previous + 45 new):
  - `test_branding_model.py` (29): ratio math (letterbox/crop
    horizontal/vertical/same), kit validation (missing assets,
    absolute paths, bounds, colors, ratio, fit), round-trips,
    SubtitleStyle rules.
  - `test_render_pipeline.py` (16): video filter chains (letterbox/
    crop/burn-in), subtitle style args (scaling, background box,
    quoting), logo geometry (corner expressions, margins),
    full-command shapes (music amix + fades, logo overlay),
    REAL end-to-end render: generated take + logo PNG + MP3 + SRT →
    timeline parts → join → 9:16 branded mp4 validated by ffprobe
    (1080x1920, h264, 1.5-3.5 s, progress ≥ 0.9).
- Smoke test (5 steps, real UI): take + assets in project → kit
  validation → export → 226 KB 1080x1920 h264 master → project.json
  branding + exports history persisted.
- `ruff check .` → All checks passed.
- `teleprompter_es.ts`: 181 → 220 messages.

## How to run

```bash
python3 main.py  # project → record → Review → Edit → 🎨 Brand & Export
```

## Known limitations

- Export runs on the UI thread (progress bar updates between ffmpeg
  lines); a worker thread is Phase 10 polish for long renders.
- One take per export; multi-take timeline assembly is Phase 10.
- Intro/outro concatenation stored but not yet rendered (Phase 10).
- Titles/lower thirds, B-roll, free-asset library: Phase 10.

## Next phase

Phase 9 — Optional local AI script assistant (adapters: local
backend / user-chosen HTTP / none; consent gates for anything
leaving the machine) — per the roadmap, avatars/voice-cloning stay
unimplemented and unclaimed.
