# Riyadh City View

One command center for Riyadh that covers city services and mobility together: a digital crew of AI agents watches the feeds, opens incidents and proposes work, a person approves every action, investigators verify in the field, and the result feeds learning.

It is built from two earlier projects, `Agentic_AI_City` (concept, workflow, crew) and `Agentic_AI_Transportation` (mobility). **ArcGIS Online is the system of record. There is no local database.**

## Status (2026-11-15)

| Part | State |
|---|---|
| The four city-service use cases (water leak, streetlights and poles, visual distortion, land use) | Working. Carried over from `Agentic_AI_City`. |
| ArcGIS Online as the system of record | Working. 22 hosted layers titled `CityView_*` exist in the account and hold the demo data; the app runs on them. Measurements and live checks: `docs/arcgis_checks.md`. |
| Mobility (traffic, closures, events), the three new crew members, the cross-domain link | Not started. |
| ArcGIS Field Maps tasks on the new layers | Not started. The City project's scripts are carried over and now refuse any web map without the `CityView` prefix. |

Design: `docs/superpowers/specs/2026-11-15-riyadh-city-view-design.md`. Build plan: `docs/superpowers/plans/`. What was checked against Esri documentation: `docs/arcgis_checks.md`.

## How the records are kept

- Every layer of the data model is one hosted feature service titled `CityView_<layer>`, owned by the signed-in account.
- At start-up the app loads the layers into a working copy in memory. Nothing is written to this computer.
- Every change is made in ArcGIS Online first. It counts as done only when ArcGIS Online confirms it. A refused change changes nothing and the operator sees the reason.
- Edits made in ArcGIS Online itself (Field Maps, Map Viewer) are picked up every 15 seconds; deletions within 60 seconds.
- One server at a time works on the layers. A second one refuses to start.
- The app never fills or empties the layers by itself. Only **Reset demo** and `scripts/initialize_demo.py --apply` delete rows.
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

`backend/gis/store.py` working copy and the ArcGIS Online store · `backend/gis/agol.py` ArcGIS Online gateway · `backend/orchestration/crew.py` the digital crew · `backend/tools/` the validated tools · `backend/workflows/` approvals and actions · `backend/services/` detection, imagery, simulation, learning · `frontend/` the pages · `scripts/` account setup · `tests/fakes.py` the stand-in for the hosted layers.

## Data honesty

Operational data is synthetic and imagery processing is simulated, labelled as such on screen, as in `Agentic_AI_City`. Roads and building footprints come from OpenStreetMap (c) OpenStreetMap contributors, ODbL.
