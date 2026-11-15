"""Overview filters must drive KPIs, rankings, hotspots, trends AND map layers consistently."""
import pytest
from fastapi.testclient import TestClient

from backend.agent.agent import GeoAIAgent
from backend.api.app import create_app
from backend.gis import schema as S
from backend.tools import executive, registry as R


def run(ctx, name, **a):
    r = R.execute(ctx, name, a)
    assert r["ok"], r
    return r["result"]


@pytest.fixture()
def populated(platform, ctx):
    platform.sim.scenario("multi_incident")
    run(ctx, "detect_water_leaks")
    run(ctx, "predict_streetlight_failures")
    run(ctx, "detect_imagery_changes", area="Olaya")
    run(ctx, "extract_geoai_features")
    run(ctx, "create_incidents_from_detections", detection_ids=[f["id"] for f in platform.store.all(S.DETECTIONS) if not f["attrs"]["Incident_ID"]])
    return platform


def test_priority_filter_partitions_everything(populated):
    st = populated.store
    total = executive.compute_kpis(st)
    parts = [executive.compute_kpis(st, priority=p) for p in ("P1", "P2", "P3", "P4")]
    for key in ("total_detections", "total_incidents", "open_incidents", "detected_urban_changes"):
        assert sum(p[key] for p in parts) == total[key], key
    assert total["total_detections"] > 0
    assert any(p["total_detections"] for p in parts)   # regression: priority used to zero every detection KPI
    # change candidates that never became a detection have no priority, so they are hidden once a priority is chosen
    assert sum(p["candidate_changes_total"] for p in parts) == total["detected_urban_changes"] <= total["candidate_changes_total"]


def test_area_and_category_filters(populated):
    st = populated.store
    total = executive.compute_kpis(st)
    areas = {f["attrs"]["Area_Name"] for f in st.all(S.INCIDENTS)}
    assert sum(executive.compute_kpis(st, area=a)["total_incidents"] for a in areas) == total["total_incidents"]
    water = executive.compute_kpis(st, category="water")
    assert water["predicted_streetlight_failures"] == 0 and water["detected_urban_changes"] == 0
    assert water["suspected_water_leaks"] == total["suspected_water_leaks"]
    assert executive.compute_kpis(st, category="change")["suspected_water_leaks"] == 0


def test_since_filter(populated):
    st = populated.store
    total = executive.compute_kpis(st)
    assert executive.compute_kpis(st, since="2000-01-01")["total_detections"] == total["total_detections"]
    future = executive.compute_kpis(st, since="2999-01-01")
    assert future["total_detections"] == 0 and future["total_incidents"] == 0 and future["detected_urban_changes"] == 0


def test_summary_rankings_hotspots_and_trend_follow_filters(populated, ctx):
    s = run(ctx, "executive_summary", area="Al Malaz")
    assert s["ranked_incidents"] and all(r["area"] == "Al Malaz" for r in s["ranked_incidents"])
    assert all(h["area"] == "Al Malaz" for h in s["hotspots"])
    assert s["filters"] == {"area": "Al Malaz", "category": None, "priority": None, "since": None}
    p = run(ctx, "executive_summary", priority="P1")
    assert all(r["priority"] == "P1" for r in p["ranked_incidents"])
    w = run(ctx, "executive_summary", category="water")
    assert all(r["category"] == "water" for r in w["ranked_incidents"])
    assert sum(sum(v) for v in w["trend"]["series"].values()) == sum(w["trend"]["series"]["water"])   # only water in the trend
    assert run(ctx, "executive_summary", since="2999-01-01")["ranked_incidents"] == []


def test_map_layers_obey_the_same_filters(populated):
    c = TestClient(create_app(populated, GeoAIAgent(populated)))
    props = lambda url: [f["properties"] for f in c.get(url).json()["features"]]  # noqa: E731
    assert {p["Area_Name"] for p in props("/api/layers/Riyadh_AI_Detections?area=Al%20Malaz")} == {"Al Malaz"}
    assert {p["Category"] for p in props("/api/layers/Riyadh_Operational_Incidents?category=lighting")} <= {"lighting"}
    assert {p["Priority"] for p in props("/api/layers/Riyadh_Operational_Incidents?priority=P1")} <= {"P1"}
    assert props("/api/layers/Riyadh_AI_Detections?since=2999-01-01") == []
    # infrastructure narrows by category, and pipes disappear when looking at lighting
    assert {p["Asset_Type"] for p in props("/api/layers/Riyadh_Infrastructure_Assets?category=lighting")} == {"Streetlight"}
    assert props("/api/layers/Riyadh_Water_Network?category=lighting") == []
    assert len(props("/api/layers/Riyadh_Water_Network?category=water")) == len(props("/api/layers/Riyadh_Water_Network"))
    assert {p["Area_Name"] for p in props("/api/layers/Riyadh_Water_Network?area=Olaya")} == {"Olaya"}
    assert {p["Base_Area"] for p in props("/api/layers/Riyadh_Field_Workers?area=Olaya")} <= {"Olaya"}
    # derived layers follow their parent change: extraction exists for Olaya only
    assert props("/api/layers/Riyadh_Extracted_Features?area=Olaya")
    assert props("/api/layers/Riyadh_Extracted_Features?area=KAFD") == []
    assert props("/api/layers/Riyadh_Change_Detection?category=water") == []
    # work orders / verifications follow their incident
    assert len(props("/api/layers/Riyadh_Work_Orders?area=Olaya")) <= len(props("/api/layers/Riyadh_Work_Orders"))
    # sensors: latest-per-sensor still works and narrows by area
    latest = props("/api/layers/Riyadh_Sensor_Readings?latest=true&area=Olaya")
    assert latest and len({p["Sensor_ID"] for p in latest}) == len(latest)


def test_api_executive_and_trends_accept_filters(populated):
    c = TestClient(create_app(populated, GeoAIAgent(populated)))
    r = c.get("/api/executive?area=Al%20Malaz&category=water").json()
    assert r["ok"] and r["result"]["filters"]["area"] == "Al Malaz"
    assert all(x["area"] == "Al Malaz" for x in r["result"]["ranked_incidents"])
    t = c.get("/api/trends?category=lighting").json()
    assert sum(t["series"]["water"]) == 0 and sum(t["series"]["change"]) == 0 and sum(t["series"]["distortion"]) == 0 and sum(t["series"]["land_use"]) == 0
    assert all(h["area"] == "Al Malaz" for h in c.get("/api/hotspots?area=Al%20Malaz").json())


def test_area_filter_does_not_inflate_hotspot_scores(populated):
    allh = {h["area"]: h["score"] for h in executive.hotspots(populated.store)}
    only = executive.hotspots(populated.store, area="Al Malaz")
    assert [h["area"] for h in only] == ["Al Malaz"] and only[0]["score"] == allh["Al Malaz"]
    assert allh["Al Malaz"] < 100 or len(allh) == 1
