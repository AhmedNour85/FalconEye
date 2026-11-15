"""Road-closure selection: map a corridor/section request onto concrete RoadSegment ids."""
from __future__ import annotations

import re
from typing import Dict, List, Optional

from backend.data import riyadh_network as RN
from backend.services.osm_service import haversine_km
from backend.simulation.network_model import NetworkModel

ALIASES = {"king fahd": "King Fahd Road", "northern ring": "Northern Ring Road", "eastern ring": "Eastern Ring Road",
           "southern ring": "Southern Ring Road", "western ring": "Western Ring Road", "makkah": "Makkah Road",
           "khurais": "Khurais Road", "olaya": "Olaya Street", "takhassusi": "Takhassusi Street",
           "prince turki": "Prince Turki bin Abdulaziz Al Awwal Road", "airport road": "Airport Road",
           "imam saud": "Imam Saud bin Faisal Road", "king salman": "King Salman Road"}


def resolve_corridor(text: str) -> Optional[str]:
    t = (text or "").lower()
    for k, v in ALIASES.items():
        if k in t:
            return v
    for name, *_ in RN.CORRIDORS:
        if name.lower() == t:
            return name
    return None


def corridor_segments(model: NetworkModel, corridor: str) -> List[dict]:
    segs = [s for s in model.segments.values() if s.get("corridor") == corridor and not str(s["id"]).startswith("new-")]
    return sorted(segs, key=lambda s: s["id"])


def _opposite(model: NetworkModel, sid: str, pool: List[dict]) -> List[str]:
    """One-way carriageways (OSM): a road closure closes the parallel opposite-direction carriageway too."""
    seg = model.segments[sid]
    if not (seg.get("attributes") or {}).get("oneway"):
        return []
    c = seg["geometry"]["coordinates"]
    mid = c[len(c) // 2]
    d0 = (c[-1][0] - c[0][0], c[-1][1] - c[0][1])
    best = []
    for o in pool:
        if o["id"] == sid or not (o.get("attributes") or {}).get("oneway"):
            continue
        oc = o["geometry"]["coordinates"]
        d1 = (oc[-1][0] - oc[0][0], oc[-1][1] - oc[0][1])
        if d0[0] * d1[0] + d0[1] * d1[1] >= 0:
            continue  # same direction
        dist = min(haversine_km(mid, p) for p in oc)
        if dist <= 0.15:
            best.append((dist, o["id"]))
    return [i for _, i in sorted(best)[:1]]


def select_closure(model: NetworkModel, corridor: str, baseline_edges: Dict[str, dict], segment_ids: Optional[List[str]] = None,
                   near: Optional[str] = None, section: Optional[List[float]] = None, span_km: float = 2.0) -> Dict:
    """Priority: explicit ids > fractional section > nearest to a place > most heavily loaded section (default)."""
    segs = corridor_segments(model, corridor)
    if segment_ids:
        ids = [s for s in segment_ids if s in model.segments]
        why = "explicit segment ids"
    elif not segs:
        return {"ids": [], "why": f"corridor '{corridor}' not found"}
    elif section and len(section) == 2:
        tot = sum(s["length_km"] for s in segs)
        a, b = section[0] * tot, section[1] * tot
        acc, ids = 0.0, []
        for s in segs:
            if acc + s["length_km"] > a and acc < b:
                ids.append(s["id"])
            acc += s["length_km"]
        why = f"section {section[0]:.0%}-{section[1]:.0%} of corridor length"
    elif near and model.resolve_place(near):
        n = model.resolve_place(near)
        lo, la = model.node_ll(n)
        best = min(segs, key=lambda s: min((c[0] - lo) ** 2 + (c[1] - la) ** 2 for c in s["geometry"]["coordinates"]))
        ids, why = [best["id"]], f"section nearest to {near}"
    else:
        ranked = sorted(segs, key=lambda s: -baseline_edges.get(s["id"], {}).get("flow", 0))
        top = ranked[0]
        ids = [top["id"]]
        nodes = {top["from_node"], top["to_node"]}
        for s in ranked[1:]:  # extend to adjacent heavy segment to form a realistic multi-km section
            if {s["from_node"], s["to_node"]} & nodes and top["length_km"] < 3:
                ids.append(s["id"]); break
        # grow into a through-section of >= 2 km by following the carriageway downstream along the same corridor
        succ = {}
        for sg in segs:
            succ.setdefault(sg["from_node"], []).append(sg)
            if not (sg.get("attributes") or {}).get("oneway"):
                succ.setdefault(sg["to_node"], []).append(sg)
        cur_seg = model.segments[ids[-1]]
        total = sum(model.segments[i]["length_km"] for i in ids)
        for _ in range(80):
            if total >= span_km:
                break
            cands = [x for x in succ.get(cur_seg["to_node"], []) if x["id"] not in ids]
            if not cands:  # corridor continues under another carriageway/ramp: follow any non-ramp road
                cands = [x for x in model.segments.values() if x["from_node"] == cur_seg["to_node"] and x["id"] not in ids and x["road_class"] != "collector"]
            if not cands:
                break
            cur_seg = max(cands, key=lambda x: baseline_edges.get(x["id"], {}).get("flow", 0))
            ids.append(cur_seg["id"]); total += cur_seg["length_km"]
        why = "most heavily loaded through-section (target length = 'closed length', both carriageways counted) of the corridor (default)"
    pool = corridor_segments(model, corridor) if corridor else []
    for sid0 in list(ids):
        for o in _opposite(model, sid0, pool):
            if o not in ids:
                ids.append(o)
    sel = [model.segments[i] for i in ids]
    return {"ids": ids, "why": why, "length_km": round(sum(s["length_km"] for s in sel), 2),
            "geometry": {"type": "MultiLineString", "coordinates": [s["geometry"]["coordinates"] for s in sel]},
            "end_nodes": sorted({n for s in sel for n in (s["from_node"], s["to_node"])})}
