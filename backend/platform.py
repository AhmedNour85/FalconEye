"""Platform container: store + services, wired once and shared by the API, agent and tools."""
from __future__ import annotations

import logging
from pathlib import Path

from backend.gis import schema as S
from backend.gis.store import ArcGISStore, Store, utcnow
from backend.services import synthetic
from backend.services.audit import Audit
from backend.services.simulation import SimEngine
from backend.workflows.approvals import ApprovalService
from config.settings import ConfigError, Settings, check_prefix, load_settings

log = logging.getLogger("geoai.platform")


class _RecordRefresh:
    """Field Maps (or anyone) edits the hosted layers directly, so "pulling" field updates is refreshing the working copy from ArcGIS Online."""

    def __init__(self, store: ArcGISStore):
        self.store, self._changed = store, {}

    def pull_updates(self, layer: str, since: str, store) -> int:
        if layer == S.WORK_ORDERS:           # asked once per sync, for the work orders first: one refresh covers every layer
            self._changed = self.store.refresh()
        return len(self._changed.get(layer, []))


class Platform:
    def __init__(self, settings: Settings | None = None, gateway=None, init: bool = True):
        """gateway: the ArcGIS Online gateway to use (tests pass a stand-in); by default one is made from the settings."""
        self.settings = settings or load_settings()
        self.gateway = None
        if self.settings.store == "arcgis":      # ArcGIS Online is the system of record
            check_prefix(self.settings.arcgis_layer_prefix)
            if gateway is None:
                if not self.settings.arcgis_enabled:
                    raise ConfigError("ARCGIS_USERNAME and ARCGIS_PASSWORD are not set. ArcGIS Online is the system of record, so the app cannot start without them. "
                                      "Run scripts/make_env.py, or set GEOAI_STORE=memory for a development run that keeps nothing.")
                from backend.gis.agol import ArcGISGateway

                gateway = ArcGISGateway(self.settings)
            self.gateway = gateway
            self.store = ArcGISStore(gateway)
            self.mirror = _RecordRefresh(self.store)
            self.mirror_status = f"ArcGIS Online ({self.settings.arcgis_layer_prefix})"
        else:
            self.store = Store()                 # working copy only: tests and development
            self.mirror = None
            self.mirror_status = "memory only (tests and development; nothing is stored)"
        from backend.services import tasks

        tasks.LANG = self.settings.field_lang
        self.store.write_hooks[S.WORK_ORDERS] = lambda a: {**a, **tasks.task_fields(a, self._ai_finding(a))}
        self.audit = Audit(self.store)
        self.approvals = ApprovalService(self.store, self.audit)
        self.sim = SimEngine(self.store, self.settings.seed)
        from backend.services.feeds import FeedEngine

        self.feeds = FeedEngine(self.store, self.settings.seed, self.settings.citizen_reports)
        from backend.mobility.jobs import Jobs

        self.jobs = Jobs(self, inline=self.settings.mobility_jobs_inline)   # long simulations: one background worker
        from backend.orchestration.crew import Crew  # local import: the crew depends on the tool layer

        self.crew = Crew(self)
        from backend.mobility import sources as mobility_sources, traffic

        mobility_sources.configure(self.store, self.settings.mobility_network)   # the traffic model reads its roads, hospitals and stations through here
        if init and self.settings.mobility_warm:
            traffic.warm()                   # in the background: the pages work while the model builds
        self.data_ready = self.store.count(S.INFRA) > 0
        if init and not self.store.is_hosted:
            self.reset()                     # a working copy that keeps nothing starts from freshly generated demo data
            self.data_ready = True
        elif init and not self.data_ready:   # the app never fills or empties the system of record by itself
            log.warning("the %s layers in ArcGIS Online hold no demo data yet: run scripts/initialize_demo.py (dry run first)", self.settings.arcgis_layer_prefix)
        if init and self.store.is_hosted:
            self.setup_field_tasks()
            self.start_field_sync()
            self.recover_simulations()

    def recover_simulations(self) -> list:
        """Simulations a stopped server left Queued or Running are marked Interrupted, and the crew queues each once more.
        Start-up never fails because of this: what cannot be recovered now is picked up by the next crew scan."""
        try:
            left = self.jobs.recover()
            if left:
                log.info("%d simulation(s) were interrupted by the last stop: %s", len(left), ", ".join(left))
                self.crew.resume_mobility()
            return left
        except Exception as exc:  # noqa: BLE001
            log.warning("could not recover interrupted simulations: %s", exc)
            return []

    def reset(self) -> dict:
        self.sim.pause()
        self.crew.reset()
        with self.store.batch():  # one request per layer to the system of record, not thousands of single edits
            counts = synthetic.generate(self.store, self.settings.seed)
            self.feeds.seed()
            self.apply_field_users()
        self.sim.event("control", "Environment regenerated from seed")
        self.data_ready = True
        # the imagery change layer is regenerated on demand by the agent; photos went with the rows they were attached to
        return counts

    def simulate_field_response(self, work_order_id: str, repair: bool = False) -> dict:
        """A SIMULATED field worker visits the site and submits evidence consistent with hidden ground truth."""
        from backend.services import field

        obs = self.sim.field_observation(work_order_id)
        if not obs["worker_id"]:
            raise ValueError("work order has no assigned worker")
        gps = obs["gps"]
        status, text = obs["status"], "[SIMULATED WORKER] " + obs["observation"]
        if repair and status == "Confirmed":
            status, text = "Repaired", "[SIMULATED WORKER] Fault repaired and tested; area made safe."
        res = field.submit(self.store, self.audit, work_order_id, obs["worker_id"], status, text, gps[1], gps[0], simulated=True)
        self.sim.event("field", f"Simulated worker {obs['worker_id']} submitted '{status}' for {work_order_id}", work_order_id)
        return res


    def simulate_repair(self, incident_id: str) -> dict:
        """The repair report from a SIMULATED crew for an incident the field team has confirmed (a real investigator confirmed it, or a simulated one).
        It is stored like any field report (marked Simulated_Worker = Yes), is assessed the same way, and makes the closure proposal possible.
        Closing still needs the operator's approval."""
        import random

        from backend.gis import geo
        from backend.services import field

        inc = self.store.get(S.INCIDENTS, incident_id)
        if not inc:
            raise ValueError(f"incident {incident_id} not found")
        a = inc["attrs"]
        if a["Status"] in ("Resolved", "Closed - False Positive"):
            raise ValueError(f"incident {incident_id} is already closed")
        if a["Status"] == "Repair Reported":
            raise ValueError(f"the repair of {incident_id} has already been reported")
        if a["Verification_Outcome"] != "Confirmed":
            raise ValueError(f"incident {incident_id} has not been confirmed in the field yet; a repair can only be reported after that")
        wos = [w for w in self.store.query(S.WORK_ORDERS, Incident_ID=incident_id) if w["attrs"]["Status"] in ("Assigned", "In Progress") and w["attrs"]["Assigned_Worker"]]
        if not wos:
            raise ValueError(f"incident {incident_id} has no active work order with an assigned worker")
        wo = wos[-1]
        lon, lat = geo.offset(geo.centroid(inc["geom"]), random.uniform(-15, 15), random.uniform(-15, 15))
        res = field.submit(self.store, self.audit, wo["id"], wo["attrs"]["Assigned_Worker"], "Repaired",
                           "[SIMULATED WORKER] Fault repaired and tested; area made safe.", lat, lon, simulated=True)
        self.sim.event("field", f"Simulated crew reported the repair of {incident_id} ({wo['id']})", wo["id"])
        follow = self.crew.field_update()                      # raises the "ready to close" alert for the operator
        return {"ok": True, "incident_id": incident_id, "work_order_id": wo["id"], "outcome": res.get("outcome"), "incident_status": res.get("incident_status"),
                "new_notifications": follow["new_notifications"]}

    def pull_mirror(self) -> int:
        """Pull reports made in ArcGIS Field Maps. Kept under its old name for callers; see pull_field_updates."""
        return self.pull_field_updates()["pulled"]

    def pull_field_updates(self) -> dict:
        """ArcGIS Field Maps is how investigators report: pull their edits from ArcGIS Online, assess every new report against the AI finding
        (the same assessment the old in-app form used) and tell the operator straight away."""
        if not self.mirror:
            return {"pulled": 0, "assessed": 0}
        try:
            pulled = 0
            accepted_before = {w["id"] for w in self.store.all(S.WORK_ORDERS) if w["attrs"].get("Accepted_At")}
            done_before = {w["id"] for w in self.store.all(S.WORK_ORDERS) if w["attrs"].get("esritask_status") == 3}
            for layer in (S.WORK_ORDERS, S.VERIFICATION):
                pulled += self.mirror.pull_updates(layer, "", self.store)
            for w in self.store.all(S.WORK_ORDERS):         # the worker started the task in Field Maps (task status In Progress) = accepted the assignment
                a = w["attrs"]
                if a.get("esritask_status") == 2 and a["Status"] == "Assigned" and a.get("Assigned_Worker"):
                    self.store.update(S.WORK_ORDERS, w["id"], Status="In Progress", Accepted_At=a.get("Accepted_At") or utcnow())
                if self.store.get(S.WORK_ORDERS, w["id"])["attrs"].get("Accepted_At") and w["id"] not in accepted_before and a.get("Assigned_Worker"):
                    self.crew.field_accepted(w["id"], a["Assigned_Worker"])
            assessed = self._assess_field_reports()
            for w in self.store.all(S.WORK_ORDERS):
                if w["attrs"].get("esritask_status") == 3 and w["id"] not in done_before and w["attrs"].get("Assigned_Worker") and w["attrs"]["Status"] != "Completed":
                    if self._report_from_finished_task(w):
                        assessed += 1                                  # Finish + Note is the report: the verified alert says it all
                    else:
                        self.crew.field_task_done(w["id"], w["attrs"]["Assigned_Worker"])
            if assessed:
                self.crew.field_update()
            return {"pulled": pulled, "assessed": assessed}
        except Exception as exc:
            log.warning("ArcGIS Online pull failed: %s", exc)
            return {"pulled": 0, "assessed": 0, "error": str(exc)}

    def _assess_field_reports(self) -> int:
        """Reports created in Field Maps arrive without an assessment, and possibly without a distance, worker or valid status. Complete and assess them."""
        from backend.gis import geo
        from backend.services import field

        n = 0
        for v in self.store.all(S.VERIFICATION):
            a = dict(v["attrs"])
            if a.get("Agent_Assessment"):
                continue
            wo = self.store.get(S.WORK_ORDERS, (a.get("Work_Order_ID") or "").strip().upper())
            if not wo and v["geom"]:
                wo = self._nearest_open_work_order(v["geom"])       # the worker did not type (or mistyped) the work order id: use the one they are standing at
                if wo:
                    a["Work_Order_ID"] = wo["id"]
            inc = self.store.get(S.INCIDENTS, wo["attrs"]["Incident_ID"]) if wo else None
            if not (wo and inc):
                continue                                       # not tied to a known work order yet: leave it for the worker to complete in Field Maps
            a["Incident_ID"] = inc["id"]
            a["Worker_ID"] = a.get("Worker_ID") or wo["attrs"]["Assigned_Worker"]
            a["Investigator_Name"] = a.get("Investigator_Name") or field.investigator_name(self.store, a["Worker_ID"])
            a["Verification_Status"] = a.get("Verification_Status") if a.get("Verification_Status") in field.STATUSES else "Needs Further Inspection"
            a["Observation"] = (a.get("Observation") or "").strip() or "Reported from ArcGIS Field Maps (no notes)."
            a["Timestamp"] = a.get("Timestamp") or utcnow()
            a["Simulated_Worker"] = a.get("Simulated_Worker") or "No"
            a["Data_Classification"] = S.OPERATIONAL
            g = v["geom"]
            if g:
                lon, lat = geo.centroid(g)
                a["GPS_Location"] = a.get("GPS_Location") or f"{lat:.6f},{lon:.6f}"
                a["Distance_To_Detection_M"] = round(geo.haversine_m((lon, lat), geo.centroid(inc["geom"])), 1)
            else:                                              # no GPS fix in the report: treat as far away so it is never accepted as strong evidence
                a["Distance_To_Detection_M"] = a.get("Distance_To_Detection_M") or 9999.0
            self.store.upsert(S.VERIFICATION, a, g or geo.point(*geo.centroid(inc["geom"])))
            self.audit.log("field", "FIELD SUBMISSION", "arcgis_field_maps", inc["id"], {"wo": wo["id"], "status": a["Verification_Status"]},
                           {"verification": v["id"], "distance_m": round(a["Distance_To_Detection_M"])}, actor=a["Worker_ID"])
            field.assess(self.store, self.audit, v["id"])
            n += 1
        return n

    def setup_field_tasks(self) -> bool:
        """Make the hosted work-order layer ready for Field Maps Tasks: task titles (incident types) and the logins a task can be assigned to."""
        if not self.gateway:
            return False
        from backend.services import tasks

        try:
            users = {u: u for u in (self.settings.field_users or {}).values()}
            return self.gateway.ensure_task_domains(S.WORK_ORDERS, tasks.TASK_TYPES, users)
        except Exception as exc:
            log.warning("could not prepare Field Maps tasks: %s", exc)
            return False

    def apply_field_users(self) -> int:
        """Record each investigator's ArcGIS Online (Field Maps) username from GEOAI_FIELD_USERS."""
        n = 0
        for wid, user in (self.settings.field_users or {}).items():
            w = self.store.get(S.WORKERS, wid)
            if w and w["attrs"].get("ArcGIS_Username") != user:
                self.store.upsert(S.WORKERS, {**w["attrs"], "ArcGIS_Username": user}, w["geom"])
                n += 1
        return n

    def backfill_investigator_names(self) -> int:
        """Reports saved before the Investigator_Name field existed get it from their worker (idempotent; pushed to ArcGIS Online like any edit)."""
        from backend.services import field

        n = 0
        for v in self.store.all(S.VERIFICATION):
            a = v["attrs"]
            if not a.get("Investigator_Name") and a.get("Worker_ID"):
                name = field.investigator_name(self.store, a["Worker_ID"])
                if name:
                    self.store.upsert(S.VERIFICATION, {**a, "Investigator_Name": name}, v["geom"])
                    n += 1
        self.apply_field_users()
        for w in self.store.all(S.WORK_ORDERS):         # assignments made before the Field Maps columns existed
            a = w["attrs"]
            wk = self.store.get(S.WORKERS, a["Assigned_Worker"]) if a.get("Assigned_Worker") else None
            if wk and (not a.get("Assigned_Worker_Name") or (wk["attrs"].get("ArcGIS_Username") and not a.get("Assigned_To_Username"))):
                inc = self.store.get(S.INCIDENTS, a["Incident_ID"])
                if inc:
                    self.store.upsert(S.WORK_ORDERS, {**a, "Assigned_Worker_Name": wk["attrs"]["Name"], "Assigned_To_Username": wk["attrs"].get("ArcGIS_Username", ""),
                                                      "Incident_Type": inc["attrs"]["Incident_Type"], "Area_Name": inc["attrs"]["Area_Name"],
                                                      "Assigned_At": a.get("Assigned_At") or a["Created_Date"], "Field_Maps_Status": a.get("Field_Maps_Status") or ("Sent to ArcGIS Field Maps" if self.store.is_hosted else "")}, w["geom"])
                    n += 1
        from backend.services import tasks

        for w in self.store.all(S.WORK_ORDERS):         # Field Maps task fields for work orders created before they were derived
            want = tasks.task_fields(w["attrs"], self._ai_finding(w["attrs"]))
            if any(w["attrs"].get(k) != v and not (v in (None, "") and not w["attrs"].get(k)) for k, v in want.items()):
                self.store.upsert(S.WORK_ORDERS, w["attrs"], w["geom"])
                n += 1
        return n

    def _ai_finding(self, wo_attrs: dict) -> str:
        """The AI's evidence for the work order's incident (what the investigator is asked to confirm), for the Field Maps task text."""
        try:
            inc = self.store.get(S.INCIDENTS, wo_attrs.get("Incident_ID", ""))
            ids = [d for d in (inc["attrs"].get("Detection_IDs") or "").split(",") if d] if inc else []
            return " ".join((self.store.get(S.DETECTIONS, d) or {"attrs": {}})["attrs"].get("Evidence", "") for d in ids).strip()
        except Exception:
            return ""

    VERDICTS = {"confirmed": "Confirmed", "confirm": "Confirmed", "yes": "Confirmed", "rejected": "Rejected", "reject": "Rejected", "repaired": "Repaired",
                "escalate": "Escalate", "escalated": "Escalate"}
    VERDICT_PHRASES = (("not found", "Rejected"), ("nothing wrong", "Rejected"), ("need to look again", "Needs Further Inspection"))

    def _report_from_finished_task(self, wo: dict) -> bool:
        """The investigator tapped Finish on the task in Field Maps. The task's Note is their report: its first word sets the verdict
        (Confirmed, Rejected, Repaired, Escalate); no verdict word means Needs Further Inspection. Skipped when a report already exists for the work order.
        Tasks does not record the phone's position, so the location is the task's own and there is no distance check."""
        import re

        from backend.gis import geo
        from backend.services import field

        a = wo["attrs"]
        if self.store.query(S.VERIFICATION, Work_Order_ID=wo["id"]):
            return False
        inc = self.store.get(S.INCIDENTS, a["Incident_ID"])
        if not inc:
            return False
        from backend.services import i18n

        chosen = (a.get("Field_Verdict") or "").strip()                  # the radio buttons on the task form (codes: Confirmed, Rejected, ...)
        comment = (a.get("Field_Comment") or "").strip()                 # "What did you see?"
        notes = (a.get("esritask_notes") or "").strip()                  # the old way: the Note, whose first word was the answer
        text = comment or notes
        first = re.split(r"[\s:,.;-]+", notes.lower(), maxsplit=1)[0] if notes else ""
        verdict = (chosen if chosen in field.STATUSES else None) or next((v for p, v in self.VERDICT_PHRASES if notes.lower().startswith(p)), None) \
            or self.VERDICTS.get(first) or i18n.verdict_from_note(notes) or "Needs Further Inspection"
        lon, lat = geo.centroid(inc["geom"])
        vid = self.store.next_id("VER")
        worker = a["Assigned_Worker"]
        self.store.upsert(S.VERIFICATION, {
            "Verification_ID": vid, "Work_Order_ID": wo["id"], "Incident_ID": inc["id"], "Worker_ID": worker, "Investigator_Name": field.investigator_name(self.store, worker),
            "Observation": ("[Field Maps task] " + (text or "Marked complete with no comment.")), "Verification_Status": verdict, "GPS_Location": f"{lat:.6f},{lon:.6f}", "Photo_URL": "",
            "Timestamp": utcnow(), "Distance_To_Detection_M": 0.0, "Agent_Assessment": "", "Simulated_Worker": "No", "Data_Classification": S.OPERATIONAL}, geo.point(lon, lat))
        self.audit.log("field", "FIELD SUBMISSION", "arcgis_field_maps_task", inc["id"], {"wo": wo["id"], "status": verdict}, {"verification": vid, "source": "task Finish + " + ("answer" if chosen in field.STATUSES else "Note")}, actor=worker)
        field.assess(self.store, self.audit, vid)
        return True

    def _nearest_open_work_order(self, geom: dict, radius_m: float = 300.0):
        from backend.gis import geo

        here, best, bd = geo.centroid(geom), None, radius_m
        for w in self.store.all(S.WORK_ORDERS):
            if w["attrs"]["Status"] not in ("Assigned", "In Progress"):
                continue
            inc = self.store.get(S.INCIDENTS, w["attrs"]["Incident_ID"])
            d = geo.haversine_m(here, geo.centroid(inc["geom"])) if inc else None
            if d is not None and d <= bd:
                best, bd = w, d
        return best

    def start_field_sync(self) -> None:
        """Poll ArcGIS Online for Field Maps reports in the background (only when an ArcGIS Online connection exists)."""
        if not self.mirror or getattr(self, "_field_sync", None) or self.settings.field_sync_seconds <= 0:
            return
        import threading
        import time

        def loop():
            while True:
                time.sleep(max(3.0, self.settings.field_sync_seconds))
                self.pull_field_updates()

        self._field_sync = threading.Thread(target=loop, daemon=True, name="field-maps-sync")
        self._field_sync.start()
