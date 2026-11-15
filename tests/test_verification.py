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
    res = field.submit(platform.store, platform.audit, wo["id"], w, "Confirmed", "Looks wet over here", 24.60, 46.60)
    assert res["outcome"] == "Requires Further Inspection"
    assert platform.store.get(S.INCIDENTS, iid)["attrs"]["Status"] == "Requires Further Inspection"


def test_field_submission_validation_and_photo(platform, ctx, tmp_path):
    iid, wo = _assigned(platform, ctx)
    w = wo["attrs"]["Assigned_Worker"]
    with pytest.raises(field.FieldError):
        field.submit(platform.store, platform.audit, wo["id"], "WRK-099", "Confirmed", "valid text here", 24.69, 46.68)
    with pytest.raises(field.FieldError):
        field.submit(platform.store, platform.audit, wo["id"], w, "Maybe", "valid text here", 24.69, 46.68)
    with pytest.raises(field.FieldError):
        field.submit(platform.store, platform.audit, wo["id"], w, "Confirmed", "x", 24.69, 46.68)
    pt = platform.store.get(S.INCIDENTS, iid)["geom"]["coordinates"]
    res = field.submit(platform.store, platform.audit, wo["id"], w, "Confirmed", "Water on the road surface", pt[1], pt[0], b"\x89PNG fake", "x.png")
    v = platform.store.get(S.VERIFICATION, res["verification_id"])["attrs"]
    vid = res["verification_id"]
    assert v["Photo_URL"] == f"/api/evidence/{vid}/{vid}.png" and v["Simulated_Worker"] == "No"
    assert platform.store.attachment(S.VERIFICATION, vid, f"{vid}.png") == b"\x89PNG fake"      # kept with the row, not in a folder


def test_a_photo_goes_to_arcgis_online_as_an_attachment_and_is_served_from_there():
    from fastapi.testclient import TestClient

    from backend.agent.agent import GeoAIAgent
    from backend.api.app import create_app
    from backend.gis.store import StoreWriteError
    from backend.platform import Platform
    from backend.tools.common import ToolContext
    from config.settings import Settings
    from tests.fakes import FakeGateway
    gw = FakeGateway()
    p = Platform(settings=Settings(store="arcgis", arcgis_username="u", arcgis_password="p", field_sync_seconds=0, field_form=True), gateway=gw)
    p.reset()
    iid, wo = _assigned(p, ToolContext(p, "test"))
    w, pt = wo["attrs"]["Assigned_Worker"], p.store.get(S.INCIDENTS, iid)["geom"]["coordinates"]
    res = field.submit(p.store, p.audit, wo["id"], w, "Confirmed", "Water on the road surface", pt[1], pt[0], b"\xff\xd8 jpeg", "leak.jpg")
    vid = res["verification_id"]
    assert res["photo_saved"] is True and "warning" not in res
    assert gw.attachments[(S.VERIFICATION, vid)] == {f"{vid}.jpg": b"\xff\xd8 jpeg"}
    r = TestClient(create_app(p, GeoAIAgent(p))).get(f"/api/evidence/{vid}/{vid}.jpg")
    assert r.status_code == 200 and r.content == b"\xff\xd8 jpeg" and r.headers["content-type"] == "image/jpeg"


def test_a_report_is_kept_when_arcgis_online_refuses_only_the_photo(platform, ctx):
    from backend.gis.store import StoreWriteError
    iid, wo = _assigned(platform, ctx)
    w, pt = wo["attrs"]["Assigned_Worker"], platform.store.get(S.INCIDENTS, iid)["geom"]["coordinates"]

    def refuse(layer, fid, name, data):
        raise StoreWriteError("attachments are switched off on this layer", layer=layer, fid=fid)
    platform.store.add_attachment = refuse
    res = field.submit(platform.store, platform.audit, wo["id"], w, "Confirmed", "Water on the road surface", pt[1], pt[0], b"\xff\xd8 jpeg", "leak.jpg")
    assert res["outcome"] == "Confirmed" and res["photo_saved"] is False
    assert res["warning"].startswith("Your report was saved, but the photo was not") and "attachments are switched off" in res["warning"]
    assert platform.store.get(S.VERIFICATION, res["verification_id"])["attrs"]["Photo_URL"] == ""
