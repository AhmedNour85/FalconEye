"""The three simulated mobility events (Plan 3, task 5). Each writes one synthetic row; the crew's reaction is task 6."""
import pytest

from backend.gis import schema as S
from backend.mobility import network_model, sources
from backend.orchestration.crew import Crew


def roads():
    return {r["id"]: r for r in sources.load_network()[0]}


def test_a_traffic_incident_is_one_new_synthetic_report_on_a_real_wide_road(platform):
    before = platform.store.count(S.SIM_EVENTS)
    r = platform.sim.scenario("traffic_incident")
    rows = platform.store.all(S.TRAFFIC_REPORTS)
    assert len(rows) == 1 and r["scenario"] == "traffic_incident" and r["id"] == rows[0]["id"]
    a = rows[0]["attrs"]
    road = roads()[a["Segment_ID"]]
    assert a["Status"] == "New" and a["Data_Classification"] == S.SYNTHETIC and a["Lanes_Blocked"] == 2 and a["Report_Type"] == "Crash"
    assert road["corridor"] == a["Corridor"] == r["corridor"] and road["road_class"] in ("motorway", "arterial") and a["Lanes"] == road["lanes"] >= 3
    assert rows[0]["geom"]["type"] == "Point" and a["Description"] and "SYNTHETIC" in a["Source"]
    truth = platform.store.get(S.TRUTH, r["id"])["attrs"]
    assert truth["Is_True"] == "Yes"
    assert platform.store.count(S.SIM_EVENTS) == before + 1 and platform.sim.events(1)[0]["Ref_ID"] == r["id"]


def test_three_traffic_incidents_land_on_at_least_two_roads(platform):
    picked = {platform.sim.scenario("traffic_incident")["corridor"] for _ in range(3)}
    assert len(picked) >= 2 and platform.store.count(S.TRAFFIC_REPORTS) == 3


def test_a_road_closure_request_is_one_full_closure_for_tomorrow_with_a_reason(platform):
    from backend.mobility import jobs

    r = platform.sim.scenario("road_closure")
    rows = platform.store.all(S.CLOSURES)
    assert len(rows) == 1 and r["id"] == rows[0]["id"] and r["scenario"] == "road_closure"
    a = rows[0]["attrs"]
    tomorrow = (jobs.riyadh_now() + __import__("datetime").timedelta(days=1)).date().isoformat()
    assert a["Status"] == "Requested" and a["Full_Closure"] == "Yes" and a["Reason"] and a["Data_Classification"] == S.SYNTHETIC
    assert a["Start_Time"] == f"{tomorrow}T08:00" and a["End_Time"] == f"{tomorrow}T16:00"
    ids = [i for i in a["Segment_IDs"].split(",") if i]
    assert ids and all(roads()[i]["corridor"] == a["Corridor"] == r["corridor"] for i in ids)
    assert rows[0]["geom"]["type"] in ("LineString", "MultiLineString") and a["Requested_By"] and not a["Incident_ID"] and not a["Work_Order_ID"]
    assert platform.store.get(S.TRUTH, r["id"])["attrs"]["Is_True"] == "Yes"


def test_a_major_event_is_one_notice_at_a_venue_the_engine_knows(platform):
    r = platform.sim.scenario("major_event")
    rows = platform.store.all(S.EVENT_NOTICES)
    assert len(rows) == 1 and r["id"] == rows[0]["id"] and r["scenario"] == "major_event"
    a = rows[0]["attrs"]
    assert a["Status"] == "New" and a["Data_Classification"] == S.SYNTHETIC and a["Attendance"] >= 10000 and a["Name"] and a["Venue"] == r["venue"]
    assert network_model.get_model().resolve_place(a["Venue"])
    assert a["Start_Time"].endswith("T18:00") and a["End_Time"].endswith("T23:00") and rows[0]["geom"]["type"] == "Point"
    assert platform.store.get(S.TRUTH, r["id"])["attrs"]["Is_True"] == "Yes"


def test_each_event_writes_only_its_own_layer(platform):
    counts = lambda: {k: platform.store.count(k) for k in (S.TRAFFIC_REPORTS, S.CLOSURES, S.EVENT_NOTICES, S.DETECTIONS, S.INCIDENTS, S.SCENARIOS)}  # noqa: E731
    base = counts()
    platform.sim.scenario("road_closure")
    assert counts() == {**base, S.CLOSURES: base[S.CLOSURES] + 1}
    platform.sim.scenario("major_event")
    assert counts() == {**base, S.CLOSURES: base[S.CLOSURES] + 1, S.EVENT_NOTICES: base[S.EVENT_NOTICES] + 1}


def test_the_unknown_scenario_message_lists_the_three_mobility_events(platform):
    with pytest.raises(ValueError) as e:
        platform.sim.scenario("atlantis_rising")
    assert all(n in str(e.value) for n in ("traffic_incident", "road_closure", "major_event"))


def test_the_three_events_wake_only_the_mobility_feed_and_draw_no_citizen_reports(platform):
    for name in ("traffic_incident", "road_closure", "major_event"):
        assert Crew.EVENT_SCOPE(name) == frozenset({"mobility"})
        before = platform.store.count(S.CITIZEN)
        assert platform.feeds.on_scenario(name, platform.sim.scenario(name)) == 0 and platform.store.count(S.CITIZEN) == before
    assert Crew.EVENT_SCOPE("olaya_leak") == frozenset({"water"})
