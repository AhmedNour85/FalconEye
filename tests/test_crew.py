"""NCCC digital crew: multi-agent automation raises notifications, never acts without human approval."""
from backend.gis import schema as S
from backend.orchestration import crew as crewmod


def test_sim_tick_keeps_sensor_history(platform):
    before = platform.store.count(S.SENSORS)
    platform.sim.tick()
    platform.sim.tick()
    assert platform.store.count(S.SENSORS) == before + 2 * 48          # ticks add readings; they never overwrite seeded ones


def test_first_scan_raises_alerts_and_only_proposes(platform):
    c = platform.crew.run_cycle()
    assert c["new_incidents"] and c["new_notifications"]
    assert platform.approvals.pending()                                  # work orders are proposals ...
    assert platform.store.count(S.WORK_ORDERS) == len(platform.store.all(S.WORK_ORDERS))
    assert not [w for w in platform.store.all(S.WORK_ORDERS) if w["attrs"]["Status"] in ("Assigned", "In Progress")]   # ... nothing was dispatched
    assert {s["agent"] for s in c["steps"]} >= {"abdullah", "mansour", "reem", "turki"}


def test_scan_is_idempotent(platform):
    platform.crew.run_cycle()
    n = platform.store.count(S.NOTIFICATIONS)
    again = platform.crew.run_cycle()
    assert again["new_incidents"] == [] and again["new_notifications"] == []
    assert platform.store.count(S.NOTIFICATIONS) == n


def test_injected_leak_is_found_after_ticks(platform):
    platform.crew.run_cycle()
    platform.sim.tick()
    res = platform.crew.inject("olaya_leak")
    kinds = {n["Kind"] for n in platform.crew.notifications() if n["Area_Name"] == "Olaya"}
    assert "fault" in kinds
    assert any(s["agent"] == "sarah" and "suspected" in s["detail"] for s in res["scan"]["steps"])


def test_decisions_drive_the_chain_to_closure(platform):
    platform.crew.run_cycle()
    for _ in range(6):                                                   # approve whatever the crew proposes, as an operator would
        for a in platform.approvals.pending():
            assert platform.approvals.approve(a["Approval_ID"])["ok"]
        platform.crew.run_cycle(simulate_field=True)
    assert [i for i in platform.store.all(S.INCIDENTS) if i["attrs"]["Status"] == "Resolved" and i["id"] >= "INC-0023"]
    assert any(n["Kind"] == "verified" for n in platform.crew.notifications(limit=200))


def test_agents_cover_every_tool():
    from backend.tools import registry
    assert {t.name for t in registry.TOOLS} <= set(crewmod.AGENT_FOR_TOOL)


def test_operator_can_request_inspection_on_a_watched_incident(platform):
    from backend.gis import schema as S
    platform.crew.run_cycle(deep="Olaya")
    watched = next(n for n in platform.crew.notifications(limit=200) if n["Kind"] == "change" and not n["approval"])       # kept on watch: no work order proposed
    res = platform.crew.request_inspection(watched["Incident_ID"])
    assert res["ok"] and platform.approvals.pending()
    again = next(n for n in platform.crew.notifications(limit=200) if n["Notif_ID"] == watched["Notif_ID"])
    assert again["approval"]["status"] == "Proposed" and again["Trail"][-1]["agent"] == "turki"
    assert not platform.store.query(S.WORK_ORDERS, Incident_ID=watched["Incident_ID"])                                      # nothing created until approved
    assert platform.crew.request_inspection(watched["Incident_ID"])["ok"]                                                   # asking twice does not duplicate
    assert len([a for a in platform.approvals.pending() if a["Incident_ID"] == watched["Incident_ID"]]) == 1
    assert platform.approvals.approve(res["approval_id"])["ok"]
    assert platform.crew.request_inspection(watched["Incident_ID"])["ok"] is False                                          # an active work order already exists


def test_a_simulated_event_wakes_only_its_own_feed(platform):
    """Selecting one event in the Simulate menu must not raise alerts from the other use cases."""
    from backend.gis import schema as S

    expect = {"olaya_leak": "water", "streetlight_pole": "lighting", "distortion_event": "distortion", "landuse_violation": "land_use"}
    for event, cat in expect.items():
        p = type(platform)(settings=platform.settings)
        res = p.crew.inject(event)
        raised = [p.store.get(S.NOTIFICATIONS, n)["attrs"] for n in res["scan"]["new_notifications"]]
        faults = [n for n in raised if n["Kind"] in ("fault", "change")]
        assert faults, event
        allowed = {cat} | ({"change"} if cat == "land_use" else set())          # land-use management also compares the satellite dates (urban change)
        for n in faults:
            assert p.store.get(S.INCIDENTS, n["Incident_ID"])["attrs"]["Category"] in allowed, (event, n["Title"])
        others = {f['attrs']['Category'] for f in p.store.all(S.INCIDENTS) if f['attrs']['Created_Date'] >= p.crew.epoch}
        assert others <= allowed, (event, others)             # nothing from another use case was opened by this event


def test_the_step_after_an_approval_does_not_scan_other_feeds(platform):
    """Approving work for one simulated event must not open incidents from other use cases (the UI calls scan?follow=true after a decision)."""
    from fastapi.testclient import TestClient

    from backend.agent.agent import GeoAIAgent
    from backend.api.app import create_app
    from backend.gis import schema as S

    c = TestClient(create_app(platform, GeoAIAgent(platform)))
    c.post("/api/nccc/events/olaya_leak")
    for a in c.get("/api/approvals?pending=true").json():
        c.post(f"/api/approvals/{a['Approval_ID']}/approve")
    r = c.post("/api/nccc/scan?follow=true").json()
    assert r["new_incidents"] == []
    assert {f["attrs"]["Category"] for f in platform.store.all(S.INCIDENTS) if f["attrs"]["Created_Date"] >= platform.crew.epoch} == {"water"}
    assert any(n for n in c.get("/api/nccc/state").json()["notifications"] if n["Kind"] == "dispatch")       # the crew still proposes who to send
    assert c.post("/api/nccc/scan").json()["new_incidents"]                                                  # a normal scan still checks everything


def test_a_fresh_start_has_no_open_incidents(platform):
    """Reset demo leaves only closed history, so every open incident comes from an event the operator simulates."""
    from backend.gis import schema as S
    from backend.tools import executive

    k = executive.compute_kpis(platform.store)
    assert k["open_incidents"] == 0 and k["critical_incidents"] == 0 and len(platform.approvals.pending()) == 0
    assert {f["attrs"]["Status"] for f in platform.store.all(S.INCIDENTS)} <= {"Resolved", "Closed - False Positive"}
    assert k["total_incidents"] >= 20                                      # the closed history is still there for trends and learning


def test_land_use_event_includes_change_detection_and_urban_change(platform):
    """Land-use management compares the satellite dates: violations become land-use incidents, permitted new construction becomes an urban-change review."""
    from backend.gis import schema as S

    res = platform.crew.inject("landuse_violation")
    cats: dict = {}
    for i in res["scan"]["new_incidents"]:
        a = platform.store.get(S.INCIDENTS, i)["attrs"]
        cats.setdefault(a["Category"], []).append(a)
    assert set(cats) == {"land_use", "change"}, set(cats)
    assert all(a["Incident_Type"] == "Land-Use Violation Review" for a in cats["land_use"])
    assert all(a["Incident_Type"] == "Urban Change Review" for a in cats["change"])
    assert {a["Area_Name"] for a in cats["land_use"]} == {"King Salman Park"} and "King Salman Park" not in {a["Area_Name"] for a in cats["change"]}
    steps = [s["action"] for s in res["scan"]["steps"]]
    assert steps.count("Compared satellite imagery") == 2 and steps.count("Checked land use against zoning") == 1
    # a polygon that is a violation is one incident, never a land-use incident plus an urban-change review
    assert not ({a["Related_Asset_ID"] for a in cats["land_use"]} & {a["Related_Asset_ID"] for a in cats["change"]})


def test_close_scenario_with_a_simulated_repair_report(platform):
    """A field-confirmed fault whose repair has not been reported can be taken to closure with a SIMULATED repair report (closing still needs approval)."""
    from fastapi.testclient import TestClient

    from backend.agent.agent import GeoAIAgent
    from backend.api.app import create_app
    from backend.gis import schema as S

    c = TestClient(create_app(platform, GeoAIAgent(platform)))
    c.post("/api/nccc/events/olaya_leak")
    iid = next(f["id"] for f in platform.store.all(S.INCIDENTS) if f["attrs"]["Category"] == "water" and f["attrs"]["Status"] == "Open")
    for _ in range(2):                                                                                   # approve the work order, then the assignment
        for a in c.get("/api/approvals?pending=true").json():
            c.post(f"/api/approvals/{a['Approval_ID']}/approve")
        c.post("/api/nccc/scan?follow=true")
    wo = platform.store.query(S.WORK_ORDERS, Incident_ID=iid)[-1]
    platform.simulate_field_response(wo["id"], repair=False)                                             # the crew confirms the fault; nobody has reported the repair yet
    assert platform.store.get(S.INCIDENTS, iid)["attrs"]["Status"] == "Confirmed"
    refused = c.post("/api/chat", json={"message": f"close {iid}", "session_id": "x"}).json()["reply"]
    assert "repair not yet reported" in refused and "simulate repair" in refused.lower()                 # the refusal says what to do next

    r = c.post(f"/api/nccc/incidents/{iid}/simulate-repair")
    assert r.status_code == 200 and r.json()["incident_status"] == "Repair Reported"
    v = platform.store.query(S.VERIFICATION, Incident_ID=iid)[-1]["attrs"]
    assert v["Verification_Status"] == "Repaired" and v["Simulated_Worker"] == "Yes" and "[SIMULATED WORKER]" in v["Observation"]      # labelled as simulated
    pend = [a for a in c.get("/api/approvals?pending=true").json() if a["Action_Type"] == "close_incident" and a["Incident_ID"] == iid]
    assert pend, "the closure proposal appears"
    assert platform.store.get(S.INCIDENTS, iid)["attrs"]["Status"] == "Repair Reported"                  # nothing is closed until a person approves
    c.post(f"/api/approvals/{pend[0]['Approval_ID']}/approve")
    assert platform.store.get(S.INCIDENTS, iid)["attrs"]["Status"] == "Resolved"
    assert c.post(f"/api/nccc/incidents/{iid}/simulate-repair").status_code == 409                       # not twice, and not on a closed incident


def test_simulate_repair_needs_a_confirmed_fault(platform):
    from fastapi.testclient import TestClient

    from backend.agent.agent import GeoAIAgent
    from backend.api.app import create_app
    from backend.gis import schema as S

    c = TestClient(create_app(platform, GeoAIAgent(platform)))
    c.post("/api/nccc/events/olaya_leak")
    iid = next(f["id"] for f in platform.store.all(S.INCIDENTS) if f["attrs"]["Status"] == "Open")
    r = c.post(f"/api/nccc/incidents/{iid}/simulate-repair")
    assert r.status_code == 409 and "confirmed" in r.json()["detail"]
    ar = c.post(f"/api/nccc/incidents/{iid}/simulate-repair?lang=ar").json()["detail"]
    assert "لم تُؤكَّد" in ar


def test_simulate_repair_by_chat_in_english_and_arabic(platform):
    from backend.agent.agent import GeoAIAgent
    from backend.gis import schema as S

    ag = GeoAIAgent(platform)
    platform.crew.inject("olaya_leak")
    iid = next(f["id"] for f in platform.store.all(S.INCIDENTS) if f["attrs"]["Category"] == "water" and f["attrs"]["Status"] == "Open")
    assert "has not been confirmed" in ag.chat("c1", f"simulate repair for {iid}")["reply"]
    assert "لم تُؤكَّد" in ag.chat("c2", f"حاكِ إصلاح {iid}")["reply"]


def _closed_after_simulated_repair(platform):
    from fastapi.testclient import TestClient

    from backend.agent.agent import GeoAIAgent
    from backend.api.app import create_app
    from backend.gis import schema as S

    c = TestClient(create_app(platform, GeoAIAgent(platform)))
    c.post("/api/nccc/events/olaya_leak")
    iid = next(f["id"] for f in platform.store.all(S.INCIDENTS) if f["attrs"]["Category"] == "water" and f["attrs"]["Status"] == "Open")
    for _ in range(2):
        for a in c.get("/api/approvals?pending=true").json():
            c.post(f"/api/approvals/{a['Approval_ID']}/approve")
        c.post("/api/nccc/scan?follow=true")
    platform.simulate_field_response(platform.store.query(S.WORK_ORDERS, Incident_ID=iid)[-1]["id"], repair=False)
    c.post(f"/api/nccc/incidents/{iid}/simulate-repair")
    apr = next(a for a in c.get("/api/approvals?pending=true").json() if a["Action_Type"] == "close_incident" and a["Incident_ID"] == iid)
    c.post(f"/api/approvals/{apr['Approval_ID']}/approve")
    assert platform.store.get(S.INCIDENTS, iid)["attrs"]["Status"] == "Resolved"
    return iid


def test_assessing_a_report_again_never_reopens_a_closed_incident(platform):
    from backend.gis import schema as S
    from backend.services import field

    iid = _closed_after_simulated_repair(platform)
    vid = platform.store.query(S.VERIFICATION, Incident_ID=iid)[-1]["id"]
    platform.store.update(S.VERIFICATION, vid, Agent_Assessment="")                      # what a stale pull from ArcGIS Online used to leave behind
    assert platform.store.get(S.INCIDENTS, iid)["attrs"]["Status"] == "Resolved"
    platform._assess_field_reports()                                                      # the poller assesses it again ...
    res = field.assess(platform.store, platform.audit, vid)
    assert res["already_closed"] is True
    assert platform.store.get(S.INCIDENTS, iid)["attrs"]["Status"] == "Resolved"          # ... and the incident stays closed
    assert platform.store.get(S.VERIFICATION, vid)["attrs"]["Agent_Assessment"]           # the text is restored
