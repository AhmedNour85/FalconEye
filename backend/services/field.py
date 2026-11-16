"""VERIFY: field submissions and the agent's deterministic assessment of them against the original AI finding."""
from __future__ import annotations

import re
from pathlib import Path

from backend.gis import geo
from backend.gis import schema as S
from backend.gis.store import Store, StoreWriteError, utcnow
from backend.services import learning
from backend.services.audit import Audit

STATUSES = ("Confirmed", "Rejected", "Needs Further Inspection", "Repaired", "Escalate")
GPS_TOLERANCE_M = 150.0


class FieldError(ValueError):
    pass


def tasks_for_worker(store: Store, worker_id: str) -> list[dict]:
    out = []
    for w in store.query(S.WORK_ORDERS, Assigned_Worker=worker_id):
        a = w["attrs"]
        if a["Status"] in ("Completed", "Cancelled"):
            continue
        inc = store.get(S.INCIDENTS, a["Incident_ID"])
        pt = geo.centroid(inc["geom"])
        dets = [store.get(S.DETECTIONS, d) for d in inc["attrs"]["Detection_IDs"].split(",") if d]
        out.append({"work_order": a, "incident": inc["attrs"], "location": {"lon": pt[0], "lat": pt[1]},
                    "instructions": a["Instructions"] or "Inspect the location and confirm or reject the AI finding.",
                    "ai_finding": [{"detection_id": d["id"], "type": d["attrs"]["Detection_Type"], "evidence": d["attrs"]["Evidence"], "confidence": d["attrs"]["Confidence"]} for d in dets if d]})
    out.sort(key=lambda t: t["work_order"]["Priority"])
    return out


def investigator_name(store: Store, worker_id: str) -> str:
    w = store.get(S.WORKERS, worker_id) if worker_id else None
    return w["attrs"]["Name"] if w else ""


def accept(store: Store, audit: Audit, work_order_id: str, worker_id: str) -> dict:
    """The assigned investigator confirms the assignment (the operator is told). Idempotent."""
    wo = store.get(S.WORK_ORDERS, work_order_id)
    if not wo:
        raise FieldError("work order not found")
    if wo["attrs"]["Assigned_Worker"] != worker_id:
        raise FieldError(f"work order {work_order_id} is not assigned to {worker_id}")
    if wo["attrs"]["Status"] not in ("Assigned", "In Progress"):
        raise FieldError(f"work order is {wo['attrs']['Status']}; nothing to accept")
    if wo["attrs"].get("Accepted_At"):
        return {"ok": True, "already": True, "work_order_id": work_order_id, "incident_id": wo["attrs"]["Incident_ID"], "accepted_at": wo["attrs"]["Accepted_At"]}
    when = utcnow()
    store.update(S.WORK_ORDERS, work_order_id, Accepted_At=when)
    audit.log("field", "ASSIGNMENT ACCEPTED", "field_portal", wo["attrs"]["Incident_ID"], {"wo": work_order_id}, {"accepted_at": when}, actor=worker_id)
    return {"ok": True, "already": False, "work_order_id": work_order_id, "incident_id": wo["attrs"]["Incident_ID"], "accepted_at": when}


def submit(store: Store, audit: Audit, work_order_id: str, worker_id: str, status: str, observation: str,
           lat: float, lon: float, photo: bytes | None = None, filename: str = "", simulated: bool = False) -> dict:
    """An investigator's report. A photo is kept as an attachment on the report's row in the system of record, never as a file on this computer."""
    if status not in STATUSES:
        raise FieldError(f"status must be one of {STATUSES}")
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise FieldError("invalid GPS coordinates")
    if len(observation.strip()) < 5:
        raise FieldError("observation text is required")
    wo = store.get(S.WORK_ORDERS, work_order_id)
    if not wo:
        raise FieldError("work order not found")
    if wo["attrs"]["Assigned_Worker"] != worker_id:
        raise FieldError(f"work order {work_order_id} is not assigned to {worker_id}")
    if wo["attrs"]["Status"] == "Completed":
        raise FieldError("work order already completed")
    inc = store.get(S.INCIDENTS, wo["attrs"]["Incident_ID"])
    pt = geo.centroid(inc["geom"])
    dist = geo.haversine_m((lon, lat), pt)
    vid = store.next_id("VER")
    safe = ""
    if photo:
        ext = Path(filename).suffix.lower()
        if ext not in (".jpg", ".jpeg", ".png", ".webp"):
            raise FieldError("photo must be jpg/png/webp")
        if len(photo) > 8_000_000:
            raise FieldError("photo too large (8 MB max)")
        safe = re.sub(r"[^A-Za-z0-9_.-]", "_", f"{vid}{ext}")
    store.upsert(S.VERIFICATION, {"Verification_ID": vid, "Work_Order_ID": work_order_id, "Incident_ID": inc["id"], "Worker_ID": worker_id, "Investigator_Name": investigator_name(store, worker_id), "Observation": observation.strip(),
                                  "Verification_Status": status, "GPS_Location": f"{lat:.6f},{lon:.6f}", "Photo_URL": "", "Timestamp": utcnow(),
                                  "Distance_To_Detection_M": round(dist, 1), "Agent_Assessment": "", "Simulated_Worker": "Yes" if simulated else "No",
                                  "Data_Classification": S.SIMULATED if simulated else S.OPERATIONAL}, geo.point(lon, lat))
    photo_warning = ""
    if photo:                                # the attachment needs its row to exist first
        try:
            store.add_attachment(S.VERIFICATION, vid, safe, photo)
            store.update(S.VERIFICATION, vid, Photo_URL=f"/api/evidence/{vid}/{safe}")
        except StoreWriteError as exc:       # the report itself is saved and is valid without a photo: carry on, and say so
            photo_warning = f"Your report was saved, but the photo was not: {exc}"
    audit.log("field", "FIELD SUBMISSION", "field_portal", inc["id"], {"wo": work_order_id, "status": status}, {"verification": vid, "distance_m": round(dist)},
              actor=worker_id)
    res = assess(store, audit, vid)
    if photo:
        res["photo_saved"] = not photo_warning
    if photo_warning:
        res["warning"] = photo_warning
    return res


def assess(store: Store, audit: Audit, verification_id: str) -> dict:
    """Compare field evidence with the AI prediction and update incident/detection/work-order status."""
    v = store.get(S.VERIFICATION, verification_id)
    if not v:
        raise FieldError("verification not found")
    a = v["attrs"]
    inc = store.get(S.INCIDENTS, a["Incident_ID"])
    dets = [store.get(S.DETECTIONS, d) for d in inc["attrs"]["Detection_IDs"].split(",") if d]
    dets = [d for d in dets if d]
    dist = a["Distance_To_Detection_M"] or 0.0
    st = a["Verification_Status"]
    notes = []
    if dist > GPS_TOLERANCE_M:
        notes.append(f"GPS fix was {dist:.0f} m from the detection (tolerance {GPS_TOLERANCE_M:.0f} m): evidence is weak, further inspection required.")
        outcome = "Requires Further Inspection"
    elif st == "Confirmed":
        outcome = "Confirmed"
    elif st == "Rejected":
        outcome = "Rejected"
    elif st == "Needs Further Inspection":
        outcome = "Requires Further Inspection"
    elif st == "Escalate":
        outcome = "Escalated"
    elif st == "Repaired":
        outcome = "Confirmed"
        notes.append("Worker reports the fault repaired; incident closure requires operator approval.")
    else:
        outcome = "Requires Further Inspection"
    predicted = "; ".join(f"{d['attrs']['Detection_Type']} (risk {d['attrs']['Risk_Score']}, confidence {d['attrs']['Confidence']})" for d in dets) or "n/a"
    def _assessment(obs: str) -> str:
        return f"AI predicted: {predicted}. Field observed: '{obs}' -> {st}. Distance to detection {dist:.0f} m. Agent assessment: {outcome}. " + " ".join(notes)

    assessment = _assessment(a["Observation"])
    stored = assessment                                  # the hosted field holds 255 characters: the quoted observation (kept in full in its own field) is shortened to fit
    if len(stored) > 255:
        obs = a["Observation"]
        stored = _assessment(obs[:max(20, len(obs) - (len(stored) - 255) - 3)].rstrip() + "...")
        stored = stored if len(stored) <= 255 else stored[:252].rstrip() + "..."
    inc_status = {"Confirmed": "Confirmed", "Rejected": "Rejected", "Requires Further Inspection": "Requires Further Inspection", "Escalated": "Escalated"}[outcome]
    if st == "Repaired" and outcome == "Confirmed":
        inc_status = "Repair Reported"
    changed_det = outcome in ("Confirmed", "Rejected")
    store.update(S.VERIFICATION, verification_id, Agent_Assessment=stored)
    if inc["attrs"]["Status"] in ("Resolved", "Closed - False Positive"):
        # a report that is assessed again after the incident was closed (for example a row pulled back from ArcGIS Online) keeps its text but changes nothing else
        return {"ok": True, "verification_id": verification_id, "incident_id": inc["id"], "outcome": outcome, "incident_status": inc["attrs"]["Status"], "assessment": assessment,
                "distance_m": dist, "detections_updated": [], "calibration_update": None, "already_closed": True}
    store.update(S.INCIDENTS, inc["id"], Status=inc_status, Verification_Outcome=outcome if outcome in ("Confirmed", "Rejected") else inc["attrs"]["Verification_Outcome"],
                 Last_Updated=utcnow())
    if changed_det:
        for d in dets:
            store.update(S.DETECTIONS, d["id"], Status="Verified-True" if outcome == "Confirmed" else "Verified-False")
    wo = store.get(S.WORK_ORDERS, a["Work_Order_ID"])
    # inspection finished (rejected / repaired / escalated) completes the task; a confirmed fault keeps it In Progress until repaired
    new_wo = "Completed" if (st in ("Rejected", "Repaired", "Escalate") and outcome != "Requires Further Inspection") else "In Progress" if outcome == "Confirmed" else None
    if wo and new_wo and wo["attrs"]["Status"] != "Completed":
        store.update(S.WORK_ORDERS, wo["id"], Status=new_wo)
        wid = wo["attrs"]["Assigned_Worker"]
        if wid and new_wo == "Completed":
            wk = store.get(S.WORKERS, wid)["attrs"]
            n = max(0, wk["Open_Tasks"] - 1)
            store.update(S.WORKERS, wid, Open_Tasks=n, Status="Available" if n == 0 else "Assigned", Last_Update=utcnow())
    cal = learning.recalibrate(store) if changed_det else None
    audit.log("system", "VERIFICATION ASSESSED", "verification_tool", inc["id"], {"verification": verification_id}, assessment)
    return {"ok": True, "verification_id": verification_id, "incident_id": inc["id"], "outcome": outcome, "incident_status": inc_status, "assessment": assessment,
            "distance_m": dist, "detections_updated": [d["id"] for d in dets] if changed_det else [], "calibration_update": cal}
