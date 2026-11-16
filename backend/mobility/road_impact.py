"""The cross-domain link: what a repair next to a road costs traffic, by day and by night.

A water-leak repair closes lanes of the road it sits on. Noura runs the closure twice (the day window and the night window of
rules.ROAD_IMPACT) and the alert gets one sentence with both, and which window is recommended. Every number is MODELLED.
The sentences are English here; backend/services/i18n.py holds the Arabic for each pattern.
"""
from __future__ import annotations

from backend.gis import geo
from backend.mobility import rules, sources
from backend.mobility.wording import PREFIX, clock, num

REASON = {"water": "Water leak repair"}


def nearest_road(lonlat: tuple, radius_m: float) -> dict | None:
    """The road section of the traffic model closest to this point, when it is within the radius; else None."""
    p = (float(lonlat[0]), float(lonlat[1]))
    pad = radius_m / 90_000.0                                   # degrees, generous: a quick box test before the exact distance
    best, hit = radius_m, None
    for r in sources.load_network()[0]:
        line = r["geometry"]["coordinates"]
        if not (min(c[0] for c in line) - pad <= p[0] <= max(c[0] for c in line) + pad and min(c[1] for c in line) - pad <= p[1] <= max(c[1] for c in line) + pad):
            continue                                            # outside the section's bounding box (plus the radius): not this section
        d = geo.dist_to_line(p, line)[0]
        if d <= best:
            best, hit = d, r
    if not hit:
        return None
    return {"segment_id": hit["id"], "corridor": hit["corridor"] or hit["name"], "name": hit["name"], "lanes": int(hit["lanes"]), "distance_m": round(best, 1)}


def params(category: str, road: dict) -> dict:
    """The road_impact job's inputs. A road with no more lanes than the repair closes is closed completely (lanes_closed None)."""
    rule = rules.ROAD_IMPACT[category]
    lanes = int(road["lanes"])
    return {"segment_id": road["segment_id"], "corridor": road.get("corridor") or road.get("name") or "", "lanes": lanes,
            "lanes_closed": rule["lanes"] if lanes > rule["lanes"] else None, "day": list(rule["day"]), "night": list(rule["night"]),
            "night_saving": rule["night_saving"], "category": category}


def recommend(day: dict, night: dict, night_saving: float | None = None) -> str:
    """'night' when the night window costs at least `night_saving` fewer trip-hours than the day window; else 'day'."""
    saving = rules.ROAD_IMPACT["water"]["night_saving"] if night_saving is None else float(night_saving)
    d, n = float(day.get("window_extra_trip_hours") or 0), float(night.get("window_extra_trip_hours") or 0)
    return "night" if d > 0 and n <= (1 - saving) * d else "day"


def is_small(day: dict, night: dict) -> bool:
    return max(float(day.get("window_extra_trip_hours") or 0), float(night.get("window_extra_trip_hours") or 0)) < rules.SMALL_IMPACT_TRIP_HOURS


def what(s: dict) -> str:
    """'2 lanes of Olaya Street', or the road's name alone when the whole road is closed."""
    road = s.get("road") or "the road"
    return road if s.get("full_closure") or not s.get("lanes_closed") else f"{int(s['lanes_closed'])} lanes of {road}"


def line(s: dict) -> str:
    """The alert sentence for a completed road-impact run."""
    day, night, rec = s.get("day") or {}, s.get("night") or {}, s.get("recommended") or "day"
    if s.get("small"):
        return f"{PREFIX}small in both windows (day {num(day.get('window_extra_trip_hours'))}, night {num(night.get('window_extra_trip_hours'))} trip-hours). Recommended: {rec}."
    return (f"{PREFIX}closing {what(s)} {clock(day.get('start'))} to {clock(day.get('end'))} adds {num(day.get('window_extra_trip_hours'))} trip-hours and "
            f"{float(day.get('worst_hospital_access_delta_min') or 0):g} min to the worst hospital access; at night {num(night.get('window_extra_trip_hours'))} trip-hours and "
            f"{float(night.get('worst_hospital_access_delta_min') or 0):g} min. Recommended: {rec}.")


def closure_plan(s: dict, road: dict | None = None, scenario_id: str = "") -> dict:
    """What is stored with the work-order proposal: the road, its sections, the lanes and the recommended window. Small on purpose
    (no geometry): the closure's line is read from the road network when the proposal is approved."""
    rec = s.get("recommended") or "day"
    win = s.get(rec) or {}
    road = road or {}
    return {"corridor": s.get("road") or road.get("corridor") or "", "segment_ids": list(s.get("segment_ids") or [x for x in [s.get("segment_id") or road.get("segment_id")] if x]),
            "lanes_closed": s.get("lanes_closed") or s.get("lanes") or road.get("lanes"), "full_closure": bool(s.get("full_closure") or not s.get("lanes_closed")),
            "start_time": win.get("start") or "", "end_time": win.get("end") or "", "window": rec, "scenario_id": scenario_id, "reason": REASON.get(s.get("category") or "water", "Repair")}


def plan_text(plan: dict) -> str:
    """'2 lanes of Olaya Street, 2026-11-17 22:00 to 06:00'."""
    road = plan.get("corridor") or "the road"
    lanes = road if plan.get("full_closure") else f"{int(plan.get('lanes_closed') or 0)} lanes of {road}"
    return f"{lanes}, {str(plan.get('start_time') or '').replace('T', ' ')} to {clock(plan.get('end_time'))}"
