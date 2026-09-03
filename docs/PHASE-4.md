# Phase 4 — Controls, countdown, and remote control

Status: **completed** on 2026-09-03.

## What was built

### Camera-view controls (in-app)

- **Countdown selector**: None / 3 s / 5 s / 10 s (combo, default 3 s),
  wired to `ScrollEngine.set_countdown`.
- **Keyboard shortcuts in Camera mode**, matching the legacy reading
  mode (documented in the docstring and the table below):

  | Key | Action |
  |---|---|
  | `Space` | Play / Pause (with countdown) |
  | `↑` / `↓` | WPM ±10 (`Shift`: ±50) |
  | `Home` / `R` | Restart |
  | `G` | Toggle guide line |
  | `M` | Toggle preview mirror |
  | `Q` | Start remote control + show pairing QR |

- The existing big buttons (Play, Restart, WPM spin, paragraph
  markers, slider) cover the "visible buttons" acceptance criterion
  from Phase 3.

### Secure remote control (LAN, on demand)

`remote_server.py` was rebuilt around three security layers:

1. **Pairing token** — a 6-digit code (regenerated per server start,
   or on demand) shown in the app; phones enter it once (or scan the
   QR deep-link `/pair/<code>`). Unpaired clients get read-only
   status and an explicit rejection on any command. `regenerate_token`
   invalidates every paired phone.
2. **Per-client rate limiting** — sliding window of 10 commands / 5 s
   (token bucket per socket id); floods receive a "Too many commands"
   error event and never touch the engine.
3. **LAN-only lifecycle** — the server starts only when the user
   toggles 📱 Remote (or presses Q); `stop()` frees the port; window
   close stops it (CameraView.shutdown → remote_server.stop).

Mobile page (`templates/remote.html`):

- Pairing box with 6-digit input (Enter submits); main UI is blurred
  and disabled until paired.
- Play/Pause (label follows state: Start/Pause/Resume/Cancel during
  countdown), ±10 WPM buttons, big WPM display, Restart.
- **Progress bar scrubbing**: drag to jump (pointer events, works
  with touch and mouse).
- Live status: state (Idle/Paused/Playing/Getting ready…), progress
  %, WPM, connection indicator (Connected/Disconnected).
- Status broadcasts on every command; phone disconnects do not
  affect the desktop app (engine keeps its own state).

## Acceptance criteria (ROADMAP Phase 4)

- ✅ Space, arrows, Home/R, +/-, F, O, G, Q, V kept in legacy mode;
  Camera mode has Space/arrows/Home/R/G/M/Q (the set that applies to
  a camera view) and they are documented
- ✅ Big buttons for Play/Pause, speed (WPM), restart, jump
- ✅ Configurable countdown: 0, 3, 5, or 10 seconds
- ✅ Remote server binds to the LAN only when the user activates it
- ✅ IP + port + QR shown; QR embeds the pairing code
- ✅ Temporary token/pairing code; phones that do not have it cannot
  send commands
- ✅ Server shuts down on window close
- ✅ Commands validated and rate-limited
- ✅ Mobile remote: play/pause, WPM ±, restart, progress (drag to
  jump), countdown indicator, connection indicator
- ✅ Works on the same Wi-Fi without any cloud
- ✅ App keeps working when the phone disconnects (engine state is
  local)

Deferred (noted for later phases): USB/HID pedal (needs hardware to
design against — Phase 11 hardware checklist), remote recording
button (arrives with Phase 5 recording).

## Tests

- **212 total pass** (193 previous + 19 new):
  - `tests/test_remote_server.py` (19):
    - Rate limiter unit tests (limit, per-client isolation, sliding
      window)
    - Pairing: token format, unpaired rejection, wrong-code rejection,
      correct-code pairing, pairing-disabled mode, token regeneration
      invalidating sessions
    - Commands on a real ScrollEngine: toggle start/pause, wpm up/down
      + bounds, restart, jump (valid/clamped/garbage)
    - Flood: 15 commands → ≥5 rejected errors
    - Status snapshot (engine + legacy object), QR data format,
      status broadcast after commands
- Smoke test (9 steps, real HTTP + WebSocket): mobile page serves the
  new UI, QR contains the token, `/pair/<code>` 200 vs 401, api status,
  unpaired rejection, paired toggle/wpm/jump, port freed on stop.
- `ruff check .` → All checks passed.
- `teleprompter_es.ts` regenerated: 88 → 100 messages.

## How to run

```bash
python3 main.py
# open a project → Camera tab → 📱 Remote (or press Q)
# pair the phone with the 6-digit code, then control from the phone
```

## Known limitations

- Pairing over plain HTTP on the LAN (no TLS): acceptable per roadmap
  ("local network, no cloud"), documented for the security-minded.
- The socket.io JS library loads from a CDN; without Internet the
  phone page cannot load it (embedded fallback is Phase 12 packaging
  work).
- One remote server per app instance (port 5000 fixed; configurable
  constructor parameter exists for tests).

## Next phase

Phase 5 — Audio capture and video recording: microphone selection
(PipeWire/PulseAudio), level meter, RecordingService with FFmpeg,
pre-flight checks, and the remote recording button.
