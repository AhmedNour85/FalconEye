"""Hospital / emergency accessibility on a (possibly degraded) network model."""
from __future__ import annotations

import math
from typing import Dict

import networkx as nx

from backend.data import riyadh_network as RN
from backend.gis import feature_source, store
from backend.simulation.network_model import NetworkModel

ER_TARGET_MIN = 15.0  # planning threshold used for flagging (assumption, not a standard)


def hospital_nodes(model: NetworkModel) -> Dict[str, dict]:
    out = {}
    for h in feature_source.list_hospitals():
        lo, la = h["geometry"]["coordinates"]
        out[h["id"]] = {"name": h["name"], "node": model._nearest(lo, la), "lon": lo, "lat": la}
    return out


def accessibility(model: NetworkModel, weight: str = "t") -> Dict:
    """Min travel time (minutes, on the model's current edge times) from each named zone to the nearest hospital."""
    hosp = hospital_nodes(model)
    zones = {}
    named = {n: k for k, n in model.zones.items()}
    inter = {r["id"]: r["name"] for r in store.list_("Intersection")}
    for node in model.zone_nodes:
        key = node
        dist = nx.single_source_dijkstra_path_length(model.G, node, weight=weight)
        cand = [(dist.get(h["node"], math.inf), h["name"]) for h in hosp.values()]
        t, nearest = min(cand)
        zones[key] = {"zone": RN.LOCATIONS[named[node]][0] if node in named else f"Junction {inter.get(node, node)}", "named": node in named, "node": node, "isolated": not math.isfinite(t),
                      "min_to_hospital": None if not math.isfinite(t) else round(t, 1),
                      "nearest_hospital": nearest if math.isfinite(t) else None}
    return {"zones": zones, "hospitals": hosp,
            "within_target_share": round(sum(1 for z in zones.values() if z["min_to_hospital"] is not None and z["min_to_hospital"] <= ER_TARGET_MIN) / len(zones), 2)}


def compare_accessibility(base: Dict, scen: Dict) -> Dict:
    rows = []
    for k, b in base["zones"].items():
        s = scen["zones"][k]
        bt, st = b["min_to_hospital"], s["min_to_hospital"]
        d = None if (bt is None or st is None) else round(st - bt, 1)
        rows.append({"zone": b["zone"], "node": b["node"], "named": b["named"], "baseline_min": bt, "scenario_min": st, "delta_min": d,
                     "nearest_baseline": b["nearest_hospital"], "nearest_scenario": s["nearest_hospital"],
                     "isolated": s["isolated"], "exceeds_target": st is not None and st > ER_TARGET_MIN and (bt or 0) <= ER_TARGET_MIN})
    affected = sorted([r for r in rows if r["isolated"] or (r["delta_min"] or 0) > 0.5], key=lambda r: -(r["delta_min"] or 999))
    all_rows = rows
    rows = [r for r in all_rows if r["named"] or r["isolated"] or (r["delta_min"] or 0) > 0.5]
    return {"rows": rows, "zones_evaluated": len(all_rows), "most_affected": affected[:6], "target_min": ER_TARGET_MIN,
            "baseline_within_target": base["within_target_share"], "scenario_within_target": scen["within_target_share"]
   }
