"""Where an incident stands on the seven lifecycle steps shown on every alert. Read-only: nothing is stored, the position is worked out from the records."""
from __future__ import annotations

from backend.gis import schema as S

STEPS = ["Detected", "Analysed", "Proposed", "Approved", "Dispatched", "Verified", "Resolved"]
RESOLVED = ("Resolved", "Closed")


def position(store, incident_id: str) -> dict | None:
    """{"steps": [{"key", "state": done|current|todo|stopped}], "current", "outcome": open|rejected|resolved}, or None for an unknown incident."""
    inc = store.get(S.INCIDENTS, incident_id) if incident_id else None
    if not inc:
        return None
    approvals = [a["attrs"] for a in store.query(S.APPROVALS, Incident_ID=incident_id)]
    scenarios = [s["attrs"] for s in store.query(S.SCENARIOS, Subject_ID=incident_id)]
    resolved = inc["attrs"].get("Status") in RESOLVED
    executed = [a for a in approvals if a.get("Status") == "Executed"]
    rejected = bool(approvals) and not executed and any(a.get("Status") == "Rejected" for a in approvals) and not any(a.get("Status") == "Proposed" for a in approvals)
    waiting_for_model = bool(scenarios) and all(s.get("Status") in ("Queued", "Running") for s in scenarios)
    done = {
        "Detected": True,
        "Analysed": not waiting_for_model,                           # a city incident is analysed when triage opens it; a mobility one when its simulation has finished or failed
        "Proposed": bool(executed),                                   # current while a proposal waits for a person's decision (or is being prepared)
        "Approved": bool(executed),
        "Dispatched": any(a.get("Action_Type") == "assign_worker" for a in executed),
        "Verified": bool(store.query(S.VERIFICATION, Incident_ID=incident_id)),
        "Resolved": resolved,
    }
    if resolved:
        done = {k: True for k in done}                               # closing is only possible once the incident was handled; a plan with nothing to repair has no repair visit
    steps, current = [], None
    for key in STEPS:
        if done[key]:
            state = "done"
        elif current is None:
            current, state = key, "current"
        else:
            state = "todo"
        steps.append({"key": key, "state": state})
    if rejected:                                                     # the proposal was refused: the strip stops at Proposed
        steps = [{"key": s["key"], "state": ("stopped" if s["key"] == "Proposed" else "done" if s["key"] in ("Detected", "Analysed") else "todo")} for s in steps]
        current = "Proposed"
    return {"steps": steps, "current": "Resolved" if resolved else current, "outcome": "resolved" if resolved else "rejected" if rejected else "open"}
