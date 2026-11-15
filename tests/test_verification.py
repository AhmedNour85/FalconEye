import pytest

from backend.gis import schema as S
from backend.services import field
from backend.tools import registry as R


def run(ctx, name, **args):
    r = R.execute(ctx, name, args)
    assert r["ok"], r
    return r["result"]


def _assigned(platform, ctx, scenario="olaya_leak"):
    platform.sim.scenario(scenario)
    run(ctx, "detect_water_leaks", area="Olaya")
    iid = run(ctx, "create_incidents_from_detections")["created"][0]["incident_id"]
    platform.approvals.approve(run(ctx, "propose_work_order")["approval"]["Approval_ID"])
    platform.approvals.approve(run(ctx, "propose_field_assignment")["approval"]["Approval_ID"])
    wo = platform.store.query(S.WORK_ORDERS, Incident_ID=iid)[0]
    return iid, wo


def test_full_loop_confirm_repair_close_learn(platform, ctx):
    iid, wo = _assigned(platform, ctx)
    det = platform.store.get(S.INCIDENTS, iid)["attrs"]["Detection_IDs"]
    res = platform.simulate_field_response(wo["id"])
    assert res["outcome"] == "Confirmed"
    assert platform.store.get(S.DETECTIONS, det)["attrs"]["Status"] == "Verified-True"
    v = run(ctx, "verify_outcome")
    assert v["verified"] and "Confirmed" in v["agent_assessment"]
    assert not R.execute(ctx, "propose_incident_closure", {})["ok"]  # fault confirmed but not yet repaired
    platform.simulate_field_response(wo["id"], repair=True)
    assert platform.store.get(S.INCIDENTS, iid)["attrs"]["Status"] == "Repair Reported"
    cl = run(ctx, "propose_incident_closure")
    assert platform.store.get(S.INCIDENTS, iid)["attrs"]["Status"] == "Repair Reported"  # still not closed before approval
    assert platform.approvals.approve(cl["approval"]["Approval_ID"])["ok"]
    assert platform.store.get(S.INCIDENTS, iid)["attrs"]["Status"] == "Resolved"
    ev = run(ctx, "evaluate_outcomes", recalibrate=True)
    assert ev["evaluation"]["categories"]["water"]["verified_true"] >= 1


def test_false_positive_is_rejected_and_counted(platform, ctx):
    platform.sim.scenario("multi_incident")
    run(ctx, "detect_water_leaks")
    ids = [f["id"] for f in platform.store.all(S.DETECTIONS) if f["attrs"]["Area_Name"] == "KAFD" and f["attrs"]["Status"] == "Suspected" and f["attrs"]["Source"].startswith("Sensor")]
    iid = run(ctx, "create_incidents_from_detections", detection_ids=ids)["created"][0]["incident_id"]
    platform.approvals.approve(run(ctx, "propose_work_order", incident_id=iid)["approval"]["Approval_ID"])
    platform.approvals.approve(run(ctx, "propose_field_assignment")["approval"]["Approval_ID"])
    wo = platform.store.query(S.WORK_ORDERS, Incident_ID=iid)[0]
    before = run(ctx, "evaluate_outcomes")["evaluation"]["categories"]["water"]["verified_false"]
    assert platform.simulate_field_response(wo["id"])["outcome"] == "Rejected"
    assert platform.store.get(S.DETECTIONS, ids[0])["attrs"]["Status"] == "Verified-False"
    assert run(ctx, "evaluate_outcomes")["evaluation"]["categories"]["water"]["verified_false"] == before + 1
    cl = run(ctx, "propose_incident_closure", incident_id=iid)
    platform.approvals.approve(cl["approval"]["Approval_ID"])
    assert platform.store.get(S.INCIDENTS, iid)["attrs"]["Status"] == "Closed - False Positive"


def test_calibration_drops_when_predictions_fail(platform):
    from backend.services import learning
    before = learning.calibration(platform.store, "lighting")
    for f in platform.store.all(S.DETECTIONS):
        if f["attrs"]["Category"] == "lighting":
            platform.store.update(S.DETECTIONS, f["id"], Status="Verified-False")
    learning.recalibrate(platform.store)
    assert learning.calibration(platform.store, "lighting") < before
    assert learning.get_cfg(platform.store, "streetlight.detect_threshold") > 0.55


def test_gps_far_from_site_requires_further_inspection(platform, ctx):
    iid, wo = _assigned(platform, ctx)
    w = wo["attrs"]["Assigned_Worker"]
    res = field.submit(platform.store, platform.audit, platform.settings.evidence_dir, wo["id"], w, "Confirmed", "Looks wet over here", 24.60, 46.60)
    assert res["outcome"] == "Requires Further Inspection"
    assert platform.store.get(S.INCIDENTS, iid)["attrs"]["Status"] == "Requires Further Inspection"


def test_field_submission_validation_and_photo(platform, ctx, tmp_path):
    iid, wo = _assigned(platform, ctx)
    w = wo["attrs"]["Assigned_Worker"]
    ev = platform.settings.evidence_dir
    with pytest.raises(field.FieldError):
        field.submit(platform.store, platform.audit, ev, wo["id"], "WRK-099", "Confirmed", "valid text here", 24.69, 46.68)
    with pytest.raises(field.FieldError):
        field.submit(platform.store, platform.audit, ev, wo["id"], w, "Maybe", "valid text here", 24.69, 46.68)
    with pytest.raises(field.FieldError):
        field.submit(platform.store, platform.audit, ev, wo["id"], w, "Confirmed", "x", 24.69, 46.68)
    pt = platform.store.get(S.INCIDENTS, iid)["geom"]["coordinates"]
    res = field.submit(platform.store, platform.audit, ev, wo["id"], w, "Confirmed", "Water on the road surface", pt[1], pt[0], b"\x89PNG fake", "x.png")
    v = platform.store.get(S.VERIFICATION, res["verification_id"])["attrs"]
    assert v["Photo_URL"].startswith("/api/evidence/") and v["Simulated_Worker"] == "No"
