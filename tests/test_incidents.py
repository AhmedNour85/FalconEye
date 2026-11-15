import pytest

from backend.gis import schema as S
from backend.tools import registry as R


def run(ctx, name, **args):
    r = R.execute(ctx, name, args)
    assert r["ok"], r
    return r["result"]


def test_no_leaks_before_scenario(ctx):
    assert run(ctx, "detect_water_leaks")["suspected_leaks"] == 0


def test_leak_detection_after_scenario(platform, ctx):
    sc = platform.sim.scenario("olaya_leak")
    r = run(ctx, "detect_water_leaks", area="Olaya")
    assert r["suspected_leaks"] >= 1
    d = r["detections"][0]
    assert d["pipeline_id"] == sc["pipeline_id"] and "Suspected" in d["status"]
    assert d["probable_location"]["uncertainty_radius_m"] > 0
    rec = platform.store.get(S.DETECTIONS, d["detection_id"])["attrs"]
    assert rec["Status"] == "Suspected" and "not confirmed" in rec["Evidence"].lower()
    # idempotent: re-running does not create a second detection for the pipeline
    run(ctx, "detect_water_leaks", area="Olaya")
    assert len([f for f in platform.store.all(S.DETECTIONS) if f["attrs"]["Pipeline_ID"] == sc["pipeline_id"]]) == 1


def test_decoy_has_lower_risk_than_real_leaks(platform, ctx):
    platform.sim.scenario("multi_incident")
    r = run(ctx, "detect_water_leaks")
    by_area = {d["area"]: d["risk_score"] for d in r["detections"]}
    assert by_area["KAFD"] < by_area["Al Malaz"]


def test_streetlight_cluster_on_king_fahd(ctx):
    r = run(ctx, "predict_streetlight_failures", corridor="King Fahd Road")
    assert r["predicted_failures"] >= 8 and r["clusters"]
    assert all(c["corridor"] == "King Fahd Road" for c in r["clusters"])
    assert all("not confirmed" in d["status"] for d in r["detections"])


def test_incident_creation_is_idempotent(platform, ctx):
    platform.sim.scenario("olaya_leak")
    run(ctx, "detect_water_leaks", area="Olaya")
    a = run(ctx, "create_incidents_from_detections")
    b = run(ctx, "create_incidents_from_detections")
    assert len(a["created"]) == 1 and not b["created"] and b["already_existing"] == [a["created"][0]["incident_id"]]


def test_cluster_becomes_single_incident(ctx):
    r = run(ctx, "predict_streetlight_failures", corridor="King Fahd Road")
    ids = [d["detection_id"] for d in r["detections"] if d["cluster_id"]]
    res = run(ctx, "create_incidents_from_detections", detection_ids=ids)
    assert len(res["created"]) == 1


def test_change_detection_flags_seasonal_as_not_significant(ctx):
    r = run(ctx, "detect_imagery_changes", area="Olaya")
    assert r["simulated_imagery"] and r["significant_count"] >= 2
    assert r["simulation_check"]["recovered"] == r["simulation_check"]["injected_real_changes"]
    for c in r["changes"]:
        if c["type"].startswith("Vegetation"):
            assert not c["significant"]


def test_feature_extraction_and_spatial(ctx):
    run(ctx, "detect_imagery_changes", area="Olaya")
    f = run(ctx, "extract_geoai_features")
    assert f["simulated"] and f["buildings"]
    sp = run(ctx, "spatial_analysis", target_type="change", radius_m=300)
    assert sp["target"]["area_sqm"] > 0 and sp["extracted_features"]


def test_tool_validation_errors(ctx):
    assert not R.execute(ctx, "spatial_analysis", {})["ok"]
    assert not R.execute(ctx, "detect_water_leaks", {"bogus": 1})["ok"]
    assert not R.execute(ctx, "executive_summary", {"category": "nonsense"})["ok"]
    assert not R.execute(ctx, "nope", {})["ok"]


def test_kpis_come_from_records(platform, ctx):
    k0 = run(ctx, "executive_summary")["kpis"]
    platform.sim.scenario("olaya_leak")
    run(ctx, "detect_water_leaks", area="Olaya")
    run(ctx, "create_incidents_from_detections")
    k1 = run(ctx, "executive_summary")["kpis"]
    assert k1["suspected_water_leaks"] == k0["suspected_water_leaks"] + 1
    assert k1["total_incidents"] == k0["total_incidents"] + 1
    assert run(ctx, "executive_summary", area="Olaya")["kpis"]["total_incidents"] <= k1["total_incidents"]



def test_empty_leak_scan_explains_itself_and_min_risk_changes_nothing(ctx):
    base = run(ctx, "detect_water_leaks")
    assert base["suspected_leaks"] == 0 and base["rule"]["min_pressure_drop_pct"] == 10 and base["rule"]["min_z_score"] == 3.5
    assert "min_risk" in base["no_detection_reason"] and "how_to_see_a_detection" in base
    cands = base["closest_candidates"]
    assert len(cands) == 3 and all(not c["meets_rule"] for c in cands) and cands == sorted(cands, key=lambda c: -c["z_score"])
    zero = run(ctx, "detect_water_leaks", min_risk=0)
    assert zero["suspected_leaks"] == 0 and zero["sensors_evaluated"] == base["sensors_evaluated"]   # the threshold cannot surface anything
    assert run(ctx, "detect_water_leaks", area="Olaya")["closest_candidates"][0]["area"] == "Olaya"


def test_offline_planner_explains_an_empty_scan(platform):
    from backend.agent.agent import GeoAIAgent
    r = GeoAIAgent(platform).chat("e", "Detect possible water leaks in Riyadh")["reply"]
    assert "no suspected leaks" in r and "Closest:" in r and "would not change this" in r and "Guided Demo scene 1" in r


def test_scan_after_scenario_still_finds_the_leak_and_has_no_empty_fields(platform, ctx):
    platform.sim.scenario("olaya_leak")
    r = run(ctx, "detect_water_leaks", area="Olaya")
    assert r["suspected_leaks"] >= 1 and "closest_candidates" not in r and "no_detection_reason" not in r



def test_create_incidents_falls_back_to_all_waiting_detections(platform, ctx):
    """Regression: a stale 'last detections' set (already converted) must not hide other detections that still need incidents."""
    from backend.tools.common import ToolContext
    platform.sim.scenario("olaya_leak")
    run(ctx, "detect_water_leaks", area="Olaya")
    first = run(ctx, "create_incidents_from_detections")
    assert len(first["created"]) == 1 and "Created 1 incident" in first["message"]
    other = ToolContext(platform, "other-session")                        # detections produced elsewhere (another session / the demo)
    run(other, "predict_streetlight_failures", corridor="King Fahd Road")
    again = run(ctx, "create_incidents_from_detections")                  # ctx.last_detections still points at the converted leak
    assert again["created"] and again["created"][0]["type"] == "Streetlight Cluster Maintenance" and again["waiting_before"] >= 1
    done = run(ctx, "create_incidents_from_detections")
    assert not done["created"] and "No new detections to convert" in done["message"] and "already have incidents" in done["message"]


def test_create_incidents_message_when_there_is_nothing_at_all(platform, ctx):
    for f in platform.store.all("Riyadh_AI_Detections"):
        platform.store.update("Riyadh_AI_Detections", f["id"], Status="Verified-True")
    r = run(ctx, "create_incidents_from_detections")
    assert not r["created"] and r["active_detections"] == 0 and "no active detections" in r["message"].lower()
