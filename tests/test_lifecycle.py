"""Plan 5, Task 1: where an incident stands on the seven lifecycle steps."""
import json

import pytest

from backend.gis import schema as S
from backend.services import lifecycle

MOB = frozenset({"mobility"})


def states(pos):
    return {s["key"]: s["state"] for s in pos["steps"]}


def _closure(platform):
    out = platform.crew.inject("road_closure")
    iid = out["scan"]["new_incidents"][0]
    apr = next(p for p in platform.approvals.pending() if p["Incident_ID"] == iid and p["Action_Type"] == "apply_traffic_plan")
    return out, iid, apr


def test_the_steps_are_the_seven_named_ones():
    assert lifecycle.STEPS == ["Detected", "Analysed", "Proposed", "Approved", "Dispatched", "Verified", "Resolved"]


def test_a_traffic_plan_awaiting_approval_is_at_proposed(platform):
    _out, iid, _apr = _closure(platform)
    pos = lifecycle.position(platform.store, iid)
    st = states(pos)
    assert pos["outcome"] == "open" and pos["current"] == "Proposed"
    assert st["Detected"] == st["Analysed"] == "done" and st["Proposed"] == "current" and st["Approved"] == st["Resolved"] == "todo"


def test_a_rejected_proposal_stops_at_proposed_and_says_rejected(platform):
    _out, iid, apr = _closure(platform)
    assert platform.approvals.reject(apr["Approval_ID"])["ok"]
    pos = lifecycle.position(platform.store, iid)
    assert pos["outcome"] == "rejected" and states(pos)["Proposed"] == "stopped" and states(pos)["Approved"] == "todo"


def test_a_dispatched_closure_is_at_dispatched(platform):
    _out, iid, apr = _closure(platform)
    assert platform.approvals.approve(apr["Approval_ID"])["ok"]
    assert lifecycle.position(platform.store, iid)["current"] == "Dispatched"          # approved; waiting for the investigator to be assigned
    platform.crew.run_cycle(scope=MOB)
    wo = platform.store.query(S.WORK_ORDERS, Incident_ID=iid)[0]["id"]
    a = next(p for p in platform.approvals.pending() if p["Action_Type"] == "assign_worker" and json.loads(p["Payload"])["work_order_id"] == wo)
    assert platform.approvals.approve(a["Approval_ID"])["ok"]
    pos = lifecycle.position(platform.store, iid)
    assert pos["current"] == "Verified" and states(pos)["Dispatched"] == "done"


def test_a_closure_resolved_without_a_repair_visit_has_every_step_done(platform):
    from backend.tools import registry as R
    _out, iid, apr = _closure(platform)
    platform.approvals.approve(apr["Approval_ID"])
    platform.crew.run_cycle(scope=MOB)
    wo = platform.store.query(S.WORK_ORDERS, Incident_ID=iid)[0]["id"]
    a = next(p for p in platform.approvals.pending() if p["Action_Type"] == "assign_worker")
    platform.approvals.approve(a["Approval_ID"])
    platform.simulate_field_response(wo)
    prop = R.execute(platform.crew.ctx, "propose_incident_closure", {"incident_id": iid})
    platform.approvals.approve(prop["result"]["approval"]["Approval_ID"])
    pos = lifecycle.position(platform.store, iid)
    assert pos["outcome"] == "resolved" and set(states(pos).values()) == {"done"}


def test_every_alert_carries_a_lifecycle(platform):
    platform.crew.run_cycle()
    platform.crew.inject("olaya_leak")
    platform.crew.inject("road_closure")
    alerts = platform.crew.notifications(limit=100)
    assert alerts and all("lifecycle" in a for a in alerts)
    with_inc = [a for a in alerts if a["Incident_ID"]]
    assert with_inc and all([s["key"] for s in a["lifecycle"]["steps"]] == lifecycle.STEPS for a in with_inc)
    assert all(sum(s["state"] == "current" for s in a["lifecycle"]["steps"]) <= 1 for a in with_inc)
    assert all(a["lifecycle"] is None for a in alerts if not a["Incident_ID"])
