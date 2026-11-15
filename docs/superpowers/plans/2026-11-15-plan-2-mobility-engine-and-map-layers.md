# Riyadh City View, Plan 2: Mobility Engine and Map Layers

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The Transportation project's road network, traffic model and scenario engine run inside Riyadh City View, and both maps can show traffic, metro, bus, hospitals and planned closures.

**Architecture:** The simulation modules are copied from `Agentic_AI_Transportation/backend/simulation` into `backend/mobility/` under their original file names, with only their imports changed. Everything they read from the Transportation database goes through one new module, `backend/mobility/sources.py`. Reference data (roads, metro, bus, hospitals) is built once from the Transportation project's files into `data/mobility/`, and published to hosted `CityView` layers, which the app then reads.

**Tech Stack:** Python 3.10, NetworkX, SciPy, FastAPI, ArcGIS Maps SDK for JavaScript 4.30.

**Spec:** `docs/superpowers/specs/2026-11-15-riyadh-city-view-design.md`, phases 3 and 4. Ends at Checkpoint 2.

## Global Constraints

- `Agentic_AI_Transportation` is read-only. The build script reads its `data_store/overpass_raw.json` and `backend/data/rcrc/*.geojson`.
- No SQLAlchemy and no local database. Scenario results are kept in memory in this plan; storing their summaries in a hosted layer belongs to Plan 3.
- Traffic volumes and speeds are never stored. They are calculated by the model.
- Every number on screen comes from the engine, never from a language model.
- Traffic is labelled "Modelled". Metro and bus data carry the RCRC credit. Hospital positions are labelled approximate.
- Tests use the 73-segment skeleton network and never contact ArcGIS Online.
- Reference layers are static: Reset demo never empties them, and the 15-second refresh does not read them. They are read once, at start-up. The app starts without them and then reads the files in `data/mobility`.
- Each account change is a dry run first and is applied only after the user says yes.
- ArcGIS Maps SDK for JavaScript stays at 4.30 in this plan (see Task 7, step 1 for the version check the spec asks for).

## Review Focus

1. **A closure request names a road the network does not have.** The engine answers with a clear error that lists the corridors it knows; no stack trace reaches the page. Test in Task 2.
2. **Closing a section cuts part of the network off.** The result lists the isolated zones and still returns; it does not hang or divide by zero. Test in Task 2.
3. **Lanes closed is 0, negative, or at least the number of lanes.** 0 or negative is refused; closing every lane is a full closure. Test in Task 3.
4. **The traffic layer is asked for before the model has finished building.** The API answers "not ready yet" with progress, not an error or a long wait. Test in Task 4.
5. **An hour outside 0 to 23, or not a number.** Refused with HTTP 422. Test in Task 4.

## Deviation from the spec

The spec's module table gives new file names (`network.py`, `model.py`, ...). The files keep the Transportation names (`network_model.py`, `engine.py`, `road_closure.py`, ...) so each can be compared line by line with its source. The road junctions are not a separate layer: they are derived from the ends of the road segments, as the Transportation OSM builder does.

---

### Task 1: Reference data built from the Transportation project's files

**Files:**
- Create: `scripts/build_mobility_data.py`, `data/mobility/network.json.gz`, `data/mobility/rcrc/{metro_lines,metro_stations,bus_routes,bus_stops}.geojson`, `data/mobility/NOTICE.md`
- Create: `backend/mobility/__init__.py`, `backend/mobility/riyadh_network.py`, `backend/mobility/build_network.py`, `backend/mobility/osm_network.py` (copies, imports changed)
- Test: `tests/test_mobility_data.py`

- [ ] **Step 1:** Add `networkx>=3.2` to `requirements.txt` and install it.
- [ ] **Step 2:** Copy the three data modules and change their imports to `backend.mobility.sources`.
- [ ] **Step 3:** Write the failing tests: the skeleton network has 73 segments (the Transportation README's figure; the test asserts the real count the builder returns and that every segment has `id`, `from_node`, `to_node`, `length_km > 0`, `lanes >= 1`); every segment's capacity is `lanes x 1800 / 1500 / 1200` for motorway / arterial / collector; `network.json.gz`, when present, has more than 10,000 segments and every segment's end nodes exist.
- [ ] **Step 4:** Write `scripts/build_mobility_data.py`. It prints the counts it wrote and the licences (OpenStreetMap ODbL; RCRC KSA Open Data License).
- [ ] **Step 5:** Run it, run the tests, commit.

### Task 2: The engine

**Files:**
- Create: `backend/mobility/sources.py`
- Create (copies, imports changed): `backend/mobility/{network_model,engine,road_closure,traffic_demand,event_impact,alternative_routes,accessibility,network_resilience,strategies}.py`
- Test: `tests/test_mobility_engine.py`

**Interfaces:**
- Produces:

```python
# backend/mobility/sources.py
def configure(store=None, network: str = "auto") -> None      # network: "auto" | "file" | "skeleton"
def load_network() -> tuple[list[dict], dict[str, tuple], dict]   # segments, {node: (lon, lat)}, provenance
def list_hospitals() -> list[dict]                            # {"id", "name", "geometry"}
def list_(kind: str) -> list[dict]                            # "Intersection" | "MetroStation"
def haversine_km(a, b) -> float
def demand_factor(hour: float, weekend: bool = False) -> float
# scenario archive in memory, for the engine's persist=True path
def new_id(prefix: str) -> str; def upsert_many(kind: str, rows: list[dict]) -> None; def get(kind: str, id: str) -> dict | None; def audit(*a) -> None
```

- `engine.run_scenario(params, progress=None, persist=False, actor="system") -> dict` and `strategies.compare(closure, ...) -> dict` keep the Transportation signatures and result keys.
- "auto" order: the hosted road layer when the store has rows in it, else `data/mobility/network.json.gz`, else the skeleton. The provenance says which.

- [ ] **Step 1:** Write the failing tests (skeleton network): a King Fahd Road closure returns `summary` with `vht_delta_pct > 0`, `affected_segments > 0` and a `worst_hospital_access_delta_min` that is a number; the baseline model is unchanged after a scenario; a demand increase of 20% raises `vht_scenario_peak`; an event at KAFD returns `added_vehicles_per_hour > 0`; `strategies.compare` returns five strategies with `do_nothing` scored 100 and a `recommended` id; an unknown corridor raises `ValueError` that names known corridors; a closure that isolates a zone lists it in `isolated_zones`.
- [ ] **Step 2:** Copy the nine modules, change imports, write `sources.py`.
- [ ] **Step 3:** Run the tests, fix what the port broke, commit.

### Task 3: Lane closure (new code)

**Files:**
- Modify: `backend/mobility/network_model.py` (`reduce_capacity`), `backend/mobility/engine.py` (`lanes_closed` on a closure scenario)
- Test: `tests/test_mobility_engine.py`

**Interfaces:**
- Produces: `NetworkModel.reduce_capacity(seg_ids, lanes_closed: int) -> dict[str, float]` (segment id -> capacity left), and the closure parameter `lanes_closed: int | None`. `None` means a full closure, as today.

- [ ] **Step 1:** Write the failing tests: closing 1 of 3 lanes leaves two thirds of the capacity; the delay of a 1-lane closure is above the baseline and below the full closure of the same section; `lanes_closed` of 0 or less raises `ValueError`; `lanes_closed` at or above the lane count is a full closure; the result's `scenario.resolved` records `lanes_closed` and `capacity_left_pct`.
- [ ] **Step 2:** Implement. A segment keeps `capacity x (lanes - lanes_closed) / lanes`. Both carriageways of the section are narrowed, matching how a full closure treats both.
- [ ] **Step 3:** Run the tests, commit.

### Task 4: Traffic state and the mobility API

**Files:**
- Create: `backend/mobility/traffic.py`, `backend/mobility/transit.py`
- Modify: `backend/platform.py` (configure sources, warm the model in the background), `backend/api/app.py` (routes, gzip)
- Test: `tests/test_mobility_api.py`

**Interfaces:**
- Produces:

| Route | Returns |
|---|---|
| `GET /api/mobility/status` | `{"ready": bool, "network": provenance, "segments": int, "hours_ready": [int], "labels": {...}}` |
| `GET /api/mobility/roads` | GeoJSON of the road segments: `id`, `name`, `corridor`, `road_class`, `lanes`. Sent once; gzip. |
| `GET /api/mobility/traffic?hour=0..23` | `{"hour", "modelled": true, "segments": {id: [v_over_c, flow_class]}, "totals": {...}}`; HTTP 503 with progress while the model is not ready |
| `GET /api/mobility/layers/{metro_lines\|metro_stations\|bus_routes\|bus_stops\|hospitals}` | GeoJSON with `source` and `licence` |

- `traffic.state(hour: int) -> dict` uses `get_model().assign(demand_factor(hour))`; the 24 hours are computed once in a background thread.
- Flow classes are the Transportation ones: free below 0.6, slow to 0.85, heavy to 1.1, stopped above.

- [ ] **Step 1:** Write the failing tests: status is ready on the skeleton; traffic for hour 8 has more non-free segments than hour 3; hour 24 and hour "x" are 422; every layer route returns a FeatureCollection with a `source`; roads has one feature per segment.
- [ ] **Step 2:** Implement, run the tests, commit.

### Task 5: Schema for the reference layers and the publish script

**Files:**
- Modify: `backend/gis/schema.py` (six layers, `static` flag), `backend/gis/store.py` (`clear(None)` and the refresh skip static layers), `backend/gis/agol.py` (numeric fields), `backend/mobility/sources.py` (read hosted layers)
- Create: `scripts/publish_reference_layers.py`
- Test: `tests/test_mobility_data.py`, `tests/test_arcgis_store.py`

**Interfaces:**
- Produces: layers `Riyadh_Roads`, `Riyadh_Metro_Lines`, `Riyadh_Metro_Stations`, `Riyadh_Bus_Routes`, `Riyadh_Bus_Stops`, `Riyadh_Emergency_Facilities`; `LayerDef.static: bool`; `python scripts/publish_reference_layers.py [--apply]`.

- [ ] **Step 1:** Write the failing tests: Reset demo on the stand-in leaves the six static layers untouched; a refresh never sends a request for a static layer (changed while building: reading 11,000 road ids every minute to notice an edit to reference data is not worth it; a restart reads them); the publish script's dry run writes nothing and prints the row count per layer; with the hosted road layer filled, `sources.load_network()` reports `source == "arcgis"` and the same segment count.
- [ ] **Step 2:** Implement, run the tests, commit.
- [ ] **Step 3:** Run `scripts/create_feature_layers.py` and `scripts/publish_reference_layers.py` as dry runs, show the user, **stop for a yes**, then apply and read the counts back.

### Task 6: Map layers on both maps

**Files:**
- Create: `frontend/mobility.js` (shared by both pages)
- Modify: `frontend/index.html`, `frontend/nccc.js`, `frontend/nccc.css`, `frontend/strategic_dashboard.html`, `frontend/strategic_dashboard.js`, `frontend/i18n.js`, `frontend/rtl.css`
- Test: by hand in the browser (Task 7)

- [ ] **Step 1:** Read how `nccc.js` and `strategic_dashboard.js` create their maps and the Urban change checkbox, and follow that pattern.
- [ ] **Step 2:** Add the layer checkboxes (Traffic, Metro, Bus, Hospitals, Planned closures), all off at start; an hour slider that shows only while Traffic is on; the traffic legend with the word "Modelled"; the RCRC credit while Metro or Bus is on.
  - **Changed while building (2026-11-16):** the "Planned closures" checkbox is left out of this plan. No closure records exist until Plan 3 adds the closures layer; a checkbox that shows nothing would mislead. It is added in Plan 3 with the data. Also added: the legend box folds, and starts folded on a phone-width screen, where it covered the map; the folded line still reads "Modelled".
- [ ] **Step 3:** Bus stops load only when Bus is switched on.
- [ ] **Step 4:** English and Arabic strings for every new label.

### Task 7: Checks and Checkpoint 2

- [ ] **Step 1:** Version check the spec asks for: read Esri's release notes for the current ArcGIS Maps SDK for JavaScript and record in `docs/arcgis_checks.md` what moving from 4.30 would need. No upgrade in this plan.
- [ ] **Step 2:** Run the full test suite.
- [ ] **Step 3:** In the browser, on the live app, in English and Arabic, on both pages: switch each layer on and off; move the hour slider from 3 to 8 to 17 and confirm the congested segments change; confirm no console errors; measure how long the traffic layer takes to appear.
- [ ] **Step 4:** Report to the user with the measurements.
