"""Append-only agent/operator audit log (Riyadh_Agent_Audit_Log)."""
from __future__ import annotations

import json
import logging

from backend.gis import schema as S
from backend.gis.store import Store, utcnow

log = logging.getLogger("geoai.audit")


def _short(v, n=600) -> str:
    s = v if isinstance(v, str) else json.dumps(v, default=str)
    return s if len(s) <= n else s[: n - 3] + "..."


class Audit:
    def __init__(self, store: Store):
        self.store = store

    def log(self, session_id: str, action: str, tool: str = "", incident: str = "", inp="", out="", approval: str = "N/A", actor: str = "agent") -> str:
        lid = self.store.next_id("LOG", 6)
        self.store.upsert(S.AUDIT, {"Log_ID": lid, "Session_ID": session_id, "Agent_Action": action, "Tool_Name": tool, "Related_Incident_ID": incident or "",
                                    "Input_Summary": _short(inp), "Output_Summary": _short(out), "Approval_Status": approval, "Timestamp": utcnow(), "Actor": actor})
        log.info("audit %s %s tool=%s incident=%s approval=%s", lid, action, tool, incident, approval)
        return lid

    def recent(self, n: int = 50, incident: str | None = None) -> list[dict]:
        rows = [f["attrs"] for f in self.store.all(S.AUDIT)]
        if incident:
            rows = [r for r in rows if r["Related_Incident_ID"] == incident]
        return rows[-n:][::-1]
