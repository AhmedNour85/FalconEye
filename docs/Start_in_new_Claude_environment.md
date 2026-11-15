# GeoAI Operations Center | Riyadh: start in a new Claude environment

Steps to continue the project in a new Claude Code session, on this PC or another one. Last updated 2026-11-12.

## 1. Copy the project folder

- Copy the whole project folder (today `C:\10\10`; it was `C:\AI\12` before), including `docs\`, `data\backups\` and your `.env`.
- The `.env` holds the ArcGIS credentials (and any API keys): do not commit or share it. The project is not a git repository.
- Skip `.venv` (it is rebuilt per machine). `data\geoai.sqlite` can be copied or regenerated; the demo data is rebuilt from the seed when needed.
- `data\backups\` holds JSON backups of the Field Maps web maps and of the task settings, saved before each change to your ArcGIS account. Keep them.

## 2. Rebuild the environment (PowerShell, in the project folder)

```
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m pip install arcgis six
```

Python 3.10 is what the last session used (3.12 also worked earlier). `six` must be installed with `arcgis`, otherwise hosted layers look empty.

## 3. Check the settings in `.env`

Copy `.env.example` to `.env` if you start fresh. Settings added or used recently:

| Variable | Meaning |
|---|---|
| `ARCGIS_USERNAME`, `ARCGIS_PASSWORD` | ArcGIS Online mirror and Field Maps (empty = fully local) |
| `GEOAI_FIELD_FORM` | `1` enables the in-app investigator page next to Field Maps |
| `GEOAI_FIELD_USERS` | worker id to ArcGIS login (today all seven map to `story_viewer`) |
| `GEOAI_FIELD_LANG` | task text on the phone: `en`, `ar` or `both` (also the labels used by the Field Maps setup scripts) |
| `GEOAI_PLANNER`, `OPENAI_API_KEY`, `GOOGLE_API_KEY`, `ANTHROPIC_API_KEY` | optional planner at start-up; the Operation page can switch planner at any time (keys typed there stay in memory only) |

## 4. Make the handoff load automatically

Copy `docs\NEXT_SESSION_HANDOFF.md` to the project root as `CLAUDE.md` so a new session reads it. The handoff was brought up to date on 2026-11-12 (state, decisions, ArcGIS account, code map, gotchas). Sections 13 and 14 of `docs\PROJECT_DOCUMENTATION.md` describe English/Arabic and the planner switch.

## 5. Open Claude Code in the folder

Start it from the project folder, or from the desktop app's Code tab with that folder as the working directory. Without `CLAUDE.md`, start with:

```
Read docs/NEXT_SESSION_HANDOFF.md, then docs/PROJECT_DOCUMENTATION.md and docs/field_maps.md.
```

## 6. Check that it runs

```
.venv\Scripts\python.exe -m backend.main
.venv\Scripts\python.exe -m pytest -q
```

- Open http://127.0.0.1:8000, press **Reset demo** (the cards should read 0 waiting, 0 open, 0 critical, 0 resolved) and check `/api/health` for the ArcGIS status.
- The pages have an **EN / العربية** button. The full test suite (156 tests, all passing at the last run) takes about 6 minutes.
- Restart the server after code changes. A new data version regenerates the demo data and replaces the hosted layers' contents.

## 7. What changed since the handoff

- **English and Arabic** on all pages (right-to-left layout, backend sentences translated, Arabic chat for the offline planner); `docs` section 13.
- **Planner switch** on the Operation page: offline rules, Claude, OpenAI, Gemini, LM Studio, Ollama, Hermes or any OpenAI-compatible server; section 14.
- **Simulated events** wake only their own feed; the step after an approval no longer scans other feeds; a reset starts with 0 open incidents and the Resolved card and response times start at 0.
- **Visual distortion** has eight incident types (construction waste, abandoned vehicles, illegal graffiti, non-compliant billboards, unlicensed canopies and hangars, unregulated street vendors, neglected vacant land, exposed wiring); **land-use management** now includes change detection and urban change (`backend/services/visual_types.py`).
- **Close scenario with a simulated repair:** the **Simulate repair** button on the "Fault confirmed on site" alert (or chat: "simulate repair for INC-0030") files a SIMULATED repair report; the closure proposal then needs approval. Also fixed: an assessment can no longer reopen a closed incident, and a pull from ArcGIS can no longer blank the saved assessment text.
- **Operation and Executive Hub layout:** crew panel above the alerts, urban-change layer toggle, 2D/3D on both maps, collapsible Executive Briefs, hotspots at the bottom.
- **Field Maps:**
  - Use the web map **GeoAI Field Maps - Investigator Map**. The other map, `GeoAIOps_Riyadh_Field_Verification`, shows "Tasks couldn't be loaded" because its hidden `tasks-configuration.json` points at the wrong layer id (`1a1c26d92cb-layer-5` is the report layer; the Work orders layer is `WorkOrders_assignments`). Fix that one value or leave the map unused.
  - Task buttons on the Investigator map: **Finish, Answer, Note, Attach**. Answer is a pick list for `Field_Verdict`; Note carries the comment; the server uses both as the report. Radio buttons cannot appear on a task, only on the Field verification report form (the + button), which is bilingual.
  - Scripts: `scripts\setup_field_maps_form.py` and `scripts\add_task_answer_action.py` (both default to a dry run; `--apply` changes your account and saves a backup first). Details in `docs\field_maps.md`.

## 8. Open items

1. Run an end-to-end phone test with the Answer button: Answer, Note, Finish, then confirm the "verified" alert (not yet confirmed).
2. Replace the test mapping that sends all seven workers to `story_viewer` with real per-investigator logins and one filtered map each.
3. Show Field Maps photos in the command center's report view.
4. Have an Arabic speaker review the machine-written Arabic (alerts, the eight visual-distortion types, Field Maps labels). `classic.html` is not translated.
5. Decide what to do with the first web map (fix its task layer id, or remove it after checking the item type: the hosted data layer has the same name and must stay).

## Notes

- Ask before any change to the ArcGIS Online account. Everything done so far was previewed first and backed up in `data\backups\`.
- In this shell, files that contain backslashes are safer to write with the editor tools than with heredocs.
- Never print or commit `.env`.
