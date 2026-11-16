"""The mobility numbers of the Executive Hub, the congestion hotspots and the closure window rule. Every number comes from the traffic model or the records."""
from __future__ import annotations

import datetime as dt

from backend.gis import schema as S
from backend.gis.store import utcnow
from backend.mobility import traffic
from backend.tools import mobility as T

ACTIVE = ("Requested", "Approved", "In Place")          # statuses of a closure that still matters; "Ended" and "Rejected" are history
_hospital: dict = {}                                    # worst hospital access of the peak hour, per network (the baseline does not depend on closures)


def _ready() -> bool:
    return bool(traffic.status().get("ready"))


def _riyadh_now() -> dt.datetime:
    return dt.datetime.utcnow() + dt.timedelta(hours=3)


def window_over(attrs: dict, now: dt.datetime | None = None) -> bool:
    """True when the closure's end time (Riyadh local time) has passed. A closure with no readable end time never expires."""
    raw = (attrs.get("End_Time") or "")[:16]
    try:
        end = dt.datetime.strptime(raw, "%Y-%m-%dT%H:%M")
    except ValueError:
        return False
    return end < (now or _riyadh_now())


def current_closures(platform) -> list[dict]:
    return [f for f in platform.store.all(S.CLOSURES) if f["attrs"].get("Status") in ACTIVE and not window_over(f["attrs"])]


def expire_closures(platform) -> int:
    """Closures whose window has passed become "Ended" (the record stays). Returns how many were changed."""
    n = 0
    for f in platform.store.all(S.CLOSURES):
        if f["attrs"].get("Status") in ACTIVE and window_over(f["attrs"]):
            platform.store.update(S.CLOSURES, f["id"], Status="Ended", Updated=utcnow())
            n += 1
    return n


def _hours() -> dict:
    return {h: traffic.state(h) for h in range(24)}


def summary(platform) -> dict:
    """peak_delay_ratio = average speed in the quietest hour / average speed in the busiest hour (1.0 means no slowing).
    severe_segments = road sections heavy or stopped in the busiest hour. worst_hospital_minutes = the slowest zone-to-hospital time in that hour."""
    out = {"peak_hour": None, "peak_delay_ratio": None, "severe_segments": None, "worst_hospital_minutes": None, "planned_closures": len(current_closures(platform)), "label": "Modelled"}
    if not _ready():
        return out
    states = _hours()
    peak = max(states, key=lambda h: (states[h]["totals"]["vehicle_hours"], -h))
    quiet = min(states, key=lambda h: (states[h]["totals"]["vehicle_hours"], h))
    p, q = states[peak], states[quiet]
    out["peak_hour"] = peak
    if p["totals"]["avg_speed_kph"]:
        out["peak_delay_ratio"] = round(q["totals"]["avg_speed_kph"] / p["totals"]["avg_speed_kph"], 2)
    out["severe_segments"] = p["counts"].get("heavy", 0) + p["counts"].get("stopped", 0)
    key = (traffic.status().get("network") or {}).get("fingerprint"), peak
    if key not in _hospital:
        try:
            _hospital[key] = (T.hospital_access(platform.crew.ctx, peak).get("worst") or {}).get("minutes")
        except Exception:  # noqa: BLE001  the other numbers still show
            _hospital[key] = None
    out["worst_hospital_minutes"] = _hospital[key]
    return out


def hotspots(platform, top_n: int = 3, hour: int | None = None) -> list[dict]:
    """The most congested roads at this hour (default: now, Riyadh time): one per road, score 0-100 against the worst. Empty when nothing is heavy or stopped."""
    if not _ready():
        return []
    from backend.mobility import network_model

    segs = network_model.get_model().segments
    rows = [(v[0], sid) for sid, v in traffic.state(T.riyadh_hour() if hour is None else hour)["segments"].items() if v[1] in ("heavy", "stopped") and sid in segs]
    best: dict = {}
    for vc, sid in sorted(rows, key=lambda r: (-r[0], r[1])):
        road = segs[sid].get("corridor") or segs[sid].get("name") or sid
        best.setdefault(road, (vc, sid))
    ranked = sorted(best.items(), key=lambda kv: (-kv[1][0], kv[0]))[:max(1, top_n)]
    top = ranked[0][1][0] if ranked else 1
    out = []
    for road, (vc, sid) in ranked:
        coords = segs[sid]["geometry"]["coordinates"]
        mid = coords[len(coords) // 2]
        out.append({"road": road, "kind": "congestion", "score": round(100 * vc / top, 1), "load": vc, "lon": mid[0], "lat": mid[1], "label": "Modelled"})
    return out
