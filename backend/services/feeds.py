"""Operational data feeds beyond the sensor network: citizen reports.

ALL FEED DATA HERE IS SIMULATED (labelled SYNTHETIC-DEMO). The shapes follow what a real command center receives: geotagged reports
from residents (app, call center, social media) arriving a few at a time. In production these
would be replaced by the real Balady/940 integration.
"""
from __future__ import annotations

import math
import random
from datetime import datetime, timedelta, timezone

from backend.gis import geo
from backend.gis import schema as S
from backend.gis.store import Store
from backend.services.synthetic import AREAS

CHANNELS = ("Balady app", "940 call center", "Social media")
TEXT = {
    "water": [("Low water pressure", "No water or very low pressure in the building."), ("Water leak", "Water running on the street.")],
    "lighting": [("Streetlight out", "Streetlight is not working on this street.")],
    "other": [("Road damage", "Pothole on the road."), ("Waste", "Overflowing waste container.")],
}


def _ts(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse(ts: str) -> datetime:
    return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def area_of(p: tuple[float, float]) -> str:
    return min(AREAS, key=lambda k: geo.haversine_m(p, AREAS[k]["center"]))


class FeedEngine:
    def __init__(self, store: Store, seed: int = 20260101, citizen_enabled: bool = True):
        self.store = store
        self.citizen_enabled = citizen_enabled
        self.rng = random.Random(seed + 7)
        self.last_tick: str | None = None          # when the sensor/telemetry feeds last delivered new readings

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc).replace(microsecond=0)

    def _around(self, p, max_m: float, min_m: float = 0.0):
        r, a = self.rng.uniform(min_m, max_m), self.rng.uniform(0, 2 * math.pi)
        return geo.offset(p, r * math.cos(a), r * math.sin(a))

    # ---- citizen reports ---------------------------------------------------------------------------------------
    def add_report(self, p, category: str, minutes_ago: float = 0, channel: str | None = None) -> dict:
        title, desc = self.rng.choice(TEXT[category])
        rid = self.store.next_id("CR")
        rec = {"Report_ID": rid, "Category": category, "Title": title, "Description": desc, "Channel": channel or self.rng.choice(CHANNELS),
               "Reported_At": _ts(self._now() - timedelta(minutes=minutes_ago)), "Status": "New" if category != "other" else "Logged",
               "Area_Name": area_of(p), "Linked_Incident": "", "Data_Classification": S.SYNTHETIC}
        self.store.upsert(S.CITIZEN, rec, geo.point(*p))
        return rec

    def _isolated(self, p, category: str, min_m: float = 700.0) -> bool:
        return all(geo.haversine_m(p, geo.centroid(f["geom"])) >= min_m for f in self.store.query(S.CITIZEN, Category=category))

    def _background_report(self) -> dict | None:
        """One routine report somewhere in the city. Water/lighting ones are kept apart, so ordinary noise never forms a cluster on its own."""
        cat = self.rng.choices(["other", "water", "lighting"], [0.6, 0.25, 0.15])[0]
        area = self.rng.choice(list(AREAS))
        for _ in range(8):
            p = self._around(AREAS[area]["center"], 2200)
            if cat == "other" or self._isolated(p, cat):
                return self.add_report(p, cat, minutes_ago=self.rng.uniform(1, 600))
        return None

    # ---- weather -------------------------------------------------------------------------------------------------






    # ---- lifecycle -----------------------------------------------------------------------------------------------
    def seed(self) -> None:
        now = self._now()
        if not self.citizen_enabled:
            self.last_tick = _ts(now)
            return

        for _ in range(14):
            self._background_report()
        self.last_tick = _ts(now)

    def tick(self) -> None:
        """One more hour: now and then, a routine citizen report."""

        if self.citizen_enabled and self.rng.random() < 0.45:
            self._background_report()
        self.last_tick = _ts(self._now())

    # ---- scenario feeds ------------------------------------------------------------------------------------------
    def on_scenario(self, name: str, info: dict) -> int:
        """Residents notice the same faults the sensors see: correlated reports arrive within the hour."""
        n = 0
        if not self.citizen_enabled or name in ("traffic_incident", "road_closure", "major_event"):
            return 0                                             # road events reach the crew as road reports and notices, not through residents
        if info.get("sensor_id") and (name == "olaya_leak" or name.startswith("leak")):
            c = self._sensor_point(info["sensor_id"], info.get("pipeline_id"))
            if c:
                for _ in range(4):
                    self.add_report(self._around(c, 160), "water", self.rng.uniform(3, 40)); n += 1
        elif name == "multi_incident":
            for i, an in enumerate(info.get("anomalies", [])):
                c = self._sensor_point(an.get("sensor_id"), an.get("pipeline_id"))
                if c:
                    for _ in range(3 if i < 2 else 1):          # the decoy (a pump transient) draws only one report
                        self.add_report(self._around(c, 160), "water", self.rng.uniform(3, 40)); n += 1
        elif name == "king_fahd_lights" or name.startswith("lights"):
            lamps = info.get("assets", [])[:3] or [f["id"] for f in self.store.all(S.TELEMETRY) if f["attrs"]["Asset_ID"].startswith("AST-L-") and f["attrs"]["Flicker_30d"] >= 6][:3]
            for aid in lamps:
                a = self.store.get(S.INFRA, aid)
                if a:
                    self.add_report(self._around(geo.centroid(a["geom"]), 25), "lighting", self.rng.uniform(5, 90)); n += 1
        return n

    def _sensor_point(self, sensor_id, pipe_id):
        """Where a sensor sits (its asset point); falls back to the middle of its pipe."""
        for f in self.store.query(S.INFRA, Asset_Name=sensor_id) if sensor_id else []:
            return geo.centroid(f["geom"])
        pipe = self.store.get(S.WATER, pipe_id) if pipe_id else None
        return geo.centroid(pipe["geom"]) if pipe else None

    def citizen_surge(self, area: str = "Al Malaz") -> dict:
        """Residents report low water pressure where no sensor is watching: the crew has to find it from the reports alone."""
        if not self.citizen_enabled:
            raise ValueError("citizen reports are disabled in this deployment")
        c = geo.offset(AREAS[area]["center"], 450, -300)
        for _ in range(5):
            self.add_report(self._around(c, 130), "water", self.rng.uniform(4, 45))
        return {"area": area, "location": {"lon": round(c[0], 6), "lat": round(c[1], 6)}, "reports": 5}



    # ---- status for the UI --------------------------------------------------------------------------------------
    def reports(self, limit: int = 120) -> list[dict]:
        rows = [{**f["attrs"], "lon": f["geom"]["coordinates"][0], "lat": f["geom"]["coordinates"][1]} for f in self.store.all(S.CITIZEN)]
        rows.sort(key=lambda r: r["Reported_At"], reverse=True)
        return rows[:limit]
