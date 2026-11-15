"""Small, dependency-free geodesy helpers (WGS84 lon/lat tuples, metres)."""
from __future__ import annotations

import math
from typing import Iterable, Sequence

LonLat = tuple[float, float]
R_EARTH = 6371008.8


def haversine_m(a: LonLat, b: LonLat) -> float:
    lon1, lat1, lon2, lat2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    d = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * R_EARTH * math.asin(math.sqrt(d))


def to_xy(p: LonLat, lat0: float) -> tuple[float, float]:
    return (math.radians(p[0]) * R_EARTH * math.cos(math.radians(lat0)), math.radians(p[1]) * R_EARTH)


def offset(p: LonLat, dx_m: float, dy_m: float) -> LonLat:
    dlat = math.degrees(dy_m / R_EARTH)
    dlon = math.degrees(dx_m / (R_EARTH * math.cos(math.radians(p[1]))))
    return (p[0] + dlon, p[1] + dlat)


def seg_nearest(p: LonLat, a: LonLat, b: LonLat) -> tuple[float, float, LonLat]:
    """Distance (m), parameter t in [0,1] and nearest point of p on segment ab."""
    lat0 = p[1]
    px, py = to_xy(p, lat0)
    ax, ay = to_xy(a, lat0)
    bx, by = to_xy(b, lat0)
    dx, dy = bx - ax, by - ay
    l2 = dx * dx + dy * dy
    t = 0.0 if l2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / l2))
    q = (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy)), t, q


def dist_to_line(p: LonLat, line: Sequence[LonLat]) -> tuple[float, LonLat]:
    best = (float("inf"), tuple(line[0]))
    for i in range(len(line) - 1):
        d, _, q = seg_nearest(p, line[i], line[i + 1])
        if d < best[0]:
            best = (d, q)
    return best


def line_length_m(line: Sequence[LonLat]) -> float:
    return sum(haversine_m(line[i], line[i + 1]) for i in range(len(line) - 1))


def interpolate(line: Sequence[LonLat], frac: float) -> tuple[LonLat, tuple[float, float]]:
    """Point at a fraction of total length plus unit tangent (east, north)."""
    total = line_length_m(line)
    target = max(0.0, min(1.0, frac)) * total
    acc = 0.0
    for i in range(len(line) - 1):
        seg = haversine_m(line[i], line[i + 1])
        if acc + seg >= target or i == len(line) - 2:
            t = 0 if seg == 0 else min(1.0, (target - acc) / seg)
            a, b = line[i], line[i + 1]
            pt = (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
            ax, ay = to_xy(a, a[1])
            bx, by = to_xy(b, a[1])
            n = math.hypot(bx - ax, by - ay) or 1.0
            return pt, ((bx - ax) / n, (by - ay) / n)
        acc += seg
    return tuple(line[-1]), (0.0, 1.0)


def ring_area_sqm(ring: Sequence[LonLat]) -> float:
    lat0 = sum(p[1] for p in ring) / len(ring)
    pts = [to_xy(p, lat0) for p in ring]
    s = 0.0
    for i in range(len(pts)):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % len(pts)]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0


def point_in_ring(p: LonLat, ring: Sequence[LonLat]) -> bool:
    x, y = p
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-18) + xi:
            inside = not inside
        j = i
    return inside


def dist_to_ring(p: LonLat, ring: Sequence[LonLat]) -> float:
    if point_in_ring(p, ring):
        return 0.0
    return min(seg_nearest(p, ring[i], ring[(i + 1) % len(ring)])[0] for i in range(len(ring)))


def centroid(geom: dict) -> LonLat:
    t, c = geom["type"], geom["coordinates"]
    if t == "Point":
        return (c[0], c[1])
    pts = c if t == "LineString" else c[0]
    return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))


def dist_geom_m(p: LonLat, geom: dict) -> float:
    t, c = geom["type"], geom["coordinates"]
    if t == "Point":
        return haversine_m(p, (c[0], c[1]))
    if t == "LineString":
        return dist_to_line(p, [tuple(x) for x in c])[0]
    return dist_to_ring(p, [tuple(x) for x in c[0]])


def circle_ring(center: LonLat, radius_m: float, n: int = 32) -> list[LonLat]:
    ring = [offset(center, radius_m * math.cos(2 * math.pi * k / n), radius_m * math.sin(2 * math.pi * k / n)) for k in range(n)]
    ring.append(ring[0])
    return ring


def point(lon: float, lat: float) -> dict:
    return {"type": "Point", "coordinates": [round(lon, 6), round(lat, 6)]}


def line(coords: Iterable[LonLat]) -> dict:
    return {"type": "LineString", "coordinates": [[round(x, 6), round(y, 6)] for x, y in coords]}


def polygon(ring: Iterable[LonLat]) -> dict:
    r = [[round(x, 6), round(y, 6)] for x, y in ring]
    if r[0] != r[-1]:
        r.append(r[0])
    return {"type": "Polygon", "coordinates": [r]}
