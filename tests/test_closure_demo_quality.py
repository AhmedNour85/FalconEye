"""QA-04: the simulated Road closure lands on a road where the model shows an impact, and the strategy table shows all five strategies."""
from pathlib import Path

from backend.mobility import sources
from backend.services import simulation

FRONT = Path(__file__).resolve().parents[1] / "frontend"


def _wide_roads():
    return [r for r in sources.load_network()[0] if r["road_class"] in ("motorway", "arterial") and int(r["lanes"]) >= 2 and r.get("corridor")]


def test_the_closure_request_takes_a_section_that_is_loaded_at_the_peak(platform, monkeypatch):
    roads = _wide_roads()
    assert len({r["corridor"] for r in roads}) >= 2
    busy = roads[-1]
    monkeypatch.setattr(simulation, "road_peak_load", lambda sid: 1.05 if sid == busy["id"] else 0.2)
    out = platform.sim.scenario("road_closure")
    assert out["segment_id"] == busy["id"]


def test_without_the_traffic_model_the_closure_request_still_starts(platform, monkeypatch):
    monkeypatch.setattr(simulation, "road_peak_load", lambda sid: None)
    out = platform.sim.scenario("road_closure")
    assert out["segment_id"] and out["corridor"]


def test_skipped_strategy_rows_are_not_hidden_by_the_skip_link_style():
    js = (FRONT / "nccc.js").read_text(encoding="utf-8")
    css = (FRONT / "nccc.css").read_text(encoding="utf-8")
    assert '" skip"' not in js and "x.skipped ? \" skipped\"" in js      # the row class must not be the skip-link class
    assert ".skip{position:absolute" in css                                # (that class stays the skip-to-content link)
    assert "tr.skipped" in (FRONT / "mobility.css").read_text(encoding="utf-8")


def test_the_benefit_column_is_not_shown_as_zero_when_doing_nothing_costs_nothing():
    js = (FRONT / "nccc.js").read_text(encoding="utf-8")
    assert "noDelay" in js and "fewer trip-hours than with no closure" in js


def test_among_busy_roads_one_with_an_arabic_name_is_taken(platform, monkeypatch):
    from backend.services import i18n
    roads = _wide_roads()
    named = [r for r in roads if r["corridor"] in i18n.TERMS]
    other = [r for r in roads if r["corridor"] not in i18n.TERMS]
    assert named and other
    busy = {named[0]["id"]: 0.9, other[0]["id"]: 1.4}
    monkeypatch.setattr(simulation, "road_peak_load", lambda sid: busy.get(sid, 0.1))
    assert platform.sim.scenario("road_closure")["segment_id"] == named[0]["id"]
