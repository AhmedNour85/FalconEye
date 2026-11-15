"""Modelled traffic for the map: the state of every road segment at each hour of a normal weekday.

Nothing here is measured. Volumes come from the network model's assignment of a synthetic demand profile, and nothing is
stored: the 24 hours are calculated once per network, in the background, and kept in memory.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Dict, Optional

from backend.mobility import network_model, sources

log = logging.getLogger("geoai.mobility")

LABELS = {"traffic": "Modelled, not measured: a static traffic assignment of synthetic demand on the road network",
          "roads": sources.ATTRIBUTION, "transit": sources.RCRC_ATTRIBUTION, "hospitals": sources.HOSPITAL_NOTE}
CLASSES = ("free", "slow", "heavy", "stopped")

_lock = threading.RLock()
_s: Dict = {"fp": None, "hours": {}, "roads": None, "thread": None, "error": None, "started": None, "took_s": None}


def _fresh(model) -> None:
    """Drop what was calculated for another network."""
    fp = (model.provenance or {}).get("fingerprint")
    with _lock:
        if _s["fp"] != fp:
            _s.update(fp=fp, hours={}, roads=None, error=None, took_s=None)


def state(hour: int) -> dict:
    """Traffic at one hour (0 to 23). Only segments that are not free-flowing are listed: every other segment is "free"."""
    if not isinstance(hour, int) or isinstance(hour, bool) or not 0 <= hour <= 23:
        raise ValueError("hour must be a whole number from 0 to 23")
    model = network_model.get_model()
    _fresh(model)
    with _lock:
        hit = _s["hours"].get(hour)
    if hit:
        return hit
    scale = sources.demand_factor(hour)
    res = model.assign(scale)
    counts = dict.fromkeys(CLASSES, 0)
    segs = {}
    for sid, e in res["edges"].items():
        c = network_model.flow_class(e["vc"])
        counts[c] += 1
        if c != "free":
            segs[sid] = [round(e["vc"], 2), c]
    t = res["totals"]
    out = {"hour": hour, "modelled": True, "demand_factor": round(scale, 2), "default_class": "free", "segments": segs, "counts": counts,
           "totals": {"vehicle_hours": round(t["vht"]), "vehicle_km": round(t["vkt"]), "avg_speed_kph": round(t["avg_speed_kph"], 1),
                      "trips_per_hour": round(t["trips_per_hour"]), "severe_km": round(t["severe_km"], 1)},
           "label": LABELS["traffic"]}
    with _lock:
        if _s["fp"] == (model.provenance or {}).get("fingerprint"):
            _s["hours"][hour] = out
    return out


def roads_geojson() -> dict:
    """The road segments of the network the model runs on. Sent to the map once; the hourly state refers to these ids."""
    model = network_model.get_model()
    _fresh(model)
    with _lock:
        if _s["roads"] is None:
            _s["roads"] = {"type": "FeatureCollection", "source": (model.provenance or {}).get("label"), "licence": (model.provenance or {}).get("licence"),
                           "features": [{"type": "Feature", "id": s["id"], "geometry": s["geometry"],
                                         "properties": {"id": s["id"], "name": s["name"], "corridor": s["corridor"], "road_class": s["road_class"], "lanes": s["lanes"]}}
                                        for s in model.segments.values()]}
        return _s["roads"]


def _run() -> None:
    t0 = time.time()
    try:
        for h in sorted(range(24), key=lambda h: (h not in (8, 17), h)):   # the two peaks first: they are what people look at
            state(h)
        with _lock:
            _s["took_s"] = round(time.time() - t0, 1)
        log.info("modelled traffic ready for 24 hours in %.1f s", time.time() - t0)
    except Exception as e:  # noqa: BLE001  the page is told; the server keeps running
        log.exception("the traffic model could not be built")
        with _lock:
            _s["error"] = f"{type(e).__name__}: {e}"


def warm(wait: bool = False) -> None:
    """Build the model and the 24 hours in the background (once at a time). `wait=True` returns when it is done."""
    with _lock:
        t: Optional[threading.Thread] = _s["thread"]
        if t is None or not t.is_alive():
            _s["error"], _s["started"] = None, time.time()
            t = _s["thread"] = threading.Thread(target=_run, name="mobility-traffic", daemon=True)
            t.start()
    if wait:
        t.join()


def status() -> dict:
    """Cheap: never builds anything."""
    model = network_model._model
    with _lock:
        mine = model is not None and _s["fp"] == (model.provenance or {}).get("fingerprint")
        hours = sorted(_s["hours"]) if mine else []
        t = _s["thread"]
        return {"ready": len(hours) == 24, "building": bool(t and t.is_alive()), "hours_ready": hours, "error": _s["error"],
                "network": getattr(model, "provenance", None) if model else None, "segments": len(model.segments) if model else 0,
                "took_s": _s["took_s"] if mine else None, "labels": LABELS, "classes": {"free": "< 0.60", "slow": "0.60 to 0.85", "heavy": "0.85 to 1.10", "stopped": "> 1.10"},
                "class_basis": "volume / capacity"}
