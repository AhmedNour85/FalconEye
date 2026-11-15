"""City-management use cases beyond water and lamps: visual distortion, streetlight pole health and land-use compliance.

ALL INPUTS HERE ARE SIMULATED (labelled SYNTHETIC-DEMO). Baselines are deterministic per asset; scenarios inject the faults.
The scoring/classification rules are real and transparent, so every flag can be explained from stored values.
"""
from __future__ import annotations

import random
import statistics

from backend.gis import geo
from backend.gis import schema as S
from backend.gis.store import Store, utcnow

# ---------------------------------------------------------------------------------------------------------------- poles
CORROSION = ("None", "Low", "Moderate", "Severe")          # stored as 0..3
TILT_FLAG_DEG = 4.0
CORROSION_FLAG = 2


def pole_state(asset_id: str, tel: dict | None) -> tuple[float, int]:
    """(tilt in degrees, corrosion 0..3). Seeded baseline for healthy poles unless telemetry carries a measurement."""
    t = (tel or {}).get("Pole_Tilt_Deg")
    c = (tel or {}).get("Corrosion_Level")
    r = random.Random(f"pole:{asset_id}")
    tilt = float(t) if t not in (None, "") else round(abs(r.gauss(0.8, 0.5)), 1)
    corr = int(c) if c not in (None, "") else (1 if r.random() < 0.25 else 0)
    return tilt, corr


def pole_risk(tilt: float, corr: int, age: float) -> float:
    return round(100 * (0.5 * min(1.0, tilt / 10) + 0.3 * corr / 3 + 0.2 * min(1.0, (age or 0) / 12)), 1)


def pole_flagged(tilt: float, corr: int) -> bool:
    return tilt >= TILT_FLAG_DEG or corr >= CORROSION_FLAG


# ---------------------------------------------------------------------------------------------------------- distortion
DIST_FLAG = 0.45
DIST_KINDS = ("Facade bulging / wall deformation", "Footprint skew (possible settlement)", "Roof-line sagging")


def building_score(store: Store, bid: str) -> tuple[float, str]:
    """Edge-warp index 0..1 between the two (simulated) imagery epochs. Baseline noise unless a scenario injected a deformation."""
    f = store.get(S.CONFIG, f"distortion.{bid}")
    if f:
        s, _, kind = f["attrs"]["Value"].partition("|")
        return float(s), kind
    r = random.Random(f"dist:{bid}")
    return round(min(0.30, abs(r.gauss(0.10, 0.05))), 3), ""


def inject_distortion(store: Store, bid: str, score: float, kind: str) -> None:
    store.upsert(S.CONFIG, {"Config_ID": f"distortion.{bid}", "Value": f"{score:.3f}|{kind}", "Updated": utcnow()})


# --------------------------------------------------------------------------------------------------------------- land use
ZONING: dict[str, dict] = {
    "Olaya": {"zone": "Commercial & mixed-use", "allowed": ("Residential", "Commercial")},
    "KAFD": {"zone": "Financial district", "allowed": ("Commercial", "Large-scale development")},
    "Al Malaz": {"zone": "Residential", "allowed": ("Residential",)},
    "Diplomatic Quarter": {"zone": "Institutional / diplomatic", "allowed": ("Large-scale development",)},
    "King Salman Park": {"zone": "Open space / park", "allowed": ()},
    "Diriyah": {"zone": "Heritage & tourism", "allowed": ("Commercial",)},
}
SENSITIVE = {"King Salman Park": 1.0, "Diriyah": 1.0}


def classify_change(change_type: str, area_sqm: float) -> str:
    """Land-use category inferred from what the imagery shows appearing on the ground."""
    t = change_type.lower()
    if t.startswith("new construction"):
        return "Residential" if area_sqm < 4000 else "Commercial" if area_sqm < 12000 else "Large-scale development"
    if t.startswith("clearing"):
        return "Cleared land"
    return "Vegetation change"


def zoning_check(area: str, category: str) -> tuple[bool, str]:
    z = ZONING.get(area, {"zone": "Unzoned (demo)", "allowed": ()})
    if category in ("Cleared land", "Vegetation change"):
        return True, f"{category} is not a permanent use; kept on watch"
    ok = category in z["allowed"]
    return ok, (f"{category} is permitted in the {z['zone']} zone" if ok else f"{category} is NOT permitted in the {z['zone']} zone (permitted: {', '.join(z['allowed']) or 'none'})")


def violations(store: Store, area: str, seed: int) -> list[dict]:
    """Re-run the imagery comparison for `area` and return the significant construction polygons that break the zoning rules."""
    from backend.services import imagery

    res = imagery.detect_changes(store, area, seed)
    out = []
    for c in res["changes"]:
        if not c["significant"]:
            continue
        cat = classify_change(c["type"], c["area_sqm"])
        ok, why = zoning_check(area, cat)
        out.append({**c, "land_use": cat, "compliant": ok, "why": why})
    return out


def distortion_stats(store: Store, area: str) -> tuple[list[dict], float, float]:
    rows = []
    for f in store.query(S.BUILDINGS, Area_Name=area):
        s, kind = building_score(store, f["id"])
        rows.append({"id": f["id"], "name": f["attrs"]["Name"], "score": s, "kind": kind, "geom": f["geom"], "sqm": f["attrs"]["Area_Sqm"]})
    sc = [r["score"] for r in rows]
    mean = statistics.fmean(sc) if sc else 0.0
    sd = statistics.pstdev(sc) if len(sc) > 1 else 0.0
    return rows, mean, max(sd, 0.02)
