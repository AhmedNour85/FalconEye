"""Demand adjustments: area resolution and OD multipliers."""
from __future__ import annotations

import re
from typing import Callable, Optional, Set

from backend.services.osm_service import haversine_km
from backend.simulation.network_model import NetworkModel

CENTER = (46.68, 24.71)
NAMED_AREAS = {
    "north": lambda lo, la: la > 24.76, "northern": lambda lo, la: la > 24.76,
    "south": lambda lo, la: la < 24.66, "southern": lambda lo, la: la < 24.66,
    "east": lambda lo, la: lo > 46.74, "eastern": lambda lo, la: lo > 46.74,
    "west": lambda lo, la: lo < 46.62, "western": lambda lo, la: lo < 46.62,
    "center": lambda lo, la: haversine_km((lo, la), CENTER) < 6, "central": lambda lo, la: haversine_km((lo, la), CENTER) < 6,
    "city": lambda lo, la: True, "all": lambda lo, la: True, "riyadh": lambda lo, la: True,
}


_NAMED_RE = re.compile(r"\b(" + "|".join(sorted(NAMED_AREAS, key=len, reverse=True)) + r")\b")


def resolve_area(model: NetworkModel, area) -> Set[str]:
    """area: None | 'north' | {'bbox':[minx,miny,maxx,maxy]} | {'place':'KAFD','radius_km':3}

    A named area must match as a WHOLE WORD ('Kingdom Mall' is not 'all'), and an area or place that cannot be resolved is an error:
    silently falling back to the whole city would apply a local scenario city-wide."""
    G = model.G
    if not area:
        return set(G.nodes)
    if isinstance(area, str):
        m = _NAMED_RE.search(area.lower())
        if m:
            f = NAMED_AREAS[m.group(1)]
            return {n for n, d in G.nodes(data=True) if f(d["lon"], d["lat"])}
        area = {"place": area, "radius_km": 3}
    if isinstance(area, dict):
        if area.get("bbox"):
            x0, y0, x1, y1 = area["bbox"]
            return {n for n, d in G.nodes(data=True) if x0 <= d["lon"] <= x1 and y0 <= d["lat"] <= y1}
        if area.get("place"):
            c = model.resolve_place(area["place"])
            if not c:
                raise ValueError(f"unknown area or place '{area['place']}' (use north/south/east/west/center/city, a known place such as KAFD, or a bbox)")
            cc = model.node_ll(c)
            r = float(area.get("radius_km", 3))
            if not (0 < r <= 25):
                raise ValueError("radius_km must be > 0 and <= 25")
            return {n for n, d in G.nodes(data=True) if haversine_km((d["lon"], d["lat"]), cc) <= r}
    return set(G.nodes)


def area_multiplier(nodes: Set[str], pct: float) -> Callable[[str, str], float]:
    """Trips with an origin OR destination in the area scale by (1+pct/100)."""
    f = 1 + pct / 100.0
    return lambda o, d: f if (o in nodes or d in nodes) else 1.0
