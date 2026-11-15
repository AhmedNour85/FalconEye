"""Access to the cached REAL OpenStreetMap extract (roads + building footprints) produced by scripts/fetch_osm_riyadh.py.

(c) OpenStreetMap contributors, ODbL. When the cache file is missing every function degrades gracefully (returns None / empty) and the
synthetic generator falls back to its approximate hand-placed geometry.
"""
from __future__ import annotations

import gzip
import json
import math
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path

from backend.gis import geo

PATH = Path(__file__).resolve().parent.parent.parent / "data" / "samples" / "osm_riyadh.json.gz"
MAJOR = ("motorway", "trunk", "primary", "secondary", "tertiary", "motorway_link", "trunk_link", "primary_link", "secondary_link", "tertiary_link")
LOCAL = ("unclassified", "residential", "living_street")
DIAMETER = {"motorway": 900, "trunk": 900, "primary": 800, "secondary": 600, "tertiary": 500, "unclassified": 400, "residential": 300, "living_street": 250}


@lru_cache(maxsize=1)
def load() -> dict | None:
    if not PATH.exists():
        return None
    with gzip.open(PATH, "rt", encoding="utf-8") as f:
        d = json.load(f)
    for b in d["buildings"]:
        ring = [tuple(p) for p in b["ring"]]
        b["centroid"] = (sum(p[0] for p in ring[:-1]) / (len(ring) - 1), sum(p[1] for p in ring[:-1]) / (len(ring) - 1))
        b["area"] = geo.ring_area_sqm(ring)
    d["road_by_id"] = {r["id"]: r for r in d["roads"]}
    return d


def available() -> bool:
    d = load()
    return bool(d and d["roads"])


def _bucket(p, size=0.004):
    return (int(p[0] / size), int(p[1] / size))


@lru_cache(maxsize=1)
def _building_index() -> dict:
    d = load()
    idx = defaultdict(list)
    for b in d["buildings"]:
        idx[_bucket(b["centroid"])].append(b)
    return idx


def buildings_near(center, radius_m: float) -> list[dict]:
    d = load()
    if not d:
        return []
    idx = _building_index()
    r_deg = radius_m / 100000.0 + 0.004
    cx, cy = _bucket(center)
    n = int(r_deg / 0.004) + 1
    out = []
    for i in range(cx - n, cx + n + 1):
        for j in range(cy - n, cy + n + 1):
            for b in idx.get((i, j), ()):
                if geo.haversine_m(center, b["centroid"]) <= radius_m:
                    out.append(b)
    return out


def roads_near(center, radius_m: float, classes=None) -> list[dict]:
    d = load()
    if not d:
        return []
    out = []
    for r in d["roads"]:
        if classes and r["highway"] not in classes:
            continue
        if geo.dist_to_line(center, [tuple(p) for p in r["coords"]])[0] <= radius_m:
            out.append(r)
    return out


def corridor_lines(name: str, lat_range=(24.60, 24.80)) -> list[list[tuple]]:
    """Polylines of the real ways that carry this road name (clipped to the demo latitude band)."""
    d = load()
    if not d:
        return []
    lines = []
    for wid in d["corridors"].get(name, []):
        r = d["road_by_id"].get(wid)
        if not r:
            continue
        pts = [tuple(p) for p in r["coords"] if lat_range[0] <= p[1] <= lat_range[1]]
        if len(pts) >= 2:
            lines.append(pts)
    return lines


def area_main_lines(center, radius_m: float) -> list[list[tuple]]:
    return [[tuple(p) for p in r["coords"]] for r in roads_near(center, radius_m, MAJOR)]


# ------------------------------------------------------------------------------------------------ polylines
def polyline_length(coords) -> float:
    return geo.line_length_m(coords)


def slice_polyline(coords, d0: float, d1: float) -> list[tuple]:
    """Sub-polyline between distances d0..d1 (metres) along coords."""
    out, acc = [], 0.0
    for i in range(len(coords) - 1):
        a, b = coords[i], coords[i + 1]
        seg = geo.haversine_m(a, b)
        s0, s1 = acc, acc + seg
        if s1 < d0 or s0 > d1 or seg == 0:
            acc = s1
            continue
        t0, t1 = max(0.0, (d0 - s0) / seg), min(1.0, (d1 - s0) / seg)
        pa = (a[0] + (b[0] - a[0]) * t0, a[1] + (b[1] - a[1]) * t0)
        pb = (a[0] + (b[0] - a[0]) * t1, a[1] + (b[1] - a[1]) * t1)
        if not out:
            out.append(pa)
        out.append(pb)
        acc = s1
    return out


def sample_along(coords, spacing_m: float, start=None) -> list[tuple[tuple, tuple]]:
    """Points every `spacing_m` along a polyline with the unit tangent (east, north)."""
    total = polyline_length(coords)
    n = max(1, int(total // spacing_m))
    pts = []
    for k in range(n):
        frac = ((k + 0.5) * spacing_m) / total if total else 0.0
        pts.append(geo.interpolate(coords, min(frac, 1.0)))
    return pts


# ------------------------------------------------------------------------------------------------ pipe chunks
def pipe_chunks(center, radius_m: float, min_len=70.0, max_len=380.0) -> list[dict]:
    """Split real roads into pipe-sized chunks at OSM junctions (so adjacent chunks share node ids = real network topology)."""
    d = load()
    if not d:
        return []
    junction = Counter(n for r in d["roads"] if r["highway"] in MAJOR + LOCAL for n in set(r["nodes"]))
    chunks = []
    for r in roads_near(center, radius_m, MAJOR + LOCAL):
        coords, nodes = [tuple(p) for p in r["coords"]], r["nodes"]
        if len(nodes) != len(coords):
            continue
        cuts = [0] + [i for i in range(1, len(nodes) - 1) if junction[nodes[i]] >= 2] + [len(nodes) - 1]
        for a, b in zip(cuts, cuts[1:]):
            piece = coords[a:b + 1]
            L = polyline_length(piece)
            if L < min_len:
                continue
            parts = max(1, math.ceil(L / max_len))
            for k in range(parts):
                sub = piece if parts == 1 else slice_polyline(piece, L * k / parts, L * (k + 1) / parts)
                if len(sub) < 2:
                    continue
                n_from = nodes[a] if k == 0 else f"S{r['id']}_{a}_{k}"
                n_to = nodes[b] if k == parts - 1 else f"S{r['id']}_{a}_{k + 1}"
                mid = geo.interpolate(sub, 0.5)[0]
                if geo.haversine_m(mid, center) > radius_m:
                    continue
                chunks.append({"coords": sub, "from": str(n_from), "to": str(n_to), "highway": r["highway"], "road": r["name"], "length": polyline_length(sub), "mid": mid})
    return chunks


def connected_cluster(chunks: list[dict], center, n: int) -> list[dict]:
    """BFS over shared nodes starting at the chunk closest to `center` -> a connected piece of network of up to n chunks."""
    if not chunks:
        return []
    by_node = defaultdict(list)
    for i, c in enumerate(chunks):
        by_node[c["from"]].append(i)
        by_node[c["to"]].append(i)
    start = min(range(len(chunks)), key=lambda i: geo.haversine_m(chunks[i]["mid"], center))
    seen, order, queue = {start}, [], [start]
    while queue and len(order) < n:
        i = queue.pop(0)
        order.append(i)
        nb = sorted({j for node in (chunks[i]["from"], chunks[i]["to"]) for j in by_node[node] if j not in seen},
                    key=lambda j: geo.haversine_m(chunks[j]["mid"], center))
        for j in nb:
            seen.add(j)
            queue.append(j)
    if len(order) < n:  # disconnected remainder: add nearest unused chunks
        rest = sorted((i for i in range(len(chunks)) if i not in seen), key=lambda i: geo.haversine_m(chunks[i]["mid"], center))
        order += rest[: n - len(order)]
    return [chunks[i] for i in order]


def nearest_road_point(p, radius_m=300.0):
    best = (float("inf"), None)
    for r in roads_near(p, radius_m, MAJOR + LOCAL):
        d, q = geo.dist_to_line(p, [tuple(x) for x in r["coords"]])
        if d < best[0]:
            best = (d, q)
    return best[1]
