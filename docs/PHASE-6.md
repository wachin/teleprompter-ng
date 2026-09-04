# Phase 6 — Review and non-destructive editor

Status: **completed** on 2026-09-03.

## What was built

Editors that never touch the originals: the review screen plays the
takes, and the editor cuts trims/holes/silences as decision lists in
`project.json`, with undo/redo and per-take re-recording.

### New modules

| Module | Responsibility |
|---|---|
| `edit_model.py` | `Segment` (keep-range over a clip) + `EditList`: whole-clip timeline, trim head/tail, cut holes (split keep ranges), delete, move, snapshot-based undo/redo (capped at 100), project.json round-trip with validation (missing clips skipped, overlong clamped, empty dropped). Loading a document starts a fresh history (not undoable), like any editor. |
| `ffmpeg_tools.py` | `probe_clip` (duration/resolution/fps/audio flag via ffprobe, actionable errors); `detect_silences` (ffmpeg silencedetect, ≥0.4 s gaps only, never fatal); `segment_export_command` (stream-copy default for instant previews, optional re-encode for frame-exact boundaries); `join_command` + `write_concat_list` (concat demuxer with quote-escaped paths). |
| `review_view.py` | Takes list (name, duration, size) from media/raw; embedded player with QMediaPlayer + QVideoWidget (Play, draggable seek slider, duration) when QtMultimedia is present; graceful ffplay fallback otherwise; "Edit this take" hand-off. |
| `editor_view.py` | Per-take editor: segment table (keep ranges, in/out, duration, total), position spinner, "Set start/end here" trims, "Cut hole here", "Delete range", two-step silence removal (analyze → summary → remove), Undo/Redo, "Preview cut" (exports kept ranges to temp .ts, plays with ffplay), "Re-record this take" jump to Camera. |

### Integration

- Review/Editor replace the Phase-1 placeholders in MainWindow; the
  Review list refreshes on project switch.
- Every edit persists immediately into `project.json` under
  `segments` (merged with other clips' segments); the originals in
  `media/raw` are byte-identical after any edit session (asserted in
  the smoke test).
- Silence removal previews first: the first click analyzes and shows
  the summary, the second one cuts (Roadmap: "always with a
  preview").

## Key decisions

- **Decisions, not renders**: an edit is a `{clip, in, out}` list;
  exports materialize it later (Phase 10). Cheap undo, instant
  saves, zero risk to originals.
- **Stream-copy previews**: cutting a preview is instant (-c copy,
  keyframe snap); the re-encode path exists for the final export.
- **Load is not an undo step**: opening a clip resets history — the
  undo stack belongs to the editing session, not the document.
- **Two-step silence removal** instead of a checkbox-with-preview:
  analysis is the slow part; the user sees what would be removed and
  confirms.
- **QtMultimedia optional**: the view degrades to ffplay with an
  explanatory status (installed now, but the fallback keeps the app
  working on machines without the package).

## Acceptance criteria (ROADMAP Phase 6)

- ✅ Review player with playback controls (embedded player + seek)
- ✅ Thumbnail-less take cards with duration and size (name, s, MB)
- ✅ Mark start/end and delete segments (trims + cut holes + delete)
- ✅ Head and tail trimming
- ✅ Optional silence removal with preview (two-step, ≥0.4 s gaps)
- ✅ Non-destructive: segments live in project.json; originals
  byte-identical (asserted)
- ✅ Re-record a single segment (jump to Camera, old take untouched)
- ✅ Undo/redo (snapshot stack, capped, linear history, redo cleared
  on new edits)
- ⏭️ "Do not destroy the original until the user explicitly requests
  it" — no destruction path exists at all; deletion of media files
  belongs to project management (Home delete) and is confirmed.

## Tests

- **285 total pass** (242 previous + 43 new):
  - `test_edit_model.py` (29): loading, trims (bounds + zero-valid),
    cut holes (split semantics, invalid points), delete/move, undo/
    redo (linear, fork-clears-redo, capped history, empty raises),
    persistence round-trips with validation.
  - `test_ffmpeg_tools.py` (14): real generated take (lavfi sources:
    silence→tone concat — aeval chaining fails in ffmpeg 7, sources
    don't), probe fields/missing/corrupt, silence detection on the
    real leading silence, stream-copy command shape, re-encode
    variant, real segment export + ffprobe duration, original
    untouched, concat list quote escaping.
- Smoke test (11 steps): synthetic take → Review list (3.0s card) →
  Editor load → trim head 0.5 s → cut hole at 1.2 s → undo×2 →
  redo×2 → silence detection (0.00-1.52 s found) → removal (3.0 s →
  2.52 s) → project.json segments persisted + original INTACTO →
  re-record jump.
- `ruff check .` → All checks passed.
- `teleprompter_es.ts`: 110 → 154 messages (review + editor strings).

## How to run

```bash
python3 main.py    # project → record in Camera → Review → Edit this take
```

## Known limitations

- The editor works on one take at a time; cross-take timeline
  ordering arrives with the Phase 10 export assembly.
- Preview of cuts uses ffplay (external window); embedded scrub
  preview of the edited timeline is Phase 10 polish.
- Thumbnails in the take list (roadmap mentions them) come with
  Phase 8 branding assets.

## Next phase

Phase 7 — Automatic subtitles: Vosk as the lightweight local backend,
.srt/.vtt import/export, timestamp editing, and the reviewable
pipeline (background processing with progress and cancellation).
