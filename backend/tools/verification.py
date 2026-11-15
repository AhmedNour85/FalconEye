"""VERIFY / LEARN tools."""
from __future__ import annotations

from backend.gis import schema as S
from backend.services import field, learning
from backend.tools.common import ToolContext, ToolError


def verify_outcome(ctx: ToolContext, incident_id: str | None = None) -> dict:
    """Retrieve field evidence for an incident, compare with the original AI finding and report the (system-confirmed) outcome."""
    iid = incident_id or ctx.state.get("focus_incident")
    if not iid:
        raise ToolError("no incident specified or in context")
    inc = ctx.store.get(S.INCIDENTS, iid)
    if not inc:
        raise ToolError(f"incident {iid} not found")
    ctx.state["focus_incident"] = iid
    vers = sorted(ctx.store.query(S.VERIFICATION, Incident_ID=iid), key=lambda f: f["attrs"]["Timestamp"])
    if not vers:
        wos = ctx.store.query(S.WORK_ORDERS, Incident_ID=iid)
        return {"incident_id": iid, "verified": False, "status": inc["attrs"]["Status"],
                "message": "No field verification has been submitted yet." + (f" Work order {wos[-1]['id']} is {wos[-1]['attrs']['Status']}." if wos else " No work order exists yet.")}
    latest = vers[-1]
    if not latest["attrs"]["Agent_Assessment"]:
        field.assess(ctx.p.store, ctx.p.audit, latest["id"])
        latest = ctx.store.get(S.VERIFICATION, latest["id"])
    inc = ctx.store.get(S.INCIDENTS, iid)
    dets = [ctx.store.get(S.DETECTIONS, d) for d in inc["attrs"]["Detection_IDs"].split(",") if d]
    return {"incident_id": iid, "verified": True, "incident_status": inc["attrs"]["Status"], "verification_outcome": inc["attrs"]["Verification_Outcome"],
            "latest_verification": {k: latest["attrs"][k] for k in ("Verification_ID", "Worker_ID", "Observation", "Verification_Status", "GPS_Location", "Photo_URL", "Timestamp",
                                                                 "Distance_To_Detection_M", "Simulated_Worker")},
            "agent_assessment": latest["attrs"]["Agent_Assessment"], "history": [v["attrs"]["Verification_Status"] for v in vers],
            "detections": [{"id": d["id"], "type": d["attrs"]["Detection_Type"], "status": d["attrs"]["Status"], "predicted_risk": d["attrs"]["Risk_Score"]} for d in dets if d],
            "next_step": ("Propose closure for operator approval." if inc["attrs"]["Status"] == "Repair Reported" or inc["attrs"]["Verification_Outcome"] == "Rejected"
                          else "Await repair report from the field team." if inc["attrs"]["Verification_Outcome"] == "Confirmed" else "Further inspection or escalation needed.")}


def evaluate_outcomes(ctx: ToolContext, recalibrate: bool = False) -> dict:
    """Compare predictions with verified conditions; optionally refresh the configurable risk calibration (NOT model retraining)."""
    changes = learning.recalibrate(ctx.store) if recalibrate else None
    ev = learning.evaluation(ctx.store)
    ev.pop("outcomes", None)
    if changes:
        ctx.p.audit.log(ctx.session_id, "CALIBRATION UPDATED", "outcome_evaluation", "", "recalibrate", changes)
    return {"evaluation": ev, "calibration_update": changes,
            "disclaimer": "Learning = feedback records, metrics and configurable calibration. No ML model was retrained."}
