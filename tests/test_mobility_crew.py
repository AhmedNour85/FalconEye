"""The mobility lifecycle in the crew (Plan 3, task 6). Simulations run inline on the skeleton network unless a test says otherwise."""
import json
import time

import pytest

from backend.gis import schema as S
from backend.mobility import jobs as jobsmod
from backend.orchestration import crew as crewmod
from backend.platform import Platform
from backend.tools import executive, registry
from backend.tools.common import ToolContext
from config.settings import Settings

MOB = frozenset({"mobility"})


def mob_incidents(platform):
    return [f for f in platform.store.all(S.INCIDENTS) if f["attrs"]["Category"] == "mobility"]


def alert_for(platform, iid):
    rows = [n for n in platform.crew.notifications() if n["Incident_ID"] == iid and n["Kind"] == "fault"]
    assert len(rows) == 1
    return rows[0]


def counts(platform, iid):
    st = platform.store
    return {"detections": len(st.query(S.DETECTIONS, Category="mobility")), "incidents": len(mob_incidents(platform)), "scenarios": st.count(S.SCENARIOS),
            "approvals": len(st.query(S.APPROVALS, Target=iid)), "alerts": len(st.query(S.NOTIFICATIONS, Incident_ID=iid)), "work_orders": len(st.query(S.WORK_ORDERS, Incident_ID=iid)),
            "closures": st.count(S.CLOSURES), "reports": st.count(S.TRAFFIC_REPORTS), "events": st.count(S.EVENT_NOTICES)}


@pytest.mark.parametrize("name,itype,phrase,agents", [
    ("traffic_incident", "Traffic Incident", "min to the worst hospital access", ["nasser", "mansour", "fahad", "noura", "turki"]),
    ("road_closure", "Planned Road Closure", "Recommended response:", ["noura", "mansour", "fahad", "noura", "turki"]),
    ("major_event", "Major Event Traffic Plan", "vehicles per hour at the peak", ["noura", "mansour", "noura", "turki"]),
])
def test_each_event_ends_with_one_incident_one_alert_and_one_plan_waiting_for_approval(platform, name, itype, phrase, agents):
    out = platform.crew.inject(name)
    incs = mob_incidents(platform)
    assert len(incs) == 1 and out["scan"]["new_incidents"] == [incs[0]["id"]]
    iid, a = incs[0]["id"], incs[0]["attrs"]
    assert a["Incident_Type"] == itype and a["Assigned_Team"] == "Traffic Response" and a["Status"] == "Open" and a["Area_Name"] == (out.get("corridor") or out.get("venue"))
    n = alert_for(platform, iid)
    assert "Road impact (modelled):" in n["Message"] and phrase in n["Message"] and "calculating" not in n["Message"] and n["Status"] == "New"
    seen = [t["agent"] for t in n["Trail"] if t["agent"] != "reem" and t["agent"] != "faisal"]
    assert seen[:len(agents)] == agents and any("SYNTHETIC" in t["did"] for t in n["Trail"] if t["agent"] == "fahad") == ("fahad" in agents)
    pend = [p for p in platform.approvals.pending() if p["Incident_ID"] == iid]
    assert len(pend) == 1 and pend[0]["Action_Type"] == "apply_traffic_plan" and n["Approval_ID"] == pend[0]["Approval_ID"] and n["approval"]["status"] == "Proposed"
    rows = platform.store.query(S.SCENARIOS, Subject_ID=iid)
    assert len(rows) == 1 and rows[0]["attrs"]["Status"] == "Completed" and rows[0]["attrs"]["Requested_By"] == "noura"
    assert not platform.store.query(S.WORK_ORDERS, Incident_ID=iid)                       # nothing is carried out without the operator
    before = counts(platform, iid)
    platform.crew.run_cycle(scope=MOB)
    assert counts(platform, iid) == before                                                # the scan runs twice: nothing is added
    platform.crew.run_cycle()
    assert counts(platform, iid) == before


def test_the_alert_goes_out_before_the_simulation_and_the_scan_does_not_wait(monkeypatch):
    """Jobs on the background worker, worker held: the scan returns, the alert says the impact is being calculated, Noura shows as working."""
    p = Platform(settings=Settings(anthropic_api_key="", arcgis_username="", arcgis_password="", mobility_jobs_inline=False))
    p.jobs.pause()
    try:
        out = p.crew.inject("traffic_incident")
        iid = mob_incidents(p)[0]["id"]
        n = alert_for(p, iid)
        assert crewmod.CALCULATING in n["Message"] and n["Approval_ID"] == "" and not [x for x in p.approvals.pending() if x["Incident_ID"] == iid]
        assert any(t["agent"] == "noura" and "calculating" in t["did"].lower() for t in n["Trail"])
        noura = next(r for r in p.crew.roster() if r["id"] == "noura")
        assert noura["working"] == f"simulating {out['corridor']}"
        assert p.crew.run_cycle()["cycle"] >= 2 and p.store.count(S.SCENARIOS) == 1          # a full scan still returns, and queues nothing twice
    finally:
        p.jobs.resume()
    sid = p.store.all(S.SCENARIOS)[0]["id"]
    assert p.jobs.wait(sid, 120)["status"] == "Completed"
    end = time.time() + 30                                                                # the crew's follow-up runs on the worker, just after the job ends
    while crewmod.CALCULATING in alert_for(p, iid)["Message"] and time.time() < end:
        time.sleep(0.1)
    n = alert_for(p, iid)
    assert "Road impact (modelled):" in n["Message"] and crewmod.CALCULATING not in n["Message"] and n["approval"]["status"] == "Proposed"
    assert next(r for r in p.crew.roster() if r["id"] == "noura")["working"] == ""


def test_a_failed_simulation_still_alerts_and_proposes_a_plain_field_check(platform, monkeypatch):
    def boom(params, say):
        raise RuntimeError("the road network could not be loaded")

    monkeypatch.setitem(jobsmod.RUNNERS, "incident", boom)
    platform.crew.inject("traffic_incident")
    iid = mob_incidents(platform)[0]["id"]
    n = alert_for(platform, iid)
    assert "Road impact could not be calculated: the road network could not be loaded." in n["Message"] and "field check" in n["Message"] and n["Status"] == "New"
    pend = [p for p in platform.approvals.pending() if p["Incident_ID"] == iid]
    assert [p["Action_Type"] for p in pend] == ["create_work_order"] and n["Approval_ID"] == pend[0]["Approval_ID"]
    assert [r["attrs"]["Status"] for r in platform.store.query(S.SCENARIOS, Subject_ID=iid)] == ["Failed"]
    before = counts(platform, iid)
    platform.crew.run_cycle(scope=MOB)
    assert counts(platform, iid) == before                                                # not simulated again, not proposed again


def test_a_simulation_that_cannot_be_queued_is_reported_the_same_way(platform, monkeypatch):
    def refuse(*a, **k):
        raise RuntimeError("ArcGIS Online did not accept the row")

    monkeypatch.setattr(platform.jobs, "submit", refuse)
    platform.crew.inject("major_event")
    iid = mob_incidents(platform)[0]["id"]
    n = alert_for(platform, iid)
    assert "Road impact could not be calculated: ArcGIS Online did not accept the row." in n["Message"]
    assert [p["Action_Type"] for p in platform.approvals.pending() if p["Incident_ID"] == iid] == ["create_work_order"]


def test_a_simulation_interrupted_by_a_restart_is_queued_once_more_and_the_alert_says_so(platform, monkeypatch):
    real = platform.jobs.submit
    monkeypatch.setattr(platform.jobs, "submit", lambda *a, **k: "SCN-held")               # the first run never starts: the server "stops" here
    platform.crew.inject("traffic_incident")
    iid = mob_incidents(platform)[0]["id"]
    platform.store.upsert(S.SCENARIOS, {"Scenario_ID": "SCN-9001", "Scenario_Type": "incident", "Name": "left behind", "Params": "{}", "Status": "Running", "Summary": "",
                                        "Recommended": "", "Verdict": "", "Subject_ID": iid, "Requested_By": "noura", "Created": "2026-11-16T05:00:00Z", "Completed": "",
                                        "Runtime_S": None, "Network_Fingerprint": "", "Error": "", "Data_Classification": S.MODELLED})
    monkeypatch.setattr(platform.jobs, "submit", real)
    assert platform.jobs.recover() == ["SCN-9001"]
    platform.crew.resume_mobility()
    n = alert_for(platform, iid)
    assert any("server stopped" in t["did"] for t in n["Trail"]) and "Road impact (modelled):" in n["Message"]
    assert sorted(r["attrs"]["Status"] for r in platform.store.query(S.SCENARIOS, Subject_ID=iid)) == ["Completed", "Interrupted"]
    assert [p["Action_Type"] for p in platform.approvals.pending() if p["Incident_ID"] == iid] == ["apply_traffic_plan"]


def test_a_water_only_scan_starts_no_mobility_work(platform):
    platform.sim.scenario("traffic_incident")
    out = platform.crew.run_cycle(scope=frozenset({"water"}))
    assert not mob_incidents(platform) and platform.store.count(S.SCENARIOS) == 0 and platform.store.all(S.TRAFFIC_REPORTS)[0]["attrs"]["Status"] == "New"
    assert "nasser" not in {s["agent"] for s in out["steps"]}
    platform.crew.run_cycle()                                                             # the next full scan picks it up
    assert len(mob_incidents(platform)) == 1 and platform.store.count(S.SCENARIOS) == 1


def test_a_road_name_as_the_area_does_not_break_the_overview_numbers(platform, ctx):
    road = platform.crew.inject("traffic_incident")["corridor"]
    k = executive.compute_kpis(platform.store)
    assert k["open_incidents"] >= 1 and executive.compute_kpis(platform.store, category="mobility")["open_incidents"] == 1
    assert isinstance(executive.hotspots(platform.store), list) and executive.trends(platform.store)
    assert registry.execute(ctx, "executive_summary", {})["ok"]
    rows = registry.execute(ctx, "list_incidents", {"category": "mobility"})["result"]
    assert json.dumps(rows) and road in json.dumps(rows)
    assert registry.execute(ctx, "rank_incidents", {"category": "mobility"})["ok"] and registry.execute(ctx, "count_incidents", {"category": "mobility"})["ok"]


def test_the_roster_has_eleven_agents_and_the_two_new_feeds_are_listed(platform):
    r = platform.crew.roster()
    assert len(r) == 11 and [a["id"] for a in r[:2]] == ["faisal", "mansour"] and {"nasser", "noura", "fahad"} <= {a["id"] for a in r}
    feeds = {f["id"]: f for f in platform.crew.feed_status()}
    assert feeds["traffic"]["agent"] == "nasser" and feeds["closures"]["agent"] == "noura" and feeds["closures"]["name"] == "Closures & events"
    platform.sim.scenario("road_closure")
    assert "1 closure request" in {f["id"]: f for f in platform.crew.feed_status()}["closures"]["detail"]


def test_nasser_reports_abnormal_congestion_only_from_hours_the_model_already_holds(platform, monkeypatch):
    from backend.mobility import traffic
    from backend.tools import mobility

    monkeypatch.setattr(mobility, "riyadh_hour", lambda: 8)
    monkeypatch.setattr(traffic, "status", lambda: {"hours_ready": [], "ready": False, "building": False, "error": None})
    step = next(s for s in platform.crew.run_cycle(scope=MOB)["steps"] if s["agent"] == "nasser")
    assert "no new road reports" in step["detail"] and "modelled" not in step["detail"]
    monkeypatch.setattr(traffic, "status", lambda: {"hours_ready": [8], "ready": False, "building": False, "error": None})
    step = next(s for s in platform.crew.run_cycle(scope=MOB)["steps"] if s["agent"] == "nasser")
    assert "at 08:00 (modelled)" in step["detail"]


def test_mobility_is_a_learning_category_with_its_own_calibration(platform):
    from backend.services import learning

    assert "mobility" in learning.CATS and platform.store.get(S.CONFIG, "calibration.mobility")["attrs"]["Value"] == "1.0"
    platform.store.upsert(S.CONFIG, {"Config_ID": "calibration.mobility", "Value": "0.8", "Updated": ""})
    platform.sim.scenario("traffic_incident")
    d = registry.execute(ToolContext(platform, "t"), "detect_traffic_incidents", {})["result"]["detections"][0]
    row = platform.store.get(S.DETECTIONS, d["detection_id"])["attrs"]
    assert row["Risk_Score"] == round(row["Base_Risk_Score"] * 0.8, 1)
    assert "mobility" in learning.evaluation(platform.store)["categories"]
