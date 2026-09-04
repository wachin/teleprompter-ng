# Phase 10 — Export and publishing helpers

Status: **completed** on 2026-09-03.

## What was built

Social-target export profiles with documented ffmpeg ladders,
background rendering (the UI never blocks), multi-take assembly
with intro/outro, size estimation before the export, thumbnails,
final-file validation, and the local publishing-metadata block —
clipboard or .txt, never an API (direct social publishing stays
out per the roadmap).

### New modules

| Module | Responsibility |
|---|---|
| `export_profiles.py` | 5 built-in profiles — YouTube 16:9, TikTok/Reels/Shorts 9:16, LinkedIn 1:1, Quick draft, High-quality master — each with DOCUMENTED parameters (H.264 preset/CRF, AAC bitrate, +faststart); three codec tiers (draft veryfast/CRF26/128k, balanced medium/CRF21/192k, master slow/CRF18/256k); resolution-scaled size estimates; metadata text builder (title/description/hashtags with tag cleaning). |
| `export_view.py` | Profile selector with live description + size estimate; metadata form (copy to clipboard / save .txt); **RenderWorker on a QThread** (progress 0-100, cooperative cancel, dialog close cancels); on success: thumbnail preview button, "Open output folder" (xdg-open), export recorded in project.json. |
| `render_pipeline.py` (extended) | `build_profile_command` (profile ladder swap + kit/profile ratio mismatch refused with an actionable message), `assemble_timeline` (parts + intro/outro re-encoded to the body ladder before concat), `extract_thumbnail` (frame at ~25%, output-seek — input-seek on mpegts lands where no frame decodes), `validate_output` (exists + size + ffprobe parses). |

### Integration

- BrandingView gains **🚀 Export with profile…** next to the Phase-8
  quick export; the kit's live form feeds the profiled export, and
  a kit ratio that mismatches the profile is auto-adopted to the
  profile's ratio (the profile is authoritative).

## Key decisions & bug found live

- **ffmpeg 7 + filter_complex rejects `-map [0:a]`**: with any
  filter graph present, an output label must exist IN the graph.
  Without music the render failed with "Output with label '0:a'
  does not exist" — fixed with a no-op `[0:a]anull[aout]`
  passthrough. (This also fixed the Phase-8 no-music path, which
  had never been exercised — every prior smoke used music.)
- Profile/kit ratio mismatch is REFUSED with a clear message (a
  letterboxed 16:9 rendered into a 9:16 profile would be a trap),
  except in the ExportView flow where the user explicitly chose the
  profile: there the kit adopts the profile ratio.
- Intro/outro are re-encoded to the body's ladder before concat
  (the concat demuxer needs matching streams).
- Thumbnails seek to 25% with OUTPUT seeking (input-seek produced
  "Could not generate the thumbnail" — same mpegts lesson as
  Phase 8).

## Acceptance criteria (ROADMAP Phase 10)

- ✅ Export profiles: YouTube 16:9, TikTok/Reels/Shorts 9:16,
  LinkedIn 1:1 (+ draft and high-quality master)
- ✅ FFmpeg with documented parameters (every profile description
  states codec/preset/CRF/audio bitrate)
- ✅ Container/codec/resolution/fps/bitrate chosen per profile
  (output folder fixed to media/exports per project layout)
- ✅ Size estimate before exporting (resolution-scaled)
- ✅ Final file validated: exists, reasonable size, ffprobe parses
- ✅ Optional thumbnail (JPEG at 25%)
- ✅ Title/description/hashtags → clipboard or .txt
- ✅ No direct social publishing (local export + open folder only)
- ✅ Multi-take assembly: body segments + intro + outro joined
  (the Phase-8 deferred item)

## Tests

- **387 total pass** (368 previous + 19 new):
  - `test_export_profiles.py` (19): profile data (5 built-ins,
    ratios, ladders by tier, audio bitrates, faststart, invalid
    tier/ratio, size-estimate scaling, documented descriptions),
    metadata block (full/cleaned tags), profile-command ladder
    swap, ratio-mismatch refusal, real thumbnail + validation
    (missing/tiny/garbage outputs rejected), REAL multi-take:
    intro 1 s + trimmed body 2 s + outro 1 s assembled (4.05 s)
    and exported through the shorts profile (1080x1920).
- Smoke test (7 steps, real UI + real thread): estimate shown
  before export → metadata to clipboard (#hashtags cleaned) →
  worker-thread export (UI stayed responsive) → 265 KB master →
  53 KB thumbnail → ffprobe 1080x1920, 5.1 s (intro+body+outro) →
  export recorded in project.json.
- `ruff check .` → All checks passed.
- `teleprompter_es.ts`: 220 → 242 messages.

## How to run

```bash
python3 main.py
# project → record → Review → Edit → Brand & Export → 🚀 Export with profile
```

## Known limitations

- Cancellation is cooperative: ffmpeg finishes reading its current
  stderr line; instant kill would truncate the output (deliberate).
- Multi-BODY-take (several different clips in one timeline) needs
  the Phase-6 cross-take ordering — the assembly function already
  accepts any segment list, so this is UI wiring.
- No Wayland-specific folder opener (xdg-open covers both).

## Next phase

Phase 11 — Quality and accessibility: coverage on critical
modules, HiDPI/long-script integration checks, the manual release
checklist (5-minute soaks, USB unplug, VLC playback), keyboard
navigation audit, and the Qt Linguist translation pass at the end
of the project.
