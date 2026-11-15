"""Response-strategy comparison for a road closure (decision support, step 7 of the closure workflow).

The SAME closure is simulated under several traffic-management responses and the results are ranked on three outcomes:
extra trip-hours over the closure window (change in mean trip time x trips, so suppressed trips earn no credit), worst hospital-access increase, and number of severe segments.
Every strategy's effect is an explicit, documented ASSUMPTION applied to a copy of the network (capacity uplift, demand shift, different
time window). These are planning estimates for comparing options, NOT measured effects of real interventions.
Nothing here operates real traffic control: the recommended strategy becomes a proposal that needs human approval.
"""
from __future__ import annotations

import datetime as dt
import json
from typing import Callable, Dict, List, Optional

from backend.mobility import sources as store
from backend.mobility import engine

DEFAULT_WEIGHTS = {"delay": 0.5, "access": 0.3, "congestion": 0.2}
CAPACITY_UPLIFT_PCT = 15.0   # assumed gain from signal retiming, VMS diversion and temporary lane use on the alternatives
DEMAND_SHIFT_PCT = -10.0     # assumed trip reduction near the closure from transit incentives / staggered hours / remote work
DEMAND_SHIFT_RADIUS_KM = 5.0
NIGHT_START_HOUR = 22

STRATEGIES = [
    {"id": "do_nothing", "name": "Do nothing", "effort": "none",
     "description": "Close the section as planned with no mitigation (reference case)."},
    {"id": "reschedule", "name": f"Reschedule to off-peak ({NIGHT_START_HOUR}:00 start)", "effort": "medium",
     "description": "Same closure and duration, moved to night hours when demand is a fraction of the daytime peak. Needs contractor night-work approval."},
    {"id": "divert", "name": f"Diversion plan + signal retiming (+{CAPACITY_UPLIFT_PCT:g}% capacity on alternatives)", "effort": "medium",
     "description": "Signed diversion with retimed signals, VMS and temporary lane use on the corridors that absorb the diverted traffic."},
    {"id": "demand_shift", "name": f"Demand shift ({DEMAND_SHIFT_PCT:g}% of trips near the closure)", "effort": "low",
     "description": f"Public information, transit incentives and staggered hours reduce trips starting or ending within {DEMAND_SHIFT_RADIUS_KM:g} km of the closure."},
    {"id": "combined", "name": "Combined: diversion plan + demand shift", "effort": "high",
     "description": "Diversion/signal retiming together with the demand-shift campaign."},
]
EFFORT_RANK = {"none": 0, "low": 1, "medium": 2, "high": 3}


def _window(params: dict):
    s = engine._parse(params.get("start_time")) if params.get("start_time") else None
    e = engine._parse(params.get("end_time")) if params.get("end_time") else None
    if not s:
        s = (dt.datetime.utcnow() + dt.timedelta(hours=3) + dt.timedelta(days=1)).replace(hour=8, minute=0, second=0, microsecond=0)
    if not e:
        e = s + dt.timedelta(hours=float(params.get("duration_hours") or 8))
    return s, e


def _metrics(r: dict) -> dict:
    S = r["summary"]
    return {"window_extra_trip_hours": S["window_extra_trip_hours"], "window_extra_vehicle_hours": S["window_extra_vehicle_hours"], "peak_vht_delta_pct": S["vht_delta_pct"], "mean_trip_time_delta_pct": S["mean_od_time_delta_pct"],
            "worst_hospital_access_delta_min": S["worst_hospital_access_delta_min"], "severe_segments": S["severe_segments_scenario"], "severe_segments_baseline": S["severe_segments_baseline"],
            "affected_segments": S["affected_segments"], "trips_change_pct": S["trips_change_pct"], "isolated_zones": S["isolated_zones"], "peak_hour": S["peak_hour"], "duration_h": S["duration_h"]}


def compare(closure: dict, strategy_ids: Optional[List[str]] = None, weights: Optional[Dict[str, float]] = None,
            progress: Optional[Callable[[int, str], None]] = None, persist: bool = True, actor: str = "system") -> Dict:
    """closure: engine params for a closure scenario (corridor, optional near/segment_ids/span_km/start_time/end_time/duration_hours)."""
    say = progress or (lambda *_: None)
    base = {k: v for k, v in closure.items() if k not in ("modifiers", "scenario_type", "name")}
    base["scenario_type"] = "closure"
    if not base.get("corridor") and not base.get("segment_ids"):
        raise ValueError("strategy comparison needs a closure: provide a corridor")
    w = {**DEFAULT_WEIGHTS, **(weights or {})}
    if any(v < 0 for v in w.values()) or sum(w.values()) <= 0:
        raise ValueError("strategy weights must be non-negative with a positive sum (all-zero weights would score every option 0)")
    tot = sum(w.values())
    w = {k: v / tot for k, v in w.items()}
    chosen = [s for s in STRATEGIES if not strategy_ids or s["id"] in strategy_ids or s["id"] == "do_nothing"]
    s0, e0 = _window(base)
    base["start_time"], base["end_time"] = s0.isoformat(timespec="minutes"), e0.isoformat(timespec="minutes")
    base["max_hours"] = 2   # sampled hours per run: keeps a 5-strategy study to ~1-2 minutes on the full OSM network
    results: Dict[str, dict] = {}
    notes: Dict[str, str] = {}
    n = len(chosen)

    def run(sid, extra, label):
        step = len(results)
        say(int(100 * step / n), f"Simulating: {label}")
        results[sid] = engine.run_scenario({**base, **extra, "name": f"Strategy study - {label}"}, persist=False, actor=actor)

    run("do_nothing", {}, "do nothing")
    r0 = results["do_nothing"]
    alt = sorted((a for a in r0["affected_segments"] if a["status"] == "worse"), key=lambda a: -(a["scenario_flow"] - a["baseline_flow"]))[:15]
    alt_ids = [a["segment_id"] for a in alt]
    boost = {"capacity_boost": {"segment_ids": alt_ids, "pct": CAPACITY_UPLIFT_PCT}}
    shift = {"demand_shift": {"pct": DEMAND_SHIFT_PCT, "radius_km": DEMAND_SHIFT_RADIUS_KM}}
    for st in chosen:
        sid = st["id"]
        if sid == "do_nothing":
            continue
        if sid == "reschedule":
            ns = s0.replace(hour=NIGHT_START_HOUR, minute=0)
            run(sid, {"start_time": ns.isoformat(timespec="minutes"), "end_time": (ns + (e0 - s0)).isoformat(timespec="minutes")}, st["name"])
        elif sid in ("divert", "combined") and not alt_ids:
            notes[sid] = "No alternative segment gained traffic in the do-nothing run, so there is nothing to upgrade; strategy skipped."
        elif sid == "divert":
            run(sid, {"modifiers": boost}, st["name"])
        elif sid == "demand_shift":
            run(sid, {"modifiers": shift}, st["name"])
        elif sid == "combined":
            run(sid, {"modifiers": {**boost, **shift}}, st["name"])

    m0 = _metrics(r0)
    rows = []
    for st in chosen:
        r = results.get(st["id"])
        if not r:
            rows.append({**st, "skipped": True, "note": notes.get(st["id"], "skipped")})
            continue
        m = _metrics(r)
        a = max(0.0, m["window_extra_trip_hours"] / m0["window_extra_trip_hours"]) if m0["window_extra_trip_hours"] > 0 else 1.0   # 0 = fully offsets the closure delay
        b = (m["worst_hospital_access_delta_min"] + 1) / (m0["worst_hospital_access_delta_min"] + 1)
        c = (m["severe_segments"] + 1) / (m0["severe_segments"] + 1)
        score = round(100 * (w["delay"] * a + w["access"] * b + w["congestion"] * c), 1)   # do-nothing = 100; lower is better
        g = r["geojson"]
        rows.append({**st, "skipped": False, "metrics": m, "score": score,
                     "benefit_vs_do_nothing_pct": round((1 - a) * 100, 1) if m0["window_extra_trip_hours"] > 0 else 0.0,
                     "applied": {k: v for k, v in r["scenario"]["resolved"].items() if k in ("capacity_boost", "demand_shift")} | ({"window": r["window"]["start"]} if st["id"] == "reschedule" else {}),
                     "geojson": {"segments": {"type": "FeatureCollection", "features": g["segments"]["features"][:80]}, "routes": g["routes"], "closed": g["closed"]},
                     "mitigations": r["mitigations"][:3]})
    ranked = sorted([x for x in rows if not x["skipped"]], key=lambda x: (x["score"], EFFORT_RANK[x["effort"]]))
    for i, x in enumerate(ranked):
        x["rank"] = i + 1
    best = ranked[0]
    material = best["id"] != "do_nothing" and (100 - best["score"]) >= 2.0
    if m0["window_extra_trip_hours"] < 50:
        verdict = "The closure's modelled impact is small, so no response strategy changes outcomes materially. Proceed as planned and monitor."
        recommended = "do_nothing"
    elif material:
        verdict = (f"Recommended: {best['name']}. It lowers the weighted impact score from 100 to {best['score']} "
                   f"({best['benefit_vs_do_nothing_pct']:.1f}% less trip-time lost over the window; worst hospital-access increase "
                   f"{m0['worst_hospital_access_delta_min']} -> {best['metrics']['worst_hospital_access_delta_min']} min).")
        recommended = best["id"]
        if best["metrics"]["trips_change_pct"] < -1:
            verdict += f" Note: this strategy assumes {abs(best['metrics']['trips_change_pct'])}% fewer trips network-wide at the peak hour; its benefit depends entirely on that behavioural assumption."
    else:
        verdict = "No strategy improves the weighted score by at least 2%; the differences are within the model's noise."
        recommended = "do_nothing"
    out = {"classification": "scenario comparison on a static-assignment network model (estimates, not validated microsimulation); strategy effects are assumptions",
           "data_status": "synthetic traffic inputs on OSM/approximate geometry", "closure": {k: v for k, v in r0["scenario"]["resolved"].items() if k != "geometry"},
           "closure_geometry": r0["scenario"]["resolved"].get("geometry"), "window": {"start": base["start_time"], "end": base["end_time"], "duration_h": m0["duration_h"]},
           "weights": w, "strategies": rows, "ranking": [x["id"] for x in ranked], "recommended": recommended, "verdict": verdict,
           "assumptions": [f"Diversion: +{CAPACITY_UPLIFT_PCT:g}% capacity on up to 15 segments that gained the most traffic in the do-nothing run (signal retiming/VMS/temporary lanes).",
                           f"Demand shift: {DEMAND_SHIFT_PCT:g}% of trips with an origin or destination within {DEMAND_SHIFT_RADIUS_KM:g} km of the closure.",
                           f"Reschedule: same duration starting {NIGHT_START_HOUR}:00; night demand follows the synthetic hourly profile.",
                           "Score = 100 x (w_delay * trip-hours ratio + w_access * (access delta+1) ratio + w_congestion * (severe segments+1) ratio) relative to do-nothing; lower is better.",
                           "Implementation effort is a qualitative judgement, not a cost estimate; effectiveness percentages are not measured."] + list(notes.values()),
           "limitations": r0["limitations"], "human_authorization": "Proposal only: adopting any strategy requires approval by an authorised human (see Approvals).",
           "alternative_segments_upgraded": alt_ids}
    if persist:
        sid = store.new_id("ss")
        out["study_id"] = sid
        store.upsert_many("SimulationScenario", [dict(id=sid, name=f"Strategy study: {closure.get('corridor') or 'closure'}", scenario_type="strategy_study", params=closure, status="completed",
                                                      created_by=actor, source="user", data_status="synthetic")])
        slim = json.loads(json.dumps(out, default=str))
        store.upsert_many("SimulationResult", [dict(id=f"sr-{sid}", name="strategy study", scenario_id=sid, engine="networkx-static-assignment+strategies",
                                                    summary={"recommended": recommended, "verdict": verdict}, result=slim, duration_s=0.0, source="strategy comparison", data_status="synthetic", confidence=0.3)])
        store.audit(actor, "run_strategy_study", "SimulationScenario", sid, verdict[:200])
    say(100, "Strategy comparison complete")
    return out
