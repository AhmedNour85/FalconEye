"""Shared helpers and the ToolContext passed to every tool."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from backend.gis import geo

if TYPE_CHECKING:  # pragma: no cover
    from backend.platform import Platform


@dataclass
class ToolContext:
    p: "Platform"
    session_id: str = "default"
    state: dict = field(default_factory=dict)  # conversational focus (last detections, incident, work order ...)

    @property
    def store(self):
        return self.p.store


class ToolError(Exception):
    """Structured, user-presentable tool failure."""


def severity_of(score: float) -> str:
    return "Critical" if score >= 75 else "High" if score >= 55 else "Medium" if score >= 35 else "Low"


def priority_of(score: float) -> str:
    return "P1" if score >= 75 else "P2" if score >= 55 else "P3" if score >= 35 else "P4"


def loc(geom: dict) -> tuple[float, float]:
    return geo.centroid(geom)


def buildings_within(store, p, radius_m: float) -> dict:
    """Real OSM building footprints (reference layer) whose centroid lies within radius_m of p."""
    from backend.gis import schema as S

    dlat = radius_m / 110540.0
    dlon = radius_m / (111320.0 * math.cos(math.radians(p[1])))
    n, area = 0, 0.0
    for f in store.bbox_query(S.BUILDINGS, p[0] - dlon, p[1] - dlat, p[0] + dlon, p[1] + dlat, limit=20000):
        if geo.haversine_m(p, geo.centroid(f["geom"])) <= radius_m:
            n += 1
            area += f["attrs"]["Area_Sqm"] or 0
    return {"count": n, "footprint_sqm": round(area)}


def lonlat_str(p) -> str:
    return f"{p[1]:.5f}N, {p[0]:.5f}E"
