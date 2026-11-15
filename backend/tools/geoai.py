"""SEE / UNDERSTAND tools: imagery change detection, GeoAI feature extraction, spatial analysis."""
from __future__ import annotations

from backend.gis import geo
from backend.gis import schema as S
from backend.gis.store import utcnow
from backend.services import learning
from backend.services import imagery
from backend.services.synthetic import AREAS, CORRIDORS, corridor_dist_m
from backend.tools.common import ToolContext, ToolError, buildings_within, loc, severity_of

CRITICAL_FACILITIES = ('Hospital', 'School', 'Clinic', 'Metro Station')
ESCALATION_BASE = 92.0        # base score for an escalated change; stays Critical (>= 75) after the calibration multiplier


def _escalation(ctx: ToolContext, ctr, area_sqm: float) -> str:
    """Why a large new-construction candidate is Critical: it sits on a critical facility or over a water main. Empty when it does not."""
    if area_sqm >= 10000:
        near = sorted((geo.haversine_m(ctr, geo.centroid(f['geom'])), f['attrs']['Facility_Type']) for f in ctx.store.all(S.FACILITIES) if f['attrs']['Facility_Type'] in CRITICAL_FACILITIES)
        if near and near[0][0] <= 100:
            return f"possible construction {near[0][0]:.0f} m from a {near[0][1].lower()}"
    if area_sqm >= 5000:
        pipes = sum(1 for w in ctx.store.all(S.WATER) if geo.dist_geom_m(ctr, w['geom']) <= 40)
        if pipes >= 2:
            return f"possible construction over {pipes} water mains"
    return ""


def _resolve_area(area: str | None) -> str:
    if not area:
        return "Olaya"
    for k in AREAS:
        if k.lower() == area.lower() or area.lower() in k.lower():
            return k
    raise ToolError(f"unknown area '{area}'. Available: {', '.join(AREAS)}")


def detect_imagery_changes(ctx: ToolContext, area: str | None = None, k_sigma: float = 4.0, significant_area_sqm: float = 2500.0) -> dict:
    """Compare two (simulated) imagery epochs for an area and store change candidates."""
    area = _resolve_area(area)
    res = imagery.detect_changes(ctx.store, area, ctx.p.settings.seed, k_sigma=k_sigma, significant_area_sqm=significant_area_sqm)
    sig = [c["change_id"] for c in res["changes"] if c["significant"]]
    det_ids = []
    for c in res["changes"]:
        if not c["significant"]:
            continue
        f = ctx.store.get(S.CHANGES, c["change_id"])
        ctr = geo.centroid(f["geom"])
        near_pipes = sum(1 for w in ctx.store.all(S.WATER) if geo.dist_geom_m(ctr, w["geom"]) <= 250)
        base = 100 * (0.35 * c["confidence"] + 0.25 * min(1.0, c["area_sqm"] / 30000) + 0.15 * min(1.0, near_pipes / 4))
        why = _escalation(ctx, ctr, c["area_sqm"])
        if why:
            base = max(base, ESCALATION_BASE)
        risk = float(learning.apply_calibration(ctx.store, "change", base))
        existing = [d for d in ctx.store.query(S.DETECTIONS, Related_Asset_ID=c["change_id"], Category="change")]
        did = existing[0]["id"] if existing else ctx.store.next_id("DET")
        prev = existing[0]["attrs"] if existing else {}
        ctx.store.upsert(S.DETECTIONS, {"Detection_ID": did, "Detection_Type": "Urban Change (Candidate)", "Location": f"{area} - {c['change_id']}", "Confidence": c["confidence"],
                                        "Severity": severity_of(risk), "Risk_Score": risk, "Base_Risk_Score": round(base, 1), "Detection_Date": prev.get("Detection_Date", utcnow()),
                                        "Source": "Imagery change detection (simulated imagery)", "Status": prev.get("Status", "Candidate"), "Related_Asset_ID": c["change_id"], "Pipeline_ID": "",
                                        "Area_Name": area, "Category": "change", "Cluster_ID": "",
                                        "Evidence": f"CANDIDATE: {c['type'].replace(' (candidate)', '').lower()} covering about {c['area_sqm']:,.0f} m² between {res['previous_epoch'].replace(' (simulated)', '')} and {res['current_epoch'].replace(' (simulated)', '')} (simulated imagery). Not confirmed; needs field verification." + (f" CRITICAL because {why}." if why else ""),
                                        "Incident_ID": prev.get("Incident_ID", ""), "Data_Classification": S.SIMULATED}, geo.point(*ctr))
        det_ids.append(did)
        c["detection_id"] = did
    ctx.state["last_detections"] = det_ids
    ctx.state["last_changes"] = [c["change_id"] for c in res["changes"]]
    ctx.state["significant_changes"] = sig
    if sig:
        ctx.state["focus_change"] = sig[0]
    res["labels"] = ("SIMULATED imagery and processing. Detections are CANDIDATES, not confirmed construction. Vegetation-only differences are flagged "
                     "as possibly seasonal and are not counted as significant.")
    return res


def extract_geoai_features(ctx: ToolContext, change_id: str | None = None) -> dict:
    """Extract building and road features around a change polygon (simulated GeoAI on simulated imagery)."""
    cid = change_id or ctx.state.get("focus_change")
    if not cid:
        raise ToolError("no change selected; run detect_imagery_changes first or pass change_id")
    try:
        res = imagery.extract_features(ctx.store, cid, ctx.p.settings.seed)
    except ValueError as exc:
        raise ToolError(str(exc))
    ctx.state["focus_change"] = cid
    res["tot_building_area_sqm"] = sum(b["area_sqm"] for b in res["buildings"])
    res["tot_road_length_m"] = sum(r["length_m"] for r in res["roads"])
    res["labels"] = "SIMULATED extraction: threshold/morphology on simulated imagery. No deep-learning model was executed."
    return res


# ---------------------------------------------------------------------------------------------- spatial analysis
LAYER_FOR = {"detection": S.DETECTIONS, "change": S.CHANGES, "incident": S.INCIDENTS, "asset": S.INFRA, "work_order": S.WORK_ORDERS}


def spatial_analysis(ctx: ToolContext, target_type: str, target_id: str | None = None, radius_m: float = 300.0) -> dict:
    """Proximity analysis around a detection / change / incident / asset: facilities, pipes, lights, roads, other incidents, extracted features."""
    if target_type not in LAYER_FOR:
        raise ToolError(f"target_type must be one of {list(LAYER_FOR)}")
    tid = target_id or ctx.state.get({"detection": "focus_detection", "change": "focus_change", "incident": "focus_incident"}.get(target_type, ""))
    if not tid:
        raise ToolError(f"no {target_type} selected; pass target_id")
    f = ctx.store.get(LAYER_FOR[target_type], tid)
    if not f:
        raise ToolError(f"{target_type} {tid} not found")
    radius_m = max(25.0, min(float(radius_m), 5000.0))
    g = f["geom"]
    c = geo.centroid(g)
    out: dict = {"target": {"type": target_type, "id": tid, "centroid": {"lon": round(c[0], 6), "lat": round(c[1], 6)}}, "radius_m": radius_m}
    if g["type"] == "Polygon":
        ring = [tuple(p) for p in g["coordinates"][0]]
        out["target"]["area_sqm"] = round(geo.ring_area_sqm(ring))
        within = lambda geom: geo.dist_geom_m(geo.centroid(geom), g) <= radius_m  # noqa: E731
        dist = lambda geom: round(geo.dist_geom_m(geo.centroid(geom), g))  # noqa: E731
    else:
        within = lambda geom: geo.dist_geom_m(c, geom) <= radius_m  # noqa: E731
        dist = lambda geom: round(geo.dist_geom_m(c, geom))  # noqa: E731

    fac = sorted(({"name": x["attrs"]["Name"], "type": x["attrs"]["Facility_Type"], "distance_m": dist(x["geom"]), "reference": x["attrs"]["Data_Classification"]}
                  for x in ctx.store.all(S.FACILITIES) if within(x["geom"])), key=lambda r: r["distance_m"])
    pipes = sorted(({"pipeline_id": x["id"], "diameter_mm": x["attrs"]["Diameter"], "material": x["attrs"]["Material"], "distance_m": dist(x["geom"])}
                    for x in ctx.store.all(S.WATER) if within(x["geom"])), key=lambda r: r["distance_m"])
    lights = [x["id"] for x in ctx.store.all(S.INFRA) if x["attrs"]["Asset_Type"] == "Streetlight" and within(x["geom"])]
    roads = sorted({k for k in CORRIDORS if corridor_dist_m(c, k) <= radius_m + 150})
    others = [{"incident_id": x["id"], "type": x["attrs"]["Incident_Type"], "status": x["attrs"]["Status"], "priority": x["attrs"]["Priority"], "distance_m": dist(x["geom"])}
              for x in ctx.store.all(S.INCIDENTS) if x["id"] != tid and within(x["geom"]) and x["attrs"]["Status"] not in ("Resolved", "Closed - False Positive")]
    feats = [{"feature_id": x["id"], "type": x["attrs"]["Feature_Type"], "area_sqm": x["attrs"]["Area_Sqm"], "length_m": x["attrs"]["Length_M"], "distance_m": dist(x["geom"])}
             for x in ctx.store.all(S.FEATURES) if within(x["geom"])]
    out["real_buildings"] = buildings_within(ctx.store, c, radius_m)
    out.update({"facilities": fac[:10], "water_pipes": pipes[:10], "water_pipe_count": len(pipes), "streetlights_count": len(lights), "road_corridors": roads,
                "open_incidents_nearby": others[:8], "extracted_features": feats[:12],
                "potentially_affected": {"facilities": len(fac), "pipes": len(pipes), "lights": len(lights), "buildings": out["real_buildings"]["count"]},
                "note": "Buildings are REAL OpenStreetMap footprints (ODbL). Facility positions marked REFERENCE are approximate; SYNTHETIC facilities and all operational assets are demo data."})
    return out
