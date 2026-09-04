# Phase 7 — Automatic subtitles

Status: **completed** on 2026-09-03.

## What was built

Local, offline subtitle generation and editing: Vosk word-level
recognition over the recorded take, an editable cue table, and
lossless SRT/WebVTT import/export.

### New modules

| Module | Responsibility |
|---|---|
| `subtitle_model.py` | `Cue` (start/end/text with SRT + VTT time formats, tolerant parser accepting `,` and `.` ms separators and the short VTT `MM:SS.mmm` form), `parse_srt/format_srt/parse_vtt/format_vtt` (BOM/CRLF tolerant, bad blocks skipped), `merge_short` (collapses Vosk's tiny fragments into readable cues; rule looks at the INCOMING cue), `enforce_order` (sorts, clips overlaps, drops empties), `word_timestamps_to_cues` (≤10 words / ≤4 s / pause-aware grouping). Pure Python, no Qt. |
| `subtitle_service.py` | `find_model()` (models/model-es, vosk-model-* variants, legacy layout; **`conf` is a directory** — bug found and fixed), `extract_audio` (ffmpeg → mono 16 kHz WAV), `Transcriber` (background thread, chunked 4 kB reads, `on_progress/on_done/on_error` callbacks, cooperative `cancel()` within one chunk, fail-fast file check, model check with the exact download hint). |
| `subtitle_view.py` | Generate (with % progress and Cancel — the same button toggles), editable cue table (start/end/text), import .srt/.vtt, save .srt/.vtt; thread-safe UI updates via `QMetaObject.invokeMethod` (worker never touches widgets); clean shutdown cancels running transcriptions. |

### Integration

- Editor view gains a **💬 Subtitles…** button opening the subtitle
  dialog for the loaded take; closing the dialog cancels any running
  transcription.

## Key decisions

- **Vosk word-level tokens, not full results**: word timestamps let
  cues group naturally (pause-aware) instead of trusting Vosk's
  result-chunk boundaries.
- **Model check before extraction** when the file exists (fail fast
  on the common case); file check first when it doesn't.
- **conf is a directory**: every Vosk model ships `conf/` with
  mfcc.conf etc. The old `isfile` check (Phase 0) never matched the
  downloaded model — found live when installing the small model,
  fixed in both `subtitle_service` and `speech_sync` (the voice-sync
  path benefits too).
- **Tolerant parsers**: real-world .srt files come with BOMs, CRLF,
  missing indices, and stray blocks — parse skips garbage instead of
  failing.
- **Two-model policy**: the small model (~40 MB, **~35 min download
  on a slow connection** — documented in the README per the
  maintainer's request) covers word-timing sync and draft subtitles;
  the full 1.3 GB model is opt-in only if accuracy disappoints. No
  downloads ever happen from inside the app.

## Acceptance criteria (ROADMAP Phase 7)

- ✅ Vosk as the optional lightweight local backend (kept from
  Phase 0 voice sync; now also drives subtitles)
- ✅ Language/model choice = the models/ folder (small vs full,
  documented; a settings selector lands with Phase 8 polish)
- ✅ Subtitles with timestamps (word-level → grouped cues)
- ✅ Import/export .srt and .vtt (round-trip verified)
- ✅ Manually edit text and times (editable table; export collects
  the edits, validating each row)
- ⏭️ Whisper/faster-whisper backend: deferred (the roadmap marks it
  optional "if reasonably installable"; Vosk covers the MVP)
- ⏭️ Word/phrase highlighting + position/typography styling +
  burn-in: Phase 8 branding (the cue model already carries per-cue
  ranges)
- ✅ Background processing with progress and cancellation
- ✅ No model downloads without consent (hint text only; the user
  downloads manually)

## Tests

- **323 total pass** (285 previous + 38 new):
  - `test_subtitle_model.py` (26): time formats (SRT/VTT, dot/comma,
    short VTT form, bad timestamps), SRT/VTT round-trips, BOM/CRLF,
    bad-block skipping, merge_short (fragment collapse, long-cue
    keep, gap limit, non-destructive), enforce_order (sort/clip/
    drop-empty), word grouping (10-word/4 s/pause rules).
  - `test_subtitle_service.py` (12): real WAV extraction from a
    generated take (+ missing ffmpeg/missing source errors), model
    discovery (none/found, conf-as-directory), REAL Vosk
    transcription (tone → no cues, no hang), cancellation,
    double-start rejection, threaded error surfacing.
- Smoke test (8 steps): editor + take loaded → Vosk + small model →
  real transcription of a tone take (24 progress events, 0 cues,
  no hang) → SRT import (2 cues) → table edit → SRT/VTT export
  (accents and ñ preserved) → VTT round-trip identical → Cancel.
- `ruff check .` → All checks passed.
- `teleprompter_es.ts`: 154 → 181 messages.

## How to run

```bash
python3 main.py   # project → record → Review → Edit → 💬 Subtitles…
```

## Known limitations

- The small model's accuracy is limited — it's for word-timing sync
  and drafts; swap in the full model for final subtitles (README
  documents both downloads and times).
- No subtitle styling/burn-in yet (Phase 8: position, typography,
  color, animation, and burn-in vs editable track).
- Burn-in of cues over video happens in Phase 8's export pipeline.

## Next phase

Phase 8 — Branding and visual editing: brand kit (logo, colors,
intro/outro), logo overlay, local music with fades, aspect ratios
(9:16/16:9/1:1), subtitle styling + burn-in, and the free-asset
library.
