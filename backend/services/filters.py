"""One definition of the Overview filters (area / category / priority / since), applied identically to KPIs, rankings,
hotspots, trends AND map layers, so changing a filter changes everything the user sees.

Semantics
  * area      - the demo area (Area_Name / Base_Area).
  * category  - water | lighting | change. Static infrastructure is narrowed to matching asset types.
  * priority  - P1..P4. Incidents/work orders use their stored Priority; detections derive it from Risk_Score
                (same bands as incident priority); verifications/work orders follow their incident; change candidates use their
                detection's priority, so candidates that never became a detection are hidden once a priority is chosen.
  * since     - ISO date; compared with each record's own date field (created / detected / submitted).
Static reference layers (facilities, buildings) honour only `area`.
"""
from __future__ import annotations

from typing import Callable

from backend.gis import schema as S
from backend.gis.store import Store
from backend.tools.common import priority_of

Pred = Callable[[dict], bool]

WATER_ASSETS = ("Water Pipe Segment", "Pressure/Flow Sensor")


def active(area=None, category=None, priority=None, since=None) -> dict:
    return {k: v for k, v in dict(area=area, category=category, priority=priority, since=since).items() if v}


def make_filter(store: Store, layer: str, area: str | None = None, category: str | None = None, priority: str | None = None, since: str | None = None) -> Pred:
    if not (area or category or priority or since):
        return lambda a: True

    def date_ok(v) -> bool:
        return not since or (v or "") >= since

    if layer == S.DETECTIONS:
        return lambda a: (not area or a["Area_Name"] == area) and (not category or a["Category"] == category) \
            and (not priority or priority_of(a["Risk_Score"]) == priority) and date_ok(a["Detection_Date"])

    if layer == S.INCIDENTS:
        return lambda a: (not area or a["Area_Name"] == area) and (not category or a["Category"] == category) \
            and (not priority or a["Priority"] == priority) and date_ok(a["Created_Date"])

    if layer in (S.WORK_ORDERS, S.VERIFICATION):
        inc = {f["id"]: f["attrs"] for f in store.all(S.INCIDENTS)}
        datef = "Created_Date" if layer == S.WORK_ORDERS else "Timestamp"

        def wo_ver(a: dict) -> bool:
            i = inc.get(a["Incident_ID"])
            if not i:
                return False
            return (not area or i["Area_Name"] == area) and (not category or i["Category"] == category) \
                and (not priority or i["Priority"] == priority) and date_ok(a.get(datef))
        return wo_ver

    if layer in (S.CHANGES, S.FEATURES):
        det_by_change = {f["attrs"]["Related_Asset_ID"]: f["attrs"] for f in store.all(S.DETECTIONS) if f["attrs"]["Category"] == "change"}

        def change_ok(a: dict) -> bool:
            if category and category != "change":
                return False
            if area and a["Area_Name"] != area:
                return False
            if priority:
                d = det_by_change.get(a["Change_ID"])
                if not d or priority_of(d["Risk_Score"]) != priority:
                    return False
            return date_ok(a["Detection_Date"])
        if layer == S.CHANGES:
            return change_ok
        ok_ids = {f["id"] for f in store.all(S.CHANGES) if change_ok(f["attrs"])}
        return lambda a: a["Related_Change_ID"] in ok_ids

    if layer == S.INFRA:
        def infra(a: dict) -> bool:
            if area and a["Area_Name"] != area:
                return False
            if category == "water":
                return a["Asset_Type"] in WATER_ASSETS
            if category == "lighting":
                return a["Asset_Type"] == "Streetlight"
            return category != "change"
        return infra

    if layer == S.WATER:
        return lambda a: (not area or a["Area_Name"] == area) and category in (None, "", "water")

    if layer == S.SENSORS:
        asset_area = {f["id"]: f["attrs"]["Area_Name"] for f in store.all(S.INFRA)}

        def sensor(a: dict) -> bool:
            if area and asset_area.get(a["Asset_ID"]) != area:
                return False
            if category == "water":
                return a["Sensor_Type"] == "Pressure/Flow"
            if category == "lighting":
                return a["Sensor_Type"] == "Lamp Power Meter"
            return category != "change"
        return sensor

    if layer in (S.FACILITIES, S.BUILDINGS):
        return lambda a: not area or a["Area_Name"] == area

    if layer == S.WORKERS:
        return lambda a: not area or a["Base_Area"] == area

    return lambda a: True
