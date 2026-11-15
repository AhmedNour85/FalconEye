"""The assigned investigator confirms the assignment and the incident; the operator then sees the report."""
from fastapi.testclient import TestClient

from backend.agent.agent import GeoAIAgent
from backend.api.app import create_app
from backend.gis import schema as S


def client(platform):
    return TestClient(create_app(platform, GeoAIAgent(platform)))


def assigned_work_order(platform):
    """Drive the crew to the point where a work order is assigned to an investigator (humans approve, nobody simulates a crew)."""
    platform.crew.run_cycle()
    for _ in range(4):
        for a in platform.approvals.pending():
            if a["Action_Type"] in ("create_work_order", "assign_worker"):
                platform.approvals.approve(a["Approval_ID"])
        platform.crew.run_cycle()
        wos = [w for w in platform.store.all(S.WORK_ORDERS) if w["attrs"]["Assigned_Worker"] and w["attrs"]["Status"] == "Assigned"]
        if wos:
            return wos[0]
    raise AssertionError("no assigned work order")


def test_nobody_answers_for_the_investigator_by_default(platform):
    wo = assigned_work_order(platform)
    platform.crew.run_cycle()
    assert not platform.store.query(S.VERIFICATION, Work_Order_ID=wo["id"])            # no simulated visit: the work order waits for a person


def test_pop_up_data_accept_and_report(platform):
    c = client(platform)
    wo = assigned_work_order(platform)
    worker = wo["attrs"]["Assigned_Worker"]
    task = next(t for t in c.get(f"/api/field/tasks/{worker}").json() if t["work_order"]["Work_Order_ID"] == wo["id"])
    assert task["work_order"]["Accepted_At"] == "" and task["ai_finding"] and task["instructions"]       # what the pop-up shows
    # another investigator cannot accept it
    other = next(w["id"] for w in platform.store.all(S.WORKERS) if w["id"] != worker)
    assert c.post("/api/field/accept", data={"work_order_id": wo["id"], "worker_id": other}).status_code == 422
    # accepting tells the operator, once
    assert c.post("/api/field/accept", data={"work_order_id": wo["id"], "worker_id": worker}).json()["already"] is False
    assert c.post("/api/field/accept", data={"work_order_id": wo["id"], "worker_id": worker}).json()["already"] is True
    assert sum(1 for n in platform.crew.notifications(limit=200) if n["Kind"] == "accepted" and n["Ref_ID"] == wo["id"]) == 1
    # confirming the incident sends the report, visible to the operator straight away
    lon, lat = task["location"]["lon"], task["location"]["lat"]
    r = c.post("/api/field/submit", data={"work_order_id": wo["id"], "worker_id": worker, "status": "Confirmed", "observation": "Water seeping through the asphalt near the valve.",
                                          "lat": lat, "lon": lon}, files={"photo": ("site.jpg", b"\xff\xd8\xff\xe0fakejpeg", "image/jpeg")})
    assert r.status_code == 200 and r.json()["outcome"] == "Confirmed"
    note = next(n for n in platform.crew.notifications(limit=200) if n["Kind"] == "verified")
    assert "valve" in note["Message"] and note["Incident_ID"] == wo["attrs"]["Incident_ID"]
    rep = c.get(f"/api/nccc/field-report/{note['Ref_ID']}").json()
    assert rep["status"] == "Confirmed" and rep["observation"].startswith("Water seeping") and rep["photo"].startswith("/api/evidence/")
    assert rep["worker"]["id"] == worker and rep["incident"]["id"] == wo["attrs"]["Incident_ID"] and rep["assessment"]
    assert c.get(rep["photo"]).status_code == 200                                                         # the photo can be opened
    assert c.get("/api/nccc/field-report/VER-9999").status_code == 404


def test_simulated_crew_toggle(platform):
    c = client(platform)
    assert c.post("/api/nccc/field-sim?on=true").json()["simulate_field"] is True
    assert c.post("/api/nccc/field-sim?on=false").json()["simulate_field"] is False
    assert c.get("/field.html").status_code == 200


def test_reassigning_clears_the_acceptance(platform):
    wo = assigned_work_order(platform)
    worker = wo["attrs"]["Assigned_Worker"]
    from backend.services import field
    field.accept(platform.store, platform.audit, wo["id"], worker)
    assert platform.store.get(S.WORK_ORDERS, wo["id"])["attrs"]["Accepted_At"]
    other = next(w["id"] for w in platform.store.all(S.WORKERS) if w["id"] != worker)
    from backend.workflows.actions import assign_worker
    assert assign_worker(platform.store, {"work_order_id": wo["id"], "worker_id": other})["ok"]
    assert platform.store.get(S.WORK_ORDERS, wo["id"])["attrs"]["Accepted_At"] == ""                    # the new investigator has to accept
