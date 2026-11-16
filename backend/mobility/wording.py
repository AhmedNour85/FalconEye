"""The sentences the crew writes about a simulation result.

English here; backend/services/i18n.py holds the Arabic for each pattern, so a sentence changed here needs its rule changed there.
Every number comes from the stored result of a simulation: nothing is worked out in this file.
"""
from __future__ import annotations

PREFIX = "Road impact (modelled): "
FAILED = "Road impact could not be calculated: "


def num(x) -> str:
    """A whole number with thousands separators."""
    return f"{float(x or 0):,.0f}"


def clock(iso) -> str:
    """'2026-11-17T08:00' -> '08:00'."""
    s = str(iso or "")
    return s[11:16] if len(s) >= 16 else s


def impact(kind: str, s: dict, recommended: str = "", verdict: str = "") -> str:
    """One sentence for the alert, from a completed simulation's summary (kind: incident | closure | event)."""
    h = num(s.get("window_extra_trip_hours"))
    if kind == "event":
        return (f"{PREFIX}{num(s.get('attendance'))} people at {s.get('venue')} add {num(s.get('added_vehicles_per_hour'))} vehicles per hour at the peak "
                f"and {h} trip-hours; parking is short by {num(s.get('parking_deficit_vehicles'))} vehicles.")
    road = s.get("road") or "the road"
    if kind == "closure":
        win = s.get("window") or {}
        best = next((x for x in s.get("strategies") or [] if x.get("id") == recommended and not x.get("skipped")), None)
        if best and recommended != "do_nothing":
            rec = f"Recommended response: {best['name']} ({float(best.get('benefit_vs_do_nothing_pct') or 0):g}% less delay)."
        else:
            rec = "Recommended response: no extra measures."
        return f"{PREFIX}closing {road} {clock(win.get('start'))} to {clock(win.get('end'))} adds {h} trip-hours. {rec}" + (f" {verdict}" if verdict else "")
    severe = max(0, int(s.get("severe_segments") or 0) - int(s.get("severe_segments_baseline") or 0))
    what = f"{road} blocked" if s.get("full_closure") or not s.get("lanes_closed") else f"{int(s['lanes_closed'])} lane(s) blocked on {road}"
    return (f"{PREFIX}{what} for about {float(s.get('duration_h') or 2):g} hours adds {h} trip-hours and {float(s.get('worst_hospital_access_delta_min') or 0):g} min "
            f"to the worst hospital access; {severe} road sections become severe.")


def failed(error: str) -> str:
    why = (error or "the simulation failed").strip().rstrip(".")
    return f"{FAILED}{why}. A field check is proposed instead."
