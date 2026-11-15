# Riyadh City View, Plan 3: Mobility Crew, Mobility Events and the Road-Impact Link

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Status:** written 2026-11-16, **waiting for the user's review**. Nothing in it is built yet.

**Goal:** Three mobility specialists (Nasser, Noura, Fahad) join the crew; a traffic incident, a road-closure request and a major-event notice each run through the same lifecycle as the city-service use cases; and a water-leak repair next to a modelled road gets a road-impact line before the operator approves it.

**Architecture:** A mobility finding is an ordinary detection with category `mobility`, so Mansour's triage, alerts, approvals, work orders, dispatch, field verification, closing and learning are reused unchanged. Simulations take 10 seconds to 2 minutes, so they run on one background worker (`backend/mobility/jobs.py`); the alert goes out at once and is updated when the result arrives. Every simulation result is stored as summary numbers in a hosted table; the map preview is recalculated when asked for.

**Tech Stack:** Python 3.10, FastAPI, NetworkX (the engine from Plan 2), vanilla JavaScript, ArcGIS Maps SDK for JavaScript 4.30, ArcGIS API for Python 2.4.2.

**Spec:** `docs/superpowers/specs/2026-11-15-riyadh-city-view-design.md`, sections 5 and 6 and build phases 5 and 6. Ends at **Checkpoint 3**: the headline story end to end.

## Decisions for you

These are the choices in this plan that go beyond, or fill a gap in, the approved design. Each has my proposal; say which you want changed.

| # | Decision | Proposal | Alternative |
|---|---|---|---|
| 1 | **A fourth new hosted layer.** The design lists traffic incidents, planned closures and scenario results. A major-event notice (venue, attendance, hours) has no home in those three. | Add `CityView_Riyadh_Event_Notices`. Four layers are created in this plan. | Keep event notices inside the planned-closures layer with a type column. Fewer layers, mixed meaning. |
| 2 | **Accident history and road-asset condition** (Fahad's inputs). The design calls them "generated, seed-reproducible" and names no layer for them. | Generate them from the seed when the app starts, and keep them in memory, labelled Synthetic. They are inputs worked out again at each start, like traffic volumes; no record is kept only on this computer. | Two more hosted layers (about 2,000 and 1,500 rows). Everything visible in ArcGIS Online; two more layers to create and reset. |
| 3 | **Names of the two Traffic Response investigators.** | Bandar Al-Shehri and Rayan Al-Anazi. No clash with the crew or the seven existing investigators. | Your names. |
| 4 | **Field Maps task titles for mobility work.** Adding the three mobility task types changes the hosted Work Orders layer's task list; the design puts that in the Field Maps phase (Plan 4). | Leave the task list alone in this plan. Until Plan 4 a mobility task shows in Field Maps under the title "Other"; the in-app investigator page shows the right title. | Add the three task types now (one more account change in this plan). |
| 5 | **Closing a closure or event incident.** City incidents close after "confirmed" and then "repaired". A closure or an event plan has nothing to repair. | "Planned Road Closure" and "Major Event Traffic Plan" incidents can be closed once the investigator confirms the plan is in place. A traffic incident keeps the two steps: confirmed on site, then cleared. | Same two steps for all three. |
| 6 | **The road-impact rule for water-leak repairs.** | Road within 60 m; 2 lanes closed (all lanes if the road has 2 or fewer, shown as "closing the road"); day window 08:00 to 16:00, night window 22:00 to 06:00; night is recommended when it costs at least 10% fewer trip-hours. | Your values. The rule is one small table. |
| 7 | **Area name of a mobility incident.** The six demo areas do not cover the whole road network. | The road's name is used as the area ("Traffic Incident - King Fahd Road"). | Nearest demo area. |

## Global Constraints

- The two source projects are read-only.
- ArcGIS Online is the system of record. No local database, no record kept only on this computer. A simulation result that the system of record refuses is reported as an error, never kept quietly.
- Every account change is a dry run first and is applied only after the user's yes: dry run, show, wait, apply, read back. Only items titled `CityView_*` and owned by the signed-in account are created or changed. Nothing is deleted by title. The prefix `GeoAIOps` is refused.
- Every number on screen comes from a Python tool, never from a language model.
- Nothing is carried out without a person's approval. `propose_traffic_plan` only creates an approval request. An approved plan is a record; nothing controls signals, signs or dispatch systems.
- Simulation results are labelled "Modelled". Road reports, accident history and road-asset condition are labelled "Synthetic". Strategy effects are listed as assumptions with every comparison.
- The 60-second crew scan never waits for a simulation.
- The four city-service use cases keep working exactly as they do now; their tests stay green without edits to what they assert.
- Tests run on the memory stand-in and the 73-segment skeleton network, with simulations run inline; they never contact ArcGIS Online.
- English and Arabic for every new label, alert sentence and trail sentence.
- ArcGIS Maps SDK for JavaScript stays at 4.30. The Field Maps task-type list is not changed in this plan (decision 4).
- Commits are local only.

## Review Focus

1. **A simulation fails, or the traffic model is not ready, when a mobility event arrives.** The alert still goes out and says the impact could not be calculated and why; Turki proposes a plain field check so the incident is not stuck; the scan and the next jobs carry on. The same holds when ArcGIS Online refuses the result's write. Tests in Tasks 3 and 6.
2. **The operator approves the water work order before the road impact arrives.** The work order goes ahead with no closure plan and no closure record; the impact is added to the alert as information only. Test in Task 8.
3. **The leak is not near a modelled road, or the road has two lanes or fewer.** No road, no road-impact step and no line. Two lanes or fewer: the run is a full closure and the line says "closing the road", not "closing 2 lanes". Tests in Task 8.
4. **The same event is injected twice, or the scan runs twice.** No second detection, incident, simulation, approval or closure record for the same report. Tests in Tasks 5 and 6.
5. **The server stops while a simulation is running.** At the next start the scenario row left "Running" is marked "Interrupted", the alert says so, and the crew queues the simulation once more. Test in Task 3.

## Deviations from the spec

- One more hosted layer than the design lists (decision 1).
- `backend/mobility/safety.py` generates its inputs in memory (decision 2).
- The design's "View impact on map" and "Planned closures" map items are built here because Checkpoint 3 needs them. "Compare strategies" as a table, the lifecycle strip and the Executive Hub mobility numbers stay in Plan 5.
- The road-impact sentences start "Road impact (modelled):" where the design's example starts "Road impact:". The word is added so the alert itself says the number is not measured.
- The two new investigators are added to the hosted Field Workers layer here; adding them to the Field Maps assignee list belongs to Plan 4.
- The mobility questions for "Ask the crew" stay in Plan 5. Language-model planners get the new tools through the registry now, except `compare_closure_strategies`.

---

### Task 1: Four mobility layers in the data model

**Files:**
- Modify: `backend/gis/schema.py`, `backend/gis/agol.py` (`NUMERIC`, `LONG_TEXT`), `tests/fakes.py` (its own `LONG_TEXT` copy must match)
- Test: `tests/test_gis.py`, `tests/test_gateway.py`

**Interfaces:**
- Produces (constants in `backend/gis/schema.py`, none static, none internal):

| Constant | Layer | Geometry | Id field (prefix) | Other fields |
|---|---|---|---|---|
| `TRAFFIC_REPORTS` | `Riyadh_Traffic_Incidents` | Point | `Report_ID` (`TRF`) | `Report_Type`, `Segment_ID`, `Corridor`, `Road_Class`, `Lanes`, `Lanes_Blocked`, `Reported_At`, `Source`, `Status`, `Detection_ID`, `Description`, `Data_Classification` |
| `CLOSURES` | `Riyadh_Planned_Closures` | Polyline | `Closure_ID` (`CLS`) | `Corridor`, `Section`, `Segment_IDs`, `Lanes_Closed`, `Full_Closure`, `Start_Time`, `End_Time`, `Reason`, `Status`, `Strategy`, `Incident_ID`, `Work_Order_ID`, `Scenario_ID`, `Requested_By`, `Created`, `Updated`, `Data_Classification` |
| `EVENT_NOTICES` | `Riyadh_Event_Notices` | Point | `Event_ID` (`EVN`) | `Name`, `Venue`, `Attendance`, `Start_Time`, `End_Time`, `Status`, `Detection_ID`, `Incident_ID`, `Source`, `Created`, `Data_Classification` |
| `SCENARIOS` | `Riyadh_Mobility_Scenarios` | table | `Scenario_ID` (`SCN`) | `Scenario_Type`, `Name`, `Params`, `Status`, `Summary`, `Recommended`, `Verdict`, `Subject_ID`, `Requested_By`, `Created`, `Completed`, `Runtime_S`, `Network_Fingerprint`, `Error`, `Data_Classification` |

- Status values: reports `New | Detected | Cleared`; closures `Requested | Approved | In Place | Rejected`; event notices `New | Detected | Planned`; scenarios `Queued | Running | Completed | Failed | Interrupted`.
- `schema.MODELLED = "MODELLED-ESTIMATE"` is the classification of scenario rows. `CATEGORY_OF_TYPE["mobility"] = "Mobility"`.
- Long text (16,000): `Params`, `Segment_IDs`, `Verdict` (`Summary` and `Description` already are). Numeric: `Lanes_Blocked`, `Lanes_Closed`, `Attendance`, `Runtime_S`.

- [ ] **Step 1:** Write the failing tests: the four layers exist with these id fields; a row with a 9,000-character `Params` is accepted by the stand-in gateway and a 17,000-character one is refused, not cut; `Store.clear(None)` empties the four layers (they are demo data, not reference data); `next_id("SCN")` on a store that already holds `SCN-0007` returns `SCN-0008`.
- [ ] **Step 2:** Implement, run the tests, commit.

### Task 2: Synthetic road-safety inputs, the Traffic Response team, the rules table

**Files:**
- Create: `backend/mobility/safety.py`, `backend/mobility/rules.py`
- Modify: `backend/services/synthetic.py` (two workers), `backend/services/workforce.py`
- Create: `scripts/add_mobility_demo_rows.py`
- Test: `tests/test_mobility_safety.py`, `tests/test_scripts.py`

**Interfaces:**
- Produces:

```python
# backend/mobility/safety.py  (ported from Transportation tools/safety.py and tools/infrastructure.py; inputs generated, not read from a database)
LABEL = "SYNTHETIC accident records and road-asset condition - not real data"
def build(seed: int) -> None                      # deterministic for one seed and one network fingerprint; called once after the network is known
def accident_history(segment_ids: list[str]) -> dict   # {"accidents", "severe", "weighted_per_km", "period": "last 12 months (synthetic)", "label"}
def asset_condition(segment_ids: list[str]) -> dict    # {"worst_condition", "mean_condition", "proposed_action", "label"}
def maintenance_priority(top_n: int = 10) -> list[dict]  # condition 0.40, traffic 0.25, criticality 0.20, inspection age 0.10, road class 0.05

# backend/mobility/rules.py
ROAD_IMPACT = {"water": {"radius_m": 60, "lanes": 2, "day": (8, 16), "night": (22, 6), "night_saving": 0.10}}
SMALL_IMPACT_TRIP_HOURS = 50
ABNORMAL_VC = 0.85                                 # "heavy" in the flow classes
INCIDENT_WINDOW_HOURS = 2
def report_risk(lanes: int, lanes_blocked: int, road_class: str, vc_after: float) -> float   # min(95, 40 + 30*blocked/lanes + 15 if motorway + 20 if vc_after >= ABNORMAL_VC)
def closure_risk(road_class: str, full: bool, hours: float) -> float                          # min(95, 50 + 15 if motorway + 10 if full + min(15, hours))
def event_risk(attendance: int) -> float                                                      # min(95, 45 + min(40, attendance / 2000))
```

- `workforce.SKILL_FOR["mobility"] = "traffic"`, `TEAM_FOR["mobility"] = "Traffic Response"`.
- Workers `WRK-008` Bandar Al-Shehri (base Olaya) and `WRK-009` Rayan Al-Anazi (base KAFD), team Traffic Response, skills `traffic,inspection`.
- `python scripts/add_mobility_demo_rows.py [--apply]`: adds the two workers to the hosted Field Workers layer when they are missing. It adds at most two rows, changes no existing row and deletes nothing. Exit codes as in `publish_reference_layers.py`.

- [ ] **Step 1:** Write the failing tests: `safety.build` twice with one seed gives identical answers; `accident_history` of an unknown segment returns zeros, not an error; every answer carries `LABEL`; a mobility incident's best-ranked worker is in Traffic Response; the script's dry run writes nothing and prints "2 to add", and after an apply on the stand-in a second dry run prints "0 to add"; the three risk functions never return more than 95.
- [ ] **Step 2:** Implement, run the tests, commit.

### Task 3: The background worker

**Files:**
- Create: `backend/mobility/jobs.py`
- Modify: `backend/platform.py` (`self.jobs`), `config/settings.py` (`mobility_jobs_inline`: on for hand-built settings, off by default from the environment)
- Test: `tests/test_mobility_jobs.py`

**Interfaces:**
- Consumes: `engine.run_scenario`, `strategies.compare`, `traffic.status`, `schema.SCENARIOS`.
- Produces:

```python
class Jobs:
    def __init__(self, platform, inline: bool = False)
    def submit(self, kind: str, params: dict, subject_id: str, requested_by: str, on_done=None) -> str
        # kind: "incident" | "closure" | "event" | "road_impact". Returns the Scenario_ID.
        # A job of the same kind and subject that is Queued or Running is returned, not doubled.
    def status(self, scenario_id: str) -> dict        # {"id", "kind", "status", "progress", "message", "error"}
    def preview(self, scenario_id: str) -> dict | None  # {"closed", "segments", "routes"} of a finished run; held in memory for the last 20 runs only
    def recover(self) -> list[str]                     # at start-up: rows left Queued or Running become Interrupted; returns their ids
```

- What each kind runs and what goes into `Summary` (JSON):
  - `incident`: a lane closure of `lanes_blocked` lanes on the report's segment for `INCIDENT_WINDOW_HOURS` from now. Summary: `window_extra_trip_hours`, `worst_hospital_access_delta_min`, `severe_segments`, `affected_segments`, `peak_hour`, `duration_h`.
  - `closure`: `strategies.compare`. Summary: the same numbers for do-nothing, plus `strategies` (`id`, `name`, `score`, `benefit_vs_do_nothing_pct` for each), `assumptions`. `Recommended` and `Verdict` are filled.
  - `event`: an event scenario. Summary: the numbers above plus `added_vehicles_per_hour`, `parking_deficit_vehicles`.
  - `road_impact`: two closure runs. Summary: `road`, `lanes_closed`, `full_closure`, `day` and `night` (each `window`, `extra_trip_hours`, `hospital_delta_min`), `recommended` (`day` or `night`).
- One worker thread, one job at a time. A job waits until `traffic.status()["ready"]` when the traffic warm-up is on. `on_done(row)` is called on the worker thread after the row is written.
- A failed run writes `Status = Failed` and `Error`; a refused write is logged, shown in `status()` and passed to `on_done` with `status == "Failed"`.

- [ ] **Step 1:** Write the failing tests (inline, skeleton network): an `incident` job ends `Completed` with a `window_extra_trip_hours` number; a closure on an unknown road ends `Failed` with the engine's message; submitting the same subject twice while the first is queued returns one id; a row left `Running` is `Interrupted` after `recover()`; a store that refuses the write produces `Failed` in `on_done` and no exception on the worker; `preview` returns the three parts for a fresh run and `None` for an unknown id.
- [ ] **Step 2:** Implement, run the tests, commit.

### Task 4: The eight mobility tools

**Files:**
- Create: `backend/tools/mobility.py`
- Modify: `backend/tools/registry.py` (the tools; `Tool.llm: bool = True`; `schemas()` leaves out tools with `llm=False`; category enums gain `mobility`)
- Test: `tests/test_mobility_tools.py`

**Interfaces:**
- Produces (all take `ctx: ToolContext` first; each result carries a `label` saying Modelled or Synthetic):

| Tool | Parameters | Returns | Stage |
|---|---|---|---|
| `traffic_state` | `hour?: int`, `corridor?: str`, `top_n?: int` | `hour`, `totals`, `counts`, `worst` (segment, road, v/c, class) | SENSE |
| `detect_traffic_incidents` | none | `reports_evaluated`, `detected`, `detections`. Each `New` report becomes one detection (category `mobility`, type "Traffic Incident", risk from `rules.report_risk`) and the report becomes `Detected`. The detection's evidence states the modelled load on that road section at this hour with the lanes blocked, and whether that is abnormal (`rules.ABNORMAL_VC`); this is the design's "blocked-lane report and abnormal congestion". While the traffic model is not ready, the evidence says the load is not known yet and the risk leaves that part out. | SENSE |
| `simulate_closure` | `corridor: str` (required), `lanes_closed?: int`, `start_time?`, `end_time?`, `duration_hours?: number`, `near?: str` | `scenario_id`, `summary`, `resolved` | UNDERSTAND |
| `compare_closure_strategies` | as `simulate_closure` | `scenario_id`, `recommended`, `verdict`, `strategies`, `assumptions`. `llm=False`. | UNDERSTAND |
| `simulate_event` | `place: str` (required), `attendance: int` (required), `start_time?`, `end_time?` | `scenario_id`, `summary`, `event` | UNDERSTAND |
| `hospital_access` | `hour?: int` | `worst`, `mean_min`, `rows` (zone, nearest hospital, minutes) | UNDERSTAND |
| `road_safety_context` | `segment_id?: str`, `corridor?: str`, `top_n?: int` | `accidents`, `asset_condition`, `maintenance_priority` | UNDERSTAND |
| `propose_traffic_plan` | `incident_id?: str`, `scenario_id?: str` | `status: "AWAITING_APPROVAL"`, `approval`. Consequential. | ACT |

- The three simulation tools run in the caller's thread and store their scenario row through `Jobs` code paths, so a tool call and a crew job produce the same kind of row.
- `traffic_state` and `hospital_access` raise `ToolError("The traffic model is still being built. Try again in a few seconds.")` while the model is not ready.

- [ ] **Step 1:** Write the failing tests: `detect_traffic_incidents` twice creates one detection per report; `simulate_closure` with `lanes_closed=0` returns a structured error with the engine's sentence; `compare_closure_strategies` is missing from `registry.schemas()` and still runs through `registry.execute`; `propose_traffic_plan` on a closed incident is an error and on an open one creates exactly one `Proposed` approval; every tool's audit row is written.
- [ ] **Step 2:** Implement, run the tests, commit.

### Task 5: The three simulated mobility events

**Files:**
- Modify: `backend/services/simulation.py` (`scenario()` names `traffic_incident`, `road_closure`, `major_event`), `backend/orchestration/crew.py` (`EVENT_SCOPE`), `backend/services/feeds.py` (`on_scenario` ignores them)
- Test: `tests/test_mobility_events.py`

**Interfaces:**
- Produces: `sim.scenario("traffic_incident")` writes one `TRAFFIC_REPORTS` row (a crash blocking 2 lanes on a motorway or arterial section chosen by the seeded generator, status `New`); `"road_closure"` writes one `CLOSURES` row (status `Requested`, full closure, tomorrow 08:00 to 16:00, with a reason); `"major_event"` writes one `EVENT_NOTICES` row (a named venue the engine can resolve, attendance, 18:00 to 23:00, status `New`). Each sets the simulator's answer key for its id and writes a `Sim_Events` line. Each returns `{"scenario", "id", "corridor" or "venue"}`. `Crew.EVENT_SCOPE` returns `frozenset({"mobility"})` for the three names.

- [ ] **Step 1:** Write the failing tests: each event writes exactly one row with `Data_Classification` synthetic; the chosen road exists in the network; injecting `traffic_incident` three times picks sections on at least two different roads; the unknown-scenario error message lists the three new names.
- [ ] **Step 2:** Implement, run the tests, commit.

### Task 6: The crew: three agents and the mobility lifecycle

**Files:**
- Modify: `backend/orchestration/crew.py`, `backend/tools/ops.py` (`create_incidents_from_detections`, `INSTR`), `backend/services/learning.py` (`CATS`), `backend/services/synthetic.py` (learning settings for `mobility`)
- Test: `tests/test_mobility_crew.py`, `tests/test_crew.py` (unchanged assertions must still pass)

**Interfaces:**
- Consumes: Tasks 1 to 5.
- Produces:
  - Agents: `nasser` "Traffic GeoCoworker" (`traffic_state`, `detect_traffic_incidents`), `noura` "Mobility Simulation GeoCoworker" (`simulate_closure`, `compare_closure_strategies`, `simulate_event`, `hospital_access`), `fahad` "Road Safety & Assets GeoCoworker" (`road_safety_context`). Turki gains `propose_traffic_plan`. Eleven agents in the roster.
  - Incident types: "Traffic Incident", "Planned Road Closure", "Major Event Traffic Plan". Team "Traffic Response".
  - `DETECTOR["mobility"] = "nasser"`.
  - `Crew.mobility_result(row: dict) -> dict | None`: called when a job ends; takes the crew lock, then the store.
  - `Crew.roster()` shows Noura as working ("simulating {road or venue}") while one of her jobs is queued or running, read from `Jobs`.
  - `Crew.feed_status()` gains two entries: `traffic` (agent `nasser`) and `closures` "Closures & events" (agent `noura`).
- The lifecycle, one scan:
  1. **Watch** (`want("mobility")`): Nasser runs `detect_traffic_incidents`. `Requested` closures and `New` event notices each become one detection (types "Road Closure Request", "Major Event"), written by the crew as citizen-report clusters are today.
  2. **Triage:** Mansour's existing step. One incident per detection.
  3. **Assess:** Reem's existing impact step. Fahad adds one trail line from `road_safety_context`. Faisal escalates a Critical one. The alert goes out now, with "Noura is calculating the road impact" and no approval yet.
  4. **Understand:** after the scan's batch has been sent, the crew submits one job per new mobility incident (`incident`, `closure` or `event`).
  5. **Decide and act** (`mobility_result`): the alert's message and trail are updated with the numbers and its status returns to `New`; Turki calls `propose_traffic_plan`; the approval is attached to the alert. On `Failed` or `Interrupted` the alert says why, and Turki calls `propose_work_order` for a plain field check instead.
  6. **Follow through:** dispatch, field results and closing are the existing steps. A `Requested` closure whose plan was rejected becomes `Rejected`.
- Alert sentences (English; each has an Arabic version):
  - Traffic incident: "Road impact (modelled): {n} lane(s) blocked on {road} for about 2 hours adds {h} trip-hours and {m} min to the worst hospital access; {s} road sections become severe."
  - Closure: "Road impact (modelled): closing {road} {start} to {end} adds {h} trip-hours. Recommended response: {strategy} ({b}% less delay)." followed by the verdict.
  - Event: "Road impact (modelled): {attendance} people at {venue} add {v} vehicles per hour at the peak and {h} trip-hours; parking is short by {p} vehicles."

- [ ] **Step 1:** Write the failing tests (jobs inline): injecting each of the three events ends with one incident of the right type, one alert whose message holds the modelled sentence, and one `Proposed` `apply_traffic_plan` approval; a second scan adds nothing; with the job runner forced to fail, the alert says the impact could not be calculated and a `create_work_order` approval exists instead; a mobility incident whose area is a road name does not break `executive.compute_kpis`, the hotspots, the trends or `list_incidents`; a water-only scan (`scope={"water"}`) starts no mobility job; the roster has eleven agents and the first two are Faisal and Mansour; with a job held in the queue (jobs not inline, worker paused) the roster shows Noura as working and a full scan still returns.
- [ ] **Step 2:** Implement, run the new tests and the whole existing suite, commit.

### Task 7: Approval, the plan record, field verification and closing

**Files:**
- Modify: `backend/workflows/actions.py` (`apply_traffic_plan`, `NO_REPAIR_TYPES`, `close_incident`), `backend/tools/ops.py` (`propose_incident_closure`), `backend/services/simulation.py` (`field_observation` for `mobility`), `backend/tools/verification.py` if it lists categories
- Test: `tests/test_mobility_workflow.py`

**Interfaces:**
- Produces:
  - `HANDLERS["apply_traffic_plan"](store, payload) -> {"ok", "work_order_id", "incident_id", "closure_id"?}`. Payload: `incident_id`, `kind` (`incident | closure | event`), `scenario_id`, `strategy`, `team`, `task_type`, `instructions`, `due_hours`, and for a closure `closure_id`. It creates the work order (the field check of the plan), moves the incident to "Work Order Created", sets a closure to `Approved` with its `Strategy` and `Work_Order_ID`, and an event notice to `Planned`. A second run for an incident with an active work order is refused, as `create_work_order` does.
  - `actions.NO_REPAIR_TYPES = ("Planned Road Closure", "Major Event Traffic Plan")`: for these, `Confirmed` is enough to propose and to carry out the closing (decision 5). When such an incident is closed, its closure moves to `In Place`.
  - Task types on the work order: "Confirm the road is clear", "Confirm the closure is in place", "Confirm the traffic plan is in place".
  - Simulated investigator texts for the three types, true and false, consistent with the answer key.

- [ ] **Step 1:** Write the failing tests: approving a closure plan gives a work order, a closure row `Approved` with the recommended strategy, and nothing else changed; rejecting it changes no record except the approval, and the next scan marks the closure `Rejected`; a confirmed "Planned Road Closure" incident can be closed without a repair report and a confirmed "Traffic Incident" cannot; the whole path for a traffic incident (approve plan, approve dispatch, simulated visit, simulated clearing, approve closing) ends `Resolved` and adds one verified detection to the `mobility` learning numbers.
- [ ] **Step 2:** Implement, run the tests, commit.

### Task 8: The cross-domain link: road impact on a water-leak repair

**Files:**
- Create: `backend/mobility/road_impact.py`
- Modify: `backend/orchestration/crew.py` (after Turki prepares a water work order), `backend/workflows/approvals.py` (`amend`), `backend/workflows/actions.py` (`create_work_order` with a closure plan)
- Test: `tests/test_road_impact.py`

**Interfaces:**
- Produces:

```python
# backend/mobility/road_impact.py
def nearest_road(lonlat: tuple, radius_m: float) -> dict | None      # the model's road section within the radius: {"segment_id", "corridor", "name", "lanes", "distance_m"}
def params(category: str, road: dict) -> dict                         # the road_impact job's parameters from rules.ROAD_IMPACT
def recommend(day: dict, night: dict) -> str                          # "night" when night trip-hours < (1 - night_saving) x day; else "day"
def line(summary: dict) -> str                                        # the sentence below
def closure_plan(summary: dict, road: dict) -> dict                   # what is stored with the proposal: road, section ids, lanes, window, scenario id

# backend/workflows/approvals.py
def amend(self, approval_id: str, patch: dict, expected_suffix: str = "") -> bool   # only while Proposed; merges into the payload; audited; False otherwise
```

- The sentence: "Road impact (modelled): closing 2 lanes of Olaya Street 08:00 to 16:00 adds 1,200 trip-hours and 4 min to the worst hospital access; at night 150 trip-hours and 1 min. Recommended: night." With a full closure it reads "closing Olaya Street". When both windows are under `SMALL_IMPACT_TRIP_HOURS` it reads "Road impact (modelled): small in both windows (day {a}, night {b} trip-hours). Recommended: day."
- Flow: Turki's work-order alert gets the trail line "Noura is calculating the road impact of the repair"; the `road_impact` job is submitted after the scan's batch; on the result the line is added to the alert. If the approval is still `Proposed`, `amend` adds `closure_plan` and the "If approved" text gains the window. If it was already approved or rejected, the line is added as information and nothing else changes.
- `create_work_order` with a `closure_plan` in its payload also creates one `CLOSURES` row (`Approved`, linked to the work order and incident, reason "Water leak repair") and puts the window into the work order's instructions. One approval covers both.

- [ ] **Step 1:** Write the failing tests (jobs inline): a leak within 60 m of a skeleton road gets the line and a `closure_plan` in the pending approval; approving it creates the work order and exactly one closure row; approving first and running the job after leaves no closure row and adds the line as information; a leak 200 m from any road gets no job and no line; on a 2-lane road the line says "closing {road}" and the run is a full closure; `recommend` returns "day" when night saves 5% and "night" when it saves 50%; a streetlight incident never starts a road-impact job.
- [ ] **Step 2:** Implement, run the tests, commit.

### Task 9: API and pages

**Files:**
- Modify: `backend/api/app.py`, `frontend/index.html` (menu), `frontend/nccc.js` (alert buttons, crew panel), `frontend/nccc.css`, `frontend/mobility.js` (Planned closures layer, impact drawing), `frontend/mobility.css`, `frontend/strategic_dashboard.js` only if the shared module needs a new argument, `frontend/i18n.js`, `backend/services/i18n.py`
- Test: `tests/test_mobility_api.py`, `tests/test_i18n.py`

**Interfaces:**
- Produces:

| Route | Returns |
|---|---|
| `GET /api/mobility/closures` | GeoJSON of closures that are `Requested`, `Approved` or `In Place`: id, road, lanes closed, window, status, incident |
| `GET /api/mobility/scenarios/{id}` | the stored row with `Summary` parsed, plus the job status; 404 for an unknown id |
| `GET /api/mobility/scenarios/{id}/map` | `{"closed", "segments", "routes"}`; while it is being recalculated HTTP 503 with `Retry-After: 3`, as the traffic route does; 404 for an unknown id |
| `POST /api/nccc/events/{name}` | unchanged; accepts the three new names |

- The notification carries `scenario_id` and `scenario_status` so the page knows when to show the button.
- Page changes:
  - **Simulate an event** menu in two groups: City services (the four existing entries) and Mobility (Traffic incident, Road closure, Major event).
  - **Crew panel:** eleven agents; Faisal and Mansour on the first row, then three per row.
  - **Alerts:** a "View impact on map" button on alerts that have a finished scenario. It draws the closed section, the road sections that get worse and the detour routes, with a "Modelled" note and a button to clear the drawing.
  - **Map:** the "Planned closures" checkbox deferred from Plan 2, on both pages.
  - **Feed cards:** Traffic and Closures & events appear through the existing card list.

- [ ] **Step 1:** Write the failing tests: the closures route returns only the three statuses; the map route answers 503 then 200 for a scenario whose preview is no longer held, and 404 for `SCN-9999`; every new page string and every alert and trail sentence pattern has an Arabic entry.
- [ ] **Step 2:** Implement. Check the page syntax with `node --check`. Commit.

### Task 10: Account changes and Checkpoint 3

- [ ] **Step 1:** Run the full test suite.
- [ ] **Step 2:** Dry runs: `scripts/create_feature_layers.py` (expected: 4 to create, 28 unchanged) and `scripts/add_mobility_demo_rows.py` (expected: 2 rows to add). Show both to the user and **stop for a yes**.
- [ ] **Step 3:** After the yes: apply both, read back the four layers' fields and the two workers.
- [ ] **Step 4:** On the live app, in the browser, in English and Arabic:
  - Inject each of the three mobility events; follow one traffic incident from alert to `Resolved`.
  - The headline story: inject the water leak; the alert gains the road-impact line; approve once; the work order and the planned closure exist in ArcGIS Online (read directly); the closure is drawn on the map; simulated verification; closing.
  - Approve a second leak's work order before the impact arrives and confirm no closure record is created.
  - No console errors. The four city-service use cases still work.
- [ ] **Step 5:** Measure and record in `docs/arcgis_checks.md`: time for an incident simulation, a strategy comparison and a road-impact run on the full network; scan time with and without a job running; start-up with 32 layers.
- [ ] **Step 6:** Update `README.md`, commit, and report **Checkpoint 3** to the user with the measurements and what was not checked.
