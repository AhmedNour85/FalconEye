# Agent tools and sample prompts

All tools are exposed to the single **GeoAI Operations Agent** (`GET /api/tools`). Tools marked 🔒 only *propose*; a human approval executes them.

| Stage | Tool | What it does |
|---|---|---|
| SENSE | `sensor_intelligence` | Sensor state vs same hour yesterday |
| SENSE | `detect_water_leaks` | Suspected leaks, localisation, risk, impact context; persists detections |
| SENSE | `predict_streetlight_failures` | Failure probability, clusters, priority; persists predicted detections |
| SENSE | `monitor_poles` | Poles beyond the tilt or corrosion limits; merged into the streetlight use case |
| SEE | `detect_imagery_changes` | Two-epoch change candidates (simulated imagery) |
| SEE | `detect_visual_distortion` | Visual distortion between two imagery dates: the eight street-level types and structural shape change (simulated imagery) |
| SEE | `analyze_land_use` | Significant changes classified and checked against each area's zoning: violation candidates |
| UNDERSTAND | `extract_geoai_features` | Buildings/roads around a change (simulated GeoAI) |
| UNDERSTAND | `spatial_analysis` | Facilities, pipes, lights, roads, incidents within a radius |
| DECIDE | `executive_summary`, `rank_incidents` | KPIs, hotspots, ranking, evidence-based recommendations |
| ACT | `create_incidents_from_detections`, `list_incidents`, `get_incident`, `count_incidents`, `feeds_summary` | Idempotent incident management, counts by area/type/status, the citizen-report feed |
| ACT 🔒 | `propose_work_order`, `propose_work_orders_bulk`, `propose_field_assignment`, `propose_incident_closure`, `propose_asset_status_change` | Approval requests |
| VERIFY | `verify_outcome` | Field evidence vs AI finding |
| LEARN | `evaluate_outcomes` | Metrics; `recalibrate=true` updates configurable risk calibration |

Spec tools Work Order Management / Field Assignment / Incident Management are the `propose_*` + incident tools; Outcome Evaluation is `evaluate_outcomes`.

## Sample prompts
- Detect possible water leaks in Riyadh. / Check the water network for potential leaks.
- Which one is the most critical? → Create a work order for that one. → Approve. → Assign a field worker. → Approve. → Verify the outcome.
- Identify streetlights with a high probability of failure on King Fahd Road.
- Compare imagery epochs in Olaya District. / Show me all significant urban changes.
- Extract buildings and roads around the detected changes. / Show spatial context for that one.
- Identify the highest-risk geographic areas. / Which incidents require immediate intervention?
- Create work orders for the top five priority incidents. → approve all
- Show me which incidents have been verified. / Compare the AI predictions with actual field observations.

The planner can be switched on the Operation page (planner icon): offline rules, Claude, OpenAI, Gemini, LM Studio, Ollama, Hermes or any OpenAI-compatible server (`backend/agent/providers.py`). Every planner uses these same tools and the same approval gate. Arabic questions are understood by the offline planner and answered in Arabic.

The agent runs on Claude when `ANTHROPIC_API_KEY` is set (manual tool-use loop, `claude-opus-5-5`, configurable via `ANTHROPIC_MODEL`); otherwise an offline planner maps these phrasings to the same tools.
