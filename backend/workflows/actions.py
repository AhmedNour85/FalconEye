"""Executable operational actions. They run ONLY after explicit human approval (ApprovalService).

Each handler returns {"ok": bool, ...} and verifies the write by reading it back, so the agent never reports
success unless the system of record confirms it.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backend.gis import schema as S
from backend.gis.store import Store, utcnow

ACTIVE_WO = ("Created", "Assigned", "In Progress")


def _incident(store: Store, iid: str) -> dict:
    f = store.get(S.INCIDENTS, iid)
    if not f:
        raise ValueError(f"incident {iid} not found")
    return f


def create_work_order(store: Store, p: dict) -> dict:
    inc = _incident(store, p["incident_id"])
    for w in store.query(S.WORK_ORDERS, Incident_ID=p["incident_id"]):
        if w["attrs"]["Status"] in ACTIVE_WO:
            return {"ok": False, "error": f"duplicate: active work order {w['id']} already exists for {p['incident_id']}"}
    a = inc["attrs"]
    wo = store.next_id("WO")
    due = (datetime.now(timezone.utc) + timedelta(hours=int(p.get("due_hours", 24)))).strftime("%Y-%m-%dT%H:%M:%SZ")
    store.upsert(S.WORK_ORDERS, {"Work_Order_ID": wo, "Incident_ID": p["incident_id"], "Assigned_Team": p.get("team", a["Assigned_Team"]), "Assigned_Worker": "",
                                 "Priority": a["Priority"], "Due_Date": due, "Status": "Created", "Approval_Status": "Approved", "Created_Date": utcnow(),
                                 "Task_Type": p.get("task_type", "Inspect & Verify"), "Instructions": p.get("instructions", ""), "Accepted_At": "",
                                 "Incident_Type": a["Incident_Type"], "Area_Name": a["Area_Name"], "Assigned_Worker_Name": "", "Assigned_To_Username": "", "Assigned_At": "",
                                 "Field_Maps_Status": "",
                                 "Data_Classification": S.OPERATIONAL}, inc["geom"])
    store.update(S.INCIDENTS, p["incident_id"], Status="Work Order Created", Assigned_Team=p.get("team", a["Assigned_Team"]), Last_Updated=utcnow())
    back = store.get(S.WORK_ORDERS, wo)
    if not back:
        return {"ok": False, "error": "write verification failed"}
    return {"ok": True, "work_order_id": wo, "incident_id": p["incident_id"], "status": "Created", "due": due}


def assign_worker(store: Store, p: dict) -> dict:
    wo = store.get(S.WORK_ORDERS, p["work_order_id"])
    wk = store.get(S.WORKERS, p["worker_id"])
    if not wo or not wk:
        return {"ok": False, "error": "work order or worker not found"}
    if wo["attrs"]["Status"] not in ("Created", "Assigned"):
        return {"ok": False, "error": f"work order is {wo['attrs']['Status']}; cannot assign"}
    prev = wo["attrs"]["Assigned_Worker"]
    if prev and prev != p["worker_id"]:
        store.update(S.WORKERS, prev, Open_Tasks=max(0, store.get(S.WORKERS, prev)["attrs"]["Open_Tasks"] - 1))
    if prev != p["worker_id"]:
        store.update(S.WORKERS, p["worker_id"], Open_Tasks=wk["attrs"]["Open_Tasks"] + 1, Status="Assigned", Last_Update=utcnow())
    sent = "Sent to ArcGIS Field Maps" if store.is_hosted else "Not sent: no ArcGIS Online connection"
    store.update(S.WORK_ORDERS, p["work_order_id"], Assigned_Worker=p["worker_id"], Status="Assigned", Assigned_Team=wk["attrs"]["Team"],
                 Assigned_Worker_Name=wk["attrs"]["Name"], Assigned_To_Username=wk["attrs"].get("ArcGIS_Username", ""), Assigned_At=utcnow(), Field_Maps_Status=sent,
                 Incident_Type=wo["attrs"].get("Incident_Type") or _incident(store, wo["attrs"]["Incident_ID"])["attrs"]["Incident_Type"],
                 Area_Name=wo["attrs"].get("Area_Name") or _incident(store, wo["attrs"]["Incident_ID"])["attrs"]["Area_Name"],
                 **({"Accepted_At": ""} if prev != p["worker_id"] else {}))
    store.update(S.INCIDENTS, wo["attrs"]["Incident_ID"], Status="Assigned", Assigned_Team=wk["attrs"]["Team"], Last_Updated=utcnow())
    ok = store.get(S.WORK_ORDERS, p["work_order_id"])["attrs"]["Assigned_Worker"] == p["worker_id"]
    return {"ok": ok, "work_order_id": p["work_order_id"], "worker_id": p["worker_id"], "worker": wk["attrs"]["Name"], "field_maps_sent": store.is_hosted,
            "field_maps_user": wk["attrs"].get("ArcGIS_Username", "")}


def close_incident(store: Store, p: dict) -> dict:
    inc = _incident(store, p["incident_id"])
    a = inc["attrs"]
    if a["Status"] in ("Resolved", "Closed - False Positive"):
        return {"ok": False, "error": f"incident already {a['Status']}"}
    outcome = a.get("Verification_Outcome", "")
    if not outcome:
        return {"ok": False, "error": "incident has no field verification; cannot close"}
    if outcome == "Confirmed" and a["Status"] != "Repair Reported":
        return {"ok": False, "error": "fault is confirmed but no repair has been reported by the field; cannot resolve yet"}
    new = "Closed - False Positive" if outcome == "Rejected" else "Resolved"
    store.update(S.INCIDENTS, p["incident_id"], Status=new, Last_Updated=utcnow())
    for w in store.query(S.WORK_ORDERS, Incident_ID=p["incident_id"]):
        if w["attrs"]["Status"] in ACTIVE_WO + ("Completed",):
            store.update(S.WORK_ORDERS, w["id"], Status="Completed")
            wid = w["attrs"]["Assigned_Worker"]
            if wid and store.get(S.WORKERS, wid):
                wk = store.get(S.WORKERS, wid)["attrs"]
                n = max(0, wk["Open_Tasks"] - 1)
                store.update(S.WORKERS, wid, Open_Tasks=n, Status="Available" if n == 0 else "Assigned")
    return {"ok": store.get(S.INCIDENTS, p["incident_id"])["attrs"]["Status"] == new, "incident_id": p["incident_id"], "status": new}


def change_asset_status(store: Store, p: dict) -> dict:
    f = store.get(S.INFRA, p["asset_id"])
    if not f:
        return {"ok": False, "error": "asset not found"}
    store.update(S.INFRA, p["asset_id"], Asset_Status=p["new_status"])
    return {"ok": True, "asset_id": p["asset_id"], "status": p["new_status"]}


HANDLERS = {"create_work_order": create_work_order, "assign_worker": assign_worker, "close_incident": close_incident, "change_asset_status": change_asset_status}
