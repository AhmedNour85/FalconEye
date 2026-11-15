"""Build a routable, directed road network from Overpass ways (OpenStreetMap, ODbL).

Steps: split ways at shared nodes (true junctions) and way ends -> segments; honour `oneway`; derive lanes/speed/class;
keep the largest strongly connected component so every OD pair is routable; drop parallel duplicates (the model keeps one
edge per directed node pair). Corridor names are canonicalised to the app's corridor list when the OSM name matches
(e.g. "Northern Ring Rd" -> "Northern Ring Road") so closure requests like "King Fahd Road" resolve.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Dict, List

import networkx as nx

from backend.mobility.sources import ATTRIBUTION, haversine_km

CANON = [  # (canonical name, regex on lower-case OSM name/ref)
    ("King Fahd Road", r"^king fahd road$"), ("Northern Ring Road", r"northern ring"), ("Eastern Ring Road", r"^eastern ring( road| rd)?$"),
    ("Southern Ring Road", r"south(ern)? ring"), ("Western Ring Road", r"western ring"), ("Makkah Road", r"makkah al.?mukarramah( branch)? road"),
    ("Khurais Road", r"^khurais road$"), ("Olaya Street", r"olaya (street|road)"), ("Takhassusi Street", r"takhass?ous?si"),
    ("Prince Turki bin Abdulaziz Al Awwal Road", r"prince turki bin abdulaziz al awa?l road"), ("Airport Road", r"^airport r(oa)?d$"),
    ("Imam Saud bin Faisal Road", r"imam saud bin faisal"), ("King Salman Road", r"^king salman road$"),
]
CLASS_OF = {"motorway": "motorway", "trunk": "motorway", "primary": "arterial", "secondary": "arterial", "tertiary": "collector",
            "motorway_link": "collector", "trunk_link": "collector", "primary_link": "collector", "secondary_link": "collector", "tertiary_link": "collector"}
SPEED = {"motorway": 100, "trunk": 90, "primary": 70, "secondary": 60, "tertiary": 50, "motorway_link": 50, "trunk_link": 50, "primary_link": 45, "secondary_link": 40, "tertiary_link": 40}
LANES = {"motorway": 3, "trunk": 3, "primary": 2, "secondary": 2, "tertiary": 1, "motorway_link": 1, "trunk_link": 1, "primary_link": 1, "secondary_link": 1, "tertiary_link": 1}
INCLUDED = {"motorway", "trunk", "primary", "secondary", "motorway_link", "trunk_link", "primary_link", "secondary_link"}  # tertiary/local streets excluded for tractability
PRIORITY = {"motorway": 0, "trunk": 1, "primary": 2, "secondary": 3, "tertiary": 4, "motorway_link": 5, "trunk_link": 5, "primary_link": 5, "secondary_link": 5, "tertiary_link": 5}


def canonical(name: str) -> str:
    low = (name or "").lower()
    for c, rx in CANON:
        if re.search(rx, low):
            return c
    return name or ""


def _num(v, default):
    try:
        return float(str(v).split(";")[0].split()[0])
    except Exception:
        return default


def build(raw: dict) -> Dict:
    ways = [w for w in raw.get("elements", []) if w.get("type") == "way" and w.get("tags", {}).get("highway") in INCLUDED and w.get("nodes") and w.get("geometry") and len(w["nodes"]) == len(w["geometry"])]
    use = Counter(n for w in ways for n in set(w["nodes"]))
    segs: List[dict] = []
    for w in ways:
        t = w["tags"]; hw = t["highway"]
        raw_name = t.get("name:en") or t.get("name") or t.get("ref") or ""
        corridor = canonical(raw_name) or f"unnamed {hw}"
        ow = t.get("oneway", "yes" if hw in ("motorway", "motorway_link", "trunk_link", "primary_link", "secondary_link", "tertiary_link") or t.get("junction") == "roundabout" else "no")
        nodes, geom = list(w["nodes"]), [(g["lon"], g["lat"]) for g in w["geometry"]]
        oneway = ow in ("yes", "true", "1", "-1")
        if ow == "-1":
            nodes, geom = nodes[::-1], geom[::-1]
        lanes_tag = _num(t.get("lanes"), None)
        lanes = max(1, int(lanes_tag if oneway and lanes_tag else (lanes_tag / 2 if lanes_tag else LANES[hw]))) if lanes_tag else LANES[hw]
        speed = _num(t.get("maxspeed"), SPEED[hw])
        cut = [i for i, n in enumerate(nodes) if i in (0, len(nodes) - 1) or use[n] > 1]
        for k, (i, j) in enumerate(zip(cut, cut[1:])):
            if nodes[i] == nodes[j]:
                continue
            coords = geom[i:j + 1]
            length = sum(haversine_km(a, b) for a, b in zip(coords, coords[1:]))
            if length < 0.005:
                continue
            segs.append(dict(id=f"osm-{w['id']}-{k:02d}", corridor=corridor, road_class=CLASS_OF[hw], lanes=lanes, speed_limit=float(min(max(speed, 20), 120)), length_km=round(length, 3),
                             from_node=f"o{nodes[i]}", to_node=f"o{nodes[j]}", coords=[[round(x, 6), round(y, 6)] for x, y in coords], oneway=oneway,
                             osm_id=w["id"], osm_name=raw_name, hw=hw))
    # drop parallel/duplicate directed pairs (keep the higher-priority, longer-lived class)
    segs.sort(key=lambda s: (PRIORITY[s["hw"]], -s["length_km"]))
    taken, keep = set(), []
    for s in segs:
        pairs = {(s["from_node"], s["to_node"])} | (set() if s["oneway"] else {(s["to_node"], s["from_node"])})
        if pairs & taken:
            continue
        taken |= pairs; keep.append(s)
    # strongly connected core
    D = nx.DiGraph()
    for s in keep:
        D.add_edge(s["from_node"], s["to_node"])
        if not s["oneway"]:
            D.add_edge(s["to_node"], s["from_node"])
    core = max(nx.strongly_connected_components(D), key=len)
    keep = [s for s in keep if s["from_node"] in core and s["to_node"] in core]
    pos: Dict[str, tuple] = {}
    corr = defaultdict(set)
    for s in keep:
        pos[s["from_node"]] = tuple(s["coords"][0]); pos[s["to_node"]] = tuple(s["coords"][-1])
        corr[s["from_node"]].add(s["corridor"]); corr[s["to_node"]].add(s["corridor"])
    nodes = {n: {"id": n, "lon": p[0], "lat": p[1], "corridors": sorted(corr[n])} for n, p in pos.items()}
    for i, s in enumerate(keep):
        s["id"] = s["id"]
    return {"segments": keep, "nodes": nodes, "attribution": ATTRIBUTION,
            "stats": {"ways": len(ways), "segments": len(keep), "nodes": len(nodes), "dropped_not_strongly_connected": len(segs) - len(keep)}}
