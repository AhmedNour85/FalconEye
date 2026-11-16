"""Mobility tools: traffic state, road reports, closure and event simulations, hospital access, road-safety context, traffic plans.

Every traffic number here is MODELLED (a static assignment of synthetic demand on the road network), never measured. Road reports,
accident history and road-asset condition are SYNTHETIC. `propose_traffic_plan` only creates an approval request: an approved plan
is a record, and nothing controls signals, signs or dispatch systems.
"""
from __future__ import annotations

import datetime as dt

from backend.gis import schema as S
from backend.gis.store import utcnow
from backend.mobility import accessibility, network_model, rules, safety, sources, traffic
from backend.services import learning
from backend.services.workforce import TEAM_FOR
from backend.tools.common import ToolContext, ToolError, severity_of

MODELLED = "Modelled: calculated from the road network and synthetic demand, not measured"
BUILDING = "The traffic model is still being built. Try again in a few seconds."
CLOSED = ("Resolved", "Closed - False Positive")
DUE_HOURS = {"P1": 4, "P2": 12, "P3": 48, "P4": 120}

# incident type -> what kind of plan it gets, and the field check that goes with it
KINDS = {"Traffic Incident": "incident", "Planned Road Closure": "closure", "Major Event Traffic Plan": "event"}
TASK_TYPE = {"incident": "Confirm the road is clear", "closure": "Confirm the closure is in place", "event": "Confirm the traffic plan is in place"}


def riyadh_hour() -> int:
    return (dt.datetime.utcnow() + dt.timedelta(hours=3)).hour


def _hour(hour) -> int:
    h = riyadh_hour() if hour is None else hour
    if not 0 <= h <= 23:
        raise ToolError("hour must be a whole number from 0 to 23")
    return h


def model_ready(ctx: ToolContext, hour: int) -> bool:
    """False while the start-up build of the traffic model has not reached this hour. Without a start-up build the model is built on demand."""
    if not getattr(ctx.p.settings, "mobility_warm", False):
        return True
    return hour in traffic.status()["hours_ready"]


def _roads() -> dict:
    return {r["id"]: r for r in sources.load_network()[0]}


def _corridor_ids(corridor: str) -> list[str]:
    want = corridor.strip().lower()
    ids = [i for i, r in _roads().items() if (r["corridor"] or "").lower() == want]
    if not ids:
        raise ToolError(f"The road network has no road named '{corridor}'.")
    return ids


def load_on(ctx: ToolContext, segment_id: str, hour: int) -> float | None:
    """Modelled volume / capacity of one road section at this hour, or None when the model is not ready or the section is unknown."""
    if not model_ready(ctx, hour):
        return None
    e = network_model.get_model().assign(sources.demand_factor(hour))["edges"].get(segment_id)
    return round(float(e["vc"]), 2) if e else None


# ---------------------------------------------------------------------------------------------- SENSE
def traffic_state(ctx: ToolContext, hour: int | None = None, corridor: str | None = None, top_n: int = 5) -> dict:
    h = _hour(hour)
    if not model_ready(ctx, h):
        raise ToolError(BUILDING)
    s = traffic.state(h)
    roads = _roads()
    only = set(_corridor_ids(corridor)) if corridor else None
    rows = [{"segment_id": sid, "road": roads[sid]["corridor"] or roads[sid]["name"], "load": v[0], "class": v[1]}
            for sid, v in s["segments"].items() if sid in roads and (only is None or sid in only)]
    rows.sort(key=lambda r: (-r["load"], r["segment_id"]))
    return {"hour": h, "totals": s["totals"], "counts": s["counts"], "worst": rows[:max(1, min(int(top_n), 25))], "sections_slow_or_worse": len(rows),
            "corridor": corridor, "load_means": "volume / capacity", "label": MODELLED}


def detect_traffic_incidents(ctx: ToolContext) -> dict:
    """Each new road report becomes one detection (category mobility). A report is evaluated once."""
    st = ctx.store
    h = riyadh_hour()
    new = [r for r in st.all(S.TRAFFIC_REPORTS) if r["attrs"].get("Status") == "New"]
    found = []
    for r in sorted(new, key=lambda r: r["id"]):
        a = r["attrs"]
        lanes, blocked = max(1, int(a.get("Lanes") or 1)), max(1, int(a.get("Lanes_Blocked") or 1))
        road = a.get("Corridor") or "the road"
        vc = load_on(ctx, a.get("Segment_ID") or "", h)
        after = None if vc is None else (round(vc * lanes / (lanes - blocked), 2) if blocked < lanes else 9.99)
        base = rules.report_risk(lanes, blocked, a.get("Road_Class") or "", after)
        risk = learning.apply_calibration(st, "mobility", base)
        if after is None:
            load = "The modelled load on this section is not known yet (the traffic model is still being built)."
        elif blocked >= lanes:
            load = f"Modelled load on this section at {h:02d}:00 is {vc:.2f} of capacity; every lane is blocked, so the section is closed."
        else:
            load = (f"Modelled load on this section at {h:02d}:00 is {vc:.2f} of capacity; with the lanes blocked about {after:.2f} "
                    f"({'abnormal: heavy or worse' if after >= rules.ABNORMAL_VC else 'within the normal range'}).")
        did = st.next_id("DET")
        st.upsert(S.DETECTIONS, {"Detection_ID": did, "Detection_Type": "Traffic Incident", "Location": road, "Confidence": 0.85, "Severity": severity_of(risk), "Risk_Score": risk,
                                 "Base_Risk_Score": base, "Detection_Date": utcnow(), "Source": "Road report (SYNTHETIC)", "Status": "Suspected", "Related_Asset_ID": r["id"],
                                 "Pipeline_ID": "", "Area_Name": road, "Category": "mobility", "Cluster_ID": "",
                                 "Evidence": f"REPORTED: {a.get('Report_Type') or 'incident'} blocking {blocked} of {lanes} lane(s) on {road} (road report, SYNTHETIC). {load} Needs confirmation on site.",
                                 "Incident_ID": "", "Data_Classification": S.SYNTHETIC}, r["geom"])
        st.update(S.TRAFFIC_REPORTS, r["id"], Status="Detected", Detection_ID=did)
        found.append({"detection_id": did, "report_id": r["id"], "road": road, "segment_id": a.get("Segment_ID"), "lanes": lanes, "lanes_blocked": blocked, "risk_score": risk,
                      "severity": severity_of(risk), "load_now": vc, "load_with_lanes_blocked": after})
    if found:
        ctx.state["last_detections"] = [f["detection_id"] for f in found]
    return {"reports_evaluated": len(new), "detected": len(found), "detections": found, "hour": h,
            "label": "Road reports are SYNTHETIC. Loads are modelled, not measured. Suspected until confirmed on site."}


# ---------------------------------------------------------------------------------------------- UNDERSTAND
def _subject(ctx: ToolContext) -> str:
    return ctx.state.get("focus_incident") or f"session:{ctx.session_id}"


def _ran(ctx: ToolContext, kind: str, params: dict, name: str) -> dict:
    try:
        res = ctx.p.jobs.run_now(kind, {k: v for k, v in params.items() if v is not None}, _subject(ctx), "noura", name)
    except ValueError as exc:
        raise ToolError(str(exc))
    if res["Status"] != "Completed":
        raise ToolError(res["Error"] or "the simulation failed")
    ctx.state["last_scenario"] = res["Scenario_ID"]
    return res


def simulate_closure(ctx: ToolContext, corridor: str, lanes_closed: int | None = None, start_time: str | None = None, end_time: str | None = None,
                     duration_hours: float | None = None, near: str | None = None) -> dict:
    res = _ran(ctx, "closure_run", {"corridor": corridor, "lanes_closed": lanes_closed, "start_time": start_time, "end_time": end_time, "duration_hours": duration_hours, "near": near},
               f"Closure of {corridor}")
    return {"scenario_id": res["Scenario_ID"], "summary": res["summary"], "resolved": {"road": res["summary"]["road"], "section": res["summary"].get("section"),
                                                                                    "window": res["summary"]["window"]}, "label": MODELLED}


def compare_closure_strategies(ctx: ToolContext, corridor: str, lanes_closed: int | None = None, start_time: str | None = None, end_time: str | None = None,
                               duration_hours: float | None = None, near: str | None = None) -> dict:
    res = _ran(ctx, "closure", {"corridor": corridor, "lanes_closed": lanes_closed, "start_time": start_time, "end_time": end_time, "duration_hours": duration_hours, "near": near},
               f"Strategy comparison for {corridor}")
    s = res["summary"]
    return {"scenario_id": res["Scenario_ID"], "recommended": res["Recommended"], "verdict": res["Verdict"], "strategies": s["strategies"], "assumptions": s["assumptions"],
            "do_nothing": {k: s[k] for k in ("window_extra_trip_hours", "worst_hospital_access_delta_min", "severe_segments")}, "window": s["window"],
            "label": MODELLED + ". Strategy effects are assumptions, listed with the result."}


def simulate_event(ctx: ToolContext, place: str, attendance: int, start_time: str | None = None, end_time: str | None = None) -> dict:
    res = _ran(ctx, "event", {"place": place, "attendance": attendance, "start_time": start_time, "end_time": end_time}, f"Event at {place}")
    s = res["summary"]
    return {"scenario_id": res["Scenario_ID"], "summary": s, "event": {"venue": s["venue"], "attendance": s["attendance"], "window": s["window"]},
            "label": MODELLED + ". Car share, parking supply and metro capacity are assumptions."}


def simulate_demand_growth(ctx: ToolContext, place: str, growth_pct: float = 20.0) -> dict:
    res = _ran(ctx, "demand", {"place": place, "growth_pct": growth_pct}, f"Demand growth near {place}")
    return {"scenario_id": res["Scenario_ID"], "summary": res["summary"], "label": MODELLED + ". The growth is the figure asked for, not a forecast."}


def hospital_access(ctx: ToolContext, hour: int | None = None) -> dict:
    h = _hour(hour)
    if not model_ready(ctx, h):
        raise ToolError(BUILDING)
    m = network_model.get_model().clone()
    m.assign(sources.demand_factor(h), use_cache=False)          # the copy keeps this hour's congested travel times
    a = accessibility.accessibility(m)
    rows = sorted(({"zone": z["zone"], "nearest_hospital": z["nearest_hospital"], "minutes": z["min_to_hospital"], "isolated": z["isolated"]}
                   for z in a["zones"].values() if z["named"]), key=lambda r: -(r["minutes"] if r["minutes"] is not None else 1e9))
    timed = [r["minutes"] for r in rows if r["minutes"] is not None]
    return {"hour": h, "worst": rows[0] if rows else None, "mean_min": round(sum(timed) / len(timed), 1) if timed else None,
            "share_within_15_min": a["within_target_share"], "rows": rows, "label": MODELLED + ". Hospital positions are approximate."}


def road_safety_context(ctx: ToolContext, segment_id: str | None = None, corridor: str | None = None, top_n: int = 5) -> dict:
    ids = [segment_id] if segment_id else _corridor_ids(corridor) if corridor else None
    n = max(1, min(int(top_n), 25))
    scope = f"road section {segment_id}" if segment_id else corridor or "the whole road network"
    return {"scope": scope, "accidents": safety.accident_history(ids if ids is not None else list(_roads())),
            "asset_condition": safety.asset_condition(ids if ids is not None else list(_roads())),
            "maintenance_priority": safety.maintenance_priority(n, ids), "label": safety.LABEL}


# ---------------------------------------------------------------------------------------------- ACT (proposal only)
def subject_of(store, incident: dict) -> dict:
    """What a mobility incident is about: its report, closure request or event notice, read through its detection."""
    out = {"kind": KINDS.get(incident["attrs"]["Incident_Type"], ""), "ref": "", "row": None, "layer": ""}
    for did in [d for d in (incident["attrs"].get("Detection_IDs") or "").split(",") if d]:
        det = store.get(S.DETECTIONS, did)
        ref = det["attrs"].get("Related_Asset_ID") if det else ""
        for layer in (S.TRAFFIC_REPORTS, S.CLOSURES, S.EVENT_NOTICES):
            row = store.get(layer, ref) if ref else None
            if row:
                return {**out, "ref": ref, "row": row, "layer": layer}
    return out


def _scenario_for(ctx: ToolContext, incident_id: str, scenario_id: str | None) -> dict:
    if scenario_id:
        row = ctx.p.jobs.row(scenario_id)
        if not row:
            raise ToolError(f"simulation {scenario_id} not found")
        if row.get("Status") != "Completed":
            raise ToolError(f"simulation {scenario_id} is {row.get('Status') or 'not finished'}; a plan needs a completed simulation")
        return row
    done = sorted((r["id"] for r in ctx.store.query(S.SCENARIOS, Subject_ID=incident_id, Status="Completed")), reverse=True)
    if not done:
        raise ToolError(f"incident {incident_id} has no completed simulation yet; wait for it, or propose a plain work order instead")
    return ctx.p.jobs.row(done[0])


def propose_traffic_plan(ctx: ToolContext, incident_id: str | None = None, scenario_id: str | None = None) -> dict:
    iid = incident_id or ctx.state.get("focus_incident")
    if not iid:
        raise ToolError("no incident specified and none in context")
    f = ctx.store.get(S.INCIDENTS, iid)
    if not f:
        raise ToolError(f"incident {iid} not found")
    a = f["attrs"]
    if a["Category"] != "mobility":
        raise ToolError(f"incident {iid} is not a mobility incident; use propose_work_order")
    if a["Status"] in CLOSED:
        raise ToolError(f"incident {iid} is {a['Status']}")
    for w in ctx.store.query(S.WORK_ORDERS, Incident_ID=iid):
        if w["attrs"]["Status"] in ("Created", "Assigned", "In Progress"):
            raise ToolError(f"incident {iid} already has active work order {w['id']}")
    sub = subject_of(ctx.store, f)
    kind = sub["kind"]
    if not kind:
        raise ToolError(f"incident {iid} ({a['Incident_Type']}) has no traffic plan type")
    sc = _scenario_for(ctx, iid, scenario_id)
    s = sc["summary"]
    team, due = TEAM_FOR["mobility"], DUE_HOURS[a["Priority"]]
    payload = {"incident_id": iid, "kind": kind, "scenario_id": sc["Scenario_ID"], "strategy": "", "team": team, "task_type": TASK_TYPE[kind], "due_hours": due}
    road = s.get("road") or a["Area_Name"]
    if kind == "incident":
        n = s.get("lanes_closed")
        what = f"{n} lane(s) blocked" if n and not s.get("full_closure") else "road blocked"
        payload["instructions"] = (f"Go to {road}. Confirm the reported blockage ({what}), make the scene safe, direct traffic and report when the road is clear. "
                                   f"Modelled impact if it lasts {s.get('duration_h', 2)} hours: {s.get('window_extra_trip_hours', 0):,} extra trip-hours.")
        summary = f"Traffic response for {iid}: send Traffic Response to {road} to confirm and clear the blockage"
        expected = "A field-check work order is created and the incident moves to 'Work Order Created'."
    elif kind == "closure":
        strat = next((x for x in s.get("strategies", []) if x["id"] == sc.get("Recommended")), None) or {"id": sc.get("Recommended") or "do_nothing", "name": "Do nothing"}
        payload.update(strategy=strat["id"], closure_id=sub["ref"])
        win = s.get("window") or {}
        payload["instructions"] = (f"Confirm the closure of {road} is set up as approved ({win.get('start', '')} to {win.get('end', '')}; response: {strat['name']}): "
                                   "signs, barriers and the diversion route in place. Photograph and report.")
        summary = f"Closure plan for {road} ({iid}): {strat['name']}"
        expected = "The closure is recorded as Approved with this response, and a field-check work order is created."
    else:
        payload.update(event_id=sub["ref"])
        payload["instructions"] = (f"Confirm the traffic plan for the event at {s.get('venue', road)} is in place: approach routes signed, parking guidance and marshals. "
                                   f"Modelled peak: {s.get('added_vehicles_per_hour', 0):,} added vehicles per hour. Photograph and report.")
        summary = f"Event traffic plan for {s.get('venue', road)} ({iid}): approach routes, parking guidance and marshals"
        expected = "The event notice is recorded as Planned, and a field-check work order is created."
    rec = ctx.p.approvals.propose(ctx.session_id, "apply_traffic_plan", payload, summary, target=iid, location=a["Location"], priority=a["Priority"], team=team,
                                  expected=expected + " The plan is a record: nothing controls signals, signs or dispatch systems.", incident_id=iid)
    ctx.state["focus_incident"] = iid
    ctx.state["pending_approval"] = rec["Approval_ID"]
    return {"status": "AWAITING_APPROVAL", "approval": rec, "kind": kind, "scenario_id": sc["Scenario_ID"],
            "message": "Nothing has been created yet. The operator must approve this proposal.", "label": MODELLED}
