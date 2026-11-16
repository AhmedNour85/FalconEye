"""Tool registry: JSON-schema tool definitions exposed to the single GeoAI Operations Agent, with input validation."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Callable

from backend.tools import analytics, city, executive, geoai, mobility, ops, verification
from backend.tools.common import ToolContext, ToolError


@dataclass
class Tool:
    name: str
    description: str
    properties: dict
    required: tuple[str, ...]
    fn: Callable
    stage: str
    consequential: bool = False  # True => only creates an approval proposal, never executes
    llm: bool = True             # False => not offered to language-model planners (too slow for a chat turn); the crew and the offline planner can still call it

    def schema(self) -> dict:
        return {"name": self.name, "description": self.description,
                "input_schema": {"type": "object", "properties": self.properties, "required": list(self.required), "additionalProperties": False}}


def _t(name, desc, props, req, fn, stage, consequential=False, llm=True):
    return Tool(name, desc, props, tuple(req), fn, stage, consequential, llm)


S_ = {"type": "string"}
CATS = ["water", "lighting", "change", "mobility"]
HOUR = {"type": "integer", "description": "Hour of the day, 0 to 23, Riyadh time. Default: now."}
ROAD = {"type": "string", "description": "Road name, e.g. 'King Fahd Road', 'Olaya Street', 'Northern Ring Road'"}
CLOSURE = {"corridor": ROAD, "lanes_closed": {"type": "integer", "description": "Lanes closed. Leave out for a full closure."},
           "start_time": {"type": "string", "description": "ISO date and time, e.g. 2026-11-17T08:00. Default: tomorrow 08:00."},
           "end_time": {"type": "string", "description": "ISO date and time"}, "duration_hours": {"type": "number"},
           "near": {"type": "string", "description": "A named place the closed section is nearest to, e.g. 'KAFD'"}}
AREA = {"type": "string", "description": "Riyadh demo area: Olaya, KAFD, Al Malaz, Diplomatic Quarter, King Salman Park, Diriyah"}

TOOLS: list[Tool] = [
    _t("sensor_intelligence", "SENSE. Evaluate water pressure/flow sensors (z-score vs same hour yesterday). Use to inspect raw sensor state or list anomalous sensors.",
       {"sensor_id": S_, "area": AREA, "anomalies_only": {"type": "boolean"}}, [], analytics.sensor_intelligence, "SENSE"),
    _t("detect_water_leaks", "SENSE. Detect SUSPECTED water leaks from pressure/flow anomalies (pressure >=10% below the same hours yesterday and z>=3.5), localise them, score risk and persist detection records. Results are suspected, never confirmed. When nothing is found the result explains why and lists the closest candidates.",
       {"area": AREA, "min_risk": {"type": "number", "description": "Hides detections whose risk score is below this value. It does NOT make detection more sensitive; with 0 nothing changes."}}, [], analytics.detect_water_leaks, "SENSE"),
    _t("predict_streetlight_failures", "SENSE. Predict streetlight failures (probability, risk, clusters). Predictions are not confirmed faults.",
       {"area": AREA, "corridor": {"type": "string", "description": "e.g. 'King Fahd Road', 'Olaya Street'"}, "min_probability": {"type": "number"}}, [], analytics.predict_streetlight_failures, "SENSE"),
    _t("detect_imagery_changes", "SEE. Compare two imagery epochs for an area (SIMULATED imagery, real algorithm) and store change candidates + detections for significant ones.",
       {"area": AREA, "k_sigma": {"type": "number"}, "significant_area_sqm": {"type": "number"}}, [], geoai.detect_imagery_changes, "SEE"),
    _t("monitor_poles", "SENSE. Monitor streetlight POLE structural health (tilt, corrosion, age) and flag poles beyond the safety limits. Predictions, not confirmed failures.",
       {"area": AREA, "corridor": {"type": "string", "description": "e.g. 'King Fahd Road', 'Olaya Street'"}}, [], city.monitor_poles, "SENSE"),
    _t("detect_visual_distortion", "SEE. Compare building footprints between two imagery epochs and flag visual/structural distortion (SIMULATED imagery). Candidates for a structural survey.",
       {"area": AREA}, [], city.detect_visual_distortion, "SEE"),
    _t("analyze_land_use", "UNDERSTAND. Classify new construction/clearing seen in the imagery and check it against the area's zoning; flags land-use violations (SIMULATED imagery and zoning).",
       {"area": AREA}, [], city.analyze_land_use, "UNDERSTAND"),
    _t("extract_geoai_features", "UNDERSTAND. Extract building footprints and road segments around a detected change (simulated GeoAI). Defaults to the change in focus.",
       {"change_id": S_}, [], geoai.extract_geoai_features, "UNDERSTAND"),
    _t("spatial_analysis", "UNDERSTAND. Proximity analysis around a detection/change/incident/asset: facilities, pipes, streetlights, roads, nearby incidents, extracted features.",
       {"target_type": {"type": "string", "enum": ["detection", "change", "incident", "asset", "work_order"]}, "target_id": S_, "radius_m": {"type": "number"}}, ["target_type"], geoai.spatial_analysis, "UNDERSTAND"),
    _t("executive_summary", "DECIDE. KPIs, hotspots, ranked incidents and evidence-based recommendations, optionally filtered.",
       {"area": AREA, "category": {"type": "string", "enum": CATS}, "priority": {"type": "string", "enum": ["P1", "P2", "P3", "P4"]}, "since": {"type": "string", "description": "ISO date"}},
       [], executive.executive_summary, "DECIDE"),
    _t("create_incidents_from_detections", "DECIDE/ACT. Convert detections into operational incidents (idempotent). Defaults to the detections this conversation just produced; if none are waiting, every active detection that still has no incident.",
       {"detection_ids": {"type": "array", "items": S_}}, [], ops.create_incidents_from_detections, "ACT"),
    _t("list_incidents", "ACT. List incidents sorted by urgency, with optional filters.",
       {"status": S_, "category": {"type": "string", "enum": CATS}, "area": AREA, "priority": {"type": "string", "enum": ["P1", "P2", "P3", "P4"]},
        "open_only": {"type": "boolean"}, "limit": {"type": "integer"}, "since": {"type": "string", "description": "ISO date"}}, [], ops.list_incidents, "ACT"),
    _t("get_incident", "ACT. Full incident record with detections, work orders, verifications and audit trail. Defaults to the incident in focus.",
       {"incident_id": S_}, [], ops.get_incident, "ACT"),
    _t("rank_incidents", "DECIDE. Rank open incidents by urgency and explain the evidence; the top one becomes the focus incident.",
       {"top_n": {"type": "integer"}, "category": {"type": "string", "enum": CATS}, "area": AREA,
        "priority": {"type": "string", "enum": ["P1", "P2", "P3", "P4"]}, "since": {"type": "string", "description": "ISO date"}}, [], ops.rank_incidents, "DECIDE"),
    _t("count_incidents", "DECIDE. How many incidents there are, and where: counts by area, type, priority and status. Use for 'how many', 'where' and 'which area' questions.",
       {"area": AREA, "category": {"type": "string", "enum": CATS}, "severity": {"type": "string", "enum": ["Critical", "High", "Medium", "Low"]},
        "open_only": {"type": "boolean", "description": "default true: only incidents that are not resolved"}}, [], ops.count_incidents, "DECIDE"),
    _t("feeds_summary", "UNDERSTAND. What the citizen-report feed says right now (SIMULATED feed): report counts by status, type and area.",
       {"area": AREA}, [], ops.feeds_summary, "UNDERSTAND"),
    _t("propose_work_order", "ACT. PROPOSE a work order for an incident. Creates an approval request only; nothing is created until a human approves.",
       {"incident_id": S_, "instructions": S_}, [], ops.propose_work_order, "ACT", True),
    _t("propose_work_orders_bulk", "ACT. PROPOSE work orders for the top N open incidents (approval required for each).",
       {"top_n": {"type": "integer"}}, [], ops.propose_work_orders_bulk, "ACT", True),
    _t("propose_field_assignment", "ACT. Recommend and PROPOSE assigning a field worker to a work order (skills, proximity, workload). Approval required.",
       {"work_order_id": S_, "worker_id": S_}, [], ops.propose_field_assignment, "ACT", True),
    _t("propose_incident_closure", "VERIFY/ACT. PROPOSE closing an incident after field verification. Approval required.",
       {"incident_id": S_}, [], ops.propose_incident_closure, "ACT", True),
    _t("propose_asset_status_change", "ACT. PROPOSE changing an operational asset status. Approval required.",
       {"asset_id": S_, "new_status": S_}, ["asset_id", "new_status"], ops.propose_asset_status_change, "ACT", True),
    _t("verify_outcome", "VERIFY. Retrieve field evidence for an incident and compare it with the original AI finding; reports the outcome recorded by the system.",
       {"incident_id": S_}, [], verification.verify_outcome, "VERIFY"),
    _t("evaluate_outcomes", "LEARN. Predicted-vs-verified evaluation metrics (precision, recall where ground truth exists); recalibrate=true refreshes the configurable risk calibration (no ML retraining).",
       {"recalibrate": {"type": "boolean"}}, [], verification.evaluate_outcomes, "LEARN"),
    # ---- mobility (Plan 3). Traffic numbers are MODELLED, never measured; road reports and safety records are SYNTHETIC.
    _t("traffic_state", "SENSE. MODELLED traffic at one hour of a normal weekday: totals, how many road sections are slow, heavy or stop-and-go, and the most loaded sections. Not measured.",
       {"hour": HOUR, "corridor": ROAD, "top_n": {"type": "integer"}}, [], mobility.traffic_state, "SENSE"),
    _t("detect_traffic_incidents", "SENSE. Turn new road reports (blocked lanes; SYNTHETIC feed) into SUSPECTED traffic-incident detections, with the modelled load on the road section. Each report is evaluated once.",
       {}, [], mobility.detect_traffic_incidents, "SENSE"),
    _t("simulate_closure", "UNDERSTAND. Simulate closing a road section, fully or by a number of lanes, for a time window. Returns MODELLED extra trip-hours, hospital-access change and congested sections. Takes 10 to 25 seconds.",
       CLOSURE, ["corridor"], mobility.simulate_closure, "UNDERSTAND"),
    _t("compare_closure_strategies", "UNDERSTAND. Simulate one closure under five response strategies (do nothing, reschedule to night, diversion with signal retiming, demand shift, combined) and recommend one. Strategy effects are assumptions. Takes 1 to 2 minutes.",
       CLOSURE, ["corridor"], mobility.compare_closure_strategies, "UNDERSTAND", llm=False),
    _t("simulate_event", "UNDERSTAND. Simulate the extra traffic of a major event at a named place. Returns MODELLED added vehicles per hour, extra trip-hours and the parking gap. Takes 10 to 25 seconds.",
       {"place": {"type": "string", "description": "A named place, e.g. 'KAFD', 'King Salman Park', 'Diriyah'"}, "attendance": {"type": "integer"},
        "start_time": {"type": "string", "description": "ISO date and time. Default: today 18:00."}, "end_time": {"type": "string", "description": "ISO date and time. Default: today 23:00."}},
       ["place", "attendance"], mobility.simulate_event, "UNDERSTAND"),
    _t("hospital_access", "UNDERSTAND. MODELLED travel time from each named district to its nearest hospital at one hour, worst first. Hospital positions are approximate.",
       {"hour": HOUR}, [], mobility.hospital_access, "UNDERSTAND"),
    _t("road_safety_context", "UNDERSTAND. Accident history, road-asset condition and maintenance priority for a road section, a road or the whole network. SYNTHETIC records, not real data.",
       {"segment_id": S_, "corridor": ROAD, "top_n": {"type": "integer"}}, [], mobility.road_safety_context, "UNDERSTAND"),
    _t("propose_traffic_plan", "ACT. PROPOSE the traffic plan for a mobility incident (traffic response, closure plan or event traffic plan) from its completed simulation. Creates an approval request only. An approved plan is a record; nothing controls signals, signs or dispatch systems.",
       {"incident_id": S_, "scenario_id": S_}, [], mobility.propose_traffic_plan, "ACT", True),
]
BY_NAME = {t.name: t for t in TOOLS}


def schemas() -> list[dict]:
    """The tools offered to a language-model planner. A tool with llm=False is left out; it can still be run through `execute`."""
    return [t.schema() for t in TOOLS if t.llm]


_TYPES = {"string": str, "number": (int, float), "integer": int, "boolean": bool, "array": list}


def validate(tool: Tool, args: dict) -> dict:
    if not isinstance(args, dict):
        raise ToolError("tool input must be an object")
    unknown = set(args) - set(tool.properties)
    if unknown:
        raise ToolError(f"unknown parameter(s) for {tool.name}: {sorted(unknown)}")
    for r in tool.required:
        if r not in args or args[r] in (None, ""):
            raise ToolError(f"missing required parameter '{r}' for {tool.name}")
    clean = {}
    for k, v in args.items():
        if v is None:
            continue
        spec = tool.properties[k]
        t = _TYPES[spec["type"]]
        if isinstance(v, bool) and spec["type"] in ("number", "integer"):
            raise ToolError(f"parameter '{k}' must be {spec['type']}")
        if not isinstance(v, t):
            raise ToolError(f"parameter '{k}' must be {spec['type']}")
        if "enum" in spec and v not in spec["enum"]:
            raise ToolError(f"parameter '{k}' must be one of {spec['enum']}")
        clean[k] = v
    return clean


def execute(ctx: ToolContext, name: str, args: dict) -> dict:
    """Run a tool with validation, timing and audit; failures return a structured error (never raise to the model)."""
    tool = BY_NAME.get(name)
    t0 = time.time()
    if tool is None:
        return {"ok": False, "error": f"unknown tool '{name}'"}
    try:
        clean = validate(tool, args)
        out = tool.fn(ctx, **clean)
        res = {"ok": True, "result": out}
    except ToolError as exc:
        res = {"ok": False, "error": str(exc)}
    except Exception as exc:  # unexpected: surface cleanly, keep the session alive
        res = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    ms = round((time.time() - t0) * 1000)
    status = "Proposed" if tool.consequential and res["ok"] else "N/A"
    ctx.p.audit.log(ctx.session_id, f"TOOL {name}", name, ctx.state.get("focus_incident", ""), args, res.get("error") or _brief(res["result"]), status)
    res["tool"], res["duration_ms"], res["stage"] = name, ms, tool.stage
    return res


def _brief(o) -> str:
    return json.dumps(o, default=str)[:300]
