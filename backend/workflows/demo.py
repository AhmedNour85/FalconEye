"""Guided executive demonstration: one continuous story, driven through the SAME agent tools/session as the chat.

Every scene executes real tool calls against the store (nothing is canned). `auto_approve=True` approves the pending proposals as
"presenter (demo)" so the story can be replayed hands-free; otherwise the presenter approves in the Approval panel and re-runs the scene.
"""
from __future__ import annotations

from backend.agent.agent import GeoAIAgent, compact
from backend.gis import geo
from backend.gis import schema as S

SID = "demo"
SCENES = [
    (1, "SENSE", "Detecting Emerging Infrastructure Problems"),
    (2, "SEE", "Observing the Changing City"),
    (3, "UNDERSTAND", "Turning Geospatial Data into Intelligence"),
    (4, "DECIDE", "Prioritizing What Matters"),
    (5, "ACT", "Moving from Intelligence to Action"),
    (6, "VERIFY", "Confirming Real-World Outcomes"),
    (7, "LEARN", "Closing the Intelligence Loop"),
    (8, "BONUS", "Streetlight Predictive Maintenance on King Fahd Road"),
]


class Demo:
    def __init__(self, agent: GeoAIAgent):
        self.agent = agent
        self.p = agent.p

    # -- helpers ----------------------------------------------------------------------------------
    @property
    def ctx(self):
        return self.agent.session(SID).ctx

    def _tool(self, trace: list, name: str, **args) -> dict:
        r = self.agent.run_tool(SID, name, args)
        trace.append(self.agent._trace_item(name, args, r))
        return r

    def _view(self, lon, lat, zoom=15, label="") -> dict:
        return {"lon": lon, "lat": lat, "zoom": zoom, "label": label}

    def reset(self) -> dict:
        self.agent.sessions.pop(SID, None)
        counts = self.p.reset()
        self.agent.session(SID)
        return {"reset": True, "counts": counts, "message": "Environment regenerated from seed. Demo ready: Scene 1 will inject the Olaya pressure anomaly."}

    def _approve(self, aid: str, trace: list) -> dict:
        res = self.agent.approve_via_ui(aid, actor="presenter (demo auto-approve)")
        trace.append({"tool": "approval_gate.approve", "stage": "ACT", "ok": bool(res.get("ok")), "input": {"approval_id": aid}, "summary": str(res)[:240], "result": compact(res)})
        return res

    def _leak_incident(self) -> dict | None:
        did = self.ctx.state.get("demo_leak_detection")
        if not did:
            return None
        d = self.p.store.get(S.DETECTIONS, did)
        return self.p.store.get(S.INCIDENTS, d["attrs"]["Incident_ID"]) if d and d["attrs"]["Incident_ID"] else None

    # -- scenes -----------------------------------------------------------------------------------
    def run(self, scene: int, auto_approve: bool = False) -> dict:
        fn = {1: self.s1, 2: self.s2, 3: self.s3, 4: self.s4, 5: self.s5, 6: self.s6, 7: self.s7, 8: self.s8}.get(scene)
        if not fn:
            raise ValueError("scene must be 1..8")
        trace: list = []
        out = fn(trace, auto_approve)
        n, stage, title = next(x for x in SCENES if x[0] == scene)
        return {"scene": n, "stage": stage, "title": title, "tool_calls": trace, "pending_approvals": self.p.approvals.pending(), **out}

    def s1(self, trace, auto):
        ev = self.p.sim.scenario("olaya_leak")
        r = self._tool(trace, "detect_water_leaks", area="Olaya")
        if not r["ok"] or not r["result"]["detections"]:
            return {"complete": False, "narrative": ["No anomaly detected - check the simulation."], "map": None}
        d = r["result"]["detections"][0]
        self.ctx.state["demo_leak_detection"] = d["detection_id"]
        loc = d["probable_location"]
        return {"complete": True, "map": self._view(loc["lon"], loc["lat"], 17, "Probable leak location"), "layers": ["Riyadh_AI_Detections", "Riyadh_Water_Network", "Riyadh_Sensor_Readings"],
                "narrative": [f"Sensor event received: {ev['event']}.",
                              f"The agent associated {d['sensor_id']} with synthetic pipeline {d['pipeline_id']} and flagged a SUSPECTED leak ({d['detection_id']}), risk {d['risk_score']} ({d['severity']}).",
                              d["why_suspicious"]], "detection_id": d["detection_id"]}

    def s2(self, trace, auto):
        r = self._tool(trace, "detect_imagery_changes", area="Olaya")
        if not r["ok"]:
            return {"complete": False, "narrative": [r["error"]], "map": None}
        res = r["result"]
        ch = self.p.store.get(S.CHANGES, self.ctx.state["focus_change"]) if self.ctx.state.get("focus_change") else None
        c = geo.centroid(ch["geom"]) if ch else (46.685, 24.6935)
        return {"complete": True, "map": self._view(c[0], c[1], 15, "Detected change candidates"), "layers": ["Riyadh_Change_Detection", "Riyadh_Water_Network"],
                "imagery": {"area": "Olaya", "epochs": ["A", "B"]},
                "narrative": [f"Compared {res['previous_epoch']} with {res['current_epoch']} over Olaya (SIMULATED imagery, real algorithm).",
                              f"{len(res['changes'])} candidate changes; {res['significant_count']} significant. Vegetation-only differences are held back as possibly seasonal.",
                              "Results are CANDIDATES - not confirmed construction."]}

    def s3(self, trace, auto):
        f = self._tool(trace, "extract_geoai_features")
        sp1 = self._tool(trace, "spatial_analysis", target_type="change", radius_m=300)
        did = self.ctx.state.get("demo_leak_detection")
        sp2 = self._tool(trace, "spatial_analysis", target_type="detection", target_id=did, radius_m=400) if did else None
        lines = []
        if f["ok"]:
            lines.append(f"Simulated GeoAI extraction around {f['result']['change_id']}: {len(f['result']['buildings'])} building footprint(s), {len(f['result']['roads'])} road segment(s).")
        if sp1["ok"]:
            pa = sp1["result"]["potentially_affected"]
            lines.append(f"Around the change polygon (300 m): {pa['pipes']} water pipes, {pa['lights']} streetlights, {pa['facilities']} facilities.")
        if sp2 and sp2["ok"]:
            pa = sp2["result"]["potentially_affected"]
            lines.append(f"Around the suspected leak (400 m): {pa['pipes']} pipes, {pa['lights']} streetlights, {pa['facilities']} facilities; corridors: {', '.join(sp2['result']['road_corridors']) or 'none'}.")
        ch = self.p.store.get(S.CHANGES, self.ctx.state["focus_change"]) if self.ctx.state.get("focus_change") else None
        c = geo.centroid(ch["geom"]) if ch else (46.685, 24.6935)
        return {"complete": f["ok"], "map": self._view(c[0], c[1], 16, "Extracted features"), "layers": ["Riyadh_Extracted_Features", "Riyadh_Change_Detection", "Riyadh_Water_Network"],
                "narrative": lines + ["Measurements come from the spatial tools, not from the language model."]}

    def s4(self, trace, auto):
        det_ids = [self.ctx.state.get("demo_leak_detection")] + [d for d in self.ctx.state.get("last_detections", []) if d != self.ctx.state.get("demo_leak_detection")]
        r = self._tool(trace, "create_incidents_from_detections", detection_ids=[d for d in det_ids if d])
        inc = self._leak_incident()
        if inc:
            self.ctx.state["focus_incident"] = inc["id"]
        ex = self._tool(trace, "executive_summary")
        lines = []
        if r["ok"]:
            lines.append(f"{len(r['result']['created'])} incident(s) created from detections (status Open - no external action yet).")
        if ex["ok"]:
            k = ex["result"]["kpis"]
            top = ex["result"]["ranked_incidents"][0] if ex["result"]["ranked_incidents"] else None
            lines.append(f"KPIs recomputed: {k['open_incidents']} open incidents, {k['critical_incidents']} critical, {k['suspected_water_leaks']} suspected leaks, hotspots: {', '.join(h['area'] for h in ex['result']['hotspots'][:3])}.")
            if top:
                lines.append(f"Highest urgency: {top['incident_id']} ({top['priority']}, risk {top['risk_score']}) - {'; '.join(top['evidence'])}.")
            for rec in ex["result"]["recommendations"][:2]:
                lines.append(f"Recommendation: {rec['incident_id']} -> {rec['recommended_action']}.")
        c = geo.centroid(inc["geom"]) if inc else (46.685, 24.6935)
        return {"complete": bool(inc), "map": self._view(c[0], c[1], 14, "Hotspot / ranked incidents"), "layers": ["Riyadh_Operational_Incidents"], "narrative": lines, "incident_id": inc["id"] if inc else None}

    def s5(self, trace, auto):
        inc = self._leak_incident()
        if not inc:
            return {"complete": False, "narrative": ["Run scene 4 first."], "map": None}
        self.ctx.state["focus_incident"] = inc["id"]
        wos = [w for w in self.p.store.query(S.WORK_ORDERS, Incident_ID=inc["id"]) if w["attrs"]["Status"] not in ("Completed", "Cancelled")]
        lines = []
        awaiting = False
        if not wos:
            r = self._tool(trace, "propose_work_order")
            if r["ok"]:
                a = r["result"]["approval"]
                lines.append(f"Proposed work order for {inc['id']} - approval {a['Approval_ID']} is waiting. Nothing exists in the system of record yet.")
                awaiting = True
                if auto:
                    self._approve(a["Approval_ID"], trace)
                    wos = self.p.store.query(S.WORK_ORDERS, Incident_ID=inc["id"])
                    lines.append(f"Operator approved -> work order {wos[-1]['id']} created and confirmed by read-back.")
                    awaiting = False
            else:
                lines.append(r["error"])
        if wos and not wos[-1]["attrs"]["Assigned_Worker"]:
            self.ctx.state["focus_work_order"] = wos[-1]["id"]
            r = self._tool(trace, "propose_field_assignment", work_order_id=wos[-1]["id"])
            if r["ok"]:
                w, a = r["result"]["recommended_worker"], r["result"]["approval"]
                lines.append(f"Recommended team/worker: {w['name']} ({w['team']}) - {w['rationale']}. Approval {a['Approval_ID']} waiting.")
                awaiting = True
                if auto:
                    self._approve(a["Approval_ID"], trace)
                    lines.append(f"Operator approved -> {w['name']} assigned; task appears in their portal.")
                    awaiting = False
        elif wos:
            lines.append(f"Work order {wos[-1]['id']} is assigned to {wos[-1]['attrs']['Assigned_Worker']}.")
        wos = self.p.store.query(S.WORK_ORDERS, Incident_ID=inc["id"])
        done = bool(wos and wos[-1]["attrs"]["Assigned_Worker"])
        if done:
            self.ctx.state["focus_work_order"] = wos[-1]["id"]
        c = geo.centroid(inc["geom"])
        return {"complete": done, "awaiting_approval": awaiting and not done, "map": self._view(c[0], c[1], 16, "Work order location"), "layers": ["Riyadh_Work_Orders", "Riyadh_Field_Workers"],
                "narrative": lines + (["Approve in the Approval panel, then press 'Run scene' again."] if awaiting and not done else [])}

    def s6(self, trace, auto):
        inc = self._leak_incident()
        wos = self.p.store.query(S.WORK_ORDERS, Incident_ID=inc["id"]) if inc else []
        if not wos or not wos[-1]["attrs"]["Assigned_Worker"]:
            return {"complete": False, "narrative": ["No assigned work order yet - finish scene 5."], "map": None}
        wo = wos[-1]
        lines = [f"Task {wo['id']} is in {wo['attrs']['Assigned_Worker']}'s Field Worker Portal (open the Field tab to submit real evidence, or let the simulator respond)."]
        vers = self.p.store.query(S.VERIFICATION, Incident_ID=inc["id"])
        if not vers and auto:
            res = self.p.simulate_field_response(wo["id"])
            lines.append(f"SIMULATED worker submitted evidence: outcome {res['outcome']} ({res['distance_m']:.0f} m from the detection).")
        v = self._tool(trace, "verify_outcome", incident_id=inc["id"])
        if v["ok"] and v["result"]["verified"]:
            lines.append(v["result"]["agent_assessment"])
        c = geo.centroid(inc["geom"])
        return {"complete": bool(v["ok"] and v["result"]["verified"]), "map": self._view(c[0], c[1], 17, "Field verification"), "layers": ["Riyadh_Field_Verification"], "narrative": lines,
                "worker_id": wo["attrs"]["Assigned_Worker"], "work_order_id": wo["id"]}

    def s7(self, trace, auto):
        inc = self._leak_incident()
        if not inc:
            return {"complete": False, "narrative": ["Run the previous scenes first."], "map": None}
        lines = []
        v = self._tool(trace, "verify_outcome", incident_id=inc["id"])
        if not (v["ok"] and v["result"]["verified"]):
            return {"complete": False, "narrative": ["No field verification yet - finish scene 6."], "map": None}
        cur = self.p.store.get(S.INCIDENTS, inc["id"])["attrs"]
        if auto and cur["Status"] == "Confirmed":
            wos = self.p.store.query(S.WORK_ORDERS, Incident_ID=inc["id"])
            res = self.p.simulate_field_response(wos[-1]["id"], repair=True)
            lines.append(f"SIMULATED crew reported the repair ({res['incident_status']}).")
            cur = self.p.store.get(S.INCIDENTS, inc["id"])["attrs"]
        if cur["Status"] in ("Repair Reported", "Rejected"):
            r = self._tool(trace, "propose_incident_closure", incident_id=inc["id"])
            if r["ok"] and auto:
                self._approve(r["result"]["approval"]["Approval_ID"], trace)
                lines.append("Closure approved by operator and confirmed by the system.")
            elif r["ok"]:
                lines.append(f"Closure proposed ({r['result']['approval']['Approval_ID']}); approve it to close the incident.")
        ev = self._tool(trace, "evaluate_outcomes", recalibrate=True)
        if ev["ok"]:
            e = ev["result"]["evaluation"]
            w = e["categories"]["water"]
            lines.append(f"Learning: {e['total_verified']} verified outcomes; water precision {w['precision']}, calibration x{w['calibration']} (configurable risk calibration - no model retraining).")
        self._tool(trace, "executive_summary")
        final = self.p.store.get(S.INCIDENTS, inc["id"])["attrs"]
        lines.append(f"Incident {inc['id']} final status: {final['Status']} (verification outcome: {final['Verification_Outcome']}).")
        c = geo.centroid(inc["geom"])
        return {"complete": final["Status"] in ("Resolved", "Closed - False Positive"), "map": self._view(c[0], c[1], 15, "Closed loop"), "layers": ["Riyadh_Operational_Incidents"], "narrative": lines}

    def s8(self, trace, auto):
        self.p.sim.scenario("king_fahd_lights")
        r = self._tool(trace, "predict_streetlight_failures", corridor="King Fahd Road")
        if not r["ok"]:
            return {"complete": False, "narrative": [r["error"]], "map": None}
        res = r["result"]
        lines = [f"{res['predicted_failures']} King Fahd Road streetlights exceed the failure-probability threshold (PREDICTED, not confirmed)."]
        cl = res["clusters"][0] if res["clusters"] else None
        c = (46.6735, 24.695)
        if cl:
            c = (cl["centroid"]["lon"], cl["centroid"]["lat"])
            lines.append(f"Cluster {cl['cluster_id']}: {cl['lights']} lights, mean probability {cl['mean_probability']:.0%}.")
        ids = [d["detection_id"] for d in res["detections"] if not cl or d["cluster_id"] == cl["cluster_id"]]
        i = self._tool(trace, "create_incidents_from_detections", detection_ids=ids)
        if i["ok"] and i["result"]["created"]:
            inc_id = i["result"]["created"][0]["incident_id"]
            self.ctx.state["focus_incident"] = inc_id
            self.ctx.state["demo_light_incident"] = inc_id
            lines.append(f"Incident {inc_id} created for preventive maintenance.")
        inc_id = self.ctx.state.get("demo_light_incident")
        if inc_id:
            wos = [w for w in self.p.store.query(S.WORK_ORDERS, Incident_ID=inc_id) if w["attrs"]["Status"] != "Completed"]
            if not wos:
                p = self._tool(trace, "propose_work_order", incident_id=inc_id)
                if p["ok"]:
                    aid = p["result"]["approval"]["Approval_ID"]
                    lines.append(f"Work order proposed ({aid}) - same approval gate as the water scenario.")
                    if auto:
                        self._approve(aid, trace)
                        wos = self.p.store.query(S.WORK_ORDERS, Incident_ID=inc_id)
            if wos and not wos[-1]["attrs"]["Assigned_Worker"]:
                a = self._tool(trace, "propose_field_assignment", work_order_id=wos[-1]["id"])
                if a["ok"] and auto:
                    self._approve(a["result"]["approval"]["Approval_ID"], trace)
                    wos = self.p.store.query(S.WORK_ORDERS, Incident_ID=inc_id)
                    lines.append(f"Assigned {a['result']['recommended_worker']['name']} (electrical).")
            if wos and wos[-1]["attrs"]["Assigned_Worker"] and auto:
                if not self.p.store.query(S.VERIFICATION, Incident_ID=inc_id):
                    res2 = self.p.simulate_field_response(wos[-1]["id"])
                    lines.append(f"SIMULATED inspection: {res2['outcome']}.")
                v = self._tool(trace, "verify_outcome", incident_id=inc_id)
                if v["ok"]:
                    lines.append(v["result"].get("agent_assessment", ""))
        return {"complete": True, "map": self._view(c[0], c[1], 14, "King Fahd Road cluster"), "layers": ["Riyadh_AI_Detections", "Riyadh_Infrastructure_Assets"], "narrative": lines}
