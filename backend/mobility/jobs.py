"""One background worker for long simulations.

A simulation takes 10 seconds to 2 minutes on the full road network, so the crew never runs one inside its 60-second scan:
it queues a job here, raises the alert at once and is called back when the result is ready.

Every job has one row in the hosted scenario table (ArcGIS Online is the system of record): Queued, Running, then Completed
or Failed, with the summary numbers and the recommended strategy. The map preview of a run is NOT stored: the last few are
kept in memory and any other is calculated again from the stored inputs when someone asks for it.

A result that ArcGIS Online refuses is reported as Failed. Nothing is kept only on this computer.
"""
from __future__ import annotations

import collections
import datetime as dt
import json
import logging
import threading
import time
from typing import Callable, Dict, List, Optional

from backend.gis import schema as S
from backend.gis.store import utcnow
from backend.mobility import engine, network_model, rules, strategies, traffic

log = logging.getLogger("geoai.mobility.jobs")

PREVIEWS = 20            # map previews kept in memory
KEEP = 200               # finished jobs remembered in memory (the rows stay in the scenario table)
WAIT_MODEL_S = 900       # how long a job waits for the traffic model that is built at start-up
ACTIVE = ("Queued", "Running")
INTERRUPTED = "The server stopped while this simulation was running."
LABEL = "Modelled: calculated from the road network and synthetic demand, not measured"


def riyadh_now() -> dt.datetime:
    return dt.datetime.utcnow() + dt.timedelta(hours=3)


def working_day(after: dt.datetime) -> dt.datetime:
    """The next working day (Sunday to Thursday) after this moment, at midnight."""
    d = (after + dt.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    while d.weekday() in (4, 5):          # Friday, Saturday
        d += dt.timedelta(days=1)
    return d


def _iso(d: dt.datetime) -> str:
    return d.isoformat(timespec="minutes")


# ---------------------------------------------------------------- the inputs of each kind, fixed when the job is queued
def _prep_incident(p: dict) -> dict:
    if not p.get("segment_id"):
        raise ValueError("an incident simulation needs the road section (segment_id)")
    try:
        n = int(p.get("lanes_blocked"))
    except (TypeError, ValueError):
        raise ValueError("an incident simulation needs the number of lanes blocked")
    start = p.get("start_time") or _iso(riyadh_now().replace(minute=0, second=0, microsecond=0))
    return {"segment_id": p["segment_id"], "corridor": p.get("corridor") or "", "lanes_blocked": n, "start_time": start,
            "duration_hours": float(p.get("duration_hours") or rules.INCIDENT_WINDOW_HOURS)}


def _prep_closure(p: dict) -> dict:
    if not p.get("corridor") and not p.get("segment_ids"):
        raise ValueError("a closure simulation needs a road name")
    s, e = strategies._window(p)
    out = {"corridor": p.get("corridor") or "", "start_time": _iso(s), "end_time": _iso(e)}
    for k in ("segment_ids", "near", "lanes_closed", "span_km"):
        if p.get(k) is not None:
            out[k] = p[k]
    return out


def _prep_closure_run(p: dict) -> dict:
    out = _prep_closure(p)
    if out.get("lanes_closed") is not None:
        try:
            n = int(out["lanes_closed"])
        except (TypeError, ValueError):
            raise ValueError(f"lanes_closed must be a whole number of lanes, not '{out['lanes_closed']}'")
        if n <= 0:
            raise ValueError("lanes_closed must be 1 or more (leave it out for a full closure)")
        out["lanes_closed"] = n
    return out


def _prep_event(p: dict) -> dict:
    place = str(p.get("place") or p.get("venue") or "").strip()
    if not place:
        raise ValueError("an event simulation needs the venue")
    try:
        n = int(p.get("attendance"))
    except (TypeError, ValueError):
        raise ValueError("an event simulation needs the expected attendance")
    if n <= 0:
        raise ValueError("the attendance must be more than zero")
    day = riyadh_now().replace(hour=0, minute=0, second=0, microsecond=0)
    return {"place": place, "attendance": n, "start_time": p.get("start_time") or _iso(day.replace(hour=18)), "end_time": p.get("end_time") or _iso(day.replace(hour=23))}


# ---------------------------------------------------------------- what each kind runs: returns (summary, recommended, verdict, preview)
def _numbers(r: dict) -> dict:
    s, res = r["summary"], r["scenario"]["resolved"]
    return {"window_extra_trip_hours": s["window_extra_trip_hours"], "worst_hospital_access_delta_min": s["worst_hospital_access_delta_min"],
            "severe_segments": s["severe_segments_scenario"], "severe_segments_baseline": s["severe_segments_baseline"], "affected_segments": s["affected_segments"],
            "peak_hour": s["peak_hour"], "duration_h": s["duration_h"], "isolated_zones": s["isolated_zones"], "length_km": res.get("length_km"),
            "window": {"start": r["window"]["start"], "end": r["window"]["end"]}}


def _road_name(ids: List[str], fallback: str = "") -> str:
    segs = network_model.get_model().segments
    return next((segs[i]["corridor"] or segs[i]["name"] for i in ids if i in segs), fallback) or fallback


def _run_incident(p: dict, say) -> tuple:
    r = engine.run_scenario({"scenario_type": "closure", "segment_ids": [p["segment_id"]], "lanes_closed": p["lanes_blocked"], "start_time": p["start_time"],
                             "duration_hours": p["duration_hours"], "name": "Traffic incident"}, progress=say, persist=False, actor="noura")
    res = r["scenario"]["resolved"]
    return ({"road": _road_name(res["ids"], p.get("corridor") or ""), "lanes_closed": res.get("lanes_closed"), "full_closure": bool(res.get("full_closure")),
             **_numbers(r)}, "", "", r["geojson"])


def _run_closure_once(p: dict, say) -> tuple:
    """One closure as asked (full, or a number of lanes), without the strategy comparison."""
    r = engine.run_scenario({"scenario_type": "closure", **p, "name": "Closure"}, progress=say, persist=False, actor="noura")
    res = r["scenario"]["resolved"]
    return ({"road": res.get("corridor") or _road_name(res["ids"], p.get("corridor") or ""), "lanes_closed": res.get("lanes_closed"),
             "full_closure": res.get("lanes_closed") is None or bool(res.get("full_closure")), "section": res.get("why"), **_numbers(r)}, "", "", r["geojson"])


def _run_closure(p: dict, say) -> tuple:
    out = strategies.compare(dict(p), progress=say, persist=False, actor="noura")
    rows = out["strategies"]
    base = next(x for x in rows if x["id"] == "do_nothing")
    m = base["metrics"]
    summary = {"road": out["closure"].get("corridor") or _road_name(out["closure"].get("ids") or [], p.get("corridor") or ""),
               "lanes_closed": out["closure"].get("lanes_closed"), "full_closure": out["closure"].get("lanes_closed") is None or bool(out["closure"].get("full_closure")),
               "window_extra_trip_hours": m["window_extra_trip_hours"], "worst_hospital_access_delta_min": m["worst_hospital_access_delta_min"],
               "severe_segments": m["severe_segments"], "severe_segments_baseline": m["severe_segments_baseline"], "affected_segments": m["affected_segments"],
               "peak_hour": m["peak_hour"], "duration_h": m["duration_h"], "isolated_zones": m["isolated_zones"], "length_km": out["closure"].get("length_km"),
               "window": {"start": out["window"]["start"], "end": out["window"]["end"]},
               "strategies": [{"id": x["id"], "name": x["name"], "effort": x["effort"], "skipped": x["skipped"], **({} if x["skipped"] else {
                   "score": x["score"], "benefit_vs_do_nothing_pct": x["benefit_vs_do_nothing_pct"], "extra_trip_hours": x["metrics"]["window_extra_trip_hours"],
                   "hospital_delta_min": x["metrics"]["worst_hospital_access_delta_min"], "rank": x.get("rank")})} for x in rows],
               "assumptions": out["assumptions"][:3]}
    best = next((x for x in rows if x["id"] == out["recommended"] and not x["skipped"]), base)
    return summary, out["recommended"], out["verdict"], best["geojson"]


def _run_event(p: dict, say) -> tuple:
    model = network_model.get_model()
    if not model.resolve_place(p["place"]):
        from backend.mobility import riyadh_network as RN

        raise ValueError(f"The road network has no place named '{p['place']}'. Places known by name include: " + ", ".join(sorted(v[0] for v in RN.LOCATIONS.values())[:12]) + ".")
    r = engine.run_scenario({"scenario_type": "event", "place": p["place"], "event": {"attendees": p["attendance"]}, "start_time": p["start_time"], "end_time": p["end_time"],
                             "name": f"Event at {p['place']}"}, progress=say, persist=False, actor="noura")
    ev = r["extra"]["event"]
    return ({"venue": p["place"], "attendance": p["attendance"], "added_vehicles_per_hour": ev["added_vehicles_per_hour"], "parking_deficit_vehicles": ev["parking_deficit_vehicles"],
             "metro_utilisation": ev["metro_utilisation"], **_numbers(r)}, "", "", r["geojson"])


def _prep_road_impact(p: dict) -> dict:
    """A repair next to a road: the same closure in the day window and in the night window of the next working day."""
    if not p.get("segment_id"):
        raise ValueError("a road-impact simulation needs the road section (segment_id)")
    rule = rules.ROAD_IMPACT.get(p.get("category") or "water", rules.ROAD_IMPACT["water"])
    day, night = p.get("day") or rule["day"], p.get("night") or rule["night"]
    d = working_day(riyadh_now())

    def window(h0: int, h1: int) -> tuple:
        s = d.replace(hour=int(h0))
        e = d.replace(hour=int(h1)) + dt.timedelta(days=1 if int(h1) <= int(h0) else 0)
        return _iso(s), _iso(e)

    n = p.get("lanes_closed")
    (ds, de), (ns, ne) = window(*day), window(*night)
    return {"segment_id": p["segment_id"], "corridor": p.get("corridor") or "", "lanes": int(p.get("lanes") or 0), "lanes_closed": int(n) if n else None,
            "day_start": ds, "day_end": de, "night_start": ns, "night_end": ne, "night_saving": float(p.get("night_saving", rule["night_saving"])),
            "category": p.get("category") or "water"}


def _run_road_impact(p: dict, say) -> tuple:
    from backend.mobility import road_impact

    def one(start: str, end: str, label: str, lo: int) -> dict:
        q = {"scenario_type": "closure", "segment_ids": [p["segment_id"]], "start_time": start, "end_time": end, "name": f"Repair closure ({label})"}
        if p.get("lanes_closed"):
            q["lanes_closed"] = p["lanes_closed"]
        return engine.run_scenario(q, progress=lambda pct, msg: say(lo + pct / 2, f"{label}: {msg}"), persist=False, actor="noura")

    runs = {"day": one(p["day_start"], p["day_end"], "day", 0), "night": one(p["night_start"], p["night_end"], "night", 50)}
    nums = {k: _numbers(r) for k, r in runs.items()}
    out = {k: {"start": v["window"]["start"], "end": v["window"]["end"], "window_extra_trip_hours": v["window_extra_trip_hours"],
               "worst_hospital_access_delta_min": v["worst_hospital_access_delta_min"], "severe_segments": v["severe_segments"],
               "severe_segments_baseline": v["severe_segments_baseline"], "affected_segments": v["affected_segments"]} for k, v in nums.items()}
    res = runs["day"]["scenario"]["resolved"]
    rec = road_impact.recommend(out["day"], out["night"], p["night_saving"])
    summary = {"road": _road_name(res["ids"], p.get("corridor") or ""), "segment_id": p["segment_id"], "segment_ids": list(res["ids"]), "lanes": p.get("lanes"),
               "lanes_closed": p.get("lanes_closed"), "full_closure": not p.get("lanes_closed") or bool(res.get("full_closure")), "length_km": res.get("length_km"),
               "day": out["day"], "night": out["night"], "recommended": rec, "small": road_impact.is_small(out["day"], out["night"]), "category": p.get("category") or "water"}
    return summary, rec, road_impact.line(summary), runs[rec]["geojson"]


PREPARE: Dict[str, Callable[[dict], dict]] = {"incident": _prep_incident, "closure": _prep_closure, "closure_run": _prep_closure_run, "event": _prep_event,
                                              "road_impact": _prep_road_impact}
RUNNERS: Dict[str, Callable] = {"incident": _run_incident, "closure": _run_closure, "closure_run": _run_closure_once, "event": _run_event,
                                "road_impact": _run_road_impact}


class Jobs:
    def __init__(self, platform, inline: bool = False):
        """inline: run each job in the caller's thread before `submit` returns (the tests). Otherwise one worker thread, one job at a time."""
        self.p, self.inline = platform, inline
        self._cv = threading.Condition(threading.RLock())
        self._jobs: Dict[str, dict] = {}
        self._queue: collections.deque = collections.deque()
        self._previews: "collections.OrderedDict[str, dict]" = collections.OrderedDict()
        self._thread: Optional[threading.Thread] = None
        self._paused = False

    # ---- test controls -------------------------------------------------------------------------------------
    def pause(self) -> None:
        with self._cv:
            self._paused = True

    def resume(self) -> None:
        with self._cv:
            self._paused = False
            self._cv.notify_all()

    def wait(self, scenario_id: str, timeout: float = 60.0) -> Optional[dict]:
        end = time.time() + timeout
        with self._cv:
            while (self._jobs.get(scenario_id) or {}).get("status") in ACTIVE and time.time() < end:
                self._cv.wait(0.2)
        return self.status(scenario_id)

    # ---- queueing -------------------------------------------------------------------------------------------
    def submit(self, kind: str, params: dict, subject_id: str, requested_by: str, on_done: Optional[Callable[[dict], None]] = None, name: str = "") -> str:
        """Queue one simulation and return its Scenario_ID. A job of the same kind for the same subject that is still queued or
        running is returned instead of a second one. Raises ValueError for unusable inputs and StoreWriteError when ArcGIS Online
        will not take the row; in both cases nothing is queued."""
        job = self._create(kind, params, subject_id, requested_by, on_done, name, dedupe=True)
        if not job.pop("fresh"):
            return job["id"]
        self._start(job)
        return job["id"]

    def run_now(self, kind: str, params: dict, subject_id: str, requested_by: str, name: str = "") -> dict:
        """Run one simulation in the caller's thread and return its result (the tools). It is stored exactly like a queued job."""
        job = self._create(kind, params, subject_id, requested_by, None, name, dedupe=False)
        job.pop("fresh")
        self._run(job)
        return job["result"]

    def _create(self, kind, params, subject_id, requested_by, on_done, name, dedupe) -> dict:
        if kind not in RUNNERS:
            raise ValueError(f"unknown simulation kind '{kind}' (use one of: {', '.join(RUNNERS)})")
        fixed = PREPARE[kind](dict(params or {}))
        with self._cv:
            for j in self._jobs.values():
                if dedupe and j["kind"] == kind and j["subject_id"] == subject_id and j["status"] in ACTIVE and not j["preview_only"]:
                    return {"id": j["id"], "fresh": False}
            sid = self.p.store.next_id("SCN")
            job = {"id": sid, "kind": kind, "params": fixed, "subject_id": subject_id, "status": "Queued", "progress": 0, "message": "Waiting for the simulation worker",
                   "error": "", "on_done": on_done, "preview_only": False, "name": name or f"{kind.replace('_', ' ').capitalize()} simulation", "result": None}
            self._jobs[sid] = job
        try:                                      # outside the lock: a write to ArcGIS Online can take a second
            self.p.store.upsert(S.SCENARIOS, {"Scenario_ID": sid, "Scenario_Type": kind, "Name": job["name"], "Params": json.dumps(fixed, default=str), "Status": "Queued",
                                              "Summary": "", "Recommended": "", "Verdict": "", "Subject_ID": subject_id, "Requested_By": requested_by, "Created": utcnow(),
                                              "Completed": "", "Runtime_S": None, "Network_Fingerprint": "", "Error": "", "Data_Classification": S.MODELLED})
        except Exception:
            with self._cv:
                self._jobs.pop(sid, None)
            raise
        job["fresh"] = True
        return job

    def _start(self, job: dict) -> None:
        if self.inline:
            self._run(job)
            return
        with self._cv:
            self._queue.append(job["id"])
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._loop, name="mobility-jobs", daemon=True)
                self._thread.start()
            self._cv.notify_all()

    def _loop(self) -> None:
        while True:
            with self._cv:
                while self._paused or not self._queue:
                    self._cv.wait(1.0)
                job = self._jobs.get(self._queue.popleft())
            if job:
                try:
                    self._run(job)
                except Exception:  # noqa: BLE001  one job must never stop the worker
                    log.exception("simulation job %s ended unexpectedly", job["id"])
                    self._set(job, status="Failed", error="The simulation worker failed unexpectedly.")

    # ---- running --------------------------------------------------------------------------------------------
    def _set(self, job: dict, **changes) -> None:
        with self._cv:
            job.update(changes)
            self._cv.notify_all()

    def _wait_for_model(self, job: dict) -> None:
        if not getattr(self.p.settings, "mobility_warm", False):
            return                                 # no start-up build is running: the engine builds the model when it needs it
        end = time.time() + WAIT_MODEL_S
        while time.time() < end:
            st = traffic.status()
            if st["ready"]:
                return
            if st["error"]:
                raise RuntimeError(f"The traffic model could not be built: {st['error']}")
            if not st["building"]:
                traffic.warm()
            self._set(job, message=f"Waiting for the traffic model ({len(st['hours_ready'])} of 24 hours ready)")
            time.sleep(2.0)
        raise RuntimeError("The traffic model was not ready in time.")

    def _run(self, job: dict) -> None:
        sid, t0 = job["id"], time.time()
        summary, rec, verdict, preview, err = {}, "", "", None, ""
        try:
            self._wait_for_model(job)
            self._set(job, status="Running", progress=1, message="Starting")
            if not job["preview_only"]:
                try:
                    self.p.store.update(S.SCENARIOS, sid, Status="Running")
                except Exception as exc:  # noqa: BLE001  the result write below is what counts
                    log.warning("could not mark %s as running in the system of record: %s", sid, exc)
            summary, rec, verdict, preview = RUNNERS[job["kind"]](job["params"], lambda pct, msg: self._set(job, progress=max(1, min(99, int(pct))), message=str(msg)))
        except Exception as exc:  # noqa: BLE001  the reason is the result
            if not isinstance(exc, (ValueError, RuntimeError)):
                log.exception("simulation %s failed", sid)
            err = (str(exc) or type(exc).__name__)[:250]
        if job["preview_only"]:
            if preview and not err:
                self._keep_preview(job["source"], preview)
            self._set(job, status="Failed" if err else "Completed", error=err, progress=100)
            return
        status = "Failed" if err else "Completed"
        fp = (getattr(network_model._model, "provenance", None) or {}).get("fingerprint", "") if network_model._model else ""
        changes = {"Status": status, "Summary": json.dumps(summary, default=str) if summary else "", "Recommended": rec, "Verdict": verdict, "Completed": utcnow(),
                   "Runtime_S": round(time.time() - t0, 1), "Network_Fingerprint": fp, "Error": err}
        try:
            self.p.store.update(S.SCENARIOS, sid, **changes)
        except Exception as exc:  # noqa: BLE001  refused by the system of record: the result is not kept anywhere
            log.error("ArcGIS Online refused the result of %s: %s", sid, exc)
            status, err, summary, rec, verdict, preview = "Failed", f"ArcGIS Online refused the simulation result: {exc}"[:250], {}, "", "", None
        if preview and status == "Completed":
            self._keep_preview(sid, preview)
        result = {"Scenario_ID": sid, "Scenario_Type": job["kind"], "Name": job["name"], "Subject_ID": job["subject_id"], "Status": status, "summary": summary,
                  "Recommended": rec, "Verdict": verdict, "Error": err, "params": job["params"]}
        self._set(job, status=status, error=err, progress=100, message="Done" if status == "Completed" else "Failed", result=result)
        self._trim()
        if job["on_done"]:
            try:
                job["on_done"](result)
            except Exception:  # noqa: BLE001  the worker goes on to the next job
                log.exception("the follow-up of simulation %s failed", sid)

    def _keep_preview(self, sid: str, g: dict) -> None:
        with self._cv:
            self._previews.pop(sid, None)
            self._previews[sid] = {"closed": g.get("closed"), "segments": g.get("segments"), "routes": g.get("routes")}
            while len(self._previews) > PREVIEWS:
                self._previews.popitem(last=False)

    def _trim(self) -> None:
        with self._cv:
            done = [k for k, j in self._jobs.items() if j["status"] not in ACTIVE]
            for k in done[:max(0, len(done) - KEEP)]:
                del self._jobs[k]

    # ---- reading --------------------------------------------------------------------------------------------
    def busy(self, kind: Optional[str] = None) -> int:
        """Jobs queued or running (map-preview recalculations are not counted)."""
        with self._cv:
            return sum(1 for j in self._jobs.values() if j["status"] in ACTIVE and not j["preview_only"] and (kind is None or j["kind"] == kind))

    def active(self) -> List[dict]:
        with self._cv:
            return [{"id": j["id"], "kind": j["kind"], "subject_id": j["subject_id"], "status": j["status"], "name": j["name"]}
                    for j in self._jobs.values() if j["status"] in ACTIVE and not j["preview_only"]]

    def status(self, scenario_id: str) -> Optional[dict]:
        with self._cv:
            j = self._jobs.get(scenario_id)
            if j and not j["preview_only"]:
                return {"id": j["id"], "kind": j["kind"], "status": j["status"], "progress": j["progress"], "message": j["message"], "error": j["error"]}
        row = self.p.store.get(S.SCENARIOS, scenario_id)
        if not row:
            return None
        a = row["attrs"]
        st = a.get("Status") or ""
        return {"id": scenario_id, "kind": a.get("Scenario_Type") or "", "status": st, "progress": 100 if st not in ACTIVE else 0, "message": "", "error": a.get("Error") or ""}

    def row(self, scenario_id: str) -> Optional[dict]:
        """The stored row with its summary and inputs parsed, or None."""
        row = self.p.store.get(S.SCENARIOS, scenario_id)
        if not row:
            return None
        a = dict(row["attrs"])
        for src, dst in (("Summary", "summary"), ("Params", "params")):
            try:
                a[dst] = json.loads(a.get(src) or "{}")
            except ValueError:
                a[dst] = {}
        return a

    def preview(self, scenario_id: str) -> Optional[dict]:
        """The map preview of a recent run: the closed section, the road sections that change and the routes. None when it is not held."""
        with self._cv:
            return self._previews.get(scenario_id)

    def request_preview(self, scenario_id: str) -> Optional[dict]:
        """The preview when it is held; otherwise start calculating it again from the stored inputs and return None (ask again shortly).
        Raises KeyError for an unknown scenario and ValueError for one that did not complete."""
        hit = self.preview(scenario_id)
        if hit:
            return hit
        row = self.row(scenario_id)
        if not row:
            raise KeyError(scenario_id)
        if row.get("Status") != "Completed" or row.get("Scenario_Type") not in RUNNERS:
            raise ValueError(f"simulation {scenario_id} has no result to draw (status: {row.get('Status') or 'unknown'})")
        with self._cv:
            for j in self._jobs.values():
                if j["preview_only"] and j["source"] == scenario_id and j["status"] in ACTIVE:
                    return None
            key = f"preview:{scenario_id}:{time.time_ns()}"
            job = {"id": key, "kind": row["Scenario_Type"], "params": row["params"], "subject_id": row.get("Subject_ID") or "", "status": "Queued", "progress": 0,
                   "message": "", "error": "", "on_done": None, "preview_only": True, "source": scenario_id, "name": "map preview", "result": None}
            self._jobs[key] = job
        self._start(job)
        return self.preview(scenario_id)

    # ---- start-up -------------------------------------------------------------------------------------------
    def recover(self) -> List[str]:
        """Rows left Queued or Running by a server that stopped become Interrupted. Returns their ids, oldest first."""
        with self._cv:
            mine = {k for k, j in self._jobs.items() if j["status"] in ACTIVE}
        out = []
        for r in sorted(self.p.store.all(S.SCENARIOS), key=lambda r: r["id"]):
            if r["attrs"].get("Status") in ACTIVE and r["id"] not in mine:
                try:
                    self.p.store.update(S.SCENARIOS, r["id"], Status="Interrupted", Error=INTERRUPTED, Completed=utcnow())
                    out.append(r["id"])
                except Exception as exc:  # noqa: BLE001
                    log.warning("could not mark %s as interrupted: %s", r["id"], exc)
        return out
