# Riyadh City View

One command center for Riyadh that covers city services and mobility together: a digital crew of AI agents watches the feeds, opens incidents and proposes work, a person approves every action, investigators verify in the field, and the result feeds learning.

It is built from two earlier projects, `Agentic_AI_City` (concept, workflow, crew) and `Agentic_AI_Transportation` (mobility). **ArcGIS Online is the system of record. There is no local database.**

## Status (2026-11-16)

| Part | State |
|---|---|
| The four city-service use cases (water leak, streetlights and poles, visual distortion, land use) | Working. Carried over from `Agentic_AI_City`. |
| ArcGIS Online as the system of record | Working. 22 hosted layers titled `CityView_*` hold the operational demo data and 6 more hold the mobility reference data; the app runs on them. Measurements and live checks: `docs/arcgis_checks.md`. |
| Mobility engine and map layers | Working. The traffic model from `Agentic_AI_Transportation` runs on the Riyadh road network (10,986 road sections) and both pages show Traffic by hour, Metro, Bus and Hospitals as map layers, off until ticked. Traffic is **modelled**, not measured, and the map says so. |
| Reference layers in ArcGIS Online (roads, metro lines and stations, bus routes and stops, emergency facilities) | Working. Six more hosted layers titled `CityView_Riyadh_*` hold 14,226 rows, filled by `scripts/publish_reference_layers.py`; the app reads them at start-up (28 layers before Plan 3). Where a reference layer is missing, the app reads the same data from `data/mobility`. |
| Mobility events, the three new crew members, the cross-domain link | Working (Plan 3). Nasser, Noura and Fahad join the crew (eleven agents). Traffic incidents, closure requests and major events are detected, simulated in the background (**modelled**), and proposed as traffic plans for a person to approve; road reports, closure requests, event notices, accident history and road-asset condition are **synthetic**. A water-leak repair within 60 m of a modelled road gets a road-impact line (day against night) and one approval records both the work order and the planned closure. Four more hosted layers hold the traffic reports, planned closures, event notices and simulation results (32 layers in all). Alerts have a "View impact on map" button and both map pages have a "Planned closures" layer. Everything is in English and Arabic. Nothing controls signals, signs or dispatch systems. |
| ArcGIS Field Maps tasks on the new layers | Working (Plan 4, Checkpoint 4 approved after the phone test, 2026-11-17). Three mobility task types, nine assignees, the `CityView Field Maps - Investigator Map` with bilingual form and Answer button. Setup steps in `docs/field_maps.md`. |
| Interface, Ask the crew, daily brief, access (Plan 5) | Working, waiting for Checkpoint 5. Lifecycle strip on every alert, a strategy comparison table, four mobility numbers, a trend line and congestion hotspots on the Executive Hub, mobility questions in Ask the crew (English and Arabic; information only, never an approval), a one-page daily brief as PDF (`/api/brief.pdf?lang=en|ar`), and one guard in front of every API route (local mode by default; token mode with `API_TOKENS`). |

Design: `docs/superpowers/specs/2026-11-15-riyadh-city-view-design.md`. Build plan: `docs/superpowers/plans/`. What was checked against Esri documentation: `docs/arcgis_checks.md`.

## How the records are kept

- Every layer of the data model is one hosted feature service titled `CityView_<layer>`, owned by the signed-in account.
- At start-up the app loads the layers into a working copy in memory. Nothing is written to this computer.
- Every change is made in ArcGIS Online first. It counts as done only when ArcGIS Online confirms it. A refused change changes nothing and the operator sees the reason.
- Edits made in ArcGIS Online itself (Field Maps, Map Viewer) are picked up every 15 seconds; deletions within 60 seconds.
- One server at a time works on the layers. A second one refuses to start.
- The app never fills or empties the layers by itself. Only **Reset demo** and `scripts/initialize_demo.py --apply` delete rows, and neither touches the reference layers (roads, metro, bus, emergency facilities). Those are filled by `scripts/publish_reference_layers.py --apply`, which only fills an empty layer unless `--replace` is given.
- The layer prefix `GeoAIOps` (the `Agentic_AI_City` layers) is refused.

## Set up (Windows, Python 3.10 to 3.13)

```bash
python -m venv .venv
```

```bash
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Each script below that changes the account is a **dry run** unless you add `--apply`.

```bash
.venv\Scripts\python.exe scripts\make_env.py <path to a .env that has your ArcGIS sign-in>
```

```bash
.venv\Scripts\python.exe scripts\setup_arcgis.py
```

```bash
.venv\Scripts\python.exe scripts\create_feature_layers.py
```

```bash
.venv\Scripts\python.exe scripts\initialize_demo.py
```

```bash
.venv\Scripts\python.exe scripts\publish_reference_layers.py
```

```bash
.venv\Scripts\python.exe -m backend.main
```

Then open http://127.0.0.1:8020.

`make_env.py` copies only the three ArcGIS sign-in lines and never shows a value. `setup_arcgis.py` only reads.

## Run without ArcGIS Online (development only)

Set `GEOAI_STORE=memory`. The app generates demo data in memory and keeps nothing when it stops. The tests run this way and never contact ArcGIS Online.

```bash
.venv\Scripts\python.exe -m pytest -q
```

## Where things are

`backend/gis/store.py` working copy and the ArcGIS Online store · `backend/gis/agol.py` ArcGIS Online gateway · `backend/orchestration/crew.py` the digital crew · `backend/tools/` the validated tools · `backend/workflows/` approvals and actions · `backend/services/` detection, imagery, simulation, learning · `backend/mobility/` the traffic model, its data sources and the map layers' data · `data/mobility/` road network and RCRC reference files · `frontend/` the pages (`frontend/mobility.js` the mobility map layers) · `scripts/` account setup · `tests/fakes.py` the stand-in for the hosted layers.

## Data honesty

Operational data is synthetic and imagery processing is simulated, labelled as such on screen, as in `Agentic_AI_City`. Roads and building footprints come from OpenStreetMap (c) OpenStreetMap contributors, ODbL.

Traffic is calculated by a model from the road network and a synthetic demand profile; nothing is measured, and the map legend says "Modelled". Metro and bus lines, stations and stops come from Royal Commission for Riyadh City (RCRC) open data under the KSA Open Data License. Hospital and ambulance-station positions are approximate and bed counts are placeholders. Sources and licences: `data/mobility/NOTICE.md`.
