# Phase 5 — Audio capture and video recording

Status: **completed** on 2026-09-03.

## What was built

The user can now record synchronized camera + microphone takes into
reliable intermediate files, with pre-flight checks, live level
metering, a recording clock, and REC control from the phone.

### New modules

| Module | Responsibility |
|---|---|
| `audio_service.py` | Microphone enumeration via `pactl` (PipeWire/PulseAudio, skips desktop monitors, uses human descriptions) with a sounddevice fallback; `LevelMeter` (background PortAudio stream, RMS normalized 0-1 at ~20 Hz, clipping signal) |
| `recording_service.py` | `build_ffmpeg_command` (pure, testable): rawvideo BGR stdin → libx264 CRF18 yuv420p + AAC 128k → MPEG-TS; `check_prerequisites` (ffmpeg present, folder creatable, ≥200 MB free, per-minute estimate); `recover_incomplete` (.ts.part crash leftovers, oldest first); `_PipeWriter` (queue+thread, drops frames instead of blocking); `RecordingService` lifecycle with graceful `q` finalize, kill on timeout, cancel-with-delete, empty-file detection |

### UI integration (CameraView)

- Recording row: **Micro** combo (pactl names), gradient **level
  meter** (green→gold→red), **⏺ REC** toggle (red while active),
  **recording clock** (00:00), **free-space label**.
- Pre-flight refusal with clear reasons: no project → "Open or create
  a project first"; camera off → "Start the camera before
  recording"; no mic → hint about pactl; ffmpeg/disk problems →
  shown before the take starts.
- Frames flow camera → `feed_frame` (same `frame_ready` path as the
  preview); the take is registered in `project.json` (`clips`) and
  written to `media/raw/take_YYYYmmdd_HHMMSS.ts` (originals are
  never overwritten — Phase 6 stays non-destructive).
- `closeEvent` stops the take and meter, then saves the project.
- Clipping shows "⚠️ Clipping — lower the input volume".

### Remote (Phase 4 server extended)

- Events `rec_start`/`rec_stop` (guarded by pairing + rate limit).
- `status()` now carries `recording: true/false`.
- Mobile page: pulsing red **REC/Stop REC** button reflecting live
  state.
- The REC request hops to the Qt thread via `QMetaObject.invokeMethod`
  (queued), so the server thread never touches widgets (rule 9).

## Key decisions

- **FFmpeg as an external process** (Roadmap 4.3): muxing, codecs and
  A/V sync belong to it; the app only pipes frames and manages the
  lifecycle.
- **MPEG-TS intermediate**: robust to truncation (a killed take
  still plays), edit-friendly for Phase 6, plays in VLC/FFprobe.
- **Script burn-in is OFF by design**: recordings are camera-only;
  the explicit burn-in option raises "not implemented" until Phase 8
  branding (recorded in build_ffmpeg_command).
- **Frame dropping over blocking**: `_PipeWriter` drops when ffmpeg
  is behind (counts them) — the UI and camera never stall on a full
  pipe.
- **No Qt in recording_service**: the service reports through
  callbacks; CameraView adapts them to the UI (testable headless).

## Acceptance criteria (ROADMAP Phase 5)

- ✅ Recording has synchronized audio and video (ffprobe: h264+aac,
  1-10 s duration, verified on 3 real takes)
- ✅ Closing the window mid-take leaves no orphan ffmpeg processes
  (stop-on-close + kill-on-timeout + no-orphans test)
- ✅ Original playable with VLC/FFplay (full demux to null passes;
  manual VLC check is on the release checklist)
- ✅ User informed before recording: no mic, no space (200 MB),
  ffmpeg missing, camera off — all with corrective actions
- ✅ Mic selection separate from camera selection
- ✅ Level meter + clipping detection
- ✅ Auto-naming with date/time; original kept (never modified)
- ✅ Duration/recording status visible (clock + REC state)
- ✅ Cancel (delete partial) and crash recovery (.ts.part listing)
- ✅ Teleprompter NOT mixed into the video (explicit opt-in raises
  until Phase 8)

## Tests

- **242 total pass** (212 previous + 30 new):
  - `test_audio_service.py` (7): pactl parsing (short+detailed,
    monitor skipping), default mic, LevelMeter on the real
    microphone (levels 0-1, idempotent stop).
  - `test_recording_service.py` (20): ffmpeg argv shape (rawvideo
    bgr24, pulse source, maps, -shortest, .ts enforcement, burn-in
    guard), pre-flight (missing ffmpeg, dir creation, low disk,
    constants), recovery listing, filename suggestion, lifecycle with
    fake processes (double-start, stop idempotence), pipe-writer
    drop behavior.
  - `test_recording_integration.py` (3, real hardware): 3-second
    take validated by ffprobe (h264+aac, size, duration), no orphan
    ffmpeg after stop, full-file demux.
- Smoke test (11 steps, real UI): mic list, free-space label,
  pre-flight rejection, camera start, REC, meter movement, clock,
  stop, ffprobe validation, project.json clip registration, clean
  close.
- `ruff check .` → All checks passed.
- `teleprompter_es.ts`: 100 → 110 messages.

## How to run

```bash
python3 main.py    # project → Camera → REC (or from the phone)
```

## Known limitations

- Audio device selection: the meter uses the system default input;
  the pactl source chosen in the combo feeds ffmpeg (full index
  mapping arrives with the Phase 5 settings polish — tracked in
  PHASE-5 backlog).
- No pause/resume of recordings (by design: takes are atomic; the
  editor joins/re-records segments in Phase 6).
- 1/5/30-minute soak recordings are release-checklist items
  (Phase 11); automated coverage is 3 s.

## Next phase

Phase 6 — Review and non-destructive editor: review player with the
recorded takes, segment marking, head/tail trimming, optional
silence removal (previewed), undo/redo, re-record single segments —
all driven by the `segments` list in project.json.
