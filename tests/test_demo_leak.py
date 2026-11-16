"""Plan 5, Task 7: the headline demo story needs the demo water leak next to a modelled road."""
from backend.gis import geo
from backend.gis import schema as S
from backend.mobility import road_impact, rules


def test_the_demo_leak_is_within_the_road_impact_rule_of_a_modelled_arterial(platform):
    out = platform.sim.scenario("olaya_leak")
    pipe = platform.store.get(S.WATER, out["pipeline_id"])
    mid = geo.interpolate(pipe["geom"]["coordinates"], 0.5)[0]
    road = road_impact.nearest_road(mid, rules.ROAD_IMPACT["water"]["radius_m"])
    assert road is not None and road["distance_m"] <= 60


def test_a_leak_with_no_modelled_road_nearby_still_starts(platform, monkeypatch):
    monkeypatch.setattr(road_impact, "nearest_road", lambda lonlat, radius_m: None)
    out = platform.sim.scenario("olaya_leak")
    assert out["pipeline_id"] and out["sensor_id"]


def test_the_leak_prefers_the_pipe_that_is_next_to_a_road(platform, monkeypatch):
    default = platform.sim.scenario("olaya_leak")["pipeline_id"]
    other = next(q for q, _s in platform.sim._pipes_with_sensors("Olaya") if q != default)
    near = geo.interpolate(platform.store.get(S.WATER, other)["geom"]["coordinates"], 0.5)[0]
    monkeypatch.setattr(road_impact, "nearest_road", lambda lonlat, radius_m: {"distance_m": 1.0} if abs(lonlat[0] - near[0]) < 1e-9 and abs(lonlat[1] - near[1]) < 1e-9 else None)
    assert platform.sim.scenario("olaya_leak")["pipeline_id"] == other


def test_the_leak_prefers_a_named_road_with_more_lanes_over_an_unnamed_link(platform, monkeypatch):
    default = platform.sim.scenario("olaya_leak")["pipeline_id"]
    pairs = [q for q, _s in platform.sim._pipes_with_sensors("Olaya")]
    named, link = [q for q in pairs if q != default][:2]
    mid = lambda q: geo.interpolate(platform.store.get(S.WATER, q)["geom"]["coordinates"], 0.5)[0]
    roads = {mid(link): {"corridor": "unnamed primary_link", "lanes": 4, "distance_m": 2.0}, mid(named): {"corridor": "Olaya Street", "lanes": 3, "distance_m": 30.0}}
    monkeypatch.setattr(road_impact, "nearest_road", lambda lonlat, radius_m: next((r for m, r in roads.items() if abs(m[0] - lonlat[0]) < 1e-9 and abs(m[1] - lonlat[1]) < 1e-9), None))
    assert platform.sim.scenario("olaya_leak")["pipeline_id"] == named
