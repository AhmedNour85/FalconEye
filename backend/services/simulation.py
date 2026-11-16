"""Simulation engine: changing operational feeds, predefined scenarios and simulated field responses.

Everything produced here is SIMULATED. Ground truth (hidden from the agent tools) lives in Riyadh_Sim_Ground_Truth so
that simulated field workers answer consistently and false positives/negatives can be measured.
"""
from __future__ import annotations

import random
import threading
import time
from datetime import datetime, timedelta, timezone

from backend.gis import geo
from backend.gis import schema as S
from backend.gis.store import Store, utcnow


class SimEngine:
    def __init__(self, store: Store, seed: int = 20260101):
        self.store = store
        self.rng = random.Random(seed + 99)
        self.injected: dict[str, int] = {}
        self.running = False
        self._thread: threading.Thread | None = None
        self.interval = 5.0
        self.tick_count = 0
        self.anomaly_rate = 0.0

    # ---- event log ------------------------------------------------------------------------
    def event(self, kind: str, message: str, ref: str = "") -> dict:
        eid = self.store.next_id("EVT", 5)
        rec = {"Event_ID": eid, "Timestamp": utcnow(), "Kind": kind, "Message": message, "Ref_ID": ref}
        self.store.upsert(S.SIM_EVENTS, rec)
        return rec

    def events(self, n: int = 30) -> list[dict]:
        return [f["attrs"] for f in self.store.all(S.SIM_EVENTS)][-n:][::-1]

    # ---- control --------------------------------------------------------------------------
    def start(self, interval: float = 5.0) -> dict:
        self.interval = interval
        if not self.running:
            self.running = True
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()
            self.event("control", "Simulation started")
        return self.status()

    def pause(self) -> dict:
        if self.running:
            self.running = False
            self.event("control", "Simulation paused")
        return self.status()

    def status(self) -> dict:
        return {"running": self.running, "ticks": self.tick_count, "interval_s": self.interval, "anomaly_rate": self.anomaly_rate}

    def _loop(self) -> None:
        while self.running:
            try:
                self.tick()
            except Exception as exc:  # pragma: no cover
                self.event("error", f"tick failed: {exc}")
            time.sleep(self.interval)

    # ---- readings -------------------------------------------------------------------------
    def _water_series(self) -> dict[str, list[dict]]:
        by: dict[str, list[dict]] = {}
        for f in self.store.all(S.SENSORS):
            if f["attrs"]["Sensor_ID"].startswith("SEN-W-"):
                by.setdefault(f["attrs"]["Sensor_ID"], []).append(f)
        for v in by.values():
            v.sort(key=lambda f: f["attrs"]["Timestamp"])
        return by

    def tick(self) -> dict:
        """Advance every water sensor by one hour of simulated time (normal behaviour, optional random anomalies)."""
        self.tick_count += 1
        n_new = 0
        for sid, rows in self._water_series().items():
            last = rows[-1]
            prev24 = rows[-24]["attrs"] if len(rows) >= 24 else last["attrs"]
            t = datetime.strptime(last["attrs"]["Timestamp"], "%Y-%m-%dT%H:%M:%SZ") + timedelta(hours=1)
            p = prev24["Pressure"] * (1 + self.rng.gauss(0, 0.006))
            f = prev24["Flow"] * (1 + self.rng.gauss(0, 0.02))
            flag = "No"
            if self.anomaly_rate and self.rng.random() < self.anomaly_rate:
                p *= 0.8
                f *= 1.25
                flag = "Yes"
            rid = self.store.next_id("RDT", 6)   # own prefix: the seeded readings already use RD-nnnnnn and must not be overwritten
            self.store.upsert(S.SENSORS, {"Reading_ID": rid, "Sensor_ID": sid, "Asset_ID": last["attrs"]["Asset_ID"], "Sensor_Type": "Pressure/Flow",
                                          "Timestamp": t.strftime("%Y-%m-%dT%H:%M:%SZ"), "Pressure": round(p, 1), "Flow": round(f, 1), "Power_Consumption": None,
                                          "Operating_Status": "OK", "Anomaly_Flag": flag, "Data_Classification": S.SYNTHETIC}, last["geom"])
            n_new += 1
        self.event("tick", f"{n_new} new pressure/flow readings ingested")
        return {"new_readings": n_new}

    def modify_sensor(self, sensor_id: str, pressure_drop_pct: float, flow_rise_pct: float, hours: int = 4) -> dict:
        """Overwrite the last `hours` readings of a sensor (explicit 'modify sensor readings' control)."""
        rows = self._water_series().get(sensor_id)
        if not rows:
            raise ValueError(f"unknown water sensor {sensor_id}")
        n = 0
        for i, r in enumerate(rows[-hours:], 1):
            ramp = min(1.0, i / max(1, hours - 1))
            ref = rows[-hours - 24 + i - 1]["attrs"] if len(rows) > hours + 24 else r["attrs"]
            self.store.update(S.SENSORS, r["id"], Pressure=round(ref["Pressure"] * (1 - pressure_drop_pct / 100 * ramp), 1),
                              Flow=round(ref["Flow"] * (1 + flow_rise_pct / 100 * ramp), 1), Anomaly_Flag="No")
            n += 1
        self.event("sensor", f"{sensor_id}: pressure -{pressure_drop_pct}% / flow +{flow_rise_pct}% injected over last {hours}h", sensor_id)
        return {"sensor_id": sensor_id, "readings_modified": n}

    def _sensor_on_pipe(self, pipe_id: str) -> str | None:
        for f in self.store.all(S.INFRA):
            if f["attrs"]["Asset_Type"] == "Pressure/Flow Sensor" and f["attrs"]["Related_Pipeline_ID"] == pipe_id:
                return f["attrs"]["Asset_Name"]
        return None

    def _set_truth(self, key: str, is_true: bool, note: str) -> None:
        self.store.upsert(S.TRUTH, {"Truth_ID": key, "Detection_ID": "", "Is_True": "Yes" if is_true else "No", "Notes": note})

    # ---- scenarios ------------------------------------------------------------------------
    SLUGS = {"olaya": "Olaya", "kafd": "KAFD", "almalaz": "Al Malaz", "dq": "Diplomatic Quarter", "ksp": "King Salman Park", "diriyah": "Diriyah"}
    def light_areas(self) -> tuple:
        """Areas that actually hold streetlights in the current data."""
        return tuple(sorted({f["attrs"]["Area_Name"] for f in self.store.all(S.INFRA) if f["attrs"]["Asset_Type"] == "Streetlight"}))


    def least_busy(self, areas) -> str:
        """The area with the fewest open incidents (random among ties), so injected events spread over the city instead of piling up."""
        busy = {a: self.injected.get(a, 0) for a in areas}      # events already injected count too, so repeats rotate through the city
        for f in self.store.all(S.INCIDENTS):
            if f["attrs"]["Status"] not in ("Resolved", "Closed - False Positive") and f["attrs"]["Area_Name"] in busy:
                busy[f["attrs"]["Area_Name"]] += 1
        low = min(busy.values())
        pick = self.rng.choice([a for a, n in busy.items() if n == low])
        self.injected[pick] = self.injected.get(pick, 0) + 1
        return pick

    def scenario(self, name: str) -> dict:
        if name == "olaya_leak":
            return self._leak("Olaya")
        if name == "multi_incident":
            return self._multi()
        if name == "king_fahd_lights":
            return self._lights()
        if name == "streetlight_pole":
            lamps = self._lights()          # one use case: lamps drift and poles lean on the same corridor
            return {**self._pole_decay(), "scenario": "streetlight_pole", "lamps_updated": lamps["lamps_updated"]}
        if name == "pole_decay":
            return self._pole_decay()
        if name == "distortion_event":
            return self._distortion("Al Malaz")
        if name.startswith("distortion_"):
            area = self.least_busy(["Olaya", "Al Malaz", "Diriyah"]) if name == "distortion_random" else self.SLUGS.get(name[11:])
            if area:
                return self._distortion(area)
        if name == "landuse_violation":
            return self._landuse("King Salman Park")
        if name.startswith("landuse_"):
            area = self.least_busy(["King Salman Park", "Diriyah", "Al Malaz"]) if name == "landuse_random" else self.SLUGS.get(name[8:])
            if area:
                return self._landuse(area)
        if name.startswith("leak_"):
            key = name[5:]
            area = self.least_busy(list(self.SLUGS.values())) if key == "random" else self.SLUGS.get(key)
            if area:
                return self._leak(area)
        if name.startswith("lights_"):
            key = name[7:]
            area = self.least_busy(self.light_areas()) if key == "random" else self.SLUGS.get(key)
            if area in self.light_areas():
                return self._lights_area(area)
        if name == "traffic_incident":
            return self._traffic_incident()
        if name == "road_closure":
            return self._road_closure()
        if name == "major_event":
            return self._major_event()
        raise ValueError(f"unknown scenario {name}; available: olaya_leak, multi_incident, king_fahd_lights, streetlight_pole, pole_decay, distortion_event, landuse_violation, "
                         "leak_<area|random>, lights_<olaya|kafd|almalaz|dq|ksp|diriyah|random>, traffic_incident, road_closure, major_event")

    # ---- mobility events (SYNTHETIC rows; the crew reads them on its next scan) ---------------------
    CLOSURE_REASONS = ("Resurfacing works", "Bridge joint replacement", "Utility crossing under the carriageway", "Drainage repair")
    EVENTS = (("Riyadh Season concert", "KAFD"), ("National festival evening", "King Abdullah Park"), ("Football final screening", "Riyadh Front"),
              ("Heritage night", "King Abdulaziz Historical Center"), ("Graduation ceremony", "King Saud University"))

    def _wide_section(self, min_lanes: int = 3) -> dict:
        """A motorway or arterial section with at least this many lanes, on the named road with the fewest open incidents and earlier events."""
        from backend.mobility import sources

        roads = [r for r in sources.load_network()[0] if r["road_class"] in ("motorway", "arterial") and int(r["lanes"]) >= min_lanes and r.get("corridor")]
        if not roads:
            raise ValueError("the road network has no motorway or arterial section wide enough for this event")
        corridor = self.least_busy(sorted({r["corridor"] for r in roads}))
        return self.rng.choice(sorted((r for r in roads if r["corridor"] == corridor), key=lambda r: r["id"]))

    @staticmethod
    def _riyadh_day(days: int = 0) -> datetime:
        return (datetime.utcnow() + timedelta(hours=3, days=days)).replace(hour=0, minute=0, second=0, microsecond=0)

    def _traffic_incident(self) -> dict:
        """A crash blocking two lanes of a wide road: one road report, as a traffic control room would log it."""
        r = self._wide_section()
        c = r["geometry"]["coordinates"]
        rid = self.store.next_id("TRF")
        self.store.upsert(S.TRAFFIC_REPORTS, {"Report_ID": rid, "Report_Type": "Crash", "Segment_ID": r["id"], "Corridor": r["corridor"], "Road_Class": r["road_class"],
                                              "Lanes": int(r["lanes"]), "Lanes_Blocked": 2, "Reported_At": utcnow(), "Source": "Road report (SYNTHETIC)", "Status": "New",
                                              "Detection_ID": "", "Description": f"Multi-vehicle crash blocking 2 of {int(r['lanes'])} lanes on {r['corridor']}.",
                                              "Data_Classification": S.SYNTHETIC}, geo.point(*c[len(c) // 2][:2]))
        self._set_truth(rid, True, "scenario: crash blocking lanes")
        self.event("scenario", f"Road report: crash blocking 2 lanes on {r['corridor']}", rid)
        return {"scenario": "traffic_incident", "id": rid, "corridor": r["corridor"], "segment_id": r["id"]}

    def _road_closure(self) -> dict:
        """A contractor asks to close one section of a road tomorrow, 08:00 to 16:00."""
        r = self._wide_section(min_lanes=2)
        cid = self.store.next_id("CLS")
        day = self._riyadh_day(1)
        reason = self.rng.choice(self.CLOSURE_REASONS)
        self.store.upsert(S.CLOSURES, {"Closure_ID": cid, "Corridor": r["corridor"], "Section": r["name"], "Segment_IDs": r["id"], "Lanes_Closed": int(r["lanes"]),
                                       "Full_Closure": "Yes", "Start_Time": day.replace(hour=8).isoformat(timespec="minutes"),
                                       "End_Time": day.replace(hour=16).isoformat(timespec="minutes"), "Reason": reason, "Status": "Requested", "Strategy": "",
                                       "Incident_ID": "", "Work_Order_ID": "", "Scenario_ID": "", "Requested_By": "Road works contractor (SYNTHETIC)", "Created": utcnow(),
                                       "Updated": utcnow(), "Data_Classification": S.SYNTHETIC}, {"type": "LineString", "coordinates": r["geometry"]["coordinates"]})
        self._set_truth(cid, True, "scenario: planned road closure")
        self.event("scenario", f"Closure request: {reason.lower()} on {r['corridor']}, tomorrow 08:00 to 16:00", cid)
        return {"scenario": "road_closure", "id": cid, "corridor": r["corridor"], "segment_id": r["id"]}

    def _major_event(self) -> dict:
        """An event notice for tonight, 18:00 to 23:00, at a venue the traffic model knows by name."""
        from backend.mobility import riyadh_network as RN

        venues = {full: (lon, lat) for full, lon, lat in RN.LOCATIONS.values()}
        venues.update({k: (v[1], v[2]) for k, v in RN.LOCATIONS.items()})
        name, venue = self.EVENTS[self.injected.get("major_event", 0) % len(self.EVENTS)]
        self.injected["major_event"] = self.injected.get("major_event", 0) + 1
        eid = self.store.next_id("EVN")
        day = self._riyadh_day()
        people = int(self.rng.randrange(20, 61) * 1000)
        self.store.upsert(S.EVENT_NOTICES, {"Event_ID": eid, "Name": name, "Venue": venue, "Attendance": people, "Start_Time": day.replace(hour=18).isoformat(timespec="minutes"),
                                            "End_Time": day.replace(hour=23).isoformat(timespec="minutes"), "Status": "New", "Detection_ID": "", "Incident_ID": "",
                                            "Source": "Event notice (SYNTHETIC)", "Created": utcnow(), "Data_Classification": S.SYNTHETIC}, geo.point(*venues[venue]))
        self._set_truth(eid, True, "scenario: major event")
        self.event("scenario", f"Event notice: {name} at {venue}, about {people:,} people, 18:00 to 23:00", eid)
        return {"scenario": "major_event", "id": eid, "venue": venue, "attendance": people}

    def _pole_decay(self, corridor: str = "King Fahd Road") -> dict:
        """A run of five neighbouring poles on a corridor leans and corrodes (inclinometer + inspection telemetry)."""
        tel = {f["id"]: f for f in self.store.all(S.TELEMETRY)}
        poles = [f for f in self.store.all(S.INFRA) if f["attrs"]["Asset_Type"] == "Streetlight" and f["attrs"]["Corridor"] == corridor and f["id"] in tel
                 and tel[f["id"]]["attrs"].get("Pole_Tilt_Deg") in (None, "")]
        if not poles:
            raise ValueError(f"no healthy poles left on {corridor}")
        seed = self.rng.choice(poles)
        c = geo.centroid(seed["geom"])
        run = sorted(poles, key=lambda f: geo.haversine_m(c, geo.centroid(f["geom"])))[:5]
        for i, f in enumerate(run):
            tilt, corr = round(self.rng.uniform(5.5, 11.0), 1), self.rng.choice([2, 3])
            if i == len(run) - 1:        # a decoy: leaning on paper (sensor drift), perfectly sound when inspected
                tilt, corr = round(self.rng.uniform(4.2, 4.8), 1), 0
            self.store.update(S.TELEMETRY, f["id"], Pole_Tilt_Deg=tilt, Corrosion_Level=corr, Updated=utcnow())
            self._set_truth(f["id"], i < len(run) - 1, f"scenario: {'structurally compromised pole' if i < len(run) - 1 else 'inclinometer drift (false positive)'} ({corridor})")
        self.event("scenario", f"Pole monitoring: {len(run)} poles on {corridor} report tilt/corrosion above limits", corridor)
        return {"scenario": "pole_decay", "corridor": corridor, "area": run[0]["attrs"]["Area_Name"], "assets": [f["id"] for f in run]}

    def _distortion(self, area: str) -> dict:
        """Three neighbouring buildings deform between the two imagery epochs; a fourth elsewhere is a scaffolding/shadow artefact."""
        from backend.services import cityops

        blds = [f for f in self.store.all(S.BUILDINGS) if f["attrs"]["Area_Name"] == area and f["attrs"]["Area_Sqm"] >= 150 and not self.store.get(S.CONFIG, f"distortion.{f['id']}")]
        if len(blds) < 5:
            raise ValueError(f"not enough buildings in {area}")
        seed = self.rng.choice(blds)
        c = geo.centroid(seed["geom"])
        near = sorted(blds, key=lambda f: geo.haversine_m(c, geo.centroid(f["geom"])))
        real, decoy = near[:3], near[-1]
        from backend.services import visual_types

        keys = list(visual_types.KEYS)
        start = self.rng.randrange(len(keys))                       # a different set of three kinds each time the event is injected
        out = []
        for i, f in enumerate(real):
            sc = round(self.rng.uniform(0.62, 0.86), 2)
            cityops.inject_distortion(self.store, f["id"], sc, keys[(start + i) % len(keys)])
            self._set_truth(f["id"], True, f"scenario: real visual distortion ({area})")
            out.append(f["id"])
        cityops.inject_distortion(self.store, decoy["id"], 0.52, keys[(start + 3) % len(keys)])
        self._set_truth(decoy["id"], False, "scenario: temporary hoarding, scaffolding or shadow mistaken for a visual problem (false positive)")
        out.append(decoy["id"])
        self.event("scenario", f"New satellite pass over {area}: street-level visual problems appear between the two dates", area)
        return {"scenario": "distortion", "area": area, "assets": out}

    def _landuse(self, area: str) -> dict:
        """Construction appears where the zoning does not allow it. The crew is told to keep watching the area."""
        from backend.services import cityops

        items = cityops.violations(self.store, area, 20260101)
        bad = [i for i in items if not i["compliant"]]
        for i in bad:
            self._set_truth(i["change_id"], True, f"scenario: unpermitted {i['land_use'].lower()} ({area})")
        self.store.upsert(S.CONFIG, {"Config_ID": f"landuse.watch.{area}", "Value": "1", "Updated": utcnow()})
        self.event("scenario", f"New satellite pass over {area}: {len(bad)} possible zoning violation(s)", area)
        return {"scenario": "landuse", "area": area, "violations": len(bad), "assets": [i["change_id"] for i in bad]}

    def _pipes_with_sensors(self, area: str) -> list[tuple[str, str]]:
        out = []
        for f in self.store.all(S.INFRA):
            a = f["attrs"]
            if a["Asset_Type"] == "Pressure/Flow Sensor" and a["Area_Name"] == area:
                out.append((a["Related_Pipeline_ID"], a["Asset_Name"]))
        return out

    def _leak(self, area: str) -> dict:
        pairs = self._pipes_with_sensors(area)
        if not pairs:
            raise ValueError(f"no water sensors in {area}")
        # choose the sensor pipe with the most sensor-bearing neighbours so localisation can be corroborated
        pipes = {f["id"]: f["attrs"] for f in self.store.all(S.WATER)}
        def nb(pid):
            n = {pipes[pid]["From_Node"], pipes[pid]["To_Node"]}
            return sum(1 for q, _ in pairs if q != pid and n & {pipes[q]["From_Node"], pipes[q]["To_Node"]})
        from backend.mobility import road_impact, rules

        reach = rules.ROAD_IMPACT["water"]["radius_m"] * 0.75      # inside the road-impact rule even if the leak is localised a little off the pipe's middle

        def by_road(pid):       # a leak next to a named road lets the crew show a road-impact line worth showing (the headline demo)
            line = self.store.get(S.WATER, pid)
            if not line:
                return (0, 0)
            mid = geo.interpolate(line["geom"]["coordinates"], 0.5)[0]
            road = road_impact.nearest_road(mid, reach)
            if not road:
                return (0, 0)
            named = not str(road.get("corridor") or road.get("name") or "").lower().startswith("unnamed")
            return (2 if named else 1, int(road.get("lanes") or 0))
        pid, sid = max(pairs, key=lambda x: (by_road(x[0]), nb(x[0]), x[0]))
        self.modify_sensor(sid, 31, 38, 4)
        for q, s2 in pairs:
            if q != pid and {pipes[pid]["From_Node"], pipes[pid]["To_Node"]} & {pipes[q]["From_Node"], pipes[q]["To_Node"]}:
                self.modify_sensor(s2, 9, 6, 4)
        self._set_truth(pid, True, f"scenario: real leak ({area})")
        ev = self.event("scenario", f"Abnormal pressure drop reported by {sid} on {pid} ({area})", pid)
        return {"scenario": "leak", "sensor_id": sid, "pipeline_id": pid, "area": area, "event": ev["Message"]}

    def _lights_area(self, area: str) -> dict:
        """A run of six neighbouring lamps in `area` starts to degrade (drifting power, flicker, comms loss)."""
        tel = {f["id"]: f for f in self.store.all(S.TELEMETRY)}
        lamps = [f for f in self.store.all(S.INFRA) if f["attrs"]["Asset_Type"] == "Streetlight" and f["attrs"]["Area_Name"] == area and f["id"] in tel
                 and tel[f["id"]]["attrs"]["Flicker_30d"] < 6]
        if not lamps:
            raise ValueError(f"no healthy streetlights left in {area}")
        seed = self.rng.choice(lamps)
        c = geo.centroid(seed["geom"])
        run = sorted(lamps, key=lambda f: geo.haversine_m(c, geo.centroid(f["geom"])))[:6]
        for f in run:
            self.store.update(S.TELEMETRY, f["id"], Power_Trend_Pct=round(self.rng.uniform(8.5, 12.0), 1), Flicker_30d=self.rng.randint(10, 14), Comm_Loss_Pct=round(self.rng.uniform(8.0, 12.5), 1),
                              Faults_12m=self.rng.randint(1, 3), Days_Since_Maintenance=self.rng.randint(400, 480), Updated=utcnow())
            self._set_truth(f["id"], True, f"scenario: degrading lamp ({area})")
        self.event("scenario", f"Streetlight telemetry: {len(run)} lamps in {area} show drifting power and flicker", area)
        return {"scenario": "lights", "area": area, "assets": [f["id"] for f in run], "lamps_updated": len(run)}

    def _multi(self) -> dict:
        picks = []
        for area, drop, flow, real in (("Olaya", 27, 30, True), ("Al Malaz", 24, 26, True), ("KAFD", 17, 11, False)):
            pairs = self._pipes_with_sensors(area)
            pid, sid = pairs[0]
            self.modify_sensor(sid, drop, flow, 4)
            self._set_truth(pid, real, "scenario: multi_incident " + ("real leak" if real else "pump transient (false positive)"))
            picks.append({"area": area, "pipeline_id": pid, "sensor_id": sid})
            self.event("scenario", f"Pressure anomaly {sid} ({area})", pid)
        return {"scenario": "multi_incident", "anomalies": picks, "note": "includes one decoy that will not verify (false-positive test)"}

    def _lights(self) -> dict:
        n = 0
        for f in self.store.all(S.TELEMETRY):
            a = f["attrs"]
            if a["Asset_ID"].startswith("AST-L-") and a["Flicker_30d"] >= 6:
                self.store.update(S.TELEMETRY, f["id"], Flicker_30d=a["Flicker_30d"] + 2, Updated=utcnow())
                n += 1
        self.event("scenario", f"Streetlight telemetry refresh: {n} degrading lamps show increased flicker", "King Fahd Road")
        return {"scenario": "king_fahd_lights", "lamps_updated": n}

    # ---- simulated field worker --------------------------------------------------------------
    def truth_for_incident(self, incident_id: str) -> tuple[bool, str]:
        inc = self.store.get(S.INCIDENTS, incident_id)
        if not inc:
            raise ValueError("incident not found")
        # a historical truth entry may exist per detection; else per pipeline/asset
        for did in [d for d in inc["attrs"]["Detection_IDs"].split(",") if d]:
            det = self.store.get(S.DETECTIONS, did)
            if not det:
                continue
            for key in (f"TR-{did}", det["attrs"]["Pipeline_ID"], det["attrs"]["Related_Asset_ID"]):
                t = self.store.get(S.TRUTH, key) if key else None
                if t:
                    return t["attrs"]["Is_True"] == "Yes", t["attrs"]["Notes"]
        return False, "no ground truth recorded"

    # incident type -> (what is found when the answer key says it is real, what is found when it is not)
    MOBILITY_OBS = {
        "Traffic Incident": ("Crashed vehicles blocking the reported lanes; traffic queuing. Scene made safe. Blockage confirmed.",
                             "All lanes are open and traffic is flowing normally; no crash or debris found at the reported point."),
        "Planned Road Closure": ("Signs, barriers and the diversion route are in place as approved; the section is closed to traffic. Closure confirmed.",
                                 "No closure found on site: no signs or barriers are set up and traffic is using the section."),
        "Major Event Traffic Plan": ("Approach routes signed, parking guidance up, marshals in position at the venue. Traffic plan confirmed in place.",
                                     "No traffic plan found on site: no signs, parking guidance or marshals at the venue."),
    }
    MOBILITY_CLEARED = "Vehicles removed and debris cleared; all lanes are open again and traffic is back to normal."

    def field_observation(self, work_order_id: str) -> dict:
        """Build what a simulated field worker would observe on site (consistent with hidden ground truth)."""
        wo = self.store.get(S.WORK_ORDERS, work_order_id)
        if not wo:
            raise ValueError("work order not found")
        inc = self.store.get(S.INCIDENTS, wo["attrs"]["Incident_ID"])
        truth, _ = self.truth_for_incident(inc["id"])
        cat = inc["attrs"]["Category"]
        if cat == "lighting" and "Pole" in inc["attrs"]["Incident_Type"]:
            cat = "pole_health"          # same use case, but the site visit is about the pole, not the lamp
        pt = geo.centroid(inc["geom"])
        gps = geo.offset(pt, self.rng.uniform(-20, 20), self.rng.uniform(-20, 20))
        from backend.services import visual_types

        vt = visual_types.by_name(inc["attrs"]["Incident_Type"]) if cat == "distortion" else None
        if vt:                                                      # one of the eight visual-distortion kinds
            if truth:
                return {"observation": f"{vt['name']} confirmed from street level: {vt['what']}. Photographed and noted for the notice to the owner.",
                        "status": "Confirmed", "gps": gps, "worker_id": wo["attrs"]["Assigned_Worker"]}
            return {"observation": f"Nothing found on site: the apparent {vt['name'].lower()} was temporary hoarding or a shadow in the imagery.",
                    "status": "Rejected", "gps": gps, "worker_id": wo["attrs"]["Assigned_Worker"]}
        if cat == "mobility":                                       # a road report, a closure request or an event notice: what is on the road
            yes, no = self.MOBILITY_OBS.get(inc["attrs"]["Incident_Type"], self.MOBILITY_OBS["Traffic Incident"])
            return {"observation": yes if truth else no, "status": "Confirmed" if truth else "Rejected", "gps": gps, "worker_id": wo["attrs"]["Assigned_Worker"]}
        if truth:
            obs = {"water": "Visible water seepage and wet asphalt at the indicated location; pipe fitting corroded. Leak confirmed.",
                   "lighting": "Lamp driver failing: intermittent flicker and heat damage observed. Fault confirmed on site.",
                   "change": "New construction site with fencing and early foundations observed.",
                   "distortion": "Visible diagonal cracks and a bulging wall section confirmed from street level; structural engineer requested.",
                   "pole_health": "Pole base heavily corroded and leaning toward the carriageway; anchor bolts loose. Structural risk confirmed.",
                   "land_use": "Active construction with site hoarding and no permit displayed; building is not allowed in this zone. Violation confirmed."}[cat]
            status = "Confirmed"
        else:
            obs = {"water": "No visible leak, dry surface; pressure transient from nearby valve operation likely. Finding not reproduced.",
                   "lighting": "Lamps operate normally; no flicker or heat damage found.",
                   "change": "Seasonal vegetation change only; no construction present.",
                   "distortion": "Building is sound: the apparent distortion was scaffolding and shadow in the imagery. No cracks or deformation.",
                   "pole_health": "Pole is plumb and the base is sound; the inclinometer reading was drift. No action needed.",
                   "land_use": "Structure is a permitted temporary works area; no violation found."}[cat]
            status = "Rejected"
        return {"observation": obs, "status": status, "gps": gps, "worker_id": wo["attrs"]["Assigned_Worker"]}
