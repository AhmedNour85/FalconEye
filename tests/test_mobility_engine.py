"""The scenario engine ported from Agentic_AI_Transportation, on the 73-segment skeleton network. No ArcGIS Online."""
import pytest

from backend.mobility import engine, network_model, sources, strategies

WINDOW = {"start_time": "2026-11-16T08:00", "duration_hours": 8}   # a Monday


@pytest.fixture(scope="module", autouse=True)
def skeleton_model():
    sources.configure(network="skeleton")
    yield network_model.get_model()
    sources.configure(network="skeleton")


def closure(**kw):
    return engine.run_scenario({"scenario_type": "closure", "corridor": "King Fahd Road", **WINDOW, **kw}, persist=False)


@pytest.fixture(scope="module")
def full():
    return closure()


# ---- carried over ---------------------------------------------------------------------------
def test_a_king_fahd_road_closure_adds_delay(full):
    s = full["summary"]
    assert s["vht_delta_pct"] > 0 and s["affected_segments"] > 0
    assert isinstance(s["worst_hospital_access_delta_min"], (int, float))
    assert full["scenario"]["resolved"]["corridor"] == "King Fahd Road"
    assert full["geojson"]["closed"]["geometry"]["type"] == "MultiLineString"
    assert full["network_provenance"]["source"] == "skeleton"


def test_the_baseline_network_is_not_changed_by_a_scenario(skeleton_model):
    before = (skeleton_model.G.number_of_edges(), sorted(e["cap"] for _, _, e in skeleton_model.G.edges(data=True)), set(skeleton_model.closed))
    closure(lanes_closed=1)
    closure()
    after = (skeleton_model.G.number_of_edges(), sorted(e["cap"] for _, _, e in skeleton_model.G.edges(data=True)), set(skeleton_model.closed))
    assert before == after and not skeleton_model.closed


def test_twenty_percent_more_demand_raises_vehicle_hours():
    r = engine.run_scenario({"scenario_type": "demand", "demand_change_pct": 20}, persist=False)
    assert r["summary"]["vht_scenario_peak"] > r["summary"]["vht_baseline_peak"]


def test_an_event_at_kafd_adds_vehicles():
    r = engine.run_scenario({"scenario_type": "event", "place": "KAFD"}, persist=False)
    assert r["extra"]["event"]["added_vehicles_per_hour"] > 0
    assert r["summary"]["vht_delta_pct"] > 0


def test_five_strategies_are_compared_and_one_is_recommended():
    c = strategies.compare({"corridor": "King Fahd Road", **WINDOW}, persist=False)
    ids = [s["id"] for s in c["strategies"]]
    assert ids == ["do_nothing", "reschedule", "divert", "demand_shift", "combined"]
    assert next(s for s in c["strategies"] if s["id"] == "do_nothing")["score"] == 100.0
    assert c["recommended"] in ids and c["verdict"]
    assert "human" in c["human_authorization"].lower()


def test_a_saved_run_goes_to_the_memory_archive_only():
    r = engine.run_scenario({"scenario_type": "demand", "demand_change_pct": 5, "name": "archive check"}, persist=True)
    assert sources.get("SimulationScenario", r["scenario_id"])["name"] == "archive check"
    assert engine.compare_scenarios([r["scenario_id"]])["scenarios"][0]["name"] == "archive check"


# ---- review focus 1 and 2 ---------------------------------------------------------------------
def test_a_road_the_network_does_not_have_is_a_clear_error_that_names_known_roads():
    with pytest.raises(ValueError) as e:
        engine.run_scenario({"scenario_type": "closure", "corridor": "Nowhere Avenue"}, persist=False)
    msg = str(e.value)
    assert "Nowhere Avenue" in msg and "King Fahd Road" in msg and "Olaya Street" in msg


def test_a_closure_without_a_road_name_says_so():
    with pytest.raises(ValueError, match="needs a road name"):
        engine.run_scenario({"scenario_type": "closure"}, persist=False)


def test_a_road_is_found_by_its_exact_name_when_no_alias_covers_it(skeleton_model):
    from backend.mobility import road_closure
    assert road_closure.model_corridor(skeleton_model, "collector c1 (synthetic)") == "Collector C1 (synthetic)"
    assert road_closure.model_corridor(skeleton_model, "") is None


def test_a_closure_that_cuts_the_airport_off_lists_it_and_still_returns():
    r = engine.run_scenario({"scenario_type": "closure", "corridor": "Airport Road", "near": "KKIA", **WINDOW}, persist=False)
    s = r["summary"]
    assert "King Khalid International Airport" in s["isolated_zones"] and s["cut_off_demand_zones"] >= 1
    assert isinstance(s["vht_delta_pct"], float)
    assert any(m["title"] == "Restore connectivity" for m in r["mitigations"])


# ---- lane closure (new in Riyadh City View) ---------------------------------------------------
def test_closing_one_of_three_lanes_leaves_two_thirds_of_the_capacity(skeleton_model):
    m = skeleton_model.clone()
    seg = next(s for s in m.segments.values() if s["corridor"] == "Olaya Street")
    assert seg["lanes"] == 3
    left = m.reduce_capacity([seg["id"]], 1)
    assert left == {seg["id"]: pytest.approx(seg["capacity"] * 2 / 3)}
    caps = [e["cap"] for _, _, e in m.G.edges(data=True) if e["seg"] == seg["id"]]
    assert len(caps) == 2 and all(c == pytest.approx(3000.0) for c in caps)   # both directions are narrowed
    assert seg["id"] not in m.closed


def test_a_one_lane_closure_delays_less_than_a_full_closure_and_more_than_none(full):
    part = closure(lanes_closed=1)
    assert 0 < part["summary"]["window_extra_trip_hours"] < full["summary"]["window_extra_trip_hours"]
    res = part["scenario"]["resolved"]
    assert res["lanes_closed"] == 1 and res["capacity_left_pct"] == 75 and res["full_closure"] is False   # 4 lanes on the skeleton
    assert res["ids"] == full["scenario"]["resolved"]["ids"]
    assert not any(a["status"] == "closed" for a in part["affected_segments"])


@pytest.mark.parametrize("bad", [0, -1, "0"])
def test_zero_or_fewer_lanes_closed_is_refused(bad):
    with pytest.raises(ValueError, match="lanes_closed"):
        closure(lanes_closed=bad)


def test_lanes_closed_that_is_not_a_number_is_refused():
    with pytest.raises(ValueError, match="lanes_closed"):
        closure(lanes_closed="two")


def test_closing_every_lane_is_a_full_closure(full):
    every = closure(lanes_closed=4)
    more = closure(lanes_closed=9)
    for r in (every, more):
        assert r["scenario"]["resolved"]["full_closure"] is True and r["scenario"]["resolved"]["capacity_left_pct"] == 0
        assert r["summary"]["vht_scenario_peak"] == full["summary"]["vht_scenario_peak"]


def test_the_strategy_study_keeps_the_lane_count():
    c = strategies.compare({"corridor": "King Fahd Road", "lanes_closed": 2, **WINDOW}, strategy_ids=["reschedule"], persist=False)
    assert c["closure"]["lanes_closed"] == 2 and c["closure"]["capacity_left_pct"] == 50
    assert [s["id"] for s in c["strategies"]] == ["do_nothing", "reschedule"]
