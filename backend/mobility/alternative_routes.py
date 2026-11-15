"""Alternative-route evaluation between baseline and scenario networks."""
from __future__ import annotations

import math
from typing import Dict, List

from backend.mobility import riyadh_network as RN
from backend.mobility.network_model import NetworkModel


def key_od_pairs(base: NetworkModel, scen: NetworkModel, top: int = 6) -> List[Dict]:
    """Compare named-place OD pairs; routes use the *congested* edge times left on each model by its last assign()."""
    keys = list(base.zones.keys())
    rows = []
    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            oa, ob = base.zones[a], base.zones[b]
            if oa == ob:
                continue
            rb, rs = base.route(oa, ob), scen.route(oa, ob)
            if not rb:
                continue
            row = {"from": RN.LOCATIONS[a][0], "to": RN.LOCATIONS[b][0], "baseline_min": rb["time_min"], "baseline_km": rb["length_km"],
                   "baseline_via": rb["via"], "baseline_geometry": rb["geometry"]}
            if rs:
                row.update(scenario_min=rs["time_min"], scenario_km=rs["length_km"], scenario_via=rs["via"], scenario_geometry=rs["geometry"],
                           delta_min=round(rs["time_min"] - rb["time_min"], 1), delta_km=round(rs["length_km"] - rb["length_km"], 2),
                           rerouted=rs["segments"] != rb["segments"], disconnected=False)
            else:
                row.update(scenario_min=None, delta_min=None, rerouted=False, disconnected=True)
            rows.append(row)
    rows.sort(key=lambda r: (-(r["disconnected"]), -(r["delta_min"] or 0)))
    return rows[:top]


def detours_around(scen: NetworkModel, base: NetworkModel, node_a: str, node_b: str, k: int = 3) -> Dict:
    """Alternatives between the two ends of a closed section."""
    direct = base.route(node_a, node_b)
    alts = scen.k_routes(node_a, node_b, k=k)
    return {"baseline": direct, "alternatives": alts}
