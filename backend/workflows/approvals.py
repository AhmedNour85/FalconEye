"""Human approval gate: analysis -> recommendation -> PROPOSED action -> APPROVED -> EXECUTED (verified)."""
from __future__ import annotations

import json

from backend.gis import schema as S
from backend.gis.store import Store, StoreWriteError, utcnow
from backend.services.audit import Audit
from backend.workflows.actions import HANDLERS


class ApprovalService:
    def __init__(self, store: Store, audit: Audit):
        self.store = store
        self.audit = audit

    def propose(self, session_id: str, action_type: str, payload: dict, summary: str, target: str, location: str = "", priority: str = "",
                team: str = "", expected: str = "", incident_id: str = "") -> dict:
        if action_type not in HANDLERS:
            raise ValueError(f"unknown action type {action_type}")
        # de-duplicate identical pending proposals
        for f in self.store.query(S.APPROVALS, Status="Proposed", Action_Type=action_type, Target=target):
            if json.loads(f["attrs"]["Payload"]) == payload:
                return {**f["attrs"], "duplicate": True}
        aid = self.store.next_id("APR")
        rec = {"Approval_ID": aid, "Action_Type": action_type, "Status": "Proposed", "Summary": summary, "Payload": json.dumps(payload), "Target": target,
               "Location": location, "Priority": priority, "Team": team, "Expected_Result": expected, "Created": utcnow(), "Decided": "", "Decided_By": "",
               "Result": "", "Session_ID": session_id, "Incident_ID": incident_id}
        self.store.upsert(S.APPROVALS, rec)
        self.audit.log(session_id, f"PROPOSED {action_type}", "approval_gate", incident_id, payload, summary, "Proposed")
        return rec

    def amend(self, approval_id: str, patch: dict, expected_suffix: str = "") -> bool:
        """Add to a proposal that is still waiting (for example the planned closure that goes with a repair). Only while Proposed:
        a decided proposal is never changed. The 'If approved' text gains the suffix so the operator sees what the approval now covers."""
        f = self.store.get(S.APPROVALS, approval_id)
        if not f or f["attrs"]["Status"] != "Proposed":
            return False
        a = f["attrs"]
        payload = {**json.loads(a["Payload"]), **patch}
        expected = a["Expected_Result"] + expected_suffix
        self.store.update(S.APPROVALS, approval_id, Payload=json.dumps(payload), Expected_Result=expected if len(expected) <= 255 else expected[:252] + "...")
        self.audit.log(a["Session_ID"], f"AMENDED {a['Action_Type']}", "approval_gate", a["Incident_ID"], patch, expected_suffix.strip() or "payload amended", "Proposed")
        return True

    def pending(self) -> list[dict]:
        return [f["attrs"] for f in self.store.query(S.APPROVALS, Status="Proposed")]

    def all(self) -> list[dict]:
        return [f["attrs"] for f in self.store.all(S.APPROVALS)][::-1]

    def approve(self, approval_id: str, actor: str = "operator") -> dict:
        f = self.store.get(S.APPROVALS, approval_id)
        if not f:
            return {"ok": False, "error": f"approval {approval_id} not found"}
        a = f["attrs"]
        if a["Status"] != "Proposed":
            return {"ok": False, "error": f"approval {approval_id} is already {a['Status']}"}
        payload = json.loads(a["Payload"])
        try:
            with self.store.batch():      # the handler's writes go to the system of record together, one request per layer
                res = HANDLERS[a["Action_Type"]](self.store, payload)
        except StoreWriteError:   # the system of record refused the change: nothing was done, the approval stays Proposed and the operator is told
            raise
        except Exception as exc:  # structured failure, never a silent success
            res = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        status = "Executed" if res.get("ok") else "Failed"
        self.store.update(S.APPROVALS, approval_id, Status=status, Decided=utcnow(), Decided_By=actor, Result=json.dumps(res))
        self.audit.log(a["Session_ID"], f"{'EXECUTED' if res.get('ok') else 'FAILED'} {a['Action_Type']}", "approval_gate", a["Incident_ID"], payload, res,
                       "Approved", actor=actor)
        return {"approval_id": approval_id, "status": status, **res}

    def reject(self, approval_id: str, actor: str = "operator", reason: str = "") -> dict:
        f = self.store.get(S.APPROVALS, approval_id)
        if not f or f["attrs"]["Status"] != "Proposed":
            return {"ok": False, "error": "approval not found or not pending"}
        self.store.update(S.APPROVALS, approval_id, Status="Rejected", Decided=utcnow(), Decided_By=actor, Result=reason)
        self.audit.log(f["attrs"]["Session_ID"], f"REJECTED {f['attrs']['Action_Type']}", "approval_gate", f["attrs"]["Incident_ID"], f["attrs"]["Payload"], reason, "Rejected", actor=actor)
        return {"ok": True, "approval_id": approval_id, "status": "Rejected"}
