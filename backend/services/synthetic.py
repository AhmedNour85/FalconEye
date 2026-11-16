"""Reproducible synthetic data generator for the Riyadh demonstration environment.

Real vs synthetic (see docs/data_dictionary.md):
  * Area centres, road corridors and landmark facilities are APPROXIMATE reference geography
    (hand-placed from public map knowledge; Data_Classification = REFERENCE-APPROXIMATE).
    They are NOT surveyed data. Replace with OSM/Living Atlas extracts for production (see scripts/fetch_osm_roads.py).
  * Water pipes, sensors, streetlights, telemetry, workers, history are SYNTHETIC (SYNTHETIC-DEMO) and do not
    represent any real government asset.
"""
from __future__ import annotations

import math
import random
from datetime import datetime, timedelta, timezone

from backend.gis import geo
from backend.gis import schema as S
from backend.gis.store import Store
from backend.services import osm

AREAS: dict[str, dict] = {
    "Olaya": {"code": "OLY", "center": (46.6850, 24.6935)},
    "KAFD": {"code": "KAF", "center": (46.6430, 24.7640)},
    "Al Malaz": {"code": "MLZ", "center": (46.7330, 24.6650)},
    "Diplomatic Quarter": {"code": "DQ", "center": (46.6200, 24.6850)},
    "King Salman Park": {"code": "KSP", "center": (46.7200, 24.7350)},
    "Diriyah": {"code": "DIR", "center": (46.5750, 24.7340)},
}

# Road corridors. When the real OSM extract is present (scripts/fetch_osm_riyadh.py) the geometry is the REAL way geometry; otherwise the
# approximate hand-placed centreline in "line" is used. "area" corridors are the real primary/secondary/tertiary roads of that demo area.
CORRIDORS: dict[str, dict] = {
    "King Fahd Road": {"n": 90, "class": "arterial", "osm": "King Fahd Road",
                       "line": [(46.6900, 24.6200), (46.6820, 24.6600), (46.6740, 24.6900), (46.6680, 24.7200), (46.6600, 24.7500), (46.6540, 24.7800)]},
    "Olaya Street": {"n": 45, "class": "arterial", "osm": "Olaya Street", "line": [(46.7030, 24.6400), (46.6900, 24.6900), (46.6830, 24.7400)]},
    "Al Malaz main roads": {"n": 30, "class": "collector", "area": "Al Malaz", "line": [(46.7150, 24.6550), (46.7450, 24.6680)]},
    "KAFD main roads": {"n": 25, "class": "collector", "area": "KAFD",
                        "line": [(46.6380, 24.7600), (46.6480, 24.7600), (46.6480, 24.7680), (46.6380, 24.7680), (46.6380, 24.7600)]},
}


def corridor_lines(name: str) -> list[list[tuple]]:
    """Real OSM geometry for the corridor if available, else the approximate fallback line."""
    c = CORRIDORS[name]
    real: list = []
    if osm.available():
        real = osm.corridor_lines(c["osm"]) if "osm" in c else osm.area_main_lines(AREAS[c["area"]]["center"], 900) if "area" in c else []
    return real or [[tuple(p) for p in c["line"]]]


def corridor_dist_m(p, name: str) -> float:
    return min(geo.dist_to_line(p, ln)[0] for ln in corridor_lines(name))


def uses_real_osm() -> bool:
    return osm.available()


def data_version() -> str:
    """Marker stored when generation finishes; a different value at startup triggers regeneration (e.g. OSM extract added)."""
    return "osm-v3" if osm.available() else "grid-v3"


# Approximate landmark locations (reference geography, +/- a few hundred metres).
LANDMARKS = [
    ("Kingdom Centre Tower", "Landmark", (46.6745, 24.7113), "Olaya"),
    ("Al Faisaliah Tower", "Landmark", (46.6855, 24.6900), "Olaya"),
    ("KAFD Metro Station", "Metro Station", (46.6420, 24.7650), "KAFD"),
    ("King Abdullah Financial District", "Landmark", (46.6430, 24.7640), "KAFD"),
    ("King Salman Park (main entrance)", "Park", (46.7200, 24.7350), "King Salman Park"),
    ("Diplomatic Quarter (centre)", "District Centre", (46.6200, 24.6850), "Diplomatic Quarter"),
    ("At-Turaif (Diriyah)", "Heritage Site", (46.5740, 24.7340), "Diriyah"),
    ("National Museum area", "Museum", (46.7100, 24.6480), "Al Malaz"),
]
FACILITY_TYPES = [("Hospital", 1), ("School", 3), ("Clinic", 2), ("Mosque", 3), ("Metro Station", 1)]

MATERIALS = ["Ductile Iron", "HDPE", "Steel", "PVC", "Cast Iron"]
TEAMS = ["Water Rapid Response", "Electrical Maintenance", "Survey & Inspection"]


def nearest_area(p) -> str:
    """The demo area whose centre is closest. Every asset belongs to one of the six areas."""
    return min(AREAS, key=lambda n: geo.haversine_m(p, AREAS[n]["center"]))


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def generate(store: Store, seed: int = 20260101, now: datetime | None = None, with_history: bool = True) -> dict:
    """Wipe and regenerate the whole environment in one transaction. Returns counts per layer."""
    with store.batch():
        return _generate(store, seed, now, with_history)


def _generate(store: Store, seed: int, now: datetime | None, with_history: bool) -> dict:
    rng = random.Random(seed)
    now = now or datetime.now(timezone.utc).replace(microsecond=0)
    store.clear()
    SYN = S.SYNTHETIC

    osm_on = osm.available()

    # -- REAL building footprints (reference layer, OSM) --------------------------------------------------------------
    area_buildings: dict[str, list] = {}
    if osm_on:
        for area, a_ in AREAS.items():
            bl = sorted(osm.buildings_near(a_["center"], 650), key=lambda b_: geo.haversine_m(a_["center"], b_["centroid"]))[:2200]
            area_buildings[area] = bl
            for b_ in bl:
                store.upsert(S.BUILDINGS, {"Building_ID": f"OSM-B{b_['id']}", "Name": b_["name"], "Building_Type": b_["type"], "Area_Name": area,
                                           "Area_Sqm": round(b_["area"]), "Data_Classification": S.OSM_REAL}, geo.polygon(b_["ring"]))

    def snap_building(p, r=160.0):
        c = [b_ for b_ in osm.buildings_near(p, r) if b_["area"] >= 150] if osm_on else []
        return min((b_["centroid"] for b_ in c), key=lambda q: geo.haversine_m(p, q)) if c else p

    # -- facilities ----------------------------------------------------------------
    for i, (name, ftype, p, area) in enumerate(LANDMARKS, 1):
        store.upsert(S.FACILITIES, {"Facility_ID": f"FAC-R{i:03d}", "Name": name, "Facility_Type": ftype, "Area_Name": area,
                                    "Data_Classification": S.REFERENCE}, geo.point(*snap_building(p)))
    k = 0
    for area, a in AREAS.items():
        big = [b_ for b_ in area_buildings.get(area, []) if b_["area"] >= 300]
        for ftype, cnt in FACILITY_TYPES:
            for _ in range(cnt if rng.random() < 0.8 else 0):
                k += 1
                p = rng.choice(big)["centroid"] if big else geo.offset(a["center"], rng.uniform(-700, 700), rng.uniform(-700, 700))
                store.upsert(S.FACILITIES, {"Facility_ID": f"FAC-S{k:03d}", "Name": f"Synthetic {ftype} {k}", "Facility_Type": ftype,
                                            "Area_Name": area, "Data_Classification": SYN}, geo.point(*p))
    facilities = store.all(S.FACILITIES)

    def fac_near(p, r):
        return sum(1 for f in facilities if geo.haversine_m(p, geo.centroid(f["geom"])) <= r and f["attrs"]["Facility_Type"] in ("Hospital", "School", "Clinic", "Metro Station"))

    # -- water network: pipes follow REAL street centrelines (connected via shared OSM junction nodes) -----------------
    pipes = []  # (pipeline_id, area, coords, diameter, from_node, to_node)
    for area, a in AREAS.items():
        code = a["code"]
        specs = []
        if osm_on:
            cl = osm.connected_cluster(osm.pipe_chunks(a["center"], 1100), a["center"], 24)
            if len(cl) >= 12:
                specs = [(c["coords"], osm.DIAMETER.get(c["highway"].replace("_link", ""), 300) + rng.choice([-50, 0, 0, 50]), c["from"], c["to"]) for c in cl]
        if not specs:  # fallback: regular mesh around the area centre (approximate, not street-aligned)
            nodes = {(i, j): geo.offset(a["center"], (i - 1.5) * 300 + rng.uniform(-25, 25), (j - 1.5) * 300 + rng.uniform(-25, 25)) for i in range(4) for j in range(4)}
            for i in range(4):
                for j in range(4):
                    for di, dj, dia_base in ((1, 0, 600), (0, 1, 400)):
                        if i + di <= 3 and j + dj <= 3:
                            specs.append(([nodes[(i, j)], nodes[(i + di, j + dj)]], dia_base + rng.choice([-100, 0, 0, 100, 200]), f"N{code}{i}{j}", f"N{code}{i + di}{j + dj}"))
        for n, (coords, dia, n_from, n_to) in enumerate(specs, 1):
            pid = f"PIPE-{code}-{n:03d}"
            pipes.append((pid, area, coords, dia, n_from, n_to))
            store.upsert(S.WATER, {"Pipeline_ID": pid, "Network_Type": "Distribution Main" if dia >= 600 else "Distribution", "Material": rng.choice(MATERIALS), "Diameter": dia,
                                   "Status": "In Service", "Risk_Level": "Low", "Area_Name": area, "From_Node": n_from, "To_Node": n_to,
                                   "Length_M": round(geo.line_length_m(coords), 1), "Data_Classification": SYN}, geo.line(coords))
            mid = geo.interpolate(coords, 0.5)[0]
            store.upsert(S.INFRA, {"Asset_ID": f"AST-W-{len(pipes):04d}", "Asset_Type": "Water Pipe Segment", "Asset_Name": f"Pipe {pid}", "Asset_Status": "In Service",
                                   "Asset_Criticality": "High" if dia >= 600 else "Medium", "Installation_Date": f"{rng.randint(1995, 2022)}-01-01",
                                   "Location": f"{area} ({mid[1]:.4f}, {mid[0]:.4f})", "Area_Name": area, "Related_Pipeline_ID": pid, "Corridor": "",
                                   "Data_Classification": SYN}, geo.point(*mid))

    # -- water sensors + 48h hourly readings -------------------------------------------
    sensors = []
    rid = 0
    by_area: dict[str, list] = {}
    for p in pipes:
        by_area.setdefault(p[1], []).append(p)
    sn = 0
    for area, plist in by_area.items():
        for p in rng.sample(plist, 8):
            sn += 1
            sid = f"SEN-W-{sn:03d}"
            mid = geo.interpolate(p[2], 0.5)[0]
            base_p = rng.uniform(330, 470)
            base_f = p[3] / 600 * rng.uniform(45, 85)
            store.upsert(S.INFRA, {"Asset_ID": f"AST-S-{sn:03d}", "Asset_Type": "Pressure/Flow Sensor", "Asset_Name": sid, "Asset_Status": "Online",
                                   "Asset_Criticality": "Medium", "Installation_Date": f"{rng.randint(2018, 2024)}-06-01",
                                   "Location": f"{area}", "Area_Name": area, "Related_Pipeline_ID": p[0], "Corridor": "", "Data_Classification": SYN}, geo.point(*mid))
            sensors.append({"sensor": sid, "asset": f"AST-S-{sn:03d}", "pipe": p[0], "area": area, "mid": mid, "bp": base_p, "bf": base_f})
            for h in range(47, -1, -1):
                t = now - timedelta(hours=h)
                hod = t.hour
                pr = base_p * (1 + 0.05 * math.sin(2 * math.pi * (hod - 6) / 24)) + rng.gauss(0, 0.008 * base_p)
                fl = base_f * (1 + 0.25 * math.sin(2 * math.pi * (hod - 8) / 24)) + rng.gauss(0, 0.02 * base_f)
                rid += 1
                store.upsert(S.SENSORS, {"Reading_ID": f"RD-{rid:06d}", "Sensor_ID": sid, "Asset_ID": f"AST-S-{sn:03d}", "Sensor_Type": "Pressure/Flow",
                                         "Timestamp": _iso(t), "Pressure": round(pr, 1), "Flow": round(fl, 1), "Power_Consumption": None,
                                         "Operating_Status": "OK", "Anomaly_Flag": "No", "Data_Classification": SYN}, geo.point(*mid))

    # -- streetlights ---------------------------------------------------------------------
    lights = []
    n = 0
    for cname, c in CORRIDORS.items():
        cand = [pt_tan for ln in corridor_lines(cname) for pt_tan in osm.sample_along(ln, 140)]
        if not cand:
            continue
        k_ = c["n"]
        focus = AREAS["Olaya"]["center"] if "osm" in c else AREAS[c["area"]]["center"]
        near = [x for x in cand if geo.haversine_m(x[0], focus) <= 1800]   # dense around the demo focus ...
        far = [x for x in cand if geo.haversine_m(x[0], focus) > 1800]     # ... sparse along the rest of the corridor
        if len(near) > int(0.6 * k_):
            near = [near[int(i * len(near) / int(0.6 * k_))] for i in range(int(0.6 * k_))]
        m_ = max(0, k_ - len(near))
        far = [far[int(i * len(far) / m_)] for i in range(m_)] if len(far) > m_ else far
        for i, (pt, tan) in enumerate(near + far):
            n += 1
            side = 1 if i % 2 == 0 else -1
            p = geo.offset(pt, -tan[1] * 9 * side, tan[0] * 9 * side)  # 9 m from the real centreline
            lights.append({"id": f"AST-L-{n:04d}", "corr": cname, "p": p, "area": nearest_area(p), "cls": c["class"]})

    kfr = [l for l in lights if l["corr"] == "King Fahd Road"]
    window = sorted(kfr, key=lambda l: geo.haversine_m(l["p"], AREAS["Olaya"]["center"]))[:16]
    failing = set(l["id"] for l in rng.sample(window, min(12, len(window))))
    others = [l for l in lights if l["id"] not in failing and l not in window]
    failing |= set(l["id"] for l in rng.sample(others, 6))
    decoys = set(l["id"] for l in rng.sample([l for l in lights if l["id"] not in failing], 5))

    for l in lights:
        fcount = fac_near(l["p"], 250)
        crit = "High" if (l["cls"] == "arterial" and fcount) or fcount >= 2 else ("Medium" if l["cls"] == "arterial" or fcount else "Low")
        install = rng.randint(2012, 2023)
        store.upsert(S.INFRA, {"Asset_ID": l["id"], "Asset_Type": "Streetlight", "Asset_Name": f"{l['corr']} light {l['id'][-4:]}", "Asset_Status": "Operational",
                               "Asset_Criticality": crit, "Installation_Date": f"{install}-03-01", "Location": f"{l['corr']}, {l['area']}",
                               "Area_Name": l["area"], "Related_Pipeline_ID": "", "Corridor": l["corr"], "Data_Classification": SYN}, geo.point(*l["p"]))
        rated = rng.choice([120, 150, 180])
        if l["id"] in failing:
            trend = rng.choice([rng.gauss(10, 3), rng.gauss(-13, 3)])
            flick, comm, faults = rng.randint(6, 14), abs(rng.gauss(14, 5)), rng.randint(1, 4)
            dsm, age = rng.randint(300, 900), rng.uniform(6, 12)
        elif l["id"] in decoys:
            trend, flick, comm, faults = rng.gauss(5.5, 1.5), rng.randint(3, 6), abs(rng.gauss(7, 2)), rng.randint(0, 2)
            dsm, age = rng.randint(150, 500), rng.uniform(4, 9)
        else:
            trend, flick, comm, faults = rng.gauss(0, 1.6), int(rng.random() * 3), abs(rng.gauss(1, 1)), 1 if rng.random() < 0.2 else 0
            dsm, age = rng.randint(20, 650), min(11, max(0.5, 2026 - install + rng.uniform(-0.5, 0.5)))
        store.upsert(S.TELEMETRY, {"Asset_ID": l["id"], "Rated_Power_W": rated, "Avg_Power_W": round(rated * (1 + trend / 100) * rng.uniform(0.96, 1.0), 1),
                                   "Power_Trend_Pct": round(trend, 1), "Flicker_30d": flick, "Comm_Loss_Pct": round(comm, 1), "Faults_12m": faults,
                                   "Days_Since_Maintenance": dsm, "Age_Years": round(age, 1), "Updated": _iso(now), "Data_Classification": SYN})
        for m in range(rng.randint(0, 3) if l["id"] not in failing else rng.randint(2, 5)):
            store.upsert(S.MAINTENANCE, {"Record_ID": store.next_id("MNT", 5), "Asset_ID": l["id"], "Date": (now - timedelta(days=dsm + 120 * m)).strftime("%Y-%m-%d"),
                                         "Action": rng.choice(["Lamp replacement", "Driver replacement", "Photocell test", "Cable repair"]),
                                         "Outcome": rng.choice(["Completed", "Completed", "Temporary fix"]), "Data_Classification": SYN})
        store.upsert(S.TRUTH, {"Truth_ID": l["id"], "Detection_ID": "", "Is_True": "Yes" if l["id"] in failing else "No",
                               "Notes": "decoy: elevated telemetry but healthy" if l["id"] in decoys else ""})

    # lamp-group power sensors: 40 monitored lights, 12 daily readings
    monitored = rng.sample(lights, 40)
    for i, l in enumerate(monitored, 1):
        sid = f"SEN-L-{i:03d}"
        tel = store.get(S.TELEMETRY, l["id"])["attrs"]
        for d in range(11, -1, -1):
            rid += 1
            pw = tel["Rated_Power_W"] * (1 + tel["Power_Trend_Pct"] / 100 * (1 - d / 12)) + rng.gauss(0, 1.5)
            store.upsert(S.SENSORS, {"Reading_ID": f"RD-{rid:06d}", "Sensor_ID": sid, "Asset_ID": l["id"], "Sensor_Type": "Lamp Power Meter",
                                     "Timestamp": _iso(now - timedelta(days=d)), "Pressure": None, "Flow": None, "Power_Consumption": round(pw, 1),
                                     "Operating_Status": "ON", "Anomaly_Flag": "No", "Data_Classification": SYN}, geo.point(*l["p"]))

    # -- workers --------------------------------------------------------------------------
    roster = [
        ("Nawaf Al-Harbi", "Water Rapid Response", ["water", "leak_repair"], "Olaya"),
        ("Khalid Al-Otaibi", "Water Rapid Response", ["water", "inspection"], "Al Malaz"),
        ("Saad Al-Qahtani", "Water Rapid Response", ["water", "valve_ops"], "KAFD"),
        ("Hamad Al-Ghamdi", "Electrical Maintenance", ["electrical", "lighting"], "Olaya"),
        ("Yousef Al-Dosari", "Electrical Maintenance", ["electrical", "lighting"], "Al Malaz"),
        ("Ibrahim Al-Shehri", "Survey & Inspection", ["survey", "inspection", "gps"], "Diriyah"),
        ("Majed Al-Mutairi", "Survey & Inspection", ["survey", "inspection", "water"], "Diplomatic Quarter"),
    ]
    for i, (nm, team, skills, base) in enumerate(roster, 1):
        p = geo.offset(AREAS[base]["center"], rng.uniform(-300, 300), rng.uniform(-300, 300))
        p = (osm.nearest_road_point(p) if osm_on else None) or p
        store.upsert(S.WORKERS, {"Worker_ID": f"WRK-{i:03d}", "Name": nm, "Team": team, "Skills": ",".join(skills), "Status": "Available", "Base_Area": base, "ArcGIS_Username": "",
                                 "Open_Tasks": 0, "Last_Update": _iso(now), "Data_Classification": SYN}, geo.point(*p))

    # -- learning config -------------------------------------------------------------------
    for cat in ("water", "lighting", "change", "mobility"):
        store.upsert(S.CONFIG, {"Config_ID": f"calibration.{cat}", "Value": "1.0", "Updated": _iso(now)})
    store.upsert(S.CONFIG, {"Config_ID": "streetlight.detect_threshold", "Value": "0.55", "Updated": _iso(now)})
    store.upsert(S.CONFIG, {"Config_ID": "meta.seed", "Value": str(seed), "Updated": _iso(now)})
    store.upsert(S.CONFIG, {"Config_ID": "meta.generated", "Value": _iso(now), "Updated": _iso(now)})

    if with_history:
        _history(store, rng, now, pipes, lights, failing)
    for attrs, geom in traffic_response_workers(now):       # after the history, with fixed positions: the seeded city-service data stays exactly as it was
        store.upsert(S.WORKERS, attrs, geom)
    store.upsert(S.CONFIG, {"Config_ID": "meta.complete", "Value": data_version(), "Updated": _iso(now)})

    return {name: store.count(name) for name in S.LAYERS if store.count(name)}


TRAFFIC_RESPONSE = [("WRK-008", "Bandar Al-Shehri", "Olaya", (120.0, -80.0)), ("WRK-009", "Rayan Al-Anazi", "KAFD", (-90.0, 60.0))]


def traffic_response_workers(now: datetime | None = None) -> list[tuple[dict, dict]]:
    """The two investigators of the Traffic Response team (mobility incidents), as (attributes, geometry). SYNTHETIC."""
    stamp = _iso(now or datetime.now(timezone.utc).replace(microsecond=0))
    return [({"Worker_ID": wid, "Name": name, "Team": "Traffic Response", "Skills": "traffic,inspection", "Status": "Available", "Base_Area": base, "ArcGIS_Username": "",
              "Open_Tasks": 0, "Last_Update": stamp, "Data_Classification": S.SYNTHETIC}, geo.point(*geo.offset(AREAS[base]["center"], dx, dy)))
            for wid, name, base, (dx, dy) in TRAFFIC_RESPONSE]


def _history(store: Store, rng: random.Random, now: datetime, pipes, lights, failing_lights) -> None:
    """Seed older detections/incidents/work orders/verifications so dashboards and learning have history.

    Historical records reference real synthetic assets, are marked Source='Historical (seeded)', and carry a
    verification outcome consistent with the simulator's ground truth, so evaluation metrics are meaningful."""
    SYN = S.SYNTHETIC
    workers = [w["attrs"]["Worker_ID"] for w in store.all(S.WORKERS)]
    names = {w["attrs"]["Worker_ID"]: w["attrs"]["Name"] for w in store.all(S.WORKERS)}
    hist_pipes = rng.sample(pipes, 10)
    hist_lights = rng.sample(lights, 8)
    specs = []
    for i, p in enumerate(hist_pipes):
        truth = i % 3 != 2  # ~2/3 true leaks
        specs.append(("water", p[0], p[1], geo.centroid(geo.line(p[2])), truth, rng.uniform(52, 92)))
    for i, l in enumerate(hist_lights):
        truth = i % 4 != 3
        specs.append(("lighting", l["id"], l["area"], l["p"], truth, rng.uniform(48, 85)))
    for i in range(4):
        a = rng.choice(list(AREAS))
        specs.append(("change", f"HIST-CHG-{i + 1}", a, geo.offset(AREAS[a]["center"], rng.uniform(-500, 500), rng.uniform(-500, 500)), i % 2 == 0, rng.uniform(45, 80)))
    for idx, (cat, ref, area, p, truth, risk) in enumerate(specs):
        age_days = rng.randint(3, 40)
        t0 = now - timedelta(days=age_days)
        det = store.next_id("DET")
        sev = "Critical" if risk >= 75 else "High" if risk >= 55 else "Medium" if risk >= 35 else "Low"
        dtype = {"water": "Water Leak (Suspected)", "lighting": "Streetlight Failure (Predicted)", "change": "Urban Change (Candidate)", "distortion": "Visual Distortion (Candidate)", "pole_health": "Pole Health (Predicted)", "land_use": "Land-Use Shift (Candidate)"}[cat]
        status = "Verified-True" if truth else "Verified-False"
        completed = True                   # the seeded history is all closed: a fresh start has no open incidents, so every open one comes from an event the operator simulates
        if not completed:
            risk = rng.uniform(36, 56)  # older unresolved items are routine; live scenarios should outrank them
        if not completed:
            status = "Suspected" if cat == "water" else "Predicted" if cat == "lighting" else "Candidate"
        inc = store.next_id("INC")
        store.upsert(S.DETECTIONS, {"Detection_ID": det, "Detection_Type": dtype, "Location": f"{area}", "Confidence": round(risk / 100 * 0.95, 2), "Severity": sev,
                                    "Risk_Score": round(risk, 1), "Base_Risk_Score": round(risk, 1), "Detection_Date": _iso(t0), "Source": "Historical (seeded)",
                                    "Status": status, "Related_Asset_ID": ref, "Pipeline_ID": ref if cat == "water" else "", "Area_Name": area,
                                    "Category": cat, "Cluster_ID": "", "Evidence": "Seeded historical record for dashboard/learning context.",
                                    "Incident_ID": inc, "Data_Classification": SYN}, geo.point(*p))
        store.upsert(S.TRUTH, {"Truth_ID": f"TR-{det}", "Detection_ID": det, "Is_True": "Yes" if truth else "No", "Notes": "historical"})
        prio = "P1" if risk >= 75 else "P2" if risk >= 55 else "P3" if risk >= 35 else "P4"
        wo_id = store.next_id("WO") if completed else None
        team = {"water": "Water Rapid Response", "lighting": "Electrical Maintenance", "change": "Survey & Inspection"}[cat]
        istatus = ("Resolved" if truth else "Closed - False Positive") if completed else ("Assigned" if idx % 2 else "Open")
        store.upsert(S.INCIDENTS, {"Incident_ID": inc, "Incident_Type": dtype.split(" (")[0], "Priority": prio, "Severity": sev, "Risk_Score": round(risk, 1),
                                   "Location": area, "Description": f"Historical {cat} incident at {area}", "Related_Asset_ID": ref, "Assigned_Team": team if completed or idx % 2 else "",
                                   "Status": istatus, "Created_Date": _iso(t0 + timedelta(minutes=20)), "Last_Updated": _iso(t0 + timedelta(hours=rng.randint(4, 40))),
                                   "Detection_IDs": det, "Area_Name": area, "Category": cat,
                                   "Verification_Outcome": ("Confirmed" if truth else "Rejected") if completed else "", "Data_Classification": SYN}, geo.point(*p))
        if completed:
            wk = rng.choice(workers)
            store.upsert(S.WORK_ORDERS, {"Work_Order_ID": wo_id, "Incident_ID": inc, "Assigned_Team": team, "Assigned_Worker": wk, "Priority": prio,
                                         "Due_Date": _iso(t0 + timedelta(days=2)), "Status": "Completed", "Approval_Status": "Approved", "Created_Date": _iso(t0 + timedelta(hours=1)),
                                         "Task_Type": "Inspect & Repair", "Instructions": "Historical work order.", "Data_Classification": SYN}, geo.point(*p))
            vid = store.next_id("VER")
            store.upsert(S.VERIFICATION, {"Verification_ID": vid, "Work_Order_ID": wo_id, "Incident_ID": inc, "Worker_ID": wk, "Investigator_Name": names.get(wk, ""),
                                          "Observation": "Fault confirmed on site." if truth else "No fault found at location.",
                                          "Verification_Status": "Confirmed" if truth else "Rejected", "GPS_Location": f"{p[1]:.6f},{p[0]:.6f}", "Photo_URL": "",
                                          "Timestamp": _iso(t0 + timedelta(hours=rng.randint(5, 30))), "Distance_To_Detection_M": round(rng.uniform(2, 40), 1),
                                          "Agent_Assessment": "Historical seeded verification.", "Simulated_Worker": "Yes", "Data_Classification": SYN}, geo.point(*p))
    # a couple of unrelated open incidents for the command centre

    # New land-use and distortion historicals
    for i in range(3):
        a = rng.choice(list(AREAS))
        p = geo.offset(AREAS[a]["center"], rng.uniform(-500, 500), rng.uniform(-500, 500))
        for cat in ["distortion", "land_use"]:
            det = store.next_id("DET")
            inc = store.next_id("INC")
            store.upsert(S.DETECTIONS, {"Detection_ID": det, "Detection_Type": "Candidate", "Location": a, "Confidence": 0.7, "Severity": "Medium", "Risk_Score": 50.0, "Detection_Date": _iso(now), "Source": "Historical", "Status": "Verified-True", "Related_Asset_ID": "", "Pipeline_ID": "", "Area_Name": a, "Category": cat, "Cluster_ID": "", "Evidence": "Seeded historical", "Base_Risk_Score": 50.0, "Incident_ID": inc, "Data_Classification": S.SYNTHETIC}, geo.point(*p))
            store.upsert(S.INCIDENTS, {"Incident_ID": inc, "Incident_Type": "Urban Case", "Priority": "P3", "Severity": "Medium", "Risk_Score": 50.0, "Location": a, "Description": f"Historical {cat} case", "Related_Asset_ID": "", "Assigned_Team": "Survey & Inspection", "Status": "Resolved", "Created_Date": _iso(now - timedelta(days=5)), "Last_Updated": _iso(now - timedelta(days=4)), "Detection_IDs": det, "Area_Name": a, "Category": cat, "Verification_Outcome": "Confirmed", "Data_Classification": S.SYNTHETIC}, geo.point(*p))
    store.upsert(S.CONFIG, {"Config_ID": "meta.history_seeded", "Value": "yes", "Updated": _iso(now)})
