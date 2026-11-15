"""Network resilience: connectivity, articulation structure and single-segment criticality (free-flow times)."""
from __future__ import annotations

import math
from typing import Dict, List

import networkx as nx

from backend.simulation.network_model import NetworkModel


def connectivity(model: NetworkModel) -> Dict:
    pristine = not model.closed and not model.added
    if pristine and getattr(model, "_conn", None):
        return model._conn
    out = _connectivity(model)
    if pristine:
        model._conn = out
    return out


def _connectivity(model: NetworkModel) -> Dict:
    U = nx.Graph(model.G)
    comps = list(nx.connected_components(U))
    return {"nodes": U.number_of_nodes(), "segments": len({d["seg"] for _, _, d in model.G.edges(data=True)}),
            "components": len(comps), "largest_component_share": round(max(len(c) for c in comps) / U.number_of_nodes(), 3),
            "cut_nodes": len(list(nx.articulation_points(U))), "bridge_segments": len(list(nx.bridges(U)))}


def _mean_time(G, nodes) -> tuple:
    tot, n, bad = 0.0, 0, 0
    for o in nodes:
        d = nx.single_source_dijkstra_path_length(G, o, weight="t0")
        for k in nodes:
            if k == o:
                continue
            if k in d:
                tot += d[k]; n += 1
            else:
                bad += 1
    return tot / max(n, 1), bad


def criticality_ranking(model: NetworkModel, top: int = 10, max_candidates: int = 60) -> List[Dict]:
    """For segments: increase in mean free-flow OD time (and disconnected OD pairs) if it alone is closed.
    Large networks evaluate only the most heavily loaded candidates between demand zones. Cached per model."""
    cache = getattr(model, "_crit_cache", None)
    if cache is None:
        cache = model._crit_cache = {}
    key = (max_candidates, top)
    if key in cache:
        return cache[key]
    nodes = list(model.zone_nodes)
    if len(model.G) > 400:
        nodes = nodes[:24]
    base, _ = _mean_time(model.G, nodes)
    ids = list(model.segments)
    if len(ids) > max_candidates:
        flow = model.assign(1.0)["edges"]
        ids = sorted(ids, key=lambda s: -flow.get(s, {}).get("flow", 0))[:max_candidates]
    out = []
    for sid in ids:
        seg = model.segments[sid]
        H = model.G.copy()
        H.remove_edges_from([(u, v) for u, v, d in model.G.edges(data=True) if d["seg"] == sid])
        t, bad = _mean_time(H, nodes)
        out.append({"segment_id": sid, "corridor": seg["corridor"], "length_km": seg["length_km"],
                    "mean_time_increase_pct": round((t / base - 1) * 100, 2), "disconnected_od_pairs": bad})
    out.sort(key=lambda r: (-r["disconnected_od_pairs"], -r["mean_time_increase_pct"]))
    cache[key] = out[:top]
    return cache[key]
