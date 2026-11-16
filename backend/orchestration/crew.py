"""NCCC digital crew: a multi-agent workforce that watches the feeds, hands findings over, and raises notifications.

An executive agent, an operations orchestrator and specialist
agents, each working at its own level and all sharing one operational context (the feature store).

    Faisal  (Executive)   escalates critical items, writes the executive brief
    Mansour  (Operations)  triages detections into incidents and coordinates the specialists
    Sarah   (Specialist)  water faults and leaks from pressure/flow sensors
    Abdullah    (Specialist)  asset health: streetlight failure prediction
    Zayed  (Specialist)  urban change from imagery epochs
    Reem    (Specialist)  service impact: what is near / affected
    Turki  (Specialist)  field operations: work orders, dispatch, closure
    Maha  (Specialist)  performance: verification outcomes and learning

Every agent calls the SAME validated tools as the chat agent. Consequential steps (work orders, dispatch, closure) are only
PROPOSED; a human approves them, so automation raises notifications and recommendations but never acts on its own.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime

from backend.gis import geo
from backend.gis import schema as S
from backend.gis.store import utcnow
from backend.mobility import jobs as mob_jobs
from backend.mobility import rules as mob_rules
from backend.mobility import sources as mobility_sources
from backend.mobility import road_impact, traffic, wording
from backend.services import learning, lifecycle, mobility_numbers
from backend.services.synthetic import AREAS
from backend.tools import executive, registry
from backend.tools import mobility as mob
from backend.tools.common import ToolContext, severity_of
from backend.workflows.actions import NO_REPAIR_TYPES

log = logging.getLogger("geoai.crew")

SEV_RANK = {"Critical": 4, "High": 3, "Medium": 2, "Low": 1, "Info": 0}
ACTIVE_DET = ("Suspected", "Predicted", "Candidate")
CLUSTER_M = 300.0                    # citizen reports closer than this belong together (and to a fault found within it)
LINK_M = 450.0                       # a report this close to an open incident of the same kind is evidence for it
CLOSED_INC = ("Resolved", "Closed - False Positive")
AUTO_PROPOSE = ("P1", "P2")          # incidents at these priorities get an automatic work-order proposal (still needs approval)
# mobility: the alert goes out with these while the simulation runs; mobility_result replaces them with the numbers
CALCULATING = "Noura is calculating the road impact."
CALC_TRAIL = "Calculating the road impact (modelled); the proposed plan follows"
RESTARTED = "The server stopped while the road impact was being calculated; the simulation has been started again"
CALC_REPAIR = "Noura is calculating the road impact of the repair"


@dataclass(frozen=True)
class AgentDef:
    id: str
    name: str
    role: str
    tier: str            # executive | operations | specialist
    focus: str
    color: str
    tools: tuple[str, ...]


AGENTS: tuple[AgentDef, ...] = (
    AgentDef("faisal", "Faisal", "Executive GeoCoworker", "executive", "Escalates critical risk and briefs leadership", "#1fb36b", ("executive_summary",)),
    AgentDef("mansour", "Mansour", "Operations GeoCoworker", "operations", "Triages findings into incidents and coordinates the crew", "#2d8cff",
             ("create_incidents_from_detections", "rank_incidents", "list_incidents", "get_incident", "count_incidents")),
    AgentDef("sarah", "Sarah", "Fault & Leak GeoCoworker", "specialist", "Watches pressure and flow sensors for water faults", "#9b6cff", ("sensor_intelligence", "detect_water_leaks")),
    AgentDef("abdullah", "Abdullah", "Asset Health GeoCoworker", "specialist", "Predicts streetlight failures and monitors pole health", "#ff8a2b", ("predict_streetlight_failures", "monitor_poles")),
    AgentDef("zayed", "Zayed", "Change & Planning GeoCoworker", "specialist", "Urban change and visual distortion from imagery epochs", "#ff5a5f", ("detect_imagery_changes", "extract_geoai_features", "detect_visual_distortion", "analyze_land_use")),
    AgentDef("reem", "Reem", "Service Impact GeoCoworker", "specialist", "Finds the facilities and services around each finding", "#22c7b8", ("spatial_analysis", "feeds_summary")),
    AgentDef("turki", "Turki", "Field Operations GeoCoworker", "specialist", "Prepares work orders, dispatch and closure", "#f2b233",
             ("propose_work_order", "propose_work_orders_bulk", "propose_field_assignment", "propose_incident_closure", "propose_asset_status_change", "propose_traffic_plan")),
    AgentDef("maha", "Maha", "Performance GeoCoworker", "specialist", "Compares field results with predictions and learns", "#4aa3ff", ("verify_outcome", "evaluate_outcomes")),
    # the mobility specialists (Plan 3). Their traffic numbers are modelled, not measured.
    AgentDef("nasser", "Nasser", "Traffic GeoCoworker", "specialist", "Watches the traffic state and road incidents", "#e0559a", ("traffic_state", "detect_traffic_incidents")),
    AgentDef("noura", "Noura", "Mobility Simulation GeoCoworker", "specialist", "Simulates closures and events, compares response strategies, checks hospital access", "#7cc242",
             ("simulate_closure", "compare_closure_strategies", "simulate_event", "hospital_access")),
    AgentDef("fahad", "Fahad", "Road Safety & Assets GeoCoworker", "specialist", "Adds accident history and road-asset condition, ranks maintenance priority", "#c98a3b", ("road_safety_context",)),
)
BY_ID = {a.id: a for a in AGENTS}
AGENT_FOR_TOOL = {t: a.id for a in AGENTS for t in a.tools}
DETECTOR = {"water": "sarah", "lighting": "abdullah", "change": "zayed", "distortion": "zayed", "land_use": "zayed", "mobility": "nasser"}


def agent_for_tool(tool: str) -> str:
    base = tool.split(".")[0]
    return AGENT_FOR_TOOL.get(base, "mansour")


def _iso_minus(seconds: int) -> str:
    from datetime import datetime, timedelta, timezone
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")


class Crew:
    def __init__(self, platform):
        self.p = platform
        self.ctx = ToolContext(platform, "crew")
        self.lock = threading.RLock()
        self.cycles = 0
        self.autopilot = False
        self.interval = 60.0
        self.simulate_field = False        # real investigators answer through the field page; turn this on for a demo without one
        self.last_cycle: dict | None = None
        self.activity: deque = deque(maxlen=60)
        self.working: dict[str, str] = {}      # agent id -> what it is doing right now
        self.last: dict[str, dict] = {}        # agent id -> {"action", "at"}
        self._thread: threading.Thread | None = None
        self.epoch: str | None = None          # set at the first scan: records that exist before it are history, not news
        self._scan_i = 0
        self._seen_reports: set = set()
        self._known_reports: dict = {}        # incident id -> citizen reports already mentioned in an alert
        self._counts: dict | None = None
        self.record_error: dict | None = None  # the last automatic scan that the system of record refused: {"at", "message"}; cleared by the next good scan
        self._impact_pending: list = []        # (incident id, category, road) whose road-impact run is queued once the scan's batch has been sent

    # ---- bookkeeping ---------------------------------------------------------------------------------------
    def reset(self) -> None:
        self.autopilot = False
        self.cycles = 0
        self.last_cycle = None
        self.activity.clear()
        self.working.clear()
        self.last.clear()
        self.epoch = None
        self._scan_i = 0
        self._seen_reports.clear()
        self._known_reports.clear()
        self._counts = None

    def _step(self, steps: list, agent: str, action: str, detail: str = "", ref: str = "") -> dict:
        s = {"agent": agent, "action": action, "detail": detail, "ref": ref, "at": utcnow()}
        steps.append(s)
        self.activity.appendleft(s)
        self.last[agent] = {"action": action if not detail else f"{action}: {detail}", "at": s["at"]}
        self.p.audit.log("crew", f"{BY_ID[agent].name}: {action}", "crew", ref if ref.startswith("INC-") else "", detail, "", "N/A", actor=f"agent:{agent}")
        return s

    def _tool(self, name: str, **args) -> dict:
        self.working[agent_for_tool(name)] = name
        try:
            return registry.execute(self.ctx, name, {k: v for k, v in args.items() if v is not None})
        finally:
            self.working.pop(agent_for_tool(name), None)

    def _approval_exists(self, action: str, target: str, statuses: tuple[str, ...]) -> bool:
        return any(f["attrs"]["Status"] in statuses for f in self.p.store.query(S.APPROVALS, Action_Type=action, Target=target))

    # ---- notifications -------------------------------------------------------------------------------------
    def notify(self, kind: str, severity: str, title: str, message: str, agent: str, trail: list, ref: str, incident: str = "", approval: str = "",
               area: str = "", lonlat: tuple | None = None) -> dict | None:
        st = self.p.store
        if st.query(S.NOTIFICATIONS, Kind=kind, Ref_ID=ref):
            return None                                              # one notification per (kind, subject): automation never repeats itself
        nid = st.next_id("NTF")
        rec = {"Notif_ID": nid, "Kind": kind, "Severity": severity, "Title": title, "Message": message, "Agent": agent, "Trail": json.dumps(trail), "Ref_ID": ref,
               "Incident_ID": incident, "Approval_ID": approval, "Area_Name": area, "Lon": lonlat[0] if lonlat else None, "Lat": lonlat[1] if lonlat else None,
               "Status": "New", "Created": utcnow(), "Updated": utcnow()}
        st.upsert(S.NOTIFICATIONS, rec)
        return rec

    def notifications(self, status: str | None = None, limit: int = 60) -> list[dict]:
        pend = {a["Approval_ID"]: a for a in self.p.approvals.all()}
        scn = {}                                                    # the latest simulation of each incident, so an alert can show its impact on the map
        for f in sorted(self.p.store.all(S.SCENARIOS), key=lambda r: r["id"]):
            if f["attrs"].get("Subject_ID"):
                scn[f["attrs"]["Subject_ID"]] = f["attrs"]
        rows = []
        for f in self.p.store.all(S.NOTIFICATIONS):
            a = dict(f["attrs"])
            if status and a["Status"] != status:
                continue
            a["Trail"] = json.loads(a["Trail"] or "[]")
            ap = pend.get(a["Approval_ID"])
            a["approval"] = {"id": ap["Approval_ID"], "status": ap["Status"], "summary": ap["Summary"], "expected": ap["Expected_Result"],
                             "worker_id": json.loads(ap["Payload"]).get("worker_id", "") if ap["Action_Type"] == "assign_worker" else ""} if ap else None
            inc = self.p.store.get(S.INCIDENTS, a["Incident_ID"]) if a["Incident_ID"] else None
            a["incident_status"] = inc["attrs"]["Status"] if inc else ""
            sc = scn.get(a["Incident_ID"]) if a["Incident_ID"] else None
            a["scenario_id"], a["scenario_status"] = (sc["Scenario_ID"], sc.get("Status") or "") if sc else ("", "")
            a["scenario_type"] = sc.get("Scenario_Type") or "" if sc else ""
            a["lifecycle"] = lifecycle.position(self.p.store, a["Incident_ID"]) if a["Incident_ID"] else None
            a["active_work_order"] = next((w["id"] for w in self.p.store.query(S.WORK_ORDERS, Incident_ID=a["Incident_ID"]) if w["attrs"]["Status"] in ("Created", "Assigned", "In Progress")), "") if inc else ""
            rows.append(a)
        rows.sort(key=lambda r: (r["Created"], r["Notif_ID"]), reverse=True)
        return rows[:limit]

    def acknowledge(self, nid: str | None = None) -> int:
        n = 0
        for f in self.p.store.all(S.NOTIFICATIONS):
            if (nid is None or f["id"] == nid) and f["attrs"]["Status"] == "New":
                self.p.store.update(S.NOTIFICATIONS, f["id"], Status="Acknowledged", Updated=utcnow())
                n += 1
        return n

    # ---- the automation cycle ---------------------------------------------------------------------------------
    def run_cycle(self, deep: bool | str = False, simulate_field: bool | None = None, scope: set | frozenset | None = None) -> dict:
        """One pass of the whole crew. Idempotent: running it twice without new data changes nothing.
        deep=True also scans satellite imagery for the next area in rotation; deep='<area>' scans that area.
        scope limits the WATCH and TRIAGE steps to some use cases ({"water"}, {"lighting"}, {"distortion"}, {"land_use"}, {"change"}); None watches everything.
        A simulated event passes its own use case, so only that feed reacts. Findings of other use cases wait for the next full scan.
        The whole scan is one batch: the system of record gets one request per layer at the end, and a refusal undoes the whole scan.
        Mobility simulations are started after that batch, on the background worker: the scan never waits for one."""
        with self.lock:
            self._impact_pending = []                     # filled by the scan; a scan the system of record refuses queues nothing
            out = self._scan(deep, simulate_field, scope)
            out["steps"].extend(self._queue_road_impacts())
            if scope is None or "mobility" in scope:
                out["steps"].extend(self._mobility_followup())
                try:
                    mobility_numbers.expire_closures(self.p)      # a closure whose window has passed becomes "Ended"; the record stays
                except Exception as exc:  # noqa: BLE001  never stops a scan
                    log.warning("could not end closures whose window has passed: %s", exc)
            return out

    def _scan(self, deep: bool | str, simulate_field: bool | None, scope: set | frozenset | None) -> dict:
        with self.lock, self.p.store.batch():
            self.cycles += 1
            if self.epoch is None:
                self.epoch = utcnow()
            steps: list = []
            raised: list = []
            sim_field = self.simulate_field if simulate_field is None else simulate_field
            st = self.p.store
            want = lambda cat: scope is None or cat in scope  # noqa: E731

            # 1. WATCH - the specialists look at their own feeds
            if want("water"):
                r = self._tool("detect_water_leaks")
                if r["ok"]:
                    n = r["result"]["suspected_leaks"]
                    self._step(steps, "sarah", "Scanned water sensors", f"{r['result']['sensors_evaluated']} sensors, {n} suspected leak(s)" if n else f"{r['result']['sensors_evaluated']} sensors, all normal")
            if want("lighting"):
                lamp_txt = "lamps not checked"
                r = self._tool("predict_streetlight_failures")
                if r["ok"]:
                    n = r["result"]["predicted_failures"]
                    lamp_txt = f"{r['result']['lights_evaluated']} lamps, {n} at risk of failing" if n else f"{r['result']['lights_evaluated']} lamps, none at risk"
                pr = self._tool("monitor_poles")
                pole_txt = f"{pr['result']['flagged']} of {pr['result']['poles_evaluated']} poles beyond tilt/corrosion limits" if pr["ok"] and pr["result"]["flagged"] else "poles sound"
                self._step(steps, "abdullah", "Checked streetlights and poles", f"{lamp_txt}; {pole_txt}")
            if want("distortion"):
                for ar in AREAS:
                    r = self._tool("detect_visual_distortion", area=ar)
                    if r["ok"] and r["result"]["flagged"]:
                        self._step(steps, "zayed", "Compared building shapes between satellite dates", f"{ar}: {r['result']['flagged']} building(s) with visual distortion")
            if want("land_use"):
                for ar in AREAS:
                    if st.get(S.CONFIG, f"landuse.watch.{ar}"):
                        r = self._tool("analyze_land_use", area=ar)
                        if r["ok"] and r["result"]["violations"]:
                            self._step(steps, "zayed", "Checked land use against zoning", f"{ar}: {r['result']['violations']} possible zoning violation(s)")
            if deep and want("change"):
                names = list(AREAS)
                area = deep if isinstance(deep, str) and deep in AREAS else names[self._scan_i % len(names)]
                self._scan_i += 1
                r = self._tool("detect_imagery_changes", area=area)
                if r["ok"]:
                    found = sum(1 for c in r["result"]["changes"] if c["significant"])
                    self._step(steps, "zayed", "Compared satellite imagery", f"{area}: {found} significant change(s)" if found else f"{area}: no significant change")
            if want("mobility"):
                self._mobility_watch(steps)

            # 1b. FEEDS - citizen reports arrive alongside the sensors
            if scope is None:
                self._citizen_detections(steps)

            # 2. TRIAGE - Mansour turns every new finding into an incident
            # a change that is also a zoning violation becomes ONE incident (the land-use one), not an urban-change review as well
            violation_of = {f["attrs"]["Related_Asset_ID"] for f in st.all(S.DETECTIONS) if f["attrs"]["Category"] == "land_use" and f["attrs"]["Status"] in ACTIVE_DET}
            waiting = [f["id"] for f in st.all(S.DETECTIONS) if f["attrs"]["Status"] in ACTIVE_DET and want(f["attrs"]["Category"])
                       and not (f["attrs"]["Category"] == "change" and f["attrs"]["Related_Asset_ID"] in violation_of)
                       and not (f["attrs"]["Incident_ID"] and st.get(S.INCIDENTS, f["attrs"]["Incident_ID"]))]
            created: list = []
            if waiting:
                r = self._tool("create_incidents_from_detections", detection_ids=waiting)
                if r["ok"]:
                    created = r["result"]["created"]
                    self._step(steps, "mansour", "Opened incidents", f"{len(created)} new incident(s) from {len(waiting)} finding(s)")

            self._link_reports(steps)

            # 3. ASSESS + PREPARE - for each new incident: Reem sizes the impact, Turki prepares the response, a notification goes out
            worst = "Info"
            for c in created:
                iid = c["incident_id"]
                inc = st.get(S.INCIDENTS, iid)["attrs"]
                cat = inc["Category"]
                det = DETECTOR[cat]
                if cat == "mobility" and inc["Incident_Type"] != "Traffic Incident":
                    det = "noura"                                    # closure requests and event notices are her feed
                from_citizens =any((st.get(S.DETECTIONS, d) or {"attrs": {"Source": ""}})["attrs"]["Source"].startswith("Citizen") for d in c["detections"])
                nrep = len(st.query(S.CITIZEN, Linked_Incident=iid))
                self._known_reports[iid] = nrep
                if from_citizens:
                    det = "reem"
                    trail = [{"agent": "reem", "did": f"{nrep} citizen reports clustered in {inc['Area_Name']} with no sensor alarm"}]
                else:
                    trail = [{"agent": det, "did": self._found(cat, c, inc)}]
                trail.append({"agent": "mansour", "did": f"Opened {iid} - {c['priority']} / {c['severity']}, team {c['assigned_team']}"})
                if nrep and not from_citizens:
                    trail.append({"agent": "reem", "did": f"{nrep} citizen report(s) nearby back this up"})
                impact = ""
                r = self._tool("spatial_analysis", target_type="incident", target_id=iid, radius_m=300)
                if r["ok"]:
                    pa, res = r["result"]["potentially_affected"], r["result"]
                    names = [f["name"] for f in res["facilities"][:3]]
                    impact = f"{pa['facilities']} facilities, {pa['pipes']} pipes, {pa['lights']} streetlights within 300 m" + (f" (e.g. {', '.join(names)})" if names else "")
                    trail.append({"agent": "reem", "did": f"Impact: {impact}"})
                    self._step(steps, "reem", "Assessed impact", f"{iid}: {impact}", iid)
                apr = ""
                if cat == "mobility":                                # the plan waits for Noura's numbers: the alert goes out now and is updated by mobility_result
                    self._road_safety(steps, trail, iid)
                    trail.append({"agent": "noura", "did": CALC_TRAIL})
                elif c["priority"] in AUTO_PROPOSE:
                    r = self._tool("propose_work_order", incident_id=iid)
                    if r["ok"]:
                        apr = r["result"]["approval"]["Approval_ID"]
                        trail.append({"agent": "turki", "did": f"Prepared a work order ({apr}) and is waiting for your approval"})
                        self._step(steps, "turki", "Prepared work order", f"{iid} -> {apr}", iid)
                        if self._repair_near_road(st.get(S.INCIDENTS, iid)):
                            trail.append({"agent": "noura", "did": CALC_REPAIR})
                else:
                    trail.append({"agent": "turki", "did": "No dispatch needed yet - kept on watch"})
                sev = c["severity"]
                if sev == "Critical":
                    trail.append({"agent": "faisal", "did": "Escalated to executive level"})
                    self._step(steps, "faisal", "Escalated", f"{iid} is Critical", iid)
                worst = max((worst, sev), key=lambda s: SEV_RANK[s])
                pt = st.get(S.INCIDENTS, iid)["geom"]["coordinates"]
                kind = "change" if cat == "change" else "fault"
                msg = self._mob_message(inc, CALCULATING) if cat == "mobility" else inc["Description"][:420].rstrip() + ("..." if len(inc["Description"]) > 420 else "")
                n = self.notify(kind, sev, self._title(cat, c, inc), msg, det, trail, iid, iid, apr, inc["Area_Name"], (pt[0], pt[1]))
                if n:
                    raised.append(n)

            self._corroboration(steps, raised, {c['incident_id'] for c in created})

            # 4. FOLLOW THROUGH - dispatch, simulated site visits, verification results, closure
            for f in st.all(S.WORK_ORDERS):
                a = f["attrs"]
                if a["Status"] == "Created" and not a["Assigned_Worker"] and not self._approval_exists("assign_worker", f["id"], ("Proposed", "Rejected")):
                    r = self._tool("propose_field_assignment", work_order_id=f["id"])
                    if r["ok"]:
                        w, apr = r["result"]["recommended_worker"], r["result"]["approval"]["Approval_ID"]
                        inc = st.get(S.INCIDENTS, a["Incident_ID"])
                        self._step(steps, "turki", "Recommended a crew", f"{w['name']} for {f['id']} ({w['rationale']})", a["Incident_ID"])
                        n = self.notify("dispatch", inc["attrs"]["Severity"], f"Dispatch {w['name']} to {a['Incident_ID']}", f"{w['name']} ({w['team']}) is the best fit: {w['rationale']}.",
                                        "turki", [{"agent": "turki", "did": f"Ranked field crews by skill, distance and workload - {w['name']} wins ({w['score']})"}],
                                        f["id"], a["Incident_ID"], apr, inc["attrs"]["Area_Name"], tuple(inc["geom"]["coordinates"]))
                        if n:
                            raised.append(n)
            self._rejected_closures(steps)
            if sim_field:
                for f in st.all(S.WORK_ORDERS):
                    a = f["attrs"]
                    vers = st.query(S.VERIFICATION, Work_Order_ID=f["id"])
                    last_v = vers[-1]["attrs"]["Verification_Status"] if vers else None
                    
                    if a["Status"] == "Assigned" and (not vers or last_v == "Requires Further Inspection"):
                        self._visit(steps, f["id"], False)
                    elif a["Status"] == "In Progress" and (not vers or last_v != "Repaired") and a.get("Incident_Type") not in NO_REPAIR_TYPES:
                        self._visit(steps, f["id"], True)                 # a closure or an event plan has nothing to repair: confirmed is enough
            self._field_results(steps, raised)

            # 5. BRIEF - Faisal summarises when something important happened
            if created and SEV_RANK[worst] >= SEV_RANK["High"]:
                k = executive.compute_kpis(st)
                pending = len(self.p.approvals.pending())
                msg = f"{len(created)} new incident(s); {k['open_incidents']} open, {k['critical_incidents']} critical; {pending} decision(s) waiting for you."
                self._step(steps, "faisal", "Briefed leadership", msg)
                n = self.notify("digest", worst, "Executive brief", msg, "faisal", [{"agent": "faisal", "did": msg}], f"cycle-{self.cycles}")
                if n:
                    raised.append(n)

            self.last_cycle = {"cycle": self.cycles, "at": utcnow(), "steps": steps, "new_notifications": [n["Notif_ID"] for n in raised], "new_incidents": [c["incident_id"] for c in created], "deep": deep}
            return self.last_cycle

    def _change_of(self, c: dict):
        """The imagery change record behind a change incident's first detection."""
        st = self.p.store
        for d in c["detections"]:
            det = st.get(S.DETECTIONS, d)
            if det and det["attrs"]["Category"] == "change":
                return st.get(S.CHANGES, det["attrs"]["Related_Asset_ID"])
        return None

    def _title(self, cat: str, c: dict, inc: dict) -> str:
        ch = self._change_of(c) if cat == "change" else None
        if ch:
            return f"Urban change: {ch['attrs']['Change_Type'].replace(' (candidate)', '').split(' (')[0].lower()} - {inc['Area_Name']}"
        return f"{c['type']} - {inc['Area_Name']}"

    def _found(self, cat: str, c: dict, inc: dict) -> str:
        ch = self._change_of(c) if cat == "change" else None
        if ch:
            a = ch["attrs"]
            return f"Compared the two satellite dates and found {a['Change_Type'].replace(' (candidate)', '').lower()} of about {a['Area_Sqm']:,.0f} m² in {inc['Area_Name']}"
        if cat == "mobility":
            return {"Planned Road Closure": f"Closure request received for {inc['Area_Name']}",
                    "Major Event Traffic Plan": f"Event notice received for {inc['Area_Name']}"}.get(c["type"], f"Road report received: blocked lanes on {inc['Area_Name']}")
        return f"Detected: {c['type']} in {inc['Area_Name']}"

    # ---- mobility: watch, simulate in the background, then decide ------------------------------------------------
    @staticmethod
    def _mob_message(inc: dict, tail: str) -> str:
        d = inc["Description"]
        return d[:420].rstrip() + ("..." if len(d) > 420 else "") + " " + tail

    def _mobility_watch(self, steps: list) -> None:
        """Nasser reads the road reports and the modelled traffic state; Noura reads closure requests and event notices."""
        r = self._tool("detect_traffic_incidents")
        n = r["result"]["detected"] if r["ok"] else 0
        txt = f"{n} new road report(s)" if n else "no new road reports"
        h = mob.riyadh_hour()
        if h in traffic.status()["hours_ready"]:                     # only hours the model already holds: the scan never builds the traffic model
            t = self._tool("traffic_state", hour=h, top_n=1)
            if t["ok"]:
                busy = t["result"]["counts"]["heavy"] + t["result"]["counts"]["stopped"]
                txt += f"; {busy} road section(s) heavy or stopped at {h:02d}:00 (modelled)" if busy else f"; no abnormal congestion at {h:02d}:00 (modelled)"
        self._step(steps, "nasser", "Checked road reports and traffic", txt)
        made = self._mobility_requests()
        if made["closures"] or made["events"]:
            self._step(steps, "noura", "Read closure requests and event notices", f"{made['closures']} closure request(s), {made['events']} event notice(s)")

    def _mobility_requests(self) -> dict:
        """Each closure request and each new event notice becomes one finding (once). They are SYNTHETIC demo rows."""
        st, out = self.p.store, {"closures": 0, "events": 0}
        roads = None

        def finding(dtype, where, base, source, ref, evidence, pt):
            did = st.next_id("DET")
            risk = learning.apply_calibration(st, "mobility", base)
            st.upsert(S.DETECTIONS, {"Detection_ID": did, "Detection_Type": dtype, "Location": where, "Confidence": 0.95, "Severity": severity_of(risk), "Risk_Score": risk,
                                     "Base_Risk_Score": base, "Detection_Date": utcnow(), "Source": source, "Status": "Candidate", "Related_Asset_ID": ref, "Pipeline_ID": "",
                                     "Area_Name": where, "Category": "mobility", "Cluster_ID": "", "Evidence": evidence, "Incident_ID": "", "Data_Classification": S.SYNTHETIC},
                      geo.point(*pt))
            return did

        for f in sorted(st.all(S.CLOSURES), key=lambda f: f["id"]):
            a = f["attrs"]
            if a.get("Status") != "Requested" or st.query(S.DETECTIONS, Related_Asset_ID=f["id"]):
                continue
            if roads is None:
                roads = {r["id"]: r for r in mobility_sources.load_network()[0]}
            seg = roads.get(next((i for i in (a.get("Segment_IDs") or "").split(",") if i), ""))
            full = a.get("Full_Closure") == "Yes"
            try:
                hours = (datetime.fromisoformat(a["End_Time"]) - datetime.fromisoformat(a["Start_Time"])).total_seconds() / 3600
            except (TypeError, ValueError):
                hours = 8.0
            road = a.get("Corridor") or "the road"
            line = f["geom"]["coordinates"] if f["geom"]["type"] == "LineString" else f["geom"]["coordinates"][0]
            what = "full closure" if full else f"closure of {int(a.get('Lanes_Closed') or 1)} lane(s)"
            finding("Road Closure Request", road, mob_rules.closure_risk(seg["road_class"] if seg else "", full, hours), "Closure request (SYNTHETIC)", f["id"],
                    f"REQUESTED: {what} of {road} ({a.get('Section') or 'one section'}), {str(a.get('Start_Time')).replace('T', ' ')} to {wording.clock(a.get('End_Time'))}, "
                    f"for {(a.get('Reason') or 'road works').lower()} (closure request, SYNTHETIC). Needs a traffic plan before it goes ahead.", line[len(line) // 2][:2])
            out["closures"] += 1
        for f in sorted(st.all(S.EVENT_NOTICES), key=lambda f: f["id"]):
            a = f["attrs"]
            if a.get("Status") != "New":
                continue
            people = int(a.get("Attendance") or 0)
            did = finding("Major Event", a.get("Venue") or "the venue", mob_rules.event_risk(people), "Event notice (SYNTHETIC)", f["id"],
                          f"NOTIFIED: {a.get('Name') or 'An event'} at {a.get('Venue')}, about {people:,} people, {str(a.get('Start_Time')).replace('T', ' ')} to "
                          f"{wording.clock(a.get('End_Time'))} (event notice, SYNTHETIC). Needs a traffic plan.", f["geom"]["coordinates"][:2])
            st.update(S.EVENT_NOTICES, f["id"], Status="Detected", Detection_ID=did)
            out["events"] += 1
        return out

    def _road_safety(self, steps: list, trail: list, iid: str) -> None:
        """Fahad adds the accident history and road-asset condition of the road section (SYNTHETIC inputs)."""
        st = self.p.store
        row = (mob.subject_of(st, st.get(S.INCIDENTS, iid))["row"] or {"attrs": {}})["attrs"]
        seg = row.get("Segment_ID") or next((i for i in (row.get("Segment_IDs") or "").split(",") if i), "")
        r = self._tool("road_safety_context", segment_id=seg) if seg else {"ok": False}
        if not r["ok"]:
            return
        acc, cond = r["result"]["accidents"], r["result"]["asset_condition"]
        line = f"Road safety (SYNTHETIC): {acc['accidents']} recorded accident(s) on this section in the last 12 months, {acc['severe']} severe"
        if cond["worst_condition"] is not None:
            line += f"; road-asset condition {cond['worst_condition']:g} of 100 ({cond['proposed_action']})"
        trail.append({"agent": "fahad", "did": line})
        self._step(steps, "fahad", "Added road-safety context", f"{iid}: {line}", iid)

    def _rejected_closures(self, steps: list) -> None:
        """A closure request whose traffic plan the operator rejected is recorded as Rejected."""
        st = self.p.store
        for f in st.query(S.APPROVALS, Action_Type="apply_traffic_plan", Status="Rejected"):
            try:
                cid = json.loads(f["attrs"]["Payload"] or "{}").get("closure_id")
            except ValueError:
                continue
            row = st.get(S.CLOSURES, cid) if cid else None
            if row and row["attrs"].get("Status") == "Requested":
                st.update(S.CLOSURES, cid, Status="Rejected", Updated=utcnow())
                self._step(steps, "turki", "Recorded rejected closure", f"{cid}: the plan was rejected, so the closure is not approved", f["attrs"].get("Incident_ID") or "")

    def _mobility_followup(self) -> list:
        """After a scan's batch is with the system of record: every open mobility incident that has no plan yet gets its simulation queued,
        or its waiting result handled. Returns the steps taken (a queued simulation reports later, through mobility_result)."""
        st, steps = self.p.store, []
        for f in sorted(st.all(S.INCIDENTS), key=lambda f: f["id"]):
            a = f["attrs"]
            if a["Category"] != "mobility" or a["Status"] != "Open" or st.query(S.APPROVALS, Action_Type="apply_traffic_plan", Target=f["id"]) \
                    or st.query(S.APPROVALS, Action_Type="create_work_order", Target=f["id"]):
                continue
            try:
                rows = sorted((r["attrs"] for r in st.query(S.SCENARIOS, Subject_ID=f["id"])), key=lambda r: r["Scenario_ID"])
                if any(r.get("Status") in ("Queued", "Running") for r in rows):
                    continue                                          # Noura is on it
                done = [r for r in rows if r.get("Status") == "Completed"]
                stopped = [r for r in rows if r.get("Status") == "Interrupted"]
                if done:
                    res = self.mobility_result(self.p.jobs.row(done[-1]["Scenario_ID"]))
                elif rows and (rows[-1].get("Status") != "Interrupted" or len(stopped) >= 2):
                    res = self.mobility_result(self.p.jobs.row(rows[-1]["Scenario_ID"]))      # failed, or interrupted twice: a plain field check instead
                else:
                    if stopped:
                        self._trail_note(f["id"], "noura", RESTARTED)
                    res = self._simulate(f)
                steps.extend((res or {}).get("steps", []))
            except Exception as exc:  # noqa: BLE001  one incident must never stop the others; the next scan tries again
                log.warning("mobility follow-up failed for %s: %s", f["id"], exc)
        return steps

    def resume_mobility(self) -> list:
        """At start-up, after Jobs.recover(): simulations a stopped server left behind are queued once more."""
        with self.lock:
            return self._mobility_followup()

    def _trail_note(self, iid: str, agent: str, text: str) -> None:
        st = self.p.store
        for n in st.query(S.NOTIFICATIONS, Kind="fault", Ref_ID=iid):
            trail = json.loads(n["attrs"]["Trail"] or "[]")
            if not any(t.get("did") == text for t in trail):
                at = next((i for i, t in enumerate(trail) if t.get("did") == CALC_TRAIL), len(trail))
                trail.insert(at, {"agent": agent, "did": text})
                st.update(S.NOTIFICATIONS, n["id"], Trail=json.dumps(trail), Updated=utcnow())

    def _simulate(self, inc: dict) -> dict | None:
        """Queue Noura's simulation for one mobility incident. Inputs come from its road report, closure request or event notice."""
        st, iid = self.p.store, inc["id"]
        sub = mob.subject_of(st, inc)
        row = (sub["row"] or {"attrs": {}})["attrs"]
        kind = sub["kind"]
        if kind == "incident":
            params = {"segment_id": row.get("Segment_ID"), "corridor": row.get("Corridor"), "lanes_blocked": row.get("Lanes_Blocked")}
        elif kind == "closure":
            params = {"corridor": row.get("Corridor"), "segment_ids": [i for i in (row.get("Segment_IDs") or "").split(",") if i] or None,
                      "start_time": row.get("Start_Time") or None, "end_time": row.get("End_Time") or None,
                      "lanes_closed": None if row.get("Full_Closure") == "Yes" else row.get("Lanes_Closed")}
        else:
            params = {"place": row.get("Venue"), "attendance": row.get("Attendance"), "start_time": row.get("Start_Time") or None, "end_time": row.get("End_Time") or None}
        try:
            if not sub["row"] or not kind:
                raise ValueError("the road report, closure request or event notice behind this incident was not found")
            self.p.jobs.submit(kind, {k: v for k, v in params.items() if v is not None}, iid, "noura", on_done=self.mobility_result,
                               name=f"{inc['attrs']['Incident_Type']}: {inc['attrs']['Area_Name']}")
        except Exception as exc:  # noqa: BLE001  unusable inputs, or ArcGIS Online would not take the row: the incident must not be stuck
            return self.mobility_result({"Scenario_ID": "", "Scenario_Type": kind, "Subject_ID": iid, "Status": "Failed", "Error": str(exc), "summary": {}})
        return None

    # ---- the cross-domain link: what a repair next to a road costs traffic -------------------------------------------
    def _repair_near_road(self, inc: dict) -> bool:
        """True when this incident's repair sits on a modelled road: the road-impact run is queued once the scan's batch has been sent."""
        rule = mob_rules.ROAD_IMPACT.get(inc["attrs"]["Category"])
        if not rule:
            return False
        try:
            road = road_impact.nearest_road(tuple(inc["geom"]["coordinates"][:2]), rule["radius_m"])
        except Exception as exc:  # noqa: BLE001  no road network is no reason to hold back the work order
            log.warning("could not look for a road near %s: %s", inc["id"], exc)
            return False
        if road:
            self._impact_pending.append((inc["id"], inc["attrs"]["Category"], road))
        return bool(road)

    def _queue_road_impacts(self) -> list:
        pending, self._impact_pending = getattr(self, "_impact_pending", []), []
        steps: list = []
        for iid, cat, road in pending:
            try:
                self.p.jobs.submit("road_impact", road_impact.params(cat, road), iid, "noura", on_done=self.mobility_result, name=f"Repair closure: {road['corridor']}")
            except Exception as exc:  # noqa: BLE001  the alert must not keep saying "calculating"
                res = self.mobility_result({"Scenario_ID": "", "Scenario_Type": "road_impact", "Subject_ID": iid, "Status": "Failed", "Error": str(exc), "summary": {}})
                steps.extend((res or {}).get("steps", []))
        return steps

    def _road_impact_result(self, row: dict, inc: dict) -> dict | None:
        """The road-impact run of a repair ended. The alert gets the line. While the work-order proposal is still waiting, the planned closure
        is added to it (one approval covers both); once it has been decided the line is information only."""
        st, iid, a, steps = self.p.store, inc["id"], inc["attrs"], []
        ok = row.get("Status") == "Completed"
        with st.batch():
            line = road_impact.line(row.get("summary") or {}) if ok else f"{wording.FAILED}{(row.get('Error') or mob_jobs.INTERRUPTED).strip().rstrip('.')}."
            notes = [n for n in st.query(S.NOTIFICATIONS, Ref_ID=iid) if n["attrs"]["Kind"] == "fault"]
            pend = [f for f in st.query(S.APPROVALS, Action_Type="create_work_order", Target=iid)
                    if f["attrs"]["Status"] == "Proposed" and "closure_plan" not in json.loads(f["attrs"]["Payload"] or "{}")] if ok else []
            shown = any(t.get("did") == line for n in notes for t in json.loads(n["attrs"]["Trail"] or "[]"))
            if shown and not pend:
                return None                                           # this result is already on the alert and there is nothing to add it to
            extra, amended = [], False
            if ok:
                if pend:
                    plan = road_impact.closure_plan(row["summary"], scenario_id=row.get("Scenario_ID") or "")
                    amended = self.p.approvals.amend(pend[-1]["id"], {"closure_plan": plan}, f" A planned closure ({road_impact.plan_text(plan)}) is recorded with it.")
                    if amended:
                        extra = [{"agent": "turki", "did": f"Added the planned closure ({road_impact.plan_text(plan)}) to work order proposal {pend[-1]['id']}; one approval covers both"}]
                if not amended:
                    extra = [{"agent": "noura", "did": "For information: the work order was decided before this result arrived, so no planned closure is recorded"}]
            self._step(steps, "noura", "Simulated the road impact of the repair" if ok else "Could not simulate the road impact of the repair", f"{iid}: {line}", iid)
            if amended:
                self._step(steps, "turki", "Added planned closure to the proposal", f"{iid} -> {pend[-1]['id']}", iid)
            for n in notes:
                trail = json.loads(n["attrs"]["Trail"] or "[]")
                at = next((i for i, t in enumerate(trail) if t.get("did") == CALC_REPAIR), None)
                if at is not None and shown:
                    del trail[at]                                     # the same numbers as an earlier run: said once
                elif at is not None:
                    trail[at] = {"agent": "noura", "did": line}
                elif not shown:
                    trail.append({"agent": "noura", "did": line})
                st.update(S.NOTIFICATIONS, n["id"], Message=self._mob_message(a, line), Trail=json.dumps(trail + extra), Updated=utcnow(),
                          **({"Status": "New"} if amended else {}))
        return {"incident_id": iid, "amended": amended, "steps": steps}

    def mobility_result(self, row: dict | None) -> dict | None:
        """A simulation ended (the worker calls this), or its result was found waiting by a scan. The alert gets the numbers and returns to New;
        Turki proposes the traffic plan. When the simulation failed or was interrupted the alert says why and Turki proposes a plain field check.
        Takes the crew lock first, then the store; never called while Jobs holds its own lock."""
        if not row:
            return None
        with self.lock:
            st, iid = self.p.store, row.get("Subject_ID") or ""
            inc = st.get(S.INCIDENTS, iid)
            if not inc or inc["attrs"]["Status"] in CLOSED_INC:
                return None
            if inc["attrs"]["Category"] != "mobility":
                return self._road_impact_result(row, inc) if row.get("Scenario_Type") == "road_impact" else None
            a, steps = inc["attrs"], []
            ok = row.get("Status") == "Completed"
            with st.batch():
                busy = self._approval_exists("create_work_order", iid, ("Proposed",)) or self._approval_exists("apply_traffic_plan", iid, ("Proposed",)) \
                    or any(w["attrs"]["Status"] in ("Created", "Assigned", "In Progress") for w in st.query(S.WORK_ORDERS, Incident_ID=iid))
                if ok:
                    line = wording.impact(row.get("Scenario_Type") or "", row.get("summary") or {}, row.get("Recommended") or "", row.get("Verdict") or "")
                    r = self._tool("propose_traffic_plan", incident_id=iid, scenario_id=row["Scenario_ID"]) if not busy else {"ok": False}
                    did = "Prepared the traffic plan ({apr}) and is waiting for your approval"
                else:
                    line = wording.failed(row.get("Error") or mob_jobs.INTERRUPTED)
                    r = self._tool("propose_work_order", incident_id=iid) if not busy else {"ok": False}
                    did = "Prepared a plain field check ({apr}) instead and is waiting for your approval"
                apr = r["result"]["approval"]["Approval_ID"] if r["ok"] else ""
                self._step(steps, "noura", "Simulated the road impact" if ok else "Could not simulate the road impact", f"{iid}: {line}", iid)
                if apr:
                    self._step(steps, "turki", "Prepared traffic plan" if ok else "Prepared work order", f"{iid} -> {apr}", iid)
                notes = [n for n in st.query(S.NOTIFICATIONS, Ref_ID=iid) if n["attrs"]["Kind"] == "fault"]
                extra = [{"agent": "turki", "did": did.format(apr=apr)}] if apr else []
                if not notes:                                        # an incident opened outside a scan has no alert yet
                    pt = inc["geom"]["coordinates"]
                    self.notify("fault", a["Severity"], f"{a['Incident_Type']} - {a['Area_Name']}", self._mob_message(a, line), "noura",
                                [{"agent": "noura", "did": line}] + extra, iid, iid, apr, a["Area_Name"], (pt[0], pt[1]))
                for n in notes:
                    trail = json.loads(n["attrs"]["Trail"] or "[]")
                    if any(t.get("did") == line for t in trail):
                        continue                                      # this result is already on the alert
                    at = next((i for i, t in enumerate(trail) if t.get("did") == CALC_TRAIL), None)
                    if at is None:
                        trail.append({"agent": "noura", "did": line})
                    else:
                        trail[at] = {"agent": "noura", "did": line}
                    st.update(S.NOTIFICATIONS, n["id"], Message=self._mob_message(a, line), Trail=json.dumps(trail + extra), Approval_ID=apr or n["attrs"]["Approval_ID"],
                              Status="New", Updated=utcnow())
            return {"incident_id": iid, "approval_id": apr, "steps": steps}

    # ---- data feeds ------------------------------------------------------------------------------------------
    def _near(self, p, cat: str, layer: str, ok, radius: float = LINK_M) -> str | None:
        """Id of the nearest record of this category within `radius` metres whose attrs satisfy ok()."""
        best, bid = radius, None
        for f in self.p.store.all(layer):
            a = f["attrs"]
            if a["Category"] == cat and ok(a):
                d = geo.haversine_m(p, geo.centroid(f["geom"]))
                if d <= best:
                    best, bid = d, f["id"]
        return bid

    def _citizen_detections(self, steps: list) -> None:
        """Reem reads the new reports. Three or more about the same thing in one place, with no fault already known there, become a finding."""
        if not self.p.feeds.citizen_enabled:
            return
        st = self.p.store
        new = [f for f in st.all(S.CITIZEN) if f["attrs"]["Status"] == "New"]
        unseen = [f for f in new if f["id"] not in self._seen_reports]
        self._seen_reports.update(f["id"] for f in new)
        if unseen:
            self._step(steps, "reem", "Read citizen reports", f"{len(unseen)} new report(s) from residents")
        for cat, label in (("water", "Water Issue (Citizen-reported)"), ("lighting", "Streetlight Failure (Citizen-reported)")):
            pts = [(f["id"], geo.centroid(f["geom"])) for f in new if f["attrs"]["Category"] == cat]
            used: set = set()
            for rid, p in pts:
                grp = [x for x in pts if x[0] not in used and geo.haversine_m(p, x[1]) <= CLUSTER_M]
                if rid in used or len(grp) < 3:
                    continue
                used.update(x[0] for x in grp)
                c = (sum(x[1][0] for x in grp) / len(grp), sum(x[1][1] for x in grp) / len(grp))
                if self._near(c, cat, S.INCIDENTS, lambda a: a["Status"] not in CLOSED_INC) or self._near(c, cat, S.DETECTIONS, lambda a: a["Status"] in ACTIVE_DET):
                    continue                                  # a fault is already known here; the reports will be linked to it
                area = st.get(S.CITIZEN, grp[0][0])["attrs"]["Area_Name"]
                risk = float(min(78, 35 + 9 * len(grp)))
                did = st.next_id("DET")
                st.upsert(S.DETECTIONS, {"Detection_ID": did, "Detection_Type": label, "Location": f"{area}, citizen reports", "Confidence": round(min(0.9, 0.4 + 0.1 * len(grp)), 2),
                                         "Severity": severity_of(risk), "Risk_Score": risk, "Base_Risk_Score": risk, "Detection_Date": utcnow(),
                                         "Source": "Citizen reports (Balady app, 940 call center; simulated)", "Status": "Suspected", "Related_Asset_ID": f"CITIZEN-{area}",
                                         "Pipeline_ID": "", "Area_Name": area, "Category": cat, "Cluster_ID": "",
                                         "Evidence": f"SUSPECTED: {len(grp)} residents reported the same problem within {CLUSTER_M:.0f} m. No sensor alarm is involved; needs field verification.",
                                         "Incident_ID": "", "Data_Classification": S.SIMULATED}, geo.point(*c))
                self._step(steps, "reem", "Clustered citizen reports", f"{len(grp)} {cat} reports in {area} -> {did}")

    def _link_reports(self, steps: list) -> None:
        """Waiting reports that sit next to an open incident of the same kind are attached to it as supporting evidence."""
        if not self.p.feeds.citizen_enabled:
            return
        st, n = self.p.store, 0
        for f in st.all(S.CITIZEN):
            a = f["attrs"]
            if a["Status"] != "New" or a["Category"] == "other":
                continue
            iid = self._near(geo.centroid(f["geom"]), a["Category"], S.INCIDENTS, lambda x: x["Status"] not in CLOSED_INC)
            if iid:
                st.update(S.CITIZEN, f["id"], Status="Linked", Linked_Incident=iid)
                n += 1
        if n:
            self._step(steps, "reem", "Linked citizen reports", f"{n} report(s) attached to open incidents")

    def _corroboration(self, steps: list, raised: list, fresh: set) -> None:
        """An older incident that residents keep reporting about gets one 'more evidence' alert (new incidents carry it in their own trail)."""
        if not self.p.feeds.citizen_enabled:
            return
        st = self.p.store
        counts: dict = {}
        for f in st.all(S.CITIZEN):
            if f["attrs"]["Linked_Incident"]:
                counts[f["attrs"]["Linked_Incident"]] = counts.get(f["attrs"]["Linked_Incident"], 0) + 1
        for iid, n in counts.items():
            inc = st.get(S.INCIDENTS, iid)
            if n - self._known_reports.get(iid, 0) < 2 or iid in fresh or not inc or inc["attrs"]["Status"] in CLOSED_INC or inc["attrs"]["Created_Date"] < (self.epoch or ""):
                continue
            dets = [st.get(S.DETECTIONS, d) for d in inc["attrs"]["Detection_IDs"].split(",") if d]
            if any(d and d["attrs"]["Source"].startswith("Citizen") for d in dets):
                continue
            a = inc["attrs"]
            nt = self.notify("corroboration", "Medium", f"More residents report {iid}", f"{a['Incident_Type']} in {a['Area_Name']}: {n} residents are now reporting the same problem, which raises confidence in the finding.",
                             "reem", [{"agent": "reem", "did": f"{n} citizen reports near {iid}"}], iid, iid, "", a["Area_Name"], tuple(inc["geom"]["coordinates"]))
            self._known_reports[iid] = n
            if nt:
                raised.append(nt)
                self._step(steps, "reem", "Corroborated incident", f"{iid}: {n} citizen reports", iid)

    def feed_status(self) -> list:
        st, f = self.p.store, self.p.feeds
        if self._counts is None:
            self._counts = {"sensors": len(st.query(S.INFRA, Asset_Type="Pressure/Flow Sensor")), "lamps": len(st.query(S.INFRA, Asset_Type="Streetlight"))}
        reps = [x["attrs"] for x in st.all(S.CITIZEN)]
        waiting = sum(1 for r in reps if r["Status"] == "New")
        hass = self.last.get("zayed")
        reports = [x["attrs"] for x in st.all(S.TRAFFIC_REPORTS)]
        closures, notices = [x["attrs"] for x in st.all(S.CLOSURES)], [x["attrs"] for x in st.all(S.EVENT_NOTICES)]
        nasser = self.last.get("nasser")
        mobility = [
            {"id": "traffic", "name": "Traffic & road reports", "detail": f"{len(reports)} road report(s) · traffic state modelled, not measured",
             "at": max([r.get("Reported_At") or "" for r in reports] + [nasser["at"] if nasser else ""]) or None, "agent": "nasser"},
            {"id": "closures", "name": "Closures & events", "detail": f"{len(closures)} closure request(s) · {len(notices)} event notice(s)",
             "at": max([r.get("Created") or "" for r in closures + notices], default="") or None, "agent": "noura"}]
        return [
            {"id": "water", "name": "Water sensors", "detail": f"{self._counts['sensors']} sensors · hourly", "at": f.last_tick, "agent": "sarah"},
            {"id": "lighting", "name": "Streetlights & poles", "detail": f"{self._counts['lamps']} lamps · telemetry, tilt & corrosion", "at": f.last_tick, "agent": "abdullah"},
            {"id": "imagery", "name": "Satellite imagery", "detail": "change scan on each new pass", "at": hass["at"] if hass else None, "agent": "zayed"},
            {"id": "distortion", "name": "Visual distortion (imagery)", "detail": "street-level problems and building shape between satellite dates", "at": hass["at"] if hass else None, "agent": "zayed"},
            {"id": "landuse", "name": "Land use / zoning", "detail": "construction vs. zoning rules", "at": hass["at"] if hass else None, "agent": "zayed"},
        ] + mobility + ([{"id": "citizen", "name": "Citizen reports", "detail": f"{len(reps)} received · {waiting} waiting", "at": max((r["Reported_At"] for r in reps), default=None), "agent": "reem"}]
              if f.citizen_enabled else [])

    def inject(self, name: str) -> dict:
        """Inject a SIMULATED event (a fault, or a new satellite pass) and let the crew react to it straight away."""
        with self.lock:
            if name == "imagery_change":
                self.p.sim.event("scenario", "New satellite pass received - change scan requested")
                return {"event": name, "scan": self.run_cycle(deep=True, scope=frozenset({"change"}))}
            if name == "imagery_critical":
                # two areas whose new construction sits on critical facilities: the satellite pass raises Critical urban-change events
                runs = [self.run_cycle(deep="Diplomatic Quarter"), self.run_cycle(deep="Diriyah")]
                merged = {**runs[-1], "steps": [x for r in runs for x in r["steps"]], "new_notifications": [x for r in runs for x in r["new_notifications"]],
                          "new_incidents": [x for r in runs for x in r["new_incidents"]]}
                return {"event": name, "scan": merged}
            if name in ("citizen_surge", "citizen_random"):
                if not self.p.feeds.citizen_enabled:
                    raise ValueError("citizen reports are disabled in this deployment")
                res = self._citizen_event("Al Malaz" if name == "citizen_surge" else None)
                return {"event": name, **res, "scan": self.run_cycle()}
            if name == "random":
                res = self.random_event()
                return {"event": name, **res, "scan": self.run_cycle(deep=res.get("deep", False))}
            res = self.p.sim.scenario(name)
            self.p.feeds.on_scenario(name, res)
            scope = self.EVENT_SCOPE(name)
            area = res.get("area") if scope and "change" in scope else None
            if not area:
                return {"event": name, **res, "scan": self.run_cycle(scope=scope)}
            # land-use management: the satellite dates are compared over the event's area (zoning violations) and over one more area, where permitted new
            # construction shows up as plain urban change
            other = self.p.sim.least_busy([a for a in ("Olaya", "KAFD", "Diriyah", "Al Malaz") if a != area])
            runs = [self.run_cycle(deep=area, scope=scope), self.run_cycle(deep=other, scope=frozenset({"change"}))]
            merged = {**runs[-1], "steps": [x for r in runs for x in r["steps"]], "new_notifications": [x for r in runs for x in r["new_notifications"]],
                      "new_incidents": [x for r in runs for x in r["new_incidents"]]}
            return {"event": name, **res, "scan": merged}

    @staticmethod
    def EVENT_SCOPE(name: str):
        """The use case a simulated event belongs to, so selecting one event wakes only its own feed (None = the event touches several)."""
        if name == "olaya_leak" or name.startswith("leak_"):
            return frozenset({"water"})
        if name in ("streetlight_pole", "king_fahd_lights", "pole_decay") or name.startswith("lights_"):
            return frozenset({"lighting"})
        if name.startswith("distortion_"):
            return frozenset({"distortion"})
        if name.startswith("landuse_"):
            return frozenset({"land_use", "change"})        # land-use management = the satellite comparison (urban change) plus the zoning check on what it finds
        if name in ("traffic_incident", "road_closure", "major_event"):
            return frozenset({"mobility"})
        return None

    def request_inspection(self, incident_id: str) -> dict:
        """An operator asks for a team on an incident the crew kept on watch. Turki prepares the work order; it still needs approval."""
        with self.lock:
            r = self._tool("propose_work_order", incident_id=incident_id)
            if not r["ok"]:
                return {"ok": False, "error": r["error"]}
            apr = r["result"]["approval"]["Approval_ID"]
            st = self.p.store
            self._impact_pending = []
            on_road = self._repair_near_road(st.get(S.INCIDENTS, incident_id))
            for f in st.query(S.NOTIFICATIONS, Ref_ID=incident_id):
                if f["attrs"]["Kind"] in ("fault", "change"):
                    trail = json.loads(f["attrs"]["Trail"] or "[]")
                    trail.append({"agent": "turki", "did": f"Inspection requested by the operator - work order {apr} prepared for approval"})
                    if on_road:
                        trail.append({"agent": "noura", "did": CALC_REPAIR})
                    st.update(S.NOTIFICATIONS, f["id"], Approval_ID=apr, Trail=json.dumps(trail), Status="New", Updated=utcnow())
            self._step([], "turki", "Prepared inspection work order", f"{incident_id} -> {apr} (operator request)", incident_id)
            self._queue_road_impacts()
            return {"ok": True, "approval_id": apr, "incident_id": incident_id}

    # ---- field results --------------------------------------------------------------------------------------
    def _field_results(self, steps: list, raised: list) -> None:
        """New field reports become alerts for the operator, and a confirmed-and-repaired (or rejected) incident gets a closure proposal."""
        st = self.p.store
        for f in st.all(S.VERIFICATION):
            v = f["attrs"]
            if v["Timestamp"] < (self.epoch or "") or st.query(S.NOTIFICATIONS, Kind="verified", Ref_ID=f["id"]):
                continue
            inc = st.get(S.INCIDENTS, v["Incident_ID"])
            if not inc:
                continue
            w = st.get(S.WORKERS, v["Worker_ID"])
            who = w["attrs"]["Name"] if w else v["Worker_ID"]
            st_ = v["Verification_Status"]
            title = {"Confirmed": "Fault confirmed on site", "Repaired": "Repair completed", "Rejected": "False alarm - nothing found",
                     "Needs Further Inspection": "Investigator needs a further inspection", "Escalate": "Investigator escalated the incident"}.get(st_, "Field update")
            sev = {"Confirmed": "Medium", "Escalate": "High"}.get(st_, "Info")
            trail = [{"agent": "turki", "did": f"{who} reported from site: {v['Observation'][:140]}"},
                     {"agent": "maha", "did": "Compared the field report with the AI prediction and updated the model calibration"}]
            self._step(steps, "maha", "Verified outcome", f"{v['Incident_ID']}: {st_}", v["Incident_ID"])
            n = self.notify("verified", sev, f"{title} - {inc['attrs']['Area_Name']}", f"{who} on {v['Incident_ID']}: {v['Observation'][:150]}", "maha", trail,
                            f["id"], v["Incident_ID"], "", inc["attrs"]["Area_Name"], tuple(inc["geom"]["coordinates"]))
            if n:
                raised.append(n)
        for f in st.all(S.INCIDENTS):
            a = f["attrs"]
            if a["Verification_Outcome"] and a["Status"] not in ("Resolved", "Closed - False Positive") and not self._approval_exists("close_incident", f["id"], ("Proposed", "Rejected", "Executed")):
                r = self._tool("propose_incident_closure", incident_id=f["id"])
                if r["ok"]:
                    apr = r["result"]["approval"]["Approval_ID"]
                    self._step(steps, "turki", "Prepared closure", f"{f['id']} -> {apr}", f["id"])
                    n = self.notify("closure", "Low", f"Ready to close {f['id']}", r["result"]["approval"]["Summary"], "turki",
                                    [{"agent": "turki", "did": "Field evidence is in - closure prepared for your approval"}], apr, f["id"], apr, a["Area_Name"], tuple(f["geom"]["coordinates"]))
                    if n:
                        raised.append(n)

    def field_update(self) -> dict:
        """Called the moment an investigator sends a report, so the operator sees it without waiting for the next scan."""
        with self.lock:
            if self.epoch is None:
                self.epoch = _iso_minus(60)
            steps: list = []
            raised: list = []
            self._field_results(steps, raised)
            return {"steps": steps, "new_notifications": [n["Notif_ID"] for n in raised]}

    def field_accepted(self, work_order_id: str, worker_id: str) -> dict | None:
        """The investigator confirmed the assignment: tell the operator who is on the way."""
        with self.lock:
            st = self.p.store
            wo, w = st.get(S.WORK_ORDERS, work_order_id), st.get(S.WORKERS, worker_id)
            inc = st.get(S.INCIDENTS, wo["attrs"]["Incident_ID"]) if wo else None
            if not (wo and w and inc):
                return None
            a = inc["attrs"]
            who = w["attrs"]["Name"]
            self._step([], "turki", "Assignment accepted", f"{who} -> {a['Area_Name']}", inc["id"])
            return self.notify("accepted", "Info", f"{who} accepted {inc['id']}", f"{who} ({w['attrs']['Team']}) confirmed the assignment and is heading to {a['Area_Name']}. The report will appear here when it is sent.",
                               "turki", [{"agent": "turki", "did": f"{who} confirmed the assignment for {work_order_id}"}], work_order_id, inc["id"], "", a["Area_Name"], tuple(inc["geom"]["coordinates"]))

    def field_task_done(self, work_order_id: str, worker_id: str) -> dict | None:
        """The investigator marked the task Completed in Field Maps: tell the operator, whether or not a report has been assessed yet."""
        with self.lock:
            st = self.p.store
            wo, w = st.get(S.WORK_ORDERS, work_order_id), st.get(S.WORKERS, worker_id)
            inc = st.get(S.INCIDENTS, wo["attrs"]["Incident_ID"]) if wo else None
            if not (wo and w and inc):
                return None
            a = inc["attrs"]
            who = w["attrs"]["Name"]
            has_report = bool(st.query(S.VERIFICATION, Work_Order_ID=work_order_id))
            tail = "Their report is being assessed." if has_report else "No report has been filed yet; ask them to submit one so it can be verified."
            self._step([], "turki", "Task finished in Field Maps", f"{who} -> {work_order_id}", inc["id"])
            return self.notify("field_done", "Info", f"{who} finished {inc['id']} in Field Maps", f"{who} marked work order {work_order_id} ({a['Incident_Type']}, {a['Area_Name']}) as completed. {tail}",
                               "turki", [{"agent": "turki", "did": f"{who} marked {work_order_id} completed in ArcGIS Field Maps"}], f"done-{work_order_id}", inc["id"], "",
                               a["Area_Name"], tuple(inc["geom"]["coordinates"]))

    def _citizen_event(self, area: str | None) -> dict:
        area = area or self.p.sim.least_busy(list(AREAS))
        res = self.p.feeds.citizen_surge(area)
        self.p.sim._set_truth(f"CITIZEN-{res['area']}", True, "scenario: citizen surge (real low pressure, no sensor)")
        self.p.sim.event("scenario", f"{res['reports']} citizen reports of low water pressure in {res['area']}")
        return res

    def random_event(self) -> dict:
        """Something happens somewhere in the city. The area with the fewest open incidents is favoured, so the activity spreads out."""
        sim = self.p.sim
        kinds = ["leak", "leak", "lights", "citizen", "change", "poles", "distortion", "landuse"]
        kind = sim.rng.choice(kinds if self.p.feeds.citizen_enabled else [k for k in kinds if k != "citizen"])
        if kind == "leak":
            res = sim.scenario("leak_random")
            self.p.feeds.on_scenario("leak_random", res)
        elif kind == "lights":
            res = sim.scenario("lights_random")
            self.p.feeds.on_scenario("lights_random", res)
        elif kind == "citizen":
            res = self._citizen_event(None)
        elif kind in ("poles", "distortion", "landuse"):
            try:
                res = sim.scenario({"poles": "pole_decay", "distortion": "distortion_random", "landuse": "landuse_random"}[kind])
            except ValueError:                       # nothing healthy left to degrade: fall back to a water event
                kind = "leak"
                res = sim.scenario("leak_random")
                self.p.feeds.on_scenario("leak_random", res)
            else:
                res = {**res, "deep": kind != "poles"}
        else:
            sim.event("scenario", "New satellite pass received - change scan requested")
            res = {"scenario": "satellite pass", "deep": True}
        return {"kind": kind, **res}

    def _visit(self, steps: list, wo_id: str, repair: bool) -> None:
        try:
            self.p.simulate_field_response(wo_id, repair)
            self._step(steps, "turki", "Crew repaired the fault (simulated)" if repair else "Crew visited the site (simulated)", wo_id)
        except Exception as exc:  # a failed simulated visit must never stop the cycle
            log.warning("simulated field visit failed for %s: %s", wo_id, exc)

    # ---- autopilot ---------------------------------------------------------------------------------------------
    def start(self, interval: float = 60.0, simulate_field: bool | None = None) -> dict:
        self.interval = max(3.0, float(interval))
        if simulate_field is not None:
            self.simulate_field = simulate_field
        if not self.autopilot:
            self.autopilot = True
            self._thread = threading.Thread(target=self._loop, daemon=True, name="nccc-autopilot")
            self._thread.start()
            self.p.sim.event("control", "NCCC autopilot started")
        return self.status()

    def stop(self) -> dict:
        if self.autopilot:
            self.autopilot = False
            self.p.sim.event("control", "NCCC autopilot paused")
        return self.status()

    def _loop(self) -> None:
        n = 0
        while self.autopilot:
            try:
                n += 1
                with self.lock:
                    self.p.sim.tick()                               # new hourly sensor readings arrive
                    self.p.feeds.tick()                             # ... and the odd citizen report
                    ev = self.random_event() if n % 3 == 0 else {}  # city activity: a new fault or change somewhere, favouring quiet areas
                    self.run_cycle(deep=bool(ev.get("deep")) or n % 8 == 0)
                self.record_error = None
            except Exception as exc:
                log.exception("autopilot cycle failed")
                self.record_error = {"at": utcnow(), "message": str(exc)}     # kept in memory: the system of record may be what failed
                try:
                    self.p.sim.event("error", f"autopilot cycle failed: {exc}")
                except Exception:
                    pass                                                      # the next cycle tries again
            for _ in range(int(self.interval * 2)):
                if not self.autopilot:
                    return
                time.sleep(0.5)

    def status(self) -> dict:
        return {"autopilot": self.autopilot, "interval_s": self.interval, "cycles": self.cycles, "simulate_field": self.simulate_field, "last_cycle": self.last_cycle,
                "record_error": self.record_error}

    def roster(self) -> list[dict]:
        out = []
        working = dict(self.working)
        jobs = self.p.jobs.active()                      # Noura's simulations run on the background worker, outside any scan
        if jobs and not working.get("noura"):
            inc = self.p.store.get(S.INCIDENTS, jobs[0]["subject_id"])
            working["noura"] = f"simulating {inc['attrs']['Area_Name'] if inc else jobs[0]['name']}"
        for a in AGENTS:
            last = self.last.get(a.id)
            out.append({"id": a.id, "name": a.name, "role": a.role, "tier": a.tier, "focus": a.focus, "color": a.color, "tools": list(a.tools),
                        "working": working.get(a.id, ""), "last_action": last["action"] if last else "", "last_at": last["at"] if last else ""})
        return out
