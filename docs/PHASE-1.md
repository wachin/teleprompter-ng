# Phase 1 — PyQt6 base and project management

Status: **completed** on 2026-09-03.

## What was built

Phase 1 turns the app from a single script reader into a
**project-based application** while keeping the legacy reading mode
fully working.

### New modules

| Module | Responsibility |
|---|---|
| `project_service.py` | `ProjectService` + `Project`: create, open, save, duplicate, rename, delete projects in the versioned `.bigprompt` format; media path routing; legacy config migration |
| `text_import.py` | Script import from `.txt`, `.md`, `.html`, `.docx` using only the standard library; word count and WPM duration estimation |
| `templates_service.py` | Loads the six built-in script templates and fills their `{placeholders}` safely |
| `main_window.py` | `MainWindow` with sidebar navigation across Home / Script / Camera / Review / Editor; `HomeView` (project list + actions) and `ScriptView` (editor + counters + import); Camera/Review/Editor are placeholders for later phases |

### Project format (`.bigprompt`)

A project is a self-contained directory:

```text
MyProject.bigprompt/
├── project.json        # metadata; RELATIVE paths only (enforced)
├── scripts/script.txt  # the script (UTF-8)
├── media/raw/          # original recordings
├── media/exports/      # exported files
├── media/assets/       # logos, intro/outro, b-roll
├── subtitles/
└── thumbnails/
```

`project.json` carries schema_version (1), name, timestamps, script
path, teleprompter settings, devices, clips, segments, subtitle
style, branding, audio, and export history. Opening a project with a
newer schema is refused with an upgrade hint.

### Launcher modes

```bash
python3 main.py                     # projects mode (default)
python3 main.py --read              # legacy reading mode
python3 main.py path/script.txt     # positional file ⇒ reading mode
```

All existing keyboard shortcuts, remote control, and voice sync in
reading mode are unchanged (Phase 0 verified them).

## Key decisions

- **All importers are stdlib**: `.docx` is parsed by reading
  `word/document.xml` from the zip and joining `<w:t>` runs; `.html`
  via `html.parser` skipping script/style/head. No new dependencies
  (ROADMAP 4.1 rule).
- **Blank-line convention**: HTML paragraphs are converted to
  blank-line-separated text, matching the script style the teleprompter
  scroll expects.
- **Delete is double-gated**: `ProjectService.delete()` requires
  `confirm=True` and the UI asks a question dialog first (ROADMAP
  rule 14).
- **English-first i18n**: every new UI string is wrapped in
  `self.tr()`; `translations/teleprompter_es.ts` regenerated — now 66
  messages (context: Teleprompter, MainWindow, HomeView, ScriptView).
- **Templates are data, not code**: plain `.txt` + `.json` sidecars in
  `resources/script_templates/`; `fill_template` keeps unknown
  `{placeholders}` visible so authors notice them.

## Acceptance criteria (ROADMAP Phase 1)

- ✅ MainWindow with navigation between Home, Script, Camera, Review, Editor
- ✅ ProjectService: new/open/save/close (plus duplicate/rename/delete)
- ✅ Current configuration migrates into project settings
  (`migrate_legacy_config`)
- ✅ `.txt` import and UTF-8 preserved (tested with ñ, accents, emojis)
- ✅ `.md`, `.html`, `.docx` import without new dependencies
- ✅ Six script templates (tutorial, presentation, class, news, review, ad)
- ✅ WPM-based duration displayed next to the word counter
- ✅ A project reopens in another session with all its settings
- ✅ Temporary (raw) and final (exports) files live in separate folders

## Tests

- 130 passed (41 pre-existing + 89 new):
  - `test_project_service.py` — 33 tests: layout, round-trips, UTF-8,
    corrupt/future JSON, relative-path enforcement, rename/duplicate/
    delete gating, listing, migration
  - `test_text_import.py` — 26 tests: txt/md/html/docx, encoding
    fallback, entities, WPM math
  - `test_templates_service.py` — 12 tests: six builtins, metadata,
    placeholder filling, path-trick rejection
  - `test_main_window.py` — 18 tests (pytest-qt, offscreen):
    navigation, lifecycle, editor wiring, template dialog
- Smoke tests: projects mode (create → edit → close → home), reading
  mode (legacy window intact), parse_args.

## How to run

```bash
python3 main.py                # project mode
python3 main.py --read         # legacy reading mode
QT_QPA_PLATFORM=offscreen python3 -m pytest tests/ -q
```

## Known limitations

- Camera/Review/Editor are placeholder screens until Phases 2+.
- Only one project open at a time (by design).
- Projects folder is fixed at `~/TeleprompterProjects`; a setting to
  change it belongs to the Phase-5 settings view.
- Renaming a project does not yet update the recent-projects order on
  other machines (projects are local only; no sync by design).

## Next phase

Phase 2 — Live webcam: V4L2 detection, CameraService thread,
preview widget with BGR/RGB conversion and aspect-ratio-correct
scaling. `v4l-utils` is already installed and the built-in camera
(`/dev/video0`, Integrated_Webcam_HD) is detected.
