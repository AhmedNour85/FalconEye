"""Plan 5, Task 3: the mobility numbers on the Executive Hub. Skeleton network, memory stand-in."""
import pytest
from fastapi.testclient import TestClient

from backend.agent.agent import GeoAIAgent
from backend.api.app import create_app
from backend.gis import schema as S
from backend.mobility import traffic
from backend.services import mobility_numbers as MN
from backend.tools import executive


@pytest.fixture()
def ready(platform):
    traffic.warm(wait=True)
    return platform


def _closure(platform, cid, status, start, end):
    platform.store.upsert(S.CLOSURES, {"Closure_ID": cid, "Corridor": "King Fahd Road", "Section": "King Fahd Road", "Lanes_Closed": 1, "Full_Closure": "No", "Start_Time": start,
                                       "End_Time": end, "Reason": "test", "Status": status, "Incident_ID": "", "Scenario_ID": ""},
                          {"type": "LineString", "coordinates": [[46.67, 24.71], [46.68, 24.72]]})


def test_the_four_numbers_come_from_the_traffic_model(ready):
    s = MN.summary(ready)
    states = {h: traffic.state(h) for h in range(24)}
    peak = max(states, key=lambda h: states[h]["totals"]["vehicle_hours"])
    quiet = min(states, key=lambda h: states[h]["totals"]["vehicle_hours"])
    assert s["peak_hour"] == peak and s["label"] == "Modelled"
    assert s["peak_delay_ratio"] == round(states[quiet]["totals"]["avg_speed_kph"] / states[peak]["totals"]["avg_speed_kph"], 2) and s["peak_delay_ratio"] >= 1
    assert s["severe_segments"] == states[peak]["counts"]["heavy"] + states[peak]["counts"]["stopped"]
    assert s["worst_hospital_minutes"] is not None and s["worst_hospital_minutes"] > 0
    assert s["planned_closures"] == 0


def test_before_the_model_is_ready_the_numbers_are_none_not_zero(platform, monkeypatch):
    monkeypatch.setattr(traffic, "status", lambda: {"ready": False})
    s = MN.summary(platform)
    assert s["peak_delay_ratio"] is None and s["severe_segments"] is None and s["worst_hospital_minutes"] is None and s["planned_closures"] == 0
    assert MN.hotspots(platform) == []


def test_an_ended_closure_is_not_counted_and_is_marked_ended(ready):
    _closure(ready, "CLS-9001", "In Place", "2099-01-01T08:00", "2099-01-01T16:00")
    _closure(ready, "CLS-9002", "In Place", "2020-01-01T08:00", "2020-01-01T16:00")
    _closure(ready, "CLS-9003", "Ended", "2099-01-01T08:00", "2099-01-01T16:00")
    assert MN.summary(ready)["planned_closures"] == 1
    assert MN.expire_closures(ready) == 1
    assert ready.store.get(S.CLOSURES, "CLS-9002")["attrs"]["Status"] == "Ended" and ready.store.get(S.CLOSURES, "CLS-9001")["attrs"]["Status"] == "In Place"
    assert MN.expire_closures(ready) == 0                                                       # nothing left to expire
    client = TestClient(create_app(ready, GeoAIAgent(ready)))
    assert [f["id"] for f in client.get("/api/mobility/closures").json()["features"]] == ["CLS-9001"]


def test_the_trend_has_a_mobility_line(ready):
    ready.crew.inject("traffic_incident")
    t = executive.trends(ready.store)
    assert "mobility" in t["series"] and sum(t["series"]["mobility"]) >= 1 and len(t["series"]["mobility"]) == len(t["dates"])


def test_congestion_hotspots_are_ranked_and_placed(ready):
    hs = MN.hotspots(ready, top_n=3, hour=MN.summary(ready)["peak_hour"])
    assert 1 <= len(hs) <= 3 and all(h["kind"] == "congestion" for h in hs)
    assert hs == sorted(hs, key=lambda h: -h["score"]) and all(h["road"] and h["lon"] and h["lat"] and 0 < h["score"] <= 100 for h in hs)


def test_the_route_serves_the_numbers_and_the_hotspots(ready):
    client = TestClient(create_app(ready, GeoAIAgent(ready)))
    d = client.get("/api/mobility/numbers").json()
    assert d["summary"]["label"] == "Modelled" and d["summary"]["peak_delay_ratio"] and isinstance(d["hotspots"], list)
