"""SENSE tools: sensor intelligence, water-leak detection, streetlight predictive maintenance.

All numbers come from deterministic code here; the LLM only interprets the returned structures.
"""
from __future__ import annotations

import math
import statistics
from collections import defaultdict
from functools import lru_cache

import numpy as np

from backend.gis import geo
from backend.gis import schema as S
from backend.gis.store import utcnow
from backend.services import learning
from backend.services.synthetic import CORRIDORS, corridor_dist_m
from backend.tools.common import ToolContext, ToolError, buildings_within, loc, lonlat_str, priority_of, severity_of

# --------------------------------------------------------------------------------------------- sensors


def _series(ctx: ToolContext) -> dict[str, list[dict]]:
    by: dict[str, list[dict]] = defaultdict(list)
    for f in ctx.store.all(S.SENSORS):
        by[f["attrs"]["Sensor_ID"]].append(f)
    for v in by.values():
        v.sort(key=lambda f: f["attrs"]["Timestamp"])
    return by


def _stats(rows: list[dict]) -> dict | None:
    """Compare the last 3 hourly readings to the same hours 24 h earlier (removes the diurnal cycle)."""
    p = [r["attrs"]["Pressure"] for r in rows]
    fl = [r["attrs"]["Flow"] for r in rows]
    if len(p) < 30 or p[-1] is None:
        return None
    diff = [p[i] - p[i - 24] for i in range(24, len(p) - 3)]
    sigma = max(1.4826 * statistics.median(abs(d - statistics.median(diff)) for d in diff), 0.004 * statistics.fmean(p))
    recent, ref = statistics.fmean(p[-3:]), statistics.fmean(p[-27:-24])
    f_recent, f_ref = statistics.fmean(fl[-3:]), statistics.fmean(fl[-27:-24])
    return {"pressure_recent": round(recent, 1), "pressure_reference": round(ref, 1), "drop_pct": round((ref - recent) / ref * 100, 1),
            "z": round((ref - recent) / sigma, 1), "flow_recent": round(f_recent, 1), "flow_reference": round(f_ref, 1),
            "flow_change_pct": round((f_recent - f_ref) / f_ref * 100, 1), "last_timestamp": rows[-1]["attrs"]["Timestamp"]}


def sensor_intelligence(ctx: ToolContext, sensor_id: str | None = None, area: str | None = None, anomalies_only: bool = False) -> dict:
    """Summarise current state of water pressure/flow sensors (z-score vs. same hour yesterday)."""
    series = _series(ctx)
    infra = {f["id"]: f for f in ctx.store.all(S.INFRA)}
    out = []
    for sid, rows in series.items():
        if not sid.startswith("SEN-W-") or (sensor_id and sid != sensor_id):
            continue
        a = infra[rows[-1]["attrs"]["Asset_ID"]]["attrs"]
        if area and a["Area_Name"] != area:
            continue
        st = _stats(rows)
        if not st:
            continue
        anomalous = st["drop_pct"] >= LEAK_MIN_DROP_PCT and st["z"] >= LEAK_MIN_Z
        if anomalies_only and not anomalous:
            continue
        out.append({"sensor_id": sid, "pipeline_id": a["Related_Pipeline_ID"], "area": a["Area_Name"], "anomalous": anomalous, **st})
    out.sort(key=lambda r: -r["z"])
    return {"sensors_evaluated": len(out), "anomalous": sum(1 for r in out if r["anomalous"]), "sensors": out[:15],
            "method": "last-3h mean vs the same hours 24h earlier; z uses robust MAD of historic day-over-day differences"}


# --------------------------------------------------------------------------------------------- water leaks


def _neighbours(ctx: ToolContext, pipe: dict) -> list[dict]:
    nodes = {pipe["attrs"]["From_Node"], pipe["attrs"]["To_Node"]}
    return [f for f in ctx.store.all(S.WATER) if f["id"] != pipe["id"] and nodes & {f["attrs"]["From_Node"], f["attrs"]["To_Node"]}]


LEAK_MIN_DROP_PCT, LEAK_MIN_Z = 10.0, 3.5


def _incident_open(ctx: ToolContext, incident_id: str | None) -> bool:
    inc = ctx.store.get(S.INCIDENTS, incident_id) if incident_id else None
    return bool(inc) and inc["attrs"]["Status"] not in ("Resolved", "Closed - False Positive")


def detect_water_leaks(ctx: ToolContext, area: str | None = None, min_risk: float = 0.0) -> dict:
    """Detect SUSPECTED water leaks from pressure/flow anomalies; persist detection records."""
    series = _series(ctx)
    infra = {f["id"]: f for f in ctx.store.all(S.INFRA)}
    pipes = {f["id"]: f for f in ctx.store.all(S.WATER)}
    facilities = ctx.store.all(S.FACILITIES)
    sensor_by_pipe: dict[str, str] = {}
    stats: dict[str, dict] = {}
    for sid, rows in series.items():
        if not sid.startswith("SEN-W-"):
            continue
        st = _stats(rows)
        if st:
            pid = infra[rows[-1]["attrs"]["Asset_ID"]]["attrs"]["Related_Pipeline_ID"]
            sensor_by_pipe[pid] = sid
            stats[sid] = {**st, "pipe": pid}
    if not stats:
        raise ToolError("no water pressure/flow sensor readings are loaded - reset the demo (Guided Demo > Reset, or scripts/initialize_demo.py)")
    found = []
    for sid, st in stats.items():
        pipe = pipes[st["pipe"]]
        if area and pipe["attrs"]["Area_Name"] != area:
            continue
        if not (st["drop_pct"] >= LEAK_MIN_DROP_PCT and st["z"] >= LEAK_MIN_Z):
            continue
        # corroboration from sensors on adjacent pipes
        corr, pts, wts = [], [loc(infra[series[sid][-1]["attrs"]["Asset_ID"]]["geom"])], [max(st["drop_pct"], 1)]
        for nb in _neighbours(ctx, pipe):
            nsid = sensor_by_pipe.get(nb["id"])
            if nsid and stats[nsid]["drop_pct"] >= 3.0:
                corr.append({"sensor_id": nsid, "pipeline_id": nb["id"], "drop_pct": stats[nsid]["drop_pct"]})
                pts.append(geo.centroid(nb["geom"]))
                wts.append(stats[nsid]["drop_pct"])
        cx = sum(p[0] * w for p, w in zip(pts, wts)) / sum(wts)
        cy = sum(p[1] * w for p, w in zip(pts, wts)) / sum(wts)
        line = [tuple(c) for c in pipe["geom"]["coordinates"]]
        _, q = geo.dist_to_line((cx, cy), line)
        seg_len = pipe["attrs"]["Length_M"]
        radius = round(max(30.0, 0.5 * seg_len / (1 + len(corr))))
        # impact context
        near_fac = [(f["attrs"]["Name"], f["attrs"]["Facility_Type"], round(geo.haversine_m(q, geo.centroid(f["geom"])))) for f in facilities
                    if geo.haversine_m(q, geo.centroid(f["geom"])) <= 500]
        near_fac.sort(key=lambda x: x[2])
        roads = sorted({c for c in CORRIDORS if corridor_dist_m(q, c) <= 400})
        bld = buildings_within(ctx.store, q, 150)
        lights_near = sum(1 for f in infra.values() if f["attrs"]["Asset_Type"] == "Streetlight" and geo.haversine_m(q, geo.centroid(f["geom"])) <= 150)
        z_n, d_n = min(1, st["z"] / 8), min(1, st["drop_pct"] / 35)
        f_n, dia_n = min(1, max(0, st["flow_change_pct"]) / 50), min(1, pipe["attrs"]["Diameter"] / 900)
        fac_n, c_n = min(1, len([x for x in near_fac if x[1] != "Mosque"]) / 3), min(1, len(corr) / 2)
        base = 100 * (0.30 * z_n + 0.20 * d_n + 0.15 * f_n + 0.10 * dia_n + 0.15 * fac_n + 0.10 * c_n)
        risk = learning.apply_calibration(ctx.store, "water", base)
        if risk < min_risk:
            continue
        conf = round(min(0.97, 0.40 + 0.35 * z_n + 0.15 * (1 if st["flow_change_pct"] > 10 else 0) + 0.10 * c_n), 2)
        sev = severity_of(risk)
        affected = round(math.pi * (40 + 2.5 * st["drop_pct"]) ** 2)
        evidence = (f"SUSPECTED leak (not confirmed). Pressure on {sid} fell {st['drop_pct']}% vs the same hours yesterday "
                    f"({st['pressure_reference']}->{st['pressure_recent']} kPa, z={st['z']}); flow changed {st['flow_change_pct']:+}%. "
                    f"{len(corr)} adjacent sensor(s) show a milder drop. Pattern is consistent with a leak but also with valve operation or a pump transient; "
                    f"field verification is required before treating it as a confirmed leak.")
        # persist (one open detection per pipeline)
        on_pipe = ctx.store.query(S.DETECTIONS, Pipeline_ID=pipe["id"], Category="water")
        if any(f["attrs"]["Status"] in ("Verified-True", "Verified-False") and _incident_open(ctx, f["attrs"].get("Incident_ID")) for f in on_pipe):
            continue                    # the field has already been to this pipe and its incident is still being handled: not a new finding
        existing = [f for f in on_pipe if f["attrs"]["Status"] == "Suspected"]
        did = existing[0]["id"] if existing else ctx.store.next_id("DET")
        prev = existing[0]["attrs"] if existing else {}
        rec = {"Detection_ID": did, "Detection_Type": "Water Leak (Suspected)", "Location": f"{pipe['attrs']['Area_Name']} - {lonlat_str(q)}", "Confidence": conf,
               "Severity": sev, "Risk_Score": risk, "Base_Risk_Score": round(base, 1), "Detection_Date": prev.get("Detection_Date", utcnow()),
               "Source": f"Sensor Intelligence ({sid})", "Status": "Suspected", "Related_Asset_ID": sid, "Pipeline_ID": pipe["id"],
               "Area_Name": pipe["attrs"]["Area_Name"], "Category": "water", "Cluster_ID": "", "Evidence": evidence,
               "Incident_ID": prev.get("Incident_ID", ""), "Data_Classification": S.SIMULATED}
        ctx.store.upsert(S.DETECTIONS, rec, geo.point(*q))
        for r in series[sid][-3:]:
            ctx.store.update(S.SENSORS, r["id"], Anomaly_Flag="Yes")
        found.append({"detection_id": did, "status": "Suspected (not confirmed)", "pipeline_id": pipe["id"], "sensor_id": sid, "area": pipe["attrs"]["Area_Name"],
                      "probable_location": {"lon": round(q[0], 6), "lat": round(q[1], 6), "uncertainty_radius_m": radius},
                      "risk_score": risk, "severity": sev, "confidence": conf, "pressure_drop_pct": st["drop_pct"], "z_score": st["z"],
                      "flow_change_pct": st["flow_change_pct"], "corroborating_sensors": corr, "pipe_diameter_mm": pipe["attrs"]["Diameter"],
                      "estimated_affected_area_sqm": affected, "estimated_affected_area_note": "heuristic radius 40 m + 2.5 m per % pressure drop; not hydraulic modelling",
                      "nearby_facilities_500m": [{"name": n, "type": t, "distance_m": d} for n, t, d in near_fac[:6]],
                      "roads_within_400m": roads, "streetlights_within_150m": lights_near, "buildings_within_150m": bld, "why_suspicious": evidence})
    found.sort(key=lambda r: -r["risk_score"])
    ctx.state["last_detections"] = [f["detection_id"] for f in found]
    if found:
        ctx.state["focus_detection"] = found[0]["detection_id"]
    out = {"sensors_evaluated": len(stats), "suspected_leaks": len(found), "detections": found, "scope": area or "all areas",
           "rule": {"min_pressure_drop_pct": LEAK_MIN_DROP_PCT, "min_z_score": LEAK_MIN_Z, "compares": "mean of the last 3 hourly readings vs the same hours 24 h earlier"},
           "caveat": "All items are SUSPECTED leaks derived from simulated sensor data; none are confirmed until field verification."}
    if min_risk:
        out["min_risk_note"] = f"min_risk={min_risk} only hides detections whose risk score is lower; it does not change what counts as an anomaly."
    if not found:
        scoped = [(sid, st) for sid, st in stats.items() if not area or pipes[st["pipe"]]["attrs"]["Area_Name"] == area]
        scoped.sort(key=lambda kv: -kv[1]["z"])
        out["no_detection_reason"] = (f"No sensor meets the anomaly rule (pressure at least {LEAK_MIN_DROP_PCT:g}% below the same hours yesterday AND z-score at least {LEAK_MIN_Z}). "
                                      "Lowering the risk threshold cannot change this: min_risk only filters detections after the rule has fired.")
        out["closest_candidates"] = [{"sensor_id": sid, "pipeline_id": st["pipe"], "area": pipes[st["pipe"]]["attrs"]["Area_Name"], "pressure_drop_pct": st["drop_pct"],
                                      "z_score": st["z"], "flow_change_pct": st["flow_change_pct"], "meets_rule": False} for sid, st in scoped[:3]]
        out["how_to_see_a_detection"] = ("This is demo data: leaks appear when a scenario is injected (Command Center > Simulation engine > Olaya leak, or Guided Demo scene 1) "
                                         "or when the simulation runs with an anomaly rate. The agent cannot inject scenarios itself.")
    return out


# --------------------------------------------------------------------------------------------- streetlights


@lru_cache(maxsize=1)
def _model():
    from sklearn.ensemble import IsolationForest
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler

    rng = np.random.default_rng(7)
    n = 900

    def draw(kind, k):
        if kind == "fail":
            tr = rng.choice([1, -1], k) * rng.normal(11, 3, k)
            return np.c_[np.abs(tr), rng.integers(6, 15, k), np.abs(rng.normal(14, 5, k)), rng.integers(1, 5, k), rng.uniform(.8, 2.5, k), rng.uniform(6, 12, k)]
        if kind == "decoy":
            return np.c_[np.abs(rng.normal(5.5, 1.5, k)), rng.integers(3, 7, k), np.abs(rng.normal(7, 2, k)), rng.integers(0, 3, k), rng.uniform(.4, 1.4, k), rng.uniform(4, 9, k)]
        return np.c_[np.abs(rng.normal(0, 1.6, k)), rng.integers(0, 3, k), np.abs(rng.normal(1, 1, k)), rng.integers(0, 2, k), rng.uniform(.05, 1.8, k), rng.uniform(.5, 11, k)]

    X = np.vstack([draw("fail", int(n * .22)), draw("decoy", int(n * .10)), draw("ok", n - int(n * .22) - int(n * .10))])
    y = np.r_[np.ones(int(n * .22)), np.zeros(n - int(n * .22))]
    sc = StandardScaler().fit(X)
    lr = LogisticRegression(max_iter=500, C=0.5).fit(sc.transform(X), y)
    return sc, lr


def _features(t: dict) -> list[float]:
    return [abs(t["Power_Trend_Pct"]), t["Flicker_30d"], t["Comm_Loss_Pct"], t["Faults_12m"], t["Days_Since_Maintenance"] / 365, t["Age_Years"]]


def predict_streetlight_failures(ctx: ToolContext, area: str | None = None, corridor: str | None = None, min_probability: float | None = None) -> dict:
    """PREDICT (not confirm) streetlight failures: logistic model + isolation-forest anomaly score; cluster high-risk lights."""
    from sklearn.cluster import DBSCAN
    from sklearn.ensemble import IsolationForest

    sc, lr = _model()
    thr = min_probability if min_probability is not None else learning.get_cfg(ctx.store, "streetlight.detect_threshold", 0.55)
    tel = {f["id"]: f["attrs"] for f in ctx.store.all(S.TELEMETRY)}
    assets = {f["id"]: f for f in ctx.store.all(S.INFRA) if f["attrs"]["Asset_Type"] == "Streetlight"}
    ids = [i for i in assets if i in tel]
    if not ids:
        raise ToolError("no streetlight assets/telemetry are loaded - reset the demo (Guided Demo > Reset, or scripts/initialize_demo.py)")
    X = np.array([_features(tel[i]) for i in ids])
    p_lr = lr.predict_proba(sc.transform(X))[:, 1]
    iso = IsolationForest(n_estimators=200, random_state=11, contamination="auto").fit(sc.transform(X))
    raw = -iso.score_samples(sc.transform(X))
    iso_pct = (raw.argsort().argsort()) / max(1, len(raw) - 1)
    prob = 0.8 * p_lr + 0.2 * iso_pct
    facilities = [geo.centroid(f["geom"]) for f in ctx.store.all(S.FACILITIES) if f["attrs"]["Facility_Type"] in ("Hospital", "School", "Clinic", "Metro Station")]
    rows = []
    for i, pr, pl in zip(ids, prob, p_lr):
        a = assets[i]["attrs"]
        if (area and a["Area_Name"] != area) or (corridor and a["Corridor"].lower() != corridor.lower()):
            continue
        p = loc(assets[i]["geom"])
        nf = sum(1 for f in facilities if geo.haversine_m(p, f) <= 250)
        crit = {"High": 1.0, "Medium": 0.6, "Low": 0.3}[a["Asset_Criticality"]]
        expo = 1.0 if CORRIDORS[a["Corridor"]]["class"] == "arterial" else 0.6
        base = 100 * (0.50 * pr + 0.20 * crit + 0.15 * min(1, nf / 2) + 0.15 * expo)
        rows.append({"asset_id": i, "p": float(pr), "p_model": float(pl), "pt": p, "area": a["Area_Name"], "corridor": a["Corridor"], "crit": a["Asset_Criticality"],
                     "facilities_250m": nf, "base": base, "tel": tel[i]})
    flagged = [r for r in rows if r["p"] >= thr]
    flagged.sort(key=lambda r: -r["p"])
    # clusters (DBSCAN on local metres)
    clusters = []
    if len(flagged) >= 3:
        lat0 = flagged[0]["pt"][1]
        xy = np.array([geo.to_xy(r["pt"], lat0) for r in flagged])
        lab = DBSCAN(eps=450, min_samples=3).fit_predict(xy)
        for k in sorted(set(lab) - {-1}):
            m = [r for r, l in zip(flagged, lab) if l == k]
            cen = (sum(r["pt"][0] for r in m) / len(m), sum(r["pt"][1] for r in m) / len(m))
            corr = max(set(r["corridor"] for r in m), key=[r["corridor"] for r in m].count)
            cid = f"CLU-{''.join(w[0] for w in corr.split())}-{k + 1:03d}"
            for r, l in zip(flagged, lab):
                if l == k:
                    r["cluster"] = cid
            clusters.append({"cluster_id": cid, "corridor": corr, "area": m[0]["area"], "lights": len(m), "mean_probability": round(float(np.mean([r["p"] for r in m])), 2),
                             "centroid": {"lon": round(cen[0], 6), "lat": round(cen[1], 6)}, "asset_ids": [r["asset_id"] for r in m],
                             "max_priority_score": round(float(max(learning.apply_calibration(ctx.store, "lighting", r["base"]) for r in m)), 1)})
    dets = []
    for r in flagged:
        risk = float(learning.apply_calibration(ctx.store, "lighting", r["base"]))
        t = r["tel"]
        ev = (f"PREDICTED failure (not a confirmed fault): estimated probability {r['p']:.0%}. Drivers: power drift {t['Power_Trend_Pct']:+}%, {t['Flicker_30d']} flicker events/30d, "
              f"{t['Comm_Loss_Pct']}% comms loss, {t['Faults_12m']} fault(s) in 12 months, {t['Days_Since_Maintenance']} days since maintenance. Preventive inspection recommended.")
        existing = [f for f in ctx.store.query(S.DETECTIONS, Related_Asset_ID=r["asset_id"], Category="lighting") if f["attrs"]["Status"] == "Predicted"]
        did = existing[0]["id"] if existing else ctx.store.next_id("DET")
        prev = existing[0]["attrs"] if existing else {}
        ctx.store.upsert(S.DETECTIONS, {"Detection_ID": did, "Detection_Type": "Streetlight Failure (Predicted)", "Location": f"{r['corridor']}, {r['area']}",
                                        "Confidence": round(r["p"], 2), "Severity": severity_of(risk), "Risk_Score": risk, "Base_Risk_Score": round(r["base"], 1),
                                        "Detection_Date": prev.get("Detection_Date", utcnow()), "Source": "Streetlight predictive model (LR + IsolationForest)", "Status": "Predicted",
                                        "Related_Asset_ID": r["asset_id"], "Pipeline_ID": "", "Area_Name": r["area"], "Category": "lighting", "Cluster_ID": r.get("cluster", ""),
                                        "Evidence": ev, "Incident_ID": prev.get("Incident_ID", ""), "Data_Classification": S.SIMULATED}, geo.point(*r["pt"]))
        dets.append({"detection_id": did, "asset_id": r["asset_id"], "probability": round(r["p"], 2), "risk_score": risk, "severity": severity_of(risk), "corridor": r["corridor"],
                     "area": r["area"], "cluster_id": r.get("cluster", ""), "criticality": r["crit"], "facilities_within_250m": r["facilities_250m"], "status": "Predicted (not confirmed)",
                     "drivers": {"power_trend_pct": t["Power_Trend_Pct"], "flicker_30d": t["Flicker_30d"], "comm_loss_pct": t["Comm_Loss_Pct"], "faults_12m": t["Faults_12m"]}})
    ctx.state["last_detections"] = [d["detection_id"] for d in dets]
    ctx.state["last_clusters"] = [c["cluster_id"] for c in clusters]
    if dets:
        ctx.state["focus_detection"] = dets[0]["detection_id"]
    return {"lights_evaluated": len(rows), "predicted_failures": len(dets), "threshold": thr, "clusters": clusters, "detections": dets[:25],
            "model": "synthetic-trained logistic regression (80%) + IsolationForest anomaly percentile (20%); retraining is a separate offline process",
            "caveat": "These are PREDICTED failures from simulated telemetry, not confirmed faults."}
