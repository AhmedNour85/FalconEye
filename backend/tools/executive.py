"""DECIDE: executive indicators, hotspots, trends and evidence-based recommendations. Every figure is computed from stored records,
and every figure honours the same filters (area / category / priority / since) via backend.services.filters."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime

from backend.gis import schema as S
from backend.gis.store import Store, utcnow
from backend.services import learning
from backend.services.filters import make_filter
from backend.tools.common import ToolContext

OPEN_WO = ("Created", "Assigned", "In Progress")
CLOSED = ("Resolved", "Closed - False Positive")


def _p(ts: str) -> datetime:
    return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")


def _rows(store: Store, layer: str, area=None, category=None, priority=None, since=None) -> list[dict]:
    pred = make_filter(store, layer, area, category, priority, since)
    return [f["attrs"] for f in store.all(layer) if pred(f["attrs"])]


def compute_kpis(store: Store, area: str | None = None, category: str | None = None, priority: str | None = None, since: str | None = None) -> dict:
    flt = (area, category, priority, since)
    dets = _rows(store, S.DETECTIONS, *flt)
    incs = _rows(store, S.INCIDENTS, *flt)
    inc_ids = {a["Incident_ID"] for a in incs}
    wos = [a for a in _rows(store, S.WORK_ORDERS, *flt) if a["Incident_ID"] in inc_ids]
    vers = [a for a in _rows(store, S.VERIFICATION, *flt) if a["Incident_ID"] in inc_ids]
    chg = _rows(store, S.CHANGES, *flt)
    open_inc = [a for a in incs if a["Status"] not in CLOSED]
    first_ver: dict[str, str] = {}
    for v in sorted(vers, key=lambda x: x["Timestamp"]):
        first_ver.setdefault(v["Incident_ID"], v["Timestamp"])
    # response times and resolution figures describe work done in this run: the seeded history (kept for trends and learning) is left out, so a fresh start reads 0
    live = [a for a in incs if not (a["Description"] or "").startswith("Historical")]
    resp = [(_p(first_ver[a["Incident_ID"]]) - _p(a["Created_Date"])).total_seconds() / 3600 for a in live if a["Incident_ID"] in first_ver]
    verified = [a for a in live if a["Verification_Outcome"]]
    resolved = [a for a in live if a["Status"] in CLOSED]
    return {
        "total_detected_anomalies": sum(1 for d in dets if d["Status"] != "Verified-False"),
        "total_detections": len(dets),
        "suspected_water_leaks": sum(1 for d in dets if d["Category"] == "water" and d["Status"] == "Suspected"),
        "predicted_streetlight_failures": sum(1 for d in dets if d["Category"] == "lighting" and d["Status"] == "Predicted"),
        "detected_urban_changes": sum(1 for c in chg if c["Significant"] == "Yes"),
        "candidate_changes_total": len(chg),
        "total_incidents": len(incs),
        "open_incidents": len(open_inc),
        "critical_incidents": sum(1 for a in open_inc if a["Severity"] == "Critical"),
        "open_work_orders": sum(1 for w in wos if w["Status"] in OPEN_WO),
        "outstanding_field_assignments": sum(1 for w in wos if w["Status"] in OPEN_WO and w["Assigned_Worker"]),
        "unassigned_work_orders": sum(1 for w in wos if w["Status"] in OPEN_WO and not w["Assigned_Worker"]),
        "verified_incidents": len(verified),
        "resolved_incidents": len(resolved),
        "avg_response_time_hours": round(sum(resp) / len(resp), 1) if resp else None,
        "verification_rate_pct": round(100 * len(verified) / len(live), 1) if live else None,
        "incident_resolution_rate_pct": round(100 * len(resolved) / len(live), 1) if live else None,
        "high_risk_areas": [h["area"] for h in hotspots(store, *flt)[:3] if h["score"] >= 60],
        "filters": {"area": area, "category": category, "priority": priority, "since": since},
    }


def hotspots(store: Store, area: str | None = None, category: str | None = None, priority: str | None = None, since: str | None = None) -> list[dict]:
    """Area-level risk: sum of open-incident risk plus unlinked active detections, normalised to 0-100 against the top area.
    The `area` filter only selects which areas are returned; scores stay relative to ALL areas so filtering cannot inflate them."""
    ranked = _hotspots_all(store, category, priority, since)
    return [h for h in ranked if not area or h["area"] == area]


def _hotspots_all(store: Store, category: str | None, priority: str | None, since: str | None) -> list[dict]:
    area = None
    agg: dict[str, dict] = defaultdict(lambda: {"incidents": 0, "risk": 0.0, "critical": 0, "cats": Counter(), "lon": 0.0, "lat": 0.0, "n": 0})
    inc_pred = make_filter(store, S.INCIDENTS, area, category, priority, since)
    det_pred = make_filter(store, S.DETECTIONS, area, category, priority, since)
    for f in store.all(S.INCIDENTS):
        a = f["attrs"]
        if a["Status"] in CLOSED or not inc_pred(a):
            continue
        h = agg[a["Area_Name"]]
        h["incidents"] += 1
        h["risk"] += a["Risk_Score"]
        h["critical"] += a["Severity"] == "Critical"
        h["cats"][a["Category"]] += 1
        h["lon"] += f["geom"]["coordinates"][0]
        h["lat"] += f["geom"]["coordinates"][1]
        h["n"] += 1
    for f in store.all(S.DETECTIONS):
        a = f["attrs"]
        if a["Incident_ID"] or a["Status"] not in ("Suspected", "Predicted", "Candidate") or not det_pred(a):
            continue
        h = agg[a["Area_Name"]]
        h["risk"] += a["Risk_Score"] * 0.5
        h["cats"][a["Category"]] += 1
        h["lon"] += f["geom"]["coordinates"][0]
        h["lat"] += f["geom"]["coordinates"][1]
        h["n"] += 1
    top = max((h["risk"] for h in agg.values()), default=0) or 1
    out = []
    for name, h in agg.items():
        n = h["n"] or 1
        out.append({"area": name, "score": round(100 * h["risk"] / top, 1), "open_incidents": h["incidents"], "critical": h["critical"], "categories": dict(h["cats"]),
                    "raw_risk": round(h["risk"], 1), "lon": h["lon"] / n, "lat": h["lat"] / n})
    out.sort(key=lambda r: -r["score"])
    return out


def trends(store: Store, days: int = 45, area: str | None = None, category: str | None = None, priority: str | None = None, since: str | None = None) -> dict:
    by: dict[str, Counter] = defaultdict(Counter)
    for a in _rows(store, S.DETECTIONS, area, category, priority, since):
        by[a["Detection_Date"][:10]]["lighting" if a["Category"] == "pole_health" else a["Category"]] += 1   # poles count with streetlights (one use case)
    dates = sorted(by)[-days:]
    return {"dates": dates, "series": {c: [by[d][c] for d in dates] for c in ("water", "lighting", "distortion", "land_use", "change")}}


def persist_indicators(store: Store, k: dict) -> None:
    for f in store.all(S.INDICATORS):
        store.delete(S.INDICATORS, f["id"])
    today = utcnow()[:10]
    for name, val in k.items():
        if isinstance(val, (int, float)) and name != "filters":
            store.upsert(S.INDICATORS, {"Indicator_ID": store.next_id("IND"), "Indicator_Name": name, "Indicator_Value": val, "Geographic_Area": k["filters"]["area"] or "Riyadh demo area",
                                        "Reporting_Date": today, "Data_Classification": S.OPERATIONAL})


def executive_summary(ctx: ToolContext, area: str | None = None, category: str | None = None, priority: str | None = None, since: str | None = None) -> dict:
    """KPIs, hotspots, ranked incidents and evidence-based intervention priorities, all under the same filters."""
    from backend.tools.ops import rank_incidents

    k = compute_kpis(ctx.store, area, category, priority, since)
    if not (area or category or priority or since):
        persist_indicators(ctx.store, k)
    hs = hotspots(ctx.store, area, category, priority, since)
    r = rank_incidents(ctx, 5, category, area, priority, since)["ranked"]
    recs = []
    for row in r:
        action = {"Open": "Approve a work order and dispatch the nearest qualified team",
                  "Work Order Created": "Assign a field worker",
                  "Assigned": "Field inspection is pending - monitor",
                  "Confirmed": "Fault confirmed - track repair, then close",
                  "Repair Reported": "Approve closure after repair report",
                  "Rejected": "Close as false positive",
                  "Requires Further Inspection": "Schedule a follow-up inspection",
                  "Escalated": "Escalate to duty manager"}.get(row["status"], "Review")
        recs.append({"rank": row["rank"], "incident_id": row["incident_id"], "recommended_action": action, "priority": row["priority"], "area": row["area"], "evidence": row["evidence"]})
    ev = learning.evaluation(ctx.store)
    return {"kpis": k, "hotspots": hs[:5], "ranked_incidents": r, "recommendations": recs, "trend": trends(ctx.store, 14, area, category, priority, since),
            "model_performance": {"overall_precision": ev["overall_precision"], "verified": ev["total_verified"]},
            "filters": k["filters"], "provenance": "all figures computed from stored records at call time"}
