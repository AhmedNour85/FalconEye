"""Synthetic road-safety inputs, the mobility rules table and the Traffic Response team (Plan 3, task 2)."""
from backend.gis import schema as S
from backend.mobility import rules, safety, sources
from backend.services import workforce
from scripts import add_mobility_demo_rows
from tests.fakes import FakeGateway


def _ids(n=5):
    roads, _nodes, _prov = sources.load_network()
    return [r["id"] for r in roads[:n]]


def test_the_safety_inputs_are_the_same_for_the_same_seed(platform):
    ids = _ids(20)
    safety.build(42)
    a = (safety.accident_history(ids), safety.asset_condition(ids), safety.maintenance_priority(5))
    safety.build(42)
    b = (safety.accident_history(ids), safety.asset_condition(ids), safety.maintenance_priority(5))
    assert a == b
    safety.build(7)
    assert (safety.accident_history(ids), safety.asset_condition(ids)) != a[:2]


def test_an_unknown_road_section_gives_zeros_not_an_error(platform):
    safety.build(42)
    h = safety.accident_history(["no-such-segment"])
    assert (h["accidents"], h["severe"], h["weighted_per_km"]) == (0, 0, 0.0)
    c = safety.asset_condition(["no-such-segment"])
    assert c["worst_condition"] is None and c["proposed_action"] == "unknown"


def test_every_answer_says_it_is_synthetic(platform):
    safety.build(42)
    ids = _ids()
    assert safety.accident_history(ids)["label"] == safety.LABEL and safety.asset_condition(ids)["label"] == safety.LABEL
    rows = safety.maintenance_priority(3)
    assert len(rows) == 3 and all(r["label"] == safety.LABEL for r in rows)
    assert rows == sorted(rows, key=lambda r: -r["priority_score"])
    assert "SYNTHETIC" in safety.LABEL


def test_the_network_has_some_accidents_and_some_poor_sections(platform):
    safety.build(42)
    roads, _n, _p = sources.load_network()
    ids = [r["id"] for r in roads]
    assert safety.accident_history(ids)["accidents"] > 0
    assert safety.asset_condition(ids)["worst_condition"] < 65


def test_the_risk_scores_never_exceed_95_and_rise_with_the_blockage():
    assert rules.report_risk(4, 4, "motorway", 2.0) == 95
    assert rules.report_risk(4, 1, "collector", 0.3) < rules.report_risk(4, 3, "collector", 0.3) < rules.report_risk(4, 3, "motorway", 0.9) <= 95
    assert rules.closure_risk("motorway", True, 200) <= 95 and rules.closure_risk("collector", False, 2) < rules.closure_risk("motorway", True, 8)
    assert rules.event_risk(10_000_000) == 85 and rules.event_risk(5_000) < rules.event_risk(60_000)      # 45 + at most 40
    r = rules.ROAD_IMPACT["water"]
    assert (r["radius_m"], r["lanes"], r["day"], r["night"], r["night_saving"]) == (60, 2, (8, 16), (22, 6), 0.10)


def test_a_mobility_incident_goes_to_the_traffic_response_team(platform):
    assert workforce.TEAM_FOR["mobility"] == "Traffic Response" and workforce.SKILL_FOR["mobility"] == "traffic"
    team = {w["attrs"]["Name"]: w["attrs"] for w in platform.store.all(S.WORKERS) if w["attrs"]["Team"] == "Traffic Response"}
    assert sorted(team) == ["Bandar Al-Shehri", "Rayan Al-Anazi"]
    assert {a["Worker_ID"] for a in team.values()} == {"WRK-008", "WRK-009"}
    best = workforce.rank_workers(platform.store, (46.6753, 24.7136), "mobility")[0]
    assert best["team"] == "Traffic Response"


def test_the_first_seven_investigators_are_unchanged(platform):
    names = [platform.store.get(S.WORKERS, f"WRK-{i:03d}")["attrs"]["Name"].split()[0] for i in range(1, 8)]
    assert names == ["Nawaf", "Khalid", "Saad", "Hamad", "Yousef", "Ibrahim", "Majed"]


def test_the_script_adds_the_two_investigators_only_when_told_to(capsys):
    gw = FakeGateway()
    gw.outside_edit(S.WORKERS, {"Worker_ID": "WRK-001", "Name": "Nawaf Al-Harbi"})
    assert add_mobility_demo_rows.main([], gateway=gw) == 0
    shown = capsys.readouterr().out
    assert gw.writes == [] and "DRY RUN (nothing is changed)" in shown and "2 to add" in shown and "Bandar Al-Shehri" in shown
    assert add_mobility_demo_rows.main(["--apply"], gateway=gw) == 0
    assert gw.ids(S.WORKERS) == {"WRK-001", "WRK-008", "WRK-009"}
    assert gw.rows(S.WORKERS)[0]["attrs"] == {"Worker_ID": "WRK-001", "Name": "Nawaf Al-Harbi"}       # no existing row is changed
    capsys.readouterr()
    assert add_mobility_demo_rows.main([], gateway=gw) == 0
    assert "0 to add" in capsys.readouterr().out


def test_the_script_stops_when_the_layer_is_missing(capsys):
    gw = FakeGateway()
    gw.missing.add(S.WORKERS)
    assert add_mobility_demo_rows.main(["--apply"], gateway=gw) == 3 and gw.writes == []
