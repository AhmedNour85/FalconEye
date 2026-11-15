# GeoAI Operations Center | Riyadh

Unified Agentic AI for geospatial operations: **one agent, one geospatial platform, one lifecycle** - SENSE → SEE → UNDERSTAND → DECIDE → ACT → VERIFY → LEARN - demonstrated on Riyadh.
*From Sensing the World to Verifying Real-World Impact.*

## Run it (Windows / macOS / Linux, Python 3.10+)

```bash
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env            # optional: add ANTHROPIC_API_KEY (agent on Claude) and ArcGIS credentials
python -m backend.main            # http://127.0.0.1:8000  (data is generated on first start)
```

Tests: `python -m pytest -q` (156 tests; no network or keys needed; about 6 min). Set `GEOAI_OFFLINE=1` to ignore ArcGIS/Claude credentials in `.env` (safe local testing; use `GEOAI_DB_PATH` for a separate database). Reset to a clean demo: **Reset demo** button, or `python scripts/initialize_demo.py`. Current state and setup in a new session: `docs/Start_in_new_Claude_environment.md`, `docs/NEXT_SESSION_HANDOFF.md`, `docs/PROJECT_DOCUMENTATION.md`.
No Node build step: the UI is static files served by FastAPI and loads the ArcGIS Maps SDK for JavaScript 4.30 from Esri's CDN (internet needed for the map only).

## NCCC command center (multi-agent, simplified UI)
`http://127.0.0.1:8000/` is now one screen: **Alerts** (what needs a decision), a **map** of open incidents and the **digital crew**. The earlier multi-page UI is still at `/classic.html`.
Modelled on the *Saudi Energy Digital Workforce* reference (executive, operations and specialist GeoCoworkers), the crew in `backend/orchestration/crew.py` is: **Faisal** (executive escalation and briefs), **Mansour** (triage, coordination), **Sarah** (water faults), **Abdullah** (streetlight health), **Zayed** (imagery change), **Reem** (service impact), **Turki** (work orders, dispatch, closure), **Maha** (field verification and learning).
**AI Agents** (the toggle in the top bar) run a scan every 60 s: specialists watch their feeds, Mansour opens incidents, Reem sizes the impact, Turki prepares the response, Faisal briefs on high-severity items, and each finding becomes one notification with the hand-off trail ("How the crew handled this"). Automation only *proposes*; every work order, dispatch and closure still needs a human **Approve**. Use *Simulate an event* to inject a fault or a new satellite pass. 
**Data feeds.** Besides water sensors, streetlight telemetry and satellite change scans, the crew reads two more (simulated) feeds, shown as chips under the key numbers: **citizen reports** (Balady app / 940 call center / social media; `backend/services/feeds.py`) and **weather**. Reem links reports to nearby incidents as evidence, and three or more reports about the same problem in one place with no sensor alarm become a finding of their own; a heat warning raises one alert. Demo events: *Citizen reports - low pressure (Al Malaz)* and *Weather - heat wave*. Click any dot on the map to select the nearest incident or report and see its details.
**Compare imagery epochs.** The *Compare imagery* button (and *Compare epochs* on every urban-change alert) opens a before/after swipe viewer for any area, with the detected change polygons overlaid, a list of change events (significant vs minor or possibly seasonal), and a *Scan this area* button that has Zayed compare the two dates and open incidents. Imagery is SIMULATED. API: `/api/nccc/imagery/{area}` and `/api/nccc/imagery/{area}/scan`.

**Field investigator pop-up and report.** When you approve a dispatch, the assigned investigator gets a pop-up on `/field.html` (open it with *Open investigator view* on the dispatch alert, or pick a name on that page): the incident, what the AI found and the task. They **Accept assignment** (you get an alert), then **confirm the incident** (confirmed / not found / look again / escalate) with notes, GPS and an optional photo. You see the alert immediately with a **View report** button that opens the full report: who, what they saw, where, the photo and the AI-vs-field assessment. Assigned work orders now wait for the investigator; tick *Simulated crew auto-responds* in the footer to have the demo answer for them.

**Request inspection.** Faults and changes the crew keeps on watch (P3 and below) show a *Request inspection* button; it has Turki prepare a work order, which still waits for your approval (`POST /api/nccc/incidents/{id}/inspection`).

**Critical urban change.** A large new-construction candidate (10,000 m² or more) within 100 m of a hospital, school, clinic or metro station, or over two or more water mains, is scored Critical (P1) with the reason stated in the alert, and Faisal escalates it. Demo: *Simulate an event > Urban change · critical* (Diplomatic Quarter and Diriyah).

API: `/api/nccc/state|scan|autopilot|events/{name}|ask`.

## Classic user interface
Single-page app (vanilla JS, no build step) with a small design system in `frontend/styles.css` (tokens for colour, type, spacing, radius, shadow; light and dark themes; reusable buttons, fields, cards, badges, tables, toasts, dialogs).
Left rail on desktop, icon rail on tablet, bottom tab bar on phones; hash routes (`#/map`, `#/cmd`, ...) so pages are linkable and the back button works.
**Ctrl/Cmd+K** opens a command palette (jump to a page, reset, inject a scenario, ask the agent). A three-swatch switcher in the top bar (or Ctrl+K) changes the theme; NCCC is the default theme, and your choice is remembered. Destructive actions (reset) ask for confirmation.

## Modes
| | Without keys (default) | With keys |
|---|---|---|
| Agent reasoning | Offline rule planner (same tools, deterministic replies) | `ANTHROPIC_API_KEY` → Claude tool-calling loop (`ANTHROPIC_MODEL`, default `claude-opus-5-5`) |
| System of record | Local SQLite feature store (`data/geoai.sqlite`) | Same, **plus write-through to ArcGIS Online** hosted layers |
| Basemap | OpenStreetMap (real Riyadh roads/buildings) | Optionally Esri styles via `ARCGIS_JS_API_KEY` |

ArcGIS Online setup (needs `pip install arcgis` and credentials in `.env`):
```bash
python scripts/setup_arcgis.py            # check sign-in and privileges
python scripts/create_feature_layers.py   # create the hosted layers
python scripts/populate_feature_layers.py # load the synthetic data
```
**The ArcGIS Online adapter has not been exercised against a live organisation** (no credentials were available when this was built); everything else below was run and tested.

## Where things are
`backend/agent` agent + approval-intent routing · `backend/tools` the 18 tools · `backend/services` detection, imagery, simulation, learning · `backend/workflows` approvals, actions, guided demo ·
`backend/gis` schema, store, ArcGIS Online adapter · `frontend/` UI · `docs/` architecture, data dictionary, tools, demo script · `scripts/` setup and data generation.
Security notes: no secrets in code (`.env`); admin credentials stay server-side; demo-grade role header `X-Role` (viewer/worker/operator) guards write endpoints - replace with OAuth/OIDC in production; tool inputs are schema-validated; approvals are de-duplicated; work orders are unique per active incident.

---

## Implementation report

### Fully functional (run and covered by tests / seen in the browser)
- End-to-end lifecycle for the same incident: sensor anomaly → suspected leak → incident → approval-gated work order → approval-gated assignment → field submission (GPS, photo) → agent comparison with the AI finding → repair → approved closure → metrics and calibration. Replayable via **Reset demo**; also for the King Fahd Road streetlight cluster.
- Conversational agent with context continuity ("that one"), tool trace, approvals in chat or panel; the model has no approval tool (verified by test). Claude loop verified only against a **fake client** in tests - not against the live API (no key available).
- Executive KPIs (all 13 suggested), hotspots, ranking, filters, drill-down, calculated from records; audit log of every action; simulation engine (start/pause/tick/scenarios/modify sensor/simulated field response).
- Field portal with real form submission, GPS capture, photo upload, validation (assignment, GPS distance tolerance).
- English and Arabic on every page (right-to-left, backend sentences translated); a **planner switch** (offline rules, Claude, OpenAI, Gemini, LM Studio, Ollama, Hermes, any OpenAI-compatible server); simulated events that wake only their own feed; the close scenario with a **simulated repair report**; eight visual-distortion incident types; land-use management with change detection and urban change; ArcGIS Field Maps tasks with an Answer pick list and a bilingual report form (`docs/PROJECT_DOCUMENTATION.md`, `docs/field_maps.md`).

### Uses actual public geographic data
- **Real OpenStreetMap roads and building footprints** (c) OpenStreetMap contributors, ODbL: `python scripts/fetch_osm_riyadh.py` caches 4,598 road ways and 11,294 buildings in `data/samples/osm_riyadh.json.gz` (committed; runtime needs no OSM access). The synthetic layers are built **on** them: water pipes follow real street centrelines (connected through shared OSM junction nodes), sensors sit on pipes, streetlights run along the real King Fahd Road / Olaya Street ways (9 m offset) and the area main roads, facilities are placed on real building footprints, and 1,270 real footprints are stored in `Riyadh_Reference_Buildings` (used for leak impact and spatial analysis). The simulated imagery is rasterised from the same real roads/buildings.
- Basemap: Esri Streets Night (dark blue), no API key needed; Dark Gray, Imagery, Topographic and OSM are selectable.
- **Still approximate:** area centres and landmark positions (landmarks are snapped to the nearest real building). Without the OSM cache the generator falls back to a regular mesh and hand-placed centrelines (not street-aligned).
- Not ingested: Living Atlas layers, Sentinel-2 or any official Saudi dataset.

### Uses synthetic operational data (labelled `SYNTHETIC-DEMO`)
382 assets (144 pipe segments, 190 streetlights, 48 sensors), 144 pipelines, ~2,800 readings, 190 telemetry records, 22 seeded historical detections/incidents, 18 work orders/verifications, 7 workers - seed-reproducible.

### Uses simulated processing (labelled `SIMULATED-PROCESSING`)
- Imagery epochs are synthetic 4-band scenes with injected changes and seasonal drift; the change-detection algorithm is real. Seasonal-looking differences are reported as unconfirmed and not significant.
- "GeoAI feature extraction" is threshold/morphology on that scene; **no deep-learning model ran**.
- Streetlight model is trained on synthetic labelled samples; leak risk weights are hand-set heuristics, not hydraulic modelling.
- Learning = metrics + calibration multipliers; **nothing is retrained**. False negatives use simulator ground truth.

### Needs additional licensing, data or integration
ArcGIS Online credentials (hosted layers, attachments for photos), ArcGIS Pro/Image Analyst or GeoAI deep-learning licences and GPU for real extraction, Sentinel-2/Esri Wayback imagery access, ArcGIS Field Maps / Survey123 (a built-in portal is provided instead), ArcGIS Dashboards (a custom dashboard is provided), real SCADA/IoT feeds, MCP wrapper over the tools (tools are plain Python functions with JSON schemas, ready to expose via MCP - not built).

### Not built / deviations from the brief
Vanilla JS instead of React+TypeScript (chosen to avoid a build chain); the Field Maps web maps are created by hand and only edited by scripts (`scripts/setup_field_maps_form.py`, `scripts/add_task_answer_action.py`; dry run by default, backups in `data/backups/`); no OAuth sign-in flow (username/password from `.env` for the server-side adapter); conversation state is in memory (records are persistent).

### Recommended next steps
1. Connect a real ArcGIS Online org and run the three scripts; add attachment upload for evidence. 2. Replace synthetic roads/buildings with OSM extracts; ingest real Sentinel-2 pairs. 3. Swap simulated extraction for a licensed GeoAI model with human review. 4. Exercise the Claude backend with a key and build an eval set of prompts. 5. OAuth/OIDC + real RBAC, persistent sessions, retention and PII policy. 6. Controlled offline model retraining using the verification records.
