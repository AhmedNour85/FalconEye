# Handoff for a new Claude Code session — GeoAI Operations Center | Riyadh

Read this first, then `docs/PROJECT_DOCUMENTATION.md` (full description, sections 13–14 are English/Arabic and the planner) and `docs/field_maps.md` (Field Maps setup).
Working directory: `C:\10\10` (Windows 11, venv `.venv`, Python 3.10 in the last session; 3.12 worked earlier). It is **not a git repository**. Last updated 2026-11-12.
If the venv is empty: `pip install -r requirements.txt`, then `pip install arcgis six` (without `six`, `item.layers` comes back empty and hosted layers look missing).
Tip: copy this file to the project root as `CLAUDE.md` so a new session loads it automatically. `docs/Start_in_new_Claude_environment.md` lists the full setup steps.

## 1. What the project is (one paragraph)

FastAPI + vanilla-JS command center with eight AI agents (Faisal, Mansour, Sarah, Abdullah, Zayed, Reem, Turki, Maha) that watch simulated feeds, open incidents, and propose work that a
person approves; field investigators verify through **ArcGIS Field Maps**; the result feeds a learning step. SQLite is the system of record, mirrored to ArcGIS Online (hosted layers
prefix `GeoAIOps_`). Four **city-management use cases**: water leak, streetlights & poles (one use case), visual distortion (eight incident types), land-use management (with change
detection and urban change). All data is synthetic/simulated and labelled so. English and Arabic everywhere.

## 2. Current state (verified unless marked)

- **156 tests pass** (`.venv\Scripts\python.exe -m pytest -q`, about 6 min). Run the full suite after any change.
- Pages: `home.html` (portal), `strategic_dashboard.html` (Executive Hub), `index.html` (**Operation**), `field.html` (in-app investigator form, enabled), `classic.html` (not translated),
  `operational_dashboard.html` (hidden). Every page has an EN / العربية button; Arabic is right-to-left (`frontend/i18n.js`, `frontend/rtl.css`).
- Operation layout: digital crew panel above the alerts (left column; Faisal and Mansour on the first row, then three per row); map in the right column with search, 2D/3D icon, an
  optional **Urban change** layer checkbox and the "Ask the crew" box under it; five feed cards at the bottom; header icons for the planner, the bell and the language.
- Executive Hub layout: City Overview on the left, map with 2D/3D and layer toggles, Executive Briefs column on the right (**collapsed by default**, remembered), Hotspots strip across the bottom.
- ArcGIS Online mirror is connected (credentials in `.env`, never commit it); writes go through a background queue (`Store.attach_mirror(..., background=True)`).
- **Simulated events** (Operation → Simulate an event) wake only their own feed; land-use also compares the satellite dates (a violation = one land-use incident, permitted growth = an urban-change review).
  The step after an approval is `POST /api/nccc/scan?follow=true` (watches no feed). **Reset demo** starts clean: 0 open incidents; the Resolved card, response time and resolution rate count only the current run.
- **Close scenario with a simulated repair:** the **Simulate repair** button on the "Fault confirmed on site" alert (or chat "simulate repair for INC-xxxx") files a report from a SIMULATED crew
  (`Platform.simulate_repair`), then the closure proposal needs approval. Fixed: a report assessed again can never reopen a closed incident, and a pull from ArcGIS can no longer blank `Agent_Assessment`.
- **Planner switch** (planner icon in the Operation header): offline rules, Claude, OpenAI, Gemini, LM Studio, Ollama, Hermes (via Ollama) or any OpenAI-compatible server (`backend/agent/providers.py`).
  Keys typed in the dialog stay in memory only. A failing planner falls back to the offline planner for that question.
- **Arabic:** the database stays English; `?lang=ar` (or `X-Lang: ar`) makes `backend/services/i18n.py` translate backend sentences with rules and a vocabulary; the offline planner understands
  Arabic questions and answers in Arabic (`backend/agent/ar.py`). Machine-written Arabic: needs a native review.
- Not yet confirmed on a phone: the "verified" alert after Answer + Note + Finish on the Investigator map.

## 3. Decisions the user made (do not undo without asking)

- Navigation: Operation page ("simulate event" menu) has exactly four flat options: Water leak, Streetlight & pole monitoring, Visual distortion detection, Land-use management.
- Citizen reports disabled (`GEOAI_CITIZEN_REPORTS=0`); weather feed removed; no "Riyadh - Other" area; streetlights and poles are one use case.
- Investigators have their own names (Nawaf, Khalid, Saad, Hamad, Yousef, Ibrahim, Majed), never the agents' names. The in-app investigator form stays enabled next to Field Maps.
- **Finish counts as the report**; on the Investigator map the task buttons are Finish, **Answer** (pick list for `Field_Verdict`), Note, Attach. Radio buttons cannot be on a task: they are on the Field verification report form (the + button).
- Use the web map **GeoAI Field Maps - Investigator Map** (`07fb979378b94c91ab463d8c17601bd0`). The first map `GeoAIOps_Riyadh_Field_Verification` (`e1e83bef0e2247de9dafac88d5a1031b`) was restored to its pre-change version and
  its tasks do not load (its hidden `tasks-configuration.json` has `layerId` = `1a1c26d92cb-layer-5`, the report layer, instead of `WorkOrders_assignments`). The user chose to leave it alone. The hosted data layer has the same
  title as that web map: never delete by title.
- The Executive Hub report/briefs, 2D/3D icons on both maps, hotspots at the bottom, and the Arabic text sizes were set by the user's requests; keep them.
- Ask before any change to the ArcGIS Online account. Pattern used so far: dry run, show the plan, wait for a yes, save a backup, apply, read it back.

## 4. ArcGIS Online account state

Account used by the app: `story_viewer` (org "Esri Saudi Arabia GeoAI Portal"). Org has other users (for example `ahmed.noureldeen_ai`); real per-investigator logins were not provided.

| Item | Id / name | State |
|---|---|---|
| Work Orders layer | item `f341df6a1a924a9c969ff542fe8a5259` | Field Maps task fields (`esritask_*`) with domains; extra fields incl. **`Field_Verdict`** (choice list, labels English / Arabic) and **`Field_Comment`**; `esritask_type` domain also lists the 8 visual-distortion types (added by the server at start-up, appended so old codes never move) |
| Field Verification layer | item `72464caa84b94c2db60baeba2757e050` | `Verification_Status` choice labels now bilingual (codes unchanged) |
| Field Workers layer | item `f8fbda2e76884aea8e08edec49b08f0e` | has `ArcGIS_Username` |
| **Investigator Map** (works) | `07fb979378b94c91ab463d8c17601bd0` | Work orders form with the answer pick list and optional comment; report form bilingual; hidden resource `tasks-configuration.json` has the **Answer** action (after Finish) |
| First map (tasks broken) | `e1e83bef…` | restored to the 03:40 backup; see section 3 |

Backups of web maps and task settings (before every change) are in `data/backups/`. Web-map JSON is edited with `item.get_data()` → `item.update(item_properties={"text": …})`; the **task settings are an item
resource** (`item.resources.get/update("tasks-configuration.json")`), not part of the web-map JSON. `.env` has `GEOAI_FIELD_USERS` mapping all seven workers to `story_viewer` (test setup) and `GEOAI_FIELD_LANG=both`.

## 5. Code map (what lives where)

- `backend/services/tasks.py` (task text and `esritask_*`, `TASK_TYPES`, `LANG`), `backend/services/field.py` (submit/assess; never reopens a closed incident), `backend/platform.py`
  (`pull_field_updates`, `_report_from_finished_task` reads `Field_Verdict`/`Field_Comment` then the Note, `simulate_repair`), `backend/gis/agol.py` (`pull_updates` with `SERVER_OWNED`, `ensure_fields`, `ensure_task_domains`).
- `backend/orchestration/crew.py` (scan cycle with `scope`, `EVENT_SCOPE`, notifications), `backend/tools/` (water, lights, poles, `city.py` visual distortion and land use, `ops.py` incidents/work orders/closure),
  `backend/services/visual_types.py` (the 8 types: name, Arabic, instructions), `backend/services/simulation.py` (events and simulated site visits).
- `backend/agent/` (`agent.py` brains, `providers.py` planner choices, `ar.py` Arabic chat, `compose.py` English replies), `backend/services/i18n.py` (Arabic rules/terms), `backend/api/app.py` (routes, `?lang=` middleware).
- Scripts: `scripts/setup_field_maps_form.py` and `scripts/add_task_answer_action.py` (dry run by default, `--apply` changes your account), `scripts/create_feature_layers.py`.

## 6. Pending / next steps

1. Phone test of the Answer button flow and the "verified" alert (not yet confirmed).
2. Per-investigator logins: replace the test mapping in `GEOAI_FIELD_USERS`; one filtered web map per investigator.
3. Show Field Maps photos in the command center's report view (`frontend/nccc.js`, `/api/nccc/field-report/{id}`).
4. Arabic review by a native speaker; translate `classic.html` if still used.
5. Decide about the first web map (fix its `layerId` or remove the web map after checking the item type).
6. Optional: Workforce/push notifications, real OAuth, a language for the LLM planners' tool results.

## 7. Gotchas learned the hard way

- **Missing `six`** breaks `arcgis` quietly. Do not name a helper script after a stdlib module (`inspect.py`).
- **Shell:** in this environment Bash heredocs lose or change backslashes (`\1`, `\n`): write files that contain backslashes with the Write tool and run them. Use PowerShell for process work.
- **Stale servers:** old test servers may keep ports 8000–8011. Check with `Get-NetTCPConnection`, kill by command line, and restart after code changes (a "Method Not Allowed" on a new route means an old process).
- A new data version (`synthetic.data_version()`) regenerates the demo data and replaces hosted layer contents at start-up.
- `arcgis` 2.4.2 has no `arcgis.mapping`; write web-map JSON by hand. Esri popup titles are `h2`: do not style bare `h2` in `role.css`. `Settings` is a frozen dataclass: build `Settings(...)` in tests.
- Field Maps: edit actions cannot prompt for multiple-choice (radio) elements; required form fields are enforced by edit actions; "Tasks couldn't be loaded" usually means the task settings point at the wrong layer id.
- ArcGIS enforces coded-value domains on write; any username written to `esritask_assignee` must be in its domain (`setup_field_tasks()` keeps it in sync with `GEOAI_FIELD_USERS`).
- Never print or commit `.env`. PDFs of the docs are printed with headless Edge from generated HTML (no pandoc or Word on this machine).

## 8. Quick commands

```bash
.venv\Scripts\python.exe -m backend.main                                   # run on :8000
.venv\Scripts\python.exe -m uvicorn backend.api.app:app_factory --factory --port 8010   # extra instance
.venv\Scripts\python.exe -m pytest -q                                      # full suite (about 6 minutes)
.venv\Scripts\python.exe scripts\setup_field_maps_form.py                  # dry run of the Field Maps form setup
.venv\Scripts\python.exe scripts\add_task_answer_action.py                 # dry run of the Answer button
```

Useful checks: `GET /api/health` (ArcGIS status, `planner`, `arcgis_pending_writes`), `GET /api/nccc/state`, `GET /api/planner`, `GET /api/approvals?pending=true`.
