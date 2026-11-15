"""Turn corridor waypoints into a topologically connected segment/node set."""
from __future__ import annotations

import math
import re
from collections import defaultdict
from typing import Dict, List, Tuple

from backend.data.riyadh_network import CORRIDORS
from backend.services.osm_service import haversine_km

SNAP_TOL = 0.02  # degrees (~2 km) for endpoint snapping of the synthetic skeleton


def _seg_intersect(p1, p2, p3, p4):
    x1, y1 = p1; x2, y2 = p2; x3, y3 = p3; x4, y4 = p4
    d = (x2 - x1) * (y4 - y3) - (y2 - y1) * (x4 - x3)
    if abs(d) < 1e-12:
        return None
    t = ((x3 - x1) * (y4 - y3) - (y3 - y1) * (x4 - x3)) / d
    u = ((x3 - x1) * (y2 - y1) - (y3 - y1) * (x2 - x1)) / d
    if 0 < t < 1 and 0 < u < 1:
        return (x1 + t * (x2 - x1), y1 + t * (y2 - y1))
    return None


def _project(p, a, b):
    ax, ay = a; bx, by = b; px, py = p
    dx, dy = bx - ax, by - ay
    L = dx * dx + dy * dy
    t = 0 if L == 0 else max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / L))
    q = (ax + t * dx, ay + t * dy)
    return q, math.hypot(px - q[0], py - q[1])


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:28]


def _key(p) -> Tuple[float, float]:
    return (round(p[0], 5), round(p[1], 5))


def build() -> Dict:
    lines = [{"name": n, "cls": c, "lanes": l, "speed": s, "pts": [tuple(p) for p in pts]}
             for n, c, l, s, pts in CORRIDORS]

    # 1) snap each corridor endpoint to the nearest *other* corridor if close (but not already on a node)
    for i, a in enumerate(lines):
        for end in (0, -1):
            p = a["pts"][end]
            best = (None, None, SNAP_TOL)
            for j, b in enumerate(lines):
                if i == j:
                    continue
                for k in range(len(b["pts"]) - 1):
                    q, d = _project(p, b["pts"][k], b["pts"][k + 1])
                    if d < best[2]:
                        best = (j, (k, q), d)
            if best[0] is not None and best[2] > 1e-6:
                j, (k, q), _ = best
                a["pts"][end] = q
                # insert q into b if not an existing vertex
                if _key(q) not in [_key(x) for x in lines[best[0]]["pts"]]:
                    lines[j]["pts"].insert(k + 1, q)

    # 2) insert true crossings into both polylines
    for i in range(len(lines)):
        for j in range(i + 1, len(lines)):
            A, B = lines[i], lines[j]
            ins_a, ins_b = [], []
            for ka in range(len(A["pts"]) - 1):
                for kb in range(len(B["pts"]) - 1):
                    x = _seg_intersect(A["pts"][ka], A["pts"][ka + 1], B["pts"][kb], B["pts"][kb + 1])
                    if x:
                        ins_a.append((ka, x)); ins_b.append((kb, x))
            for k, x in sorted(ins_a, key=lambda t: -t[0]):
                if _key(x) not in [_key(v) for v in A["pts"]]:
                    A["pts"].insert(k + 1, x)
            for k, x in sorted(ins_b, key=lambda t: -t[0]):
                if _key(x) not in [_key(v) for v in B["pts"]]:
                    B["pts"].insert(k + 1, x)

    # 3) nodes = shared vertices or corridor endpoints
    use = defaultdict(set)
    for ln in lines:
        for p in ln["pts"]:
            use[_key(p)].add(ln["name"])
    node_keys = {k for k, v in use.items() if len(v) > 1}
    for ln in lines:
        node_keys.add(_key(ln["pts"][0])); node_keys.add(_key(ln["pts"][-1]))
    node_id = {k: f"N{i:03d}" for i, k in enumerate(sorted(node_keys))}

    # 4) split into segments
    segs, counter = [], defaultdict(int)
    for ln in lines:
        cur = [ln["pts"][0]]
        for p in ln["pts"][1:]:
            cur.append(p)
            if _key(p) in node_keys:
                if len(cur) >= 2 and _key(cur[0]) != _key(cur[-1]):
                    counter[ln["name"]] += 1
                    length = sum(haversine_km(cur[i], cur[i + 1]) for i in range(len(cur) - 1))
                    segs.append(dict(
                        id=f"rs-{_slug(ln['name'])}-{counter[ln['name']]:02d}", corridor=ln["name"],
                        road_class=ln["cls"], lanes=ln["lanes"], speed_limit=float(ln["speed"]),
                        length_km=round(length, 3), from_node=node_id[_key(cur[0])], to_node=node_id[_key(cur[-1])],
                        coords=[[round(x, 6), round(y, 6)] for x, y in cur]))
                cur = [p]
    nodes = {nid: {"id": nid, "lon": k[0], "lat": k[1], "corridors": sorted(use[k])} for k, nid in node_id.items()}
    return {"segments": segs, "nodes": nodes}


if __name__ == "__main__":
    r = build()
    print(len(r["segments"]), "segments", len(r["nodes"]), "nodes")
