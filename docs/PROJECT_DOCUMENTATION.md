# GeoAI Operations Center | Riyadh — Project Documentation

*Current state of the whole project. Companion documents: `README.md` (quick start), `docs/architecture.md`, `docs/data_dictionary.md`, `docs/agent_tools.md`, `docs/field_maps.md`, `docs/PROJECT_HANDOFF.md`.*

---

## 1. What it is

A city-management command center for Riyadh in which a **crew of eight AI agents** watches several data feeds, finds problems, and turns them into
work that people approve and field teams verify. All operational data is **synthetic or simulated** (labelled `SYNTHETIC-DEMO` everywhere); road and
building geometry is real OpenStreetMap data.

**One lifecycle:** SENSE → SEE → UNDERSTAND → DECIDE → ACT → VERIFY → LEARN.
The AI proposes; **a person approves every action**; the field confirms; the result calibrates future detections (configurable calibration, no model retraining).

## 2. The four city-management use cases

| Use case | What is detected | Agent | How |
|---|---|---|---|
| **Water leak** | Suspected leaks from pressure/flow anomalies on water pipes | Sarah | z-score against the same hours yesterday; neighbouring-sensor corroboration; probable position |
| **Streetlights & poles** (one use case) | Predicted lamp failures **and** structurally unsafe poles (tilt, corrosion, age) | Abdullah | Logistic model + isolation forest for lamps; limits for poles (tilt ≥ 4°, corrosion ≥ moderate). A pole finding is added to the same streetlight detection, so one lamp never has two detections |
| **Visual distortion** | Urban visual pollution seen between two satellite dates, raised as eight incident types: **Construction Waste, Abandoned Vehicles, Illegal Graffiti, Non-compliant Billboards, Unlicensed Canopies and Hangars, Unregulated Street Vendors, Neglected Vacant Land, Exposed Wiring and Neglected Utilities** (التشوه البصري). Older structural findings (facade bulging, footprint skew, sagging) still work | Zayed | Visual-distortion score per location vs the area norm (z-score); flagged ≥ 0.45; higher risk near hospitals/schools. Each type has its own work-order instruction, Arabic name and Field Maps task type (`backend/services/visual_types.py`) |
| **Land-use management** | New construction that the zoning does not allow (for example inside a park), found by **change detection** between the two satellite dates; permitted new construction is reported as **urban change** | Zayed | Imagery change polygons classified (residential / commercial / large-scale) and checked against each area's zoning. The simulated event compares the satellite dates over the violation area and one more area; a violation is one Land-Use Violation Review, permitted growth is an Urban Change Review, never both for the same polygon |

Every detection is a **candidate or a prediction**, never a confirmed fact, until a field investigator confirms it. Each scenario includes a decoy
(a false positive) so the field step can reject something and the learning step has something to learn from.

## 3. The digital crew

| Agent | Role | Focus |
|---|---|---|
| **Faisal** | Executive | Escalates critical risk, briefs leadership (KPIs, hotspots) |
| **Mansour** | Coordinator | Triages findings into incidents, coordinates the crew |
| **Sarah** | Water specialist | Pressure and flow sensors, leak detection |
| **Abdullah** | Asset health | Streetlight failure prediction and pole monitoring |
| **Zayed** | Imagery analyst | Urban change, visual distortion, land use vs zoning |
| **Reem** | Impact analyst | Facilities, pipes and lights around each finding |
| **Turki** | Field operations | Work orders, assignment, dispatch, closure |
| **Maha** | Performance | Compares field results with predictions, calibrates |

The **field investigators** are different people with their own names: Nawaf Al-Harbi, Khalid Al-Otaibi, Saad Al-Qahtani, Hamad Al-Ghamdi,
Yousef Al-Dosari, Ibrahim Al-Shehri, Majed Al-Mutairi. Work is assigned to the best fit by skill, distance and workload.

**Areas:** Olaya, KAFD, Al Malaz, Diplomatic Quarter, King Salman Park, Diriyah (every asset belongs to the nearest one; there is no "other" area).

## 4. The workflow (and the human gate)

```
feeds → crew scan → detections → incidents (Mansour) → impact (Reem) → work-order PROPOSAL (Turki)
      → operator approves → work order created → crew proposed → operator approves → assigned (sent to ArcGIS Field Maps)
      → investigator accepts / starts → files a report → AI compares it with the finding → incident Confirmed / Rejected
      → repair report (the field team, or in a demo a SIMULATED crew: "Simulate repair") → closure proposed → operator approves → Resolved → learning (precision, calibration)
```

- The AI can only **propose**. Creating a work order, assigning a worker and closing an incident each need an explicit human approval.
- Every step is written to an **audit log**.
- A GPS fix more than 150 m from the finding, or a missing GPS point, is weak evidence ("Requires Further Inspection").
- **Closing a confirmed fault needs a repair report.** In a demo without a repair crew, the **Simulate repair** button on the "Fault confirmed on site" alert (or the chat command
  "simulate repair for INC-0030") files a report from a SIMULATED crew (marked `[SIMULATED WORKER]`, `Simulated_Worker = Yes`). The closure proposal then appears and still needs the operator's approval.
- An assessment never reopens a closed incident, and a pull from ArcGIS Online never blanks the assessment text the server wrote (`Agent_Assessment`).

## 5. The screens

| URL | Page | Purpose |
|---|---|---|
| `/` or `/home.html` | **Portal** | Pick a role: Executive Hub or Operational Center |
| `/strategic_dashboard.html` | **Executive Hub** (Faisal) | City overview (health ring, KPIs, 45-day trend), map with layer toggles and 2D/3D, executive briefs (a column that folds away; collapsed by default), hotspots strip across the bottom, printable daily report |
| `/index.html` | **Operation** (NCCC command center) | Digital crew (above the alerts), alerts needing a decision with Approve/Reject and **Simulate repair**, incident map (2D/3D, optional urban-change layer, search), "Ask the crew" chat, five live feed cards, imagery comparison, **Simulate an event**, and the **planner** button (section 14) |
| `/field.html` | Investigator form | Optional in-app form (see §8) |
| `/classic.html` | Classic view | Deep-dive tools |
| `/operational_dashboard.html` | Operational dashboard | Built but hidden (not linked from the portal or the navigation) |

**Simulate an event** (Operation page) offers exactly four options: **Water leak**, **Streetlight & pole monitoring**, **Visual distortion detection**,
**Land-use management**. Each injects a fault, lets the crew react, and produces alerts awaiting approval.
**Each event wakes only its own feed**: the crew checks just that use case, and the step after an approval does not scan the others. Land-use management also compares the satellite
dates (change detection): violations become land-use incidents, permitted new construction becomes an urban-change review. **Scan now** and the **AI Agents** switch still check everything.
**Reset demo** starts clean: no open incidents, and the Resolved card and response times count only work done in the current run (the seeded history stays for trends and learning).

## 6. Architecture

```
Browser (vanilla JS + ArcGIS Maps SDK 4.30)
   │ REST
FastAPI  backend/api/app.py
   ├─ Agent  backend/agent        (offline rule planner, or Claude when ANTHROPIC_API_KEY is set)
   ├─ Crew   backend/orchestration/crew.py   (scan cycle, notifications, autopilot)
   ├─ Tools  backend/tools        (water, lights, poles, distortion, land use, imagery, incidents, executive, verification, learning)
   ├─ Workflows  backend/workflows (approvals + executable actions, only after approval)
   ├─ Services   backend/services  (simulation, synthetic data, feeds, field, imagery, tasks, workforce, learning, audit, OSM)
   └─ Store  backend/gis/store.py  (SQLite system of record) ──background queue──► ArcGIS Online (hosted layers) ◄── ArcGIS Field Maps
```

- **Local store first.** SQLite is the system of record; ArcGIS Online is mirrored. Writes go through a **background queue** (repeated edits to
  the same record are merged), so the UI never waits for ArcGIS Online. The queue is flushed before any pull or reset.
- **Data layers** (`backend/gis/schema.py`): infrastructure assets, water network, sensor readings, AI detections, change detection, extracted
  features, operational incidents, work orders, field verification, executive indicators, audit log, field workers, reference facilities and
  buildings, maintenance history, streetlight telemetry, approvals, learning config, simulation ground truth and events, notifications.
- **Tools never calculate with the language model.** Numbers come from tools reading stored records.

## 7. ArcGIS Online and Field Maps

Hosted layers use the prefix `GeoAIOps_` (for example `GeoAIOps_Riyadh_Work_Orders`). Create them with
`python scripts/create_feature_layers.py [LayerName ...]` (idempotent; it also adds fields the data model gained later).

**Field reports come from ArcGIS Field Maps** (details and one-time setup in `docs/field_maps.md`):

1. Approving an assignment updates the work order on `GeoAIOps_Riyadh_Work_Orders` within seconds: assignee, login, time, status, incident type,
   area, due date, instructions, and the **Field Maps Task fields** (`esritask_type` = incident type, `esritask_assignee` = the investigator's login,
   `esritask_status` Unassigned/Assigned/In Progress/Completed, `esritask_priority`, `esritask_duedate`, `esritask_description`).
2. The investigator sees it as a **task** in Field Maps (web map "GeoAI Field Maps - Investigator Map"; the older map `GeoAIOps_Riyadh_Field_Verification` has a wrong task layer id in its hidden `tasks-configuration.json` and shows "Tasks couldn't be loaded").
3. A background poller (default every 15 s) pulls Field Maps edits and raises alerts on the Operation page (Alerts -> Needs action):
   - **Start** on the task -> "accepted" alert.
   - A **report** added on `GeoAIOps_Riyadh_Field_Verification` (work order, "What did you find?", notes, photos) -> completed (worker, distance, name), assessed
     exactly as the in-app form's reports are, and a "verified" alert with **View report**. The work order id may be left blank: the report is matched to the
     nearest open work order within 300 m of the report's position.
   - **Finish** on the task -> see the next point.
4. **Finish on the task is also a report** (the user's choice). The task buttons are **Finish, Answer, Note, Attach**: **Answer** is a pick list of the five answers (saved in `Field_Verdict`, labels in English and Arabic), **Note** carries what the investigator saw. With no Answer, the Note's first word (Confirmed/Yes, Rejected/"Not found", Repaired, Escalate, "Need to look again", or the Arabic equivalents) sets the verdict; otherwise "Needs Further Inspection".
   Radio buttons cannot appear on a task (Field Maps limit); they are on the **Field verification** report form (the + button).
   No distance check (Tasks does not record the phone's position); a separate report on the verification layer is stronger evidence and is never duplicated. If a report already exists, Finish only raises a "finished in Field Maps" alert.
5. `Investigator_Name` is stored on every report.

## 8. Configuration (`.env`)

| Variable | Default | Meaning |
|---|---|---|
| `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL` | none | Put the agent on Claude; without a key it uses the offline rule planner |
| `ARCGIS_URL`, `ARCGIS_USERNAME`, `ARCGIS_PASSWORD`, `ARCGIS_LAYER_PREFIX` | arcgis.com, none, none, `GeoAIOps` | ArcGIS Online mirror and Field Maps; leave empty for fully local mode |
| `ARCGIS_JS_API_KEY` | none | Optional key for the browser map |
| `GEOAI_OFFLINE` | off | `1` ignores ArcGIS and Claude credentials (safe local testing) |
| `GEOAI_DB_PATH`, `GEOAI_SEED` | `data/geoai.sqlite`, `20260101` | Database file and data seed |
| `GEOAI_CITIZEN_REPORTS` | `0` (disabled) | The citizen-report feed is off by default |
| `GEOAI_FIELD_FORM` | `0` (disabled); `.env` sets `1` | Enables the in-app investigator form `/field.html` alongside Field Maps |
| `GEOAI_FIELD_USERS` | none | `WRK-001=login,WRK-002=login,…`: each investigator's ArcGIS login (currently all seven map to the test login) |
| `GEOAI_FIELD_SYNC_SECONDS` | `15` | How often Field Maps reports are pulled |
| `GEOAI_PLANNER` | empty | Planner at start-up: `rules`, `claude`, `openai`, `google`, `lmstudio`, `ollama`, `hermes`, `custom` |
| `OPENAI_API_KEY`, `GOOGLE_API_KEY` | none | Optional keys so the planner button can switch to OpenAI / Gemini without typing one |
| `GEOAI_FIELD_LANG` | `en` | Language of the task text on investigators' phones in Field Maps: `en`, `ar`, or `both` (Arabic first, then English) |

## 9. Running it

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt            # add `pip install arcgis six` for ArcGIS Online / Field Maps (without `six` the layers look empty)
copy .env.example .env
python -m backend.main                      # http://127.0.0.1:8000, data is generated on first start
python -m pytest -q                         # 156 tests, no network or keys needed (about 6 minutes)
```

Use **Reset demo** (footer of the Operation page) to regenerate everything from the seed. It clears alerts, incidents and approvals.
Tip: time requests with `127.0.0.1`, not `localhost` (name resolution adds about 0.2 s on Windows).

## 10. Main API endpoints

| Group | Endpoints |
|---|---|
| Meta | `GET /api/health` (mode, ArcGIS status, pending background writes, field form state), `GET /api/config` |
| Layers | `GET /api/layers/{name}` (GeoJSON; filters area/category/priority/since/bbox), `GET /api/layers/{name}/{id}` |
| Command center | `GET /api/nccc/state`, `POST /api/nccc/scan` (`?follow=true` = only the step after a decision, watches no feed), `POST /api/nccc/autopilot`, `POST /api/nccc/events/{event}`, `POST /api/nccc/ask`, `POST /api/nccc/incidents/{id}/simulate-repair`, notification ack |
| Approvals | `GET /api/approvals`, `POST /api/approvals/{id}/approve`, `…/reject` |
| Intelligence | `GET /api/kpis`, `/api/hotspots`, `/api/trends`, `/api/executive`, `/api/evaluation`, `/api/audit` |
| Incidents / workers | `GET /api/incidents`, `/api/incidents/{id}`, `/api/workers` |
| Planner | `GET /api/planner`, `POST /api/planner`, `POST /api/planner/models`, `POST /api/planner/test` (any API accepts `?lang=ar` for Arabic text) |
| Field | `GET /api/field/tasks/{worker}`, `POST /api/field/submit`, `/api/field/accept` (410 when the form is disabled) |
| Simulation | `POST /api/sim/*` (scenario, field response, reset) |
| Demo | `GET /api/demo/scenes`, `POST /api/demo/run/{scene}` (guided 8-scene story), `POST /api/demo/reset` |

Roles are demo-grade (`X-Role` header: viewer / worker / operator). Production would use OAuth/OIDC.

## 11. Testing

156 automated tests cover the data model, store and background mirror, tools, agent, crew, approvals, field flows, Field Maps sync and tasks, each of the four use cases
(including the eight visual-distortion types), scoped simulated events, the close scenario, the planner choices, English/Arabic, and the API. Run `python -m pytest -q`.

## 12. Known limits and next steps

- **Synthetic data.** Sensors, telemetry, imagery processing and zoning are simulated; label them as such in any demo.
- **Field Maps on a real phone:** tasks, Start, Finish and the Answer pick list work on the Investigator map. Not yet confirmed end to end on a phone: the "verified" alert after Answer, Note and Finish.
  Radio buttons exist only on the Field verification report form. The scripts `scripts/setup_field_maps_form.py` and `scripts/add_task_answer_action.py` (dry run by default) prepare the layers and maps; details in `docs/field_maps.md`.
- **Photos** taken in Field Maps stay in ArcGIS Online as attachments; the command center's report view does not show them yet.
- **One login for all investigators** today (test mapping). Real per-person logins and one filtered map per investigator are the next step.
- **Not implemented:** ArcGIS Workforce assignments / phone push notifications, real OAuth sign-in, a single-page-app shell, a native Executive Summary PDF generator
  (the Executive Hub's daily report prints to PDF from the browser).
- **Hosted-layer changes** made for Field Maps (extra fields, a status value list, Field Maps task fields on the work-order layer) live in your ArcGIS Online
  account and survive resets of the local database.

## 13. English and Arabic

Every page has an **EN / العربية** button in its header. The choice is kept in the browser (first visit: the browser language) and reloads the page in Arabic with a right-to-left layout.

- **Front end:** `frontend/i18n.js` holds the Arabic dictionary. English text is its own key: `T("Approve")` in scripts, and static HTML is translated automatically when its exact text is a key. `frontend/rtl.css` mirrors the layout. The ArcGIS map widgets follow the same language. Numbers and ids keep Western digits. To add a phrase, add it to the dictionary in `i18n.js`; `tests/test_i18n.py` fails if a `T("...")` call has no Arabic entry.
- **Backend text:** the database, ArcGIS Online layers, ids and codes stay in English. When a request carries `?lang=ar` (the pages add it) or `X-Lang: ar`, `backend/services/i18n.py` translates the sentences the backend wrote (alert titles and messages, crew trail, approval summaries, incident evidence, work-order instructions, AI assessment) and names (areas, investigators, agents, teams, incident types). Fixed rules cover the known sentences; text that matches no rule stays English instead of breaking. Add a rule to `RULES` or a word to `TERMS` for new wording.
- **Chat:** with Claude enabled the reply is written in Arabic when the page is Arabic. The offline rule planner's replies are mostly English.
- **Field Maps:** set `GEOAI_FIELD_LANG=ar` or `both` to put the task text on the phone in Arabic. A Finish note that starts with an Arabic verdict word counts (تم التأكيد، لم يتم العثور، أحتاج إلى معاينة أخرى، تم الإصلاح، تصعيد). The labels of the Verification_Status choices on the hosted layer are still English; changing them is an ArcGIS Online edit (coded-value domain labels) that was not made.
- **Not translated:** `classic.html` and the hidden `operational_dashboard.html`, the chat answers of the offline planner, text typed by people (investigator observations), synthetic facility names, and the printed report's data rows beyond their labels. The Arabic wording is machine-written and should be reviewed by an Arabic speaker before a real deployment.

## 14. Choosing the planner (Operation page)

The **Planner** button in the Operation header switches who plans and answers in the crew chat, at any time, without a restart:

| Choice | How it connects |
|---|---|
| Offline rule planner | Built-in rules; no internet, no key (default without a Claude key) |
| Claude (Anthropic) | Anthropic SDK; key from `.env` or typed in the dialog |
| OpenAI, Google Gemini | OpenAI-compatible chat API (`api.openai.com/v1`, Gemini's `/v1beta/openai`) |
| LM Studio, Ollama, Hermes (via Ollama), any other OpenAI-compatible server | Local or self-hosted address, usually no key. Use a model that supports **tool calling** |

- All online and local choices run the **same tools and the same approval gate**: a model can only propose a work order, assignment or closure; a person approves it.
- **Save and test** makes a tiny call and shows the result (address, key and model errors are explained). If a planner fails mid-conversation, that question is answered by the offline planner with a note, so the chat never goes silent.
- **Keys** typed in the dialog stay in the server's memory only: never written to disk, logged or returned by the API (the API only says whether a key is set). Restarting the server forgets them; put them in `.env` to keep them.
- Switching clears the chat history (the formats differ). The alert feed, crew scans and the Executive Hub never use the planner; they are always rule-based.
- **Privacy:** an online planner receives your questions and the incident data the tools return. A local model keeps data on the machine. Demo data is synthetic.
- API: `GET /api/planner`, `POST /api/planner` (operator), `POST /api/planner/test`. Code: `backend/agent/providers.py`, `backend/agent/agent.py`.

