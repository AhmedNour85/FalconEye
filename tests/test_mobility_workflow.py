"""Approval, the plan record, field verification and closing for mobility incidents (Plan 3, task 7)."""
import json

import pytest

from backend.gis import schema as S
from backend.services import learning
from backend.tools import registry as R
from backend.workflows import actions

MOB = frozenset({"mobility"})


def plan(platform, name):
    """Inject one event; returns (event result, incident id, the pending traffic-plan approval)."""
    out = platform.crew.inject(name)
    iid = out["scan"]["new_incidents"][0]
    apr = next(p for p in platform.approvals.pending() if p["Incident_ID"] == iid and p["Action_Type"] == "apply_traffic_plan")
    return out, iid, apr


def dispatch(platform, iid):
    wo = platform.store.query(S.WORK_ORDERS, Incident_ID=iid)[0]["id"]
    platform.crew.run_cycle(scope=MOB)
    a = next(p for p in platform.approvals.pending() if p["Action_Type"] == "assign_worker" and json.loads(p["Payload"])["work_order_id"] == wo)
    assert platform.approvals.approve(a["Approval_ID"])["ok"]
    return wo


def status(platform, iid):
    return platform.store.get(S.INCIDENTS, iid)["attrs"]["Status"]


def test_approving_a_closure_plan_creates_the_field_check_and_records_the_plan(platform):
    out, iid, apr = plan(platform, "road_closure")
    payload = json.loads(apr["Payload"])
    before = {k: platform.store.count(k) for k in (S.CLOSURES, S.EVENT_NOTICES, S.TRAFFIC_REPORTS, S.INCIDENTS, S.DETECTIONS, S.SCENARIOS)}
    res = platform.approvals.approve(apr["Approval_ID"], "tester")
    assert res["ok"]
    wos = platform.store.query(S.WORK_ORDERS, Incident_ID=iid)
    assert len(wos) == 1 and wos[0]["attrs"]["Task_Type"] == "Confirm the closure is in place" and wos[0]["attrs"]["Assigned_Team"] == "Traffic Response"
    c = platform.store.get(S.CLOSURES, out["id"])["attrs"]
    assert c["Status"] == "Approved" and c["Strategy"] == payload["strategy"] != "" and c["Work_Order_ID"] == wos[0]["id"] and c["Scenario_ID"] == payload["scenario_id"]
    assert c["Incident_ID"] == iid and status(platform, iid) == "Work Order Created"
    assert {k: platform.store.count(k) for k in before} == before                          # nothing else was created
    assert not platform.approvals.approve(apr["Approval_ID"])["ok"]                        # cannot be approved twice
    again = R.execute(platform.crew.ctx, "propose_traffic_plan", {"incident_id": iid})
    assert not again["ok"] and "already has active work order" in again["error"]


def test_rejecting_a_closure_plan_changes_nothing_and_the_next_scan_records_the_rejection(platform):
    out, iid, apr = plan(platform, "road_closure")
    platform.approvals.reject(apr["Approval_ID"], "tester", "not this week")
    c = platform.store.get(S.CLOSURES, out["id"])["attrs"]
    assert c["Status"] == "Requested" and not c["Work_Order_ID"] and not platform.store.query(S.WORK_ORDERS, Incident_ID=iid) and status(platform, iid) == "Open"
    n_apr, n_scn = platform.store.count(S.APPROVALS), platform.store.count(S.SCENARIOS)
    platform.crew.run_cycle(scope=MOB)
    assert platform.store.get(S.CLOSURES, out["id"])["attrs"]["Status"] == "Rejected"
    assert (platform.store.count(S.APPROVALS), platform.store.count(S.SCENARIOS)) == (n_apr, n_scn)      # not proposed again, not simulated again
    platform.crew.run_cycle(scope=MOB)
    assert len(platform.store.query(S.DETECTIONS, Related_Asset_ID=out["id"])) == 1                        # a rejected request is not a new finding


def test_a_confirmed_closure_plan_can_be_closed_without_a_repair_report(platform):
    out, iid, apr = plan(platform, "road_closure")
    assert platform.approvals.approve(apr["Approval_ID"])["ok"]
    wo = dispatch(platform, iid)
    worker = platform.store.get(S.WORK_ORDERS, wo)["attrs"]["Assigned_Worker"]
    assert platform.store.get(S.WORKERS, worker)["attrs"]["Team"] == "Traffic Response"
    assert platform.simulate_field_response(wo)["outcome"] == "Confirmed" and status(platform, iid) == "Confirmed"
    prop = R.execute(platform.crew.ctx, "propose_incident_closure", {"incident_id": iid})
    assert prop["ok"], prop
    assert platform.approvals.approve(prop["result"]["approval"]["Approval_ID"])["ok"]
    assert status(platform, iid) == "Resolved" and platform.store.get(S.CLOSURES, out["id"])["attrs"]["Status"] == "In Place"
    assert platform.store.get(S.WORK_ORDERS, wo)["attrs"]["Status"] == "Completed" and platform.store.get(S.WORKERS, worker)["attrs"]["Open_Tasks"] == 0


def test_a_confirmed_traffic_incident_still_needs_the_road_to_be_cleared(platform):
    out, iid, apr = plan(platform, "traffic_incident")
    assert platform.approvals.approve(apr["Approval_ID"])["ok"]
    wo = dispatch(platform, iid)
    assert platform.simulate_field_response(wo)["outcome"] == "Confirmed"
    refused = R.execute(platform.crew.ctx, "propose_incident_closure", {"incident_id": iid})
    assert not refused["ok"] and "not yet reported" in refused["error"]
    assert not actions.close_incident(platform.store, {"incident_id": iid})["ok"] and status(platform, iid) == "Confirmed"
    assert actions.NO_REPAIR_TYPES == ("Planned Road Closure", "Major Event Traffic Plan")


def test_the_whole_path_for_a_traffic_incident_ends_resolved_and_feeds_the_learning_numbers(platform):
    out, iid, apr = plan(platform, "traffic_incident")
    assert platform.store.query(S.WORK_ORDERS, Incident_ID=iid) == []
    assert platform.approvals.approve(apr["Approval_ID"])["ok"]                             # 1. the plan
    wo = dispatch(platform, iid)                                                           # 2. the dispatch
    assert platform.store.get(S.WORK_ORDERS, wo)["attrs"]["Task_Type"] == "Confirm the road is clear"
    platform.crew.run_cycle(scope=MOB, simulate_field=True)                                # 3. simulated visit: confirmed on site
    assert status(platform, iid) == "Confirmed"
    platform.crew.run_cycle(scope=MOB, simulate_field=True)                                # 4. simulated clearing
    assert status(platform, iid) == "Repair Reported"
    texts = [v["attrs"]["Observation"] for v in platform.store.query(S.VERIFICATION, Incident_ID=iid)]
    assert len(texts) == 2 and "blocking" in texts[0] and "lanes are open" in texts[1]
    close = next(p for p in platform.approvals.pending() if p["Incident_ID"] == iid and p["Action_Type"] == "close_incident")
    assert platform.approvals.approve(close["Approval_ID"])["ok"]                           # 5. the closing
    assert status(platform, iid) == "Resolved" and platform.store.get(S.TRAFFIC_REPORTS, out["id"])["attrs"]["Status"] == "Cleared"
    m = learning.evaluation(platform.store)["categories"]["mobility"]
    assert (m["verified_true"], m["verified_false"]) == (1, 0)
    kinds = [n["Kind"] for n in platform.crew.notifications() if n["Incident_ID"] == iid]
    assert {"fault", "dispatch", "verified", "closure"} <= set(kinds)


def test_an_event_plan_is_recorded_as_planned_and_closes_once_confirmed_in_place(platform):
    out, iid, apr = plan(platform, "major_event")
    assert platform.approvals.approve(apr["Approval_ID"])["ok"]
    assert platform.store.get(S.EVENT_NOTICES, out["id"])["attrs"]["Status"] == "Planned" and platform.store.get(S.EVENT_NOTICES, out["id"])["attrs"]["Incident_ID"] == iid
    wo = dispatch(platform, iid)
    assert platform.store.get(S.WORK_ORDERS, wo)["attrs"]["Task_Type"] == "Confirm the traffic plan is in place"
    platform.crew.run_cycle(scope=MOB, simulate_field=True)
    assert status(platform, iid) == "Confirmed"
    platform.crew.run_cycle(scope=MOB, simulate_field=True)                                # no "repair" visit for a plan that has nothing to repair
    assert status(platform, iid) == "Confirmed" and len(platform.store.query(S.VERIFICATION, Incident_ID=iid)) == 1
    close = next(p for p in platform.approvals.pending() if p["Incident_ID"] == iid and p["Action_Type"] == "close_incident")
    assert platform.approvals.approve(close["Approval_ID"])["ok"] and status(platform, iid) == "Resolved"


@pytest.mark.parametrize("name,true_word,false_word", [("traffic_incident", "blocking", "flowing"), ("road_closure", "barriers", "No closure"),
                                                       ("major_event", "marshals", "No traffic plan")])
def test_the_simulated_investigator_answers_by_incident_type_and_follows_the_answer_key(platform, name, true_word, false_word):
    out, iid, apr = plan(platform, name)
    assert platform.approvals.approve(apr["Approval_ID"])["ok"]
    wo = dispatch(platform, iid)
    yes = platform.sim.field_observation(wo)
    assert yes["status"] == "Confirmed" and true_word in yes["observation"]
    platform.sim._set_truth(out["id"], False, "test: nothing there")
    no = platform.sim.field_observation(wo)
    assert no["status"] == "Rejected" and false_word in no["observation"]
    assert platform.simulate_field_response(wo)["outcome"] == "Rejected"
    platform.crew.run_cycle(scope=MOB)
    close = next(p for p in platform.approvals.pending() if p["Incident_ID"] == iid and p["Action_Type"] == "close_incident")
    assert platform.approvals.approve(close["Approval_ID"])["ok"] and status(platform, iid) == "Closed - False Positive"
    if name == "road_closure":
        assert platform.store.get(S.CLOSURES, out["id"])["attrs"]["Status"] == "Approved"   # found not in place: the record is not moved on
