"""Accident history and road-asset condition for the road network. SYNTHETIC: generated from the seed, not real data.

Ported from Agentic_AI_Transportation `tools/safety.py` and `tools/infrastructure.py`. There the records sat in a database;
here they are worked out again from the seed at each start and kept in memory, like the traffic volumes. For one seed and one
road network the answers are always the same.
"""
from __future__ import annotations

import random
import threading
from typing import Dict, List, Optional

from backend.mobility import sources

LABEL = "SYNTHETIC accident records and road-asset condition - not real data"
PERIOD = "last 12 months (synthetic)"
SEV_W = {1: 1, 2: 2, 3: 4, 4: 8, 5: 15}                      # severity weights, as in the Transportation project
WEIGHTS = {"condition": 0.40, "traffic": 0.25, "criticality": 0.20, "inspection_age": 0.10, "road_class": 0.05}
CLASS_W = {"motorway": 1.0, "arterial": 0.7, "collector": 0.4}
ACCIDENT_RATE = {"motorway": 0.9, "arterial": 0.7, "collector": 0.35}   # expected records per km per year (made up)
FIXES = {"motorway": ["Variable speed limits and average-speed enforcement", "Review median barrier and shoulder provisions"],
         "arterial": ["Signal timing and clearance-interval review", "Protected pedestrian crossings"],
         "collector": ["Traffic calming and speed management", "Improve sight distances and signage"]}

_lock = threading.RLock()
_s: Dict = {"seed": 42, "fp": None, "acc": {}, "cond": {}, "roads": {}}


def _action(cond: float) -> str:
    return "reconstruction" if cond < 35 else "rehabilitation" if cond < 50 else "preventive" if cond < 65 else "monitor"


def build(seed: int) -> None:
    """Generate the records for the current road network. Called once the network is known; safe to call again."""
    roads, _nodes, prov = sources.load_network()
    acc: Dict[str, dict] = {}
    cond: Dict[str, dict] = {}
    for r in sorted(roads, key=lambda r: r["id"]):
        rng = random.Random(f"{seed}:{r['id']}")              # one generator per section: the answer does not depend on the order
        km = max(float(r["length_km"]), 0.05)
        n = 0
        expect = ACCIDENT_RATE.get(r["road_class"], 0.35) * km
        while expect > 0:                                    # whole part, then one more with the remaining probability
            n += 1 if rng.random() < min(1.0, expect) else 0
            expect -= 1.0
        sev = [rng.choices([1, 2, 3, 4, 5], weights=[40, 30, 18, 9, 3])[0] for _ in range(n)]
        if n:
            acc[r["id"]] = {"n": n, "w": sum(SEV_W[s] for s in sev), "severe": sum(1 for s in sev if s >= 4)}
        cond[r["id"]] = {"condition": round(min(98.0, max(15.0, rng.gauss(68, 16))), 1), "inspection_days": rng.randint(20, 900), "criticality": round(rng.uniform(0.2, 1.0), 2)}
    with _lock:
        _s.update(seed=seed, fp=prov.get("fingerprint"), acc=acc, cond=cond, roads={r["id"]: r for r in roads})


def _ready() -> None:
    _roads, _nodes, prov = sources.load_network()
    with _lock:
        stale = _s["fp"] != prov.get("fingerprint")
        seed = _s["seed"]
    if stale:
        build(seed)


def accident_history(segment_ids: List[str]) -> dict:
    _ready()
    with _lock:
        rows = [(_s["acc"].get(i), _s["roads"].get(i)) for i in segment_ids]
    n = sum(a["n"] for a, _r in rows if a)
    w = sum(a["w"] for a, _r in rows if a)
    km = sum(float(r["length_km"]) for _a, r in rows if r)
    classes = {r["road_class"] for _a, r in rows if r}
    cls = "motorway" if "motorway" in classes else "arterial" if "arterial" in classes else "collector"
    return {"accidents": n, "severe": sum(a["severe"] for a, _r in rows if a), "weighted_per_km": round(w / max(km, 0.3), 1) if km else 0.0,
            "period": PERIOD, "suggested_measures": FIXES[cls] if n else [], "label": LABEL}


def asset_condition(segment_ids: List[str]) -> dict:
    _ready()
    with _lock:
        vals = [_s["cond"][i]["condition"] for i in segment_ids if i in _s["cond"]]
    if not vals:
        return {"worst_condition": None, "mean_condition": None, "proposed_action": "unknown", "label": LABEL}
    worst = min(vals)
    return {"worst_condition": worst, "mean_condition": round(sum(vals) / len(vals), 1), "proposed_action": _action(worst), "label": LABEL}


def maintenance_priority(top_n: int = 10, segment_ids: Optional[List[str]] = None) -> List[dict]:
    """Road sections ranked for maintenance: condition 0.40, traffic 0.25, criticality 0.20, inspection age 0.10, road class 0.05.
    Traffic exposure is the section's capacity (lanes and road class), a stand-in for its volume."""
    _ready()
    with _lock:
        roads, cond = _s["roads"], _s["cond"]
        ids = [i for i in (segment_ids or roads) if i in roads and i in cond]
        max_cap = max((float(r["capacity"]) for r in roads.values()), default=1.0) or 1.0
        rows = []
        for i in ids:
            r, c = roads[i], cond[i]
            comp = {"condition": (100 - c["condition"]) / 100, "traffic": float(r["capacity"]) / max_cap, "criticality": c["criticality"],
                    "inspection_age": min(c["inspection_days"] / 730, 1.0), "road_class": CLASS_W.get(r["road_class"], 0.4)}
            rows.append({"segment_id": i, "corridor": r["corridor"], "name": r["name"], "condition": c["condition"], "days_since_inspection": c["inspection_days"],
                         "priority_score": round(100 * sum(WEIGHTS[k] * comp[k] for k in WEIGHTS), 1), "proposed_action": _action(c["condition"]), "label": LABEL})
    rows.sort(key=lambda x: (-x["priority_score"], x["segment_id"]))
    return rows[:max(0, int(top_n))]
