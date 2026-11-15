"""City-management detection tools: streetlight pole monitoring, visual distortion detection and land-use compliance.

All three create DETECTIONS (never incidents or actions) so they flow through the same triage -> approval -> field -> verify loop as water and lamps.
"""
from __future__ import annotations

from backend.gis import geo
from backend.gis import schema as S
from backend.gis.store import utcnow
from backend.services import cityops, imagery, visual_types
from backend.services.synthetic import AREAS, CORRIDORS
from backend.tools.common import ToolContext, ToolError, severity_of
from backend.tools.geoai import CRITICAL_FACILITIES, _resolve_area


def _upsert_detection(ctx: ToolContext, category: str, asset_id: str, attrs: dict, point: tuple[float, float]) -> str:
    st = ctx.store
    existing = [d for d in st.query(S.DETECTIONS, Related_Asset_ID=asset_id, Category=category)]
    did = existing[0]["id"] if existing else st.next_id("DET")
    prev = existing[0]["attrs"] if existing else {}
    status = attrs.pop("Status")
    base = {"Pipeline_ID": "", "Cluster_ID": "", **attrs, "Detection_ID": did, "Detection_Date": prev.get("Detection_Date", utcnow()), "Status": prev.get("Status", status),
            "Incident_ID": prev.get("Incident_ID", ""), "Related_Asset_ID": asset_id, "Category": category}
    st.upsert(S.DETECTIONS, base, geo.point(*point))
    return did


def _nearest_facility(ctx: ToolContext, p, kinds=CRITICAL_FACILITIES, radius: float = 150.0):
    best = None
    for f in ctx.store.all(S.FACILITIES):
        if f["attrs"]["Facility_Type"] in kinds:
            d = geo.haversine_m(p, geo.centroid(f["geom"]))
            if d <= radius and (best is None or d < best[0]):
                best = (d, f["attrs"]["Name"] or f["attrs"]["Facility_Type"], f["attrs"]["Facility_Type"])
    return best


def _merge_pole_into_streetlight(ctx: ToolContext, asset_id: str, risk: float, text: str, new_attrs: dict, point) -> str:
    """Streetlights and poles are ONE use case: a pole finding is added to the lamp's own detection when one exists, else it opens a streetlight detection."""
    st = ctx.store
    existing = st.query(S.DETECTIONS, Related_Asset_ID=asset_id, Category="lighting")
    if existing:
        d = existing[0]
        a = d["attrs"]
        if "POLE:" not in a["Evidence"]:
            st.update(S.DETECTIONS, d["id"], Evidence=f"{a['Evidence']} | {text}"[:900])
        if risk > a["Risk_Score"]:
            st.update(S.DETECTIONS, d["id"], Risk_Score=risk, Severity=severity_of(risk))
        return d["id"]
    return _upsert_detection(ctx, "lighting", asset_id, {**new_attrs, "Severity": severity_of(risk), "Risk_Score": risk, "Base_Risk_Score": risk, "Status": "Predicted", "Evidence": text}, point)


# ------------------------------------------------------------------------------------------------------------- poles
def monitor_poles(ctx: ToolContext, area: str | None = None, corridor: str | None = None) -> dict:
    """SENSE. Monitor streetlight POLE structural health (tilt, corrosion, age) and flag poles that exceed the safety limits."""
    if corridor:
        key = next((k for k in CORRIDORS if k.lower() == corridor.lower() or corridor.lower() in k.lower()), None)
        if not key:
            raise ToolError(f"unknown corridor '{corridor}'. Available: {', '.join(CORRIDORS)}")
        corridor = key
    area = _resolve_area(area) if area else None
    tel = {f["id"]: f["attrs"] for f in ctx.store.all(S.TELEMETRY)}
    poles = [f for f in ctx.store.all(S.INFRA) if f["attrs"]["Asset_Type"] == "Streetlight"
             and (not area or f["attrs"]["Area_Name"] == area) and (not corridor or f["attrs"]["Corridor"] == corridor)]
    flagged = []
    for f in poles:
        t = tel.get(f["id"], {})
        tilt, corr = cityops.pole_state(f["id"], t)
        if cityops.pole_flagged(tilt, corr):
            risk = cityops.pole_risk(tilt, corr, t.get("Age_Years") or 0)
            flagged.append((f, tilt, corr, risk, t))
    by_corridor: dict[str, int] = {}
    for f, *_ in flagged:
        by_corridor[f["attrs"]["Corridor"]] = by_corridor.get(f["attrs"]["Corridor"], 0) + 1
    dets = []
    for f, tilt, corr, risk, t in flagged:
        a = f["attrs"]
        cor = a["Corridor"] or a["Area_Name"]
        cluster = f"POLE-{cor.replace(' ', '-')}" if by_corridor.get(a["Corridor"], 0) >= 2 else ""
        ctr = geo.centroid(f["geom"])
        why = []
        if tilt >= cityops.TILT_FLAG_DEG:
            why.append(f"tilt {tilt:.1f}° (limit {cityops.TILT_FLAG_DEG:.0f}°)")
        if corr >= cityops.CORROSION_FLAG:
            why.append(f"{cityops.CORROSION[corr].lower()} base corrosion")
        text = (f"POLE: {', '.join(why)}, age {t.get('Age_Years', 0):.1f} y. PREDICTED structural risk (not a confirmed failure); "
                "the pole could fall onto the carriageway if not inspected.")
        did = _merge_pole_into_streetlight(ctx, f["id"], risk, text, {
            "Detection_Type": "Streetlight Pole Risk (Predicted)", "Location": cor, "Confidence": round(min(0.97, 0.55 + risk / 200), 2),
            "Source": "Pole telemetry / inclinometer (simulated)", "Area_Name": a["Area_Name"], "Cluster_ID": cluster, "Data_Classification": S.SIMULATED}, ctr)
        dets.append({"detection_id": did, "asset_id": f["id"], "corridor": cor, "area": a["Area_Name"], "tilt_deg": tilt, "corrosion": cityops.CORROSION[corr],
                     "risk_score": risk, "severity": severity_of(risk), "cluster_id": cluster, "lon": ctr[0], "lat": ctr[1]})
    dets.sort(key=lambda d: -d["risk_score"])
    ctx.state["last_detections"] = [d["detection_id"] for d in dets]
    if dets:
        ctx.state["focus_detection"] = dets[0]["detection_id"]
    return {"scope": corridor or area or "all corridors", "poles_evaluated": len(poles), "flagged": len(dets), "detections": dets,
            "limits": {"tilt_deg": cityops.TILT_FLAG_DEG, "corrosion": cityops.CORROSION[cityops.CORROSION_FLAG] + " or worse"},
            "caveat": "SIMULATED pole telemetry. Detections are PREDICTIONS for field inspection, not confirmed failures."}


# ----------------------------------------------------------------------------------------------------------- distortion
def detect_visual_distortion(ctx: ToolContext, area: str | None = None) -> dict:
    """SEE. Compare two imagery epochs and flag visual distortion: street-level problems (construction waste, abandoned vehicles, illegal graffiti, non-compliant billboards,
    unlicensed canopies and hangars, unregulated street vendors, neglected vacant land, exposed wiring) and structural shape changes (facade bulging, footprint skew, sagging)."""
    area = _resolve_area(area)
    rows, mean, sd = cityops.distortion_stats(ctx.store, area)
    dets = []
    for r in rows:
        if r["score"] < cityops.DIST_FLAG:
            continue
        ctr = geo.centroid(r["geom"])
        z = (r["score"] - mean) / sd
        fac = _nearest_facility(ctx, ctr)
        base = round(100 * (0.75 * r["score"] + 0.25 * (1.0 if fac else 0.0)), 1)
        near = f" It stands {fac[0]:.0f} m from a {fac[2].lower()} ({fac[1]})." if fac else ""
        vt = visual_types.by_key(r["kind"])                      # one of the eight visual-distortion kinds, or an older structural kind
        if vt:
            evidence = (f"CANDIDATE (SIMULATED imagery, {imagery.EPOCH_A} -> {imagery.EPOCH_B}): {vt['name']} - {vt['what']}; visual-distortion score {r['score']:.2f} "
                        f"vs area norm {mean:.2f}±{sd:.2f} (z={z:.1f}).{near} Needs a field inspection and, if confirmed, a notice to the owner.")
        else:
            evidence = (f"CANDIDATE (SIMULATED imagery, {imagery.EPOCH_A} -> {imagery.EPOCH_B}): {r['kind'] or 'structural deformation'}; edge-warp index {r['score']:.2f} "
                        f"vs area norm {mean:.2f}±{sd:.2f} (z={z:.1f}).{near} Needs a structural survey.")
        did = _upsert_detection(ctx, "distortion", r["id"], {
            "Detection_Type": f"{vt['name']} (Candidate)" if vt else "Visual Distortion (Candidate)", "Location": f"{area} - {r['name'] or 'building'}", "Confidence": round(min(0.97, 0.5 + r["score"] / 2), 2),
            "Severity": severity_of(base), "Risk_Score": base, "Base_Risk_Score": base, "Source": "Imagery epoch comparison (simulated imagery)", "Status": "Candidate",
            "Area_Name": area, "Distortion_Score": r["score"],
            "Evidence": evidence, "Data_Classification": S.SIMULATED}, ctr)
        dets.append({"detection_id": did, "building_id": r["id"], "name": r["name"] or "building", "kind": vt["name"] if vt else (r["kind"] or "structural deformation"), "visual_type": r["kind"] if vt else "", "edge_warp_index": r["score"],
                     "z_score": round(z, 1), "risk_score": base, "severity": severity_of(base), "near_facility": fac[1] if fac else "", "lon": ctr[0], "lat": ctr[1],
                     "ring": r["geom"]["coordinates"][0] if r["geom"]["type"] == "Polygon" else None})
    dets.sort(key=lambda d: -d["risk_score"])
    ctx.state["last_detections"] = [d["detection_id"] for d in dets]
    if dets:
        ctx.state["focus_detection"] = dets[0]["detection_id"]
    return {"area": area, "buildings_evaluated": len(rows), "area_norm": {"mean": round(mean, 3), "std": round(sd, 3)}, "flagged": len(dets), "detections": dets,
            "previous_epoch": imagery.EPOCH_A, "current_epoch": imagery.EPOCH_B,
            "caveat": "SIMULATED imagery and processing. Distortion is a CANDIDATE finding that needs a structural survey; it is not a structural verdict."}


# ---------------------------------------------------------------------------------------------------------- land use
def analyze_land_use(ctx: ToolContext, area: str | None = None) -> dict:
    """UNDERSTAND. Classify what is appearing on the ground from the imagery change polygons and check it against the area's zoning; flag violations."""
    area = _resolve_area(area)
    z = cityops.ZONING.get(area, {"zone": "Unzoned (demo)", "allowed": ()})
    items = cityops.violations(ctx.store, area, ctx.p.settings.seed)
    mix: dict[str, float] = {}
    for it in items:
        mix[it["land_use"]] = mix.get(it["land_use"], 0.0) + it["area_sqm"]
    dets, ok = [], []
    for it in items:
        if it["compliant"]:
            ok.append({"change_id": it["change_id"], "land_use": it["land_use"], "area_sqm": it["area_sqm"]})
            continue
        f = ctx.store.get(S.CHANGES, it["change_id"])
        ctr = geo.centroid(f["geom"])
        sens = cityops.SENSITIVE.get(area, 0.5)
        base = round(100 * (0.4 * it["confidence"] + 0.3 * min(1.0, it["area_sqm"] / 20000) + 0.3 * sens), 1)
        did = _upsert_detection(ctx, "land_use", it["change_id"], {
            "Detection_Type": "Land-Use Violation (Candidate)", "Location": f"{area} - {it['change_id']}", "Confidence": it["confidence"], "Severity": severity_of(base),
            "Risk_Score": base, "Base_Risk_Score": base, "Source": "Imagery change + zoning check (simulated imagery)", "Status": "Candidate", "Area_Name": area,
            "Land_Use_Category": it["land_use"],
            "Evidence": f"CANDIDATE: {it['land_use'].lower()} of about {it['area_sqm']:,.0f} m² appeared between the two satellite dates. {it['why']}. Needs a site inspection before enforcement.",
            "Data_Classification": S.SIMULATED}, ctr)
        dets.append({"detection_id": did, "change_id": it["change_id"], "land_use": it["land_use"], "area_sqm": it["area_sqm"], "risk_score": base, "severity": severity_of(base),
                     "why": it["why"], "lon": ctr[0], "lat": ctr[1], "ring": f["geom"]["coordinates"][0]})
    dets.sort(key=lambda d: -d["risk_score"])
    ctx.state["last_detections"] = [d["detection_id"] for d in dets]
    if dets:
        ctx.state["focus_detection"] = dets[0]["detection_id"]
    return {"area": area, "zone": z["zone"], "permitted_uses": list(z["allowed"]), "significant_changes": len(items), "compliant": ok, "violations": len(dets), "detections": dets,
            "land_use_mix_sqm": {k: round(v) for k, v in mix.items()},
            "caveat": "SIMULATED imagery and zoning reference. Violations are CANDIDATES for site inspection, not enforcement decisions."}
