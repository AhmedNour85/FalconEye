from backend.gis import schema as S
from backend.tools import registry as R


def run(ctx, name, **args):
    r = R.execute(ctx, name, args)
    assert r["ok"], r
    return r["result"]


def _incident(platform, ctx):
    platform.sim.scenario("olaya_leak")
    run(ctx, "detect_water_leaks", area="Olaya")
    return run(ctx, "create_incidents_from_detections")["created"][0]["incident_id"]


def test_work_order_requires_approval(platform, ctx):
    iid = _incident(platform, ctx)
    n0 = platform.store.count(S.WORK_ORDERS)
    prop = run(ctx, "propose_work_order")
    assert prop["status"] == "AWAITING_APPROVAL"
    assert platform.store.count(S.WORK_ORDERS) == n0  # nothing created before approval
    res = platform.approvals.approve(prop["approval"]["Approval_ID"], "tester")
    assert res["ok"] and platform.store.count(S.WORK_ORDERS) == n0 + 1
    assert platform.store.get(S.INCIDENTS, iid)["attrs"]["Status"] == "Work Order Created"


def test_duplicate_proposals_and_work_orders_blocked(platform, ctx):
    _incident(platform, ctx)
    a = run(ctx, "propose_work_order")["approval"]
    b = run(ctx, "propose_work_order")["approval"]
    assert b.get("duplicate") and a["Approval_ID"] == b["Approval_ID"]
    platform.approvals.approve(a["Approval_ID"])
    assert not R.execute(ctx, "propose_work_order", {})["ok"]  # active WO exists
    assert not platform.approvals.approve(a["Approval_ID"])["ok"]  # cannot approve twice


def test_rejection_changes_nothing(platform, ctx):
    _incident(platform, ctx)
    n0 = platform.store.count(S.WORK_ORDERS)
    a = run(ctx, "propose_work_order")["approval"]
    platform.approvals.reject(a["Approval_ID"])
    assert platform.store.count(S.WORK_ORDERS) == n0
    assert platform.store.get(S.APPROVALS, a["Approval_ID"])["attrs"]["Status"] == "Rejected"


def test_assignment_prefers_skilled_nearby_worker(platform, ctx):
    _incident(platform, ctx)
    platform.approvals.approve(run(ctx, "propose_work_order")["approval"]["Approval_ID"])
    pa = run(ctx, "propose_field_assignment")
    w = pa["recommended_worker"]
    assert "water" in w["skills"] and w["team"] == "Water Rapid Response"
    res = platform.approvals.approve(pa["approval"]["Approval_ID"])
    assert res["ok"]
    assert platform.store.get(S.WORKERS, w["worker_id"])["attrs"]["Open_Tasks"] == 1


def test_audit_log_records_proposal_and_execution(platform, ctx):
    iid = _incident(platform, ctx)
    a = run(ctx, "propose_work_order")["approval"]
    platform.approvals.approve(a["Approval_ID"])
    actions = [r["Agent_Action"] for r in platform.audit.recent(100, iid)]
    assert "PROPOSED create_work_order" in actions and "EXECUTED create_work_order" in actions


def test_close_requires_verification(platform, ctx):
    _incident(platform, ctx)
    assert not R.execute(ctx, "propose_incident_closure", {})["ok"]
