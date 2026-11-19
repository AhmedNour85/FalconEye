"""QA-03: a leak that is being handled, or was repaired, is not raised again as a new incident on the next scan."""
from backend.gis import schema as S
from backend.tools import registry as R


def run(ctx, name, **args):
    r = R.execute(ctx, name, args)
    assert r["ok"], r
    return r["result"]


def _confirmed_leak(platform, ctx):
    platform.sim.scenario("olaya_leak")
    run(ctx, "detect_water_leaks", area="Olaya")
    iid = run(ctx, "create_incidents_from_detections")["created"][0]["incident_id"]
    a = run(ctx, "propose_work_order")["approval"]["Approval_ID"]
    assert platform.approvals.approve(a, "tester")["ok"]
    wo = platform.store.query(S.WORK_ORDERS, Incident_ID=iid)[0]["id"]
    a = run(ctx, "propose_field_assignment", work_order_id=wo)["approval"]["Approval_ID"]
    assert platform.approvals.approve(a, "tester")["ok"]
    assert platform.simulate_field_response(wo)["outcome"] == "Confirmed"
    return iid


def _water_incidents(platform):
    return {f["id"] for f in platform.store.all(S.INCIDENTS) if f["attrs"]["Category"] == "water"}


def _scan(ctx):
    run(ctx, "detect_water_leaks", area="Olaya")
    return run(ctx, "create_incidents_from_detections")


def test_a_confirmed_leak_still_open_is_not_raised_again(platform, ctx):
    _confirmed_leak(platform, ctx)
    before = _water_incidents(platform)
    _scan(ctx)
    assert _water_incidents(platform) == before


def test_a_repaired_and_closed_leak_is_not_raised_again(platform, ctx):
    iid = _confirmed_leak(platform, ctx)
    platform.simulate_repair(iid)
    a = run(ctx, "propose_incident_closure", incident_id=iid)["approval"]["Approval_ID"]
    assert platform.approvals.approve(a, "tester")["ok"]
    assert platform.store.get(S.INCIDENTS, iid)["attrs"]["Status"] == "Resolved"
    before = _water_incidents(platform)
    found = run(ctx, "detect_water_leaks", area="Olaya")
    run(ctx, "create_incidents_from_detections")
    assert _water_incidents(platform) == before
    assert found["suspected_leaks"] == 0                      # the repaired pipe's sensor reads normal again


def test_a_new_leak_after_the_repair_is_still_detected(platform, ctx):
    iid = _confirmed_leak(platform, ctx)
    platform.simulate_repair(iid)
    a = run(ctx, "propose_incident_closure", incident_id=iid)["approval"]["Approval_ID"]
    assert platform.approvals.approve(a, "tester")["ok"]
    before = _water_incidents(platform)
    platform.sim.scenario("olaya_leak")                       # the pipe breaks again
    _scan(ctx)
    assert len(_water_incidents(platform) - before) == 1
