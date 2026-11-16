"""The cross-domain link (Plan 3, task 8): a water-leak repair next to a modelled road gets a road-impact line and a planned closure."""
import json

import pytest

from backend.gis import geo
from backend.gis import schema as S
from backend.mobility import jobs as jobsmod
from backend.mobility import road_impact, rules, sources

WATER = frozenset({"water"})


def wide_road(lanes=3):
    return next(r for r in sorted(sources.load_network()[0], key=lambda r: r["id"]) if int(r["lanes"]) >= lanes and r["corridor"])


def as_found(r, lanes=None):
    return {"segment_id": r["id"], "corridor": r["corridor"], "name": r["name"], "lanes": int(lanes or r["lanes"]), "distance_m": 12.0}


def leak(platform, monkeypatch, road):
    """Inject the Olaya leak with `road` (or no road) next to it. Returns (incident id, its pending work-order approval)."""
    monkeypatch.setattr(road_impact, "nearest_road", lambda lonlat, radius_m: road)
    out = platform.crew.inject("olaya_leak")
    iid = next(i for i in out["scan"]["new_incidents"] if platform.store.get(S.INCIDENTS, i)["attrs"]["Category"] == "water")
    apr = next(f["attrs"] for f in platform.store.query(S.APPROVALS, Action_Type="create_work_order", Target=iid))
    return iid, apr


def alert(platform, iid):
    return next(n for n in platform.crew.notifications() if n["Incident_ID"] == iid and n["Kind"] == "fault")


def impact_rows(platform, iid):
    return [r["attrs"] for r in platform.store.query(S.SCENARIOS, Subject_ID=iid) if r["attrs"]["Scenario_Type"] == "road_impact"]


# ---------------------------------------------------------------- the small rules
def test_the_nearest_road_is_found_within_the_radius_only(platform):      # the platform fixes the network (skeleton), so the test does not depend on test order
    r = wide_road()
    c = r["geometry"]["coordinates"]
    mid = ((c[0][0] + c[1][0]) / 2, (c[0][1] + c[1][1]) / 2)
    near = road_impact.nearest_road(mid, 60)
    assert near and near["distance_m"] <= 1 and near["lanes"] >= 1 and near["segment_id"] and near["corridor"]
    assert road_impact.nearest_road((45.0, 23.0), 60) is None                              # far outside the city
    far = geo.offset(mid, 5000, 5000)
    hit = road_impact.nearest_road(far, 60)
    assert hit is None or hit["distance_m"] <= 60


def test_two_lanes_are_closed_on_a_wide_road_and_the_whole_road_when_it_has_two_or_fewer():
    r = wide_road()
    p = road_impact.params("water", as_found(r, lanes=4))
    assert p["lanes_closed"] == rules.ROAD_IMPACT["water"]["lanes"] == 2 and p["day"] == [8, 16] and p["night"] == [22, 6] and p["night_saving"] == 0.10
    assert road_impact.params("water", as_found(r, lanes=2))["lanes_closed"] is None
    assert road_impact.params("water", as_found(r, lanes=1))["lanes_closed"] is None


def test_night_is_recommended_only_when_it_saves_at_least_ten_percent():
    day = {"window_extra_trip_hours": 1000}
    assert road_impact.recommend(day, {"window_extra_trip_hours": 950}) == "day"            # saves 5%
    assert road_impact.recommend(day, {"window_extra_trip_hours": 500}) == "night"          # saves 50%
    assert road_impact.recommend(day, {"window_extra_trip_hours": 900}) == "night"          # saves exactly 10%
    assert road_impact.recommend({"window_extra_trip_hours": 0}, {"window_extra_trip_hours": 0}) == "day"


def test_the_three_sentences():
    day = {"start": "2026-11-17T08:00", "end": "2026-11-17T16:00", "window_extra_trip_hours": 1200.4, "worst_hospital_access_delta_min": 4}
    night = {"start": "2026-11-17T22:00", "end": "2026-11-18T06:00", "window_extra_trip_hours": 150, "worst_hospital_access_delta_min": 1}
    s = {"road": "Olaya Street", "lanes_closed": 2, "full_closure": False, "day": day, "night": night, "recommended": "night", "small": False}
    assert road_impact.line(s) == ("Road impact (modelled): closing 2 lanes of Olaya Street 08:00 to 16:00 adds 1,200 trip-hours and 4 min to the worst hospital access; "
                                   "at night 150 trip-hours and 1 min. Recommended: night.")
    assert "closing Olaya Street 08:00 to 16:00 adds" in road_impact.line({**s, "lanes_closed": None, "full_closure": True})
    small = {**s, "small": True, "recommended": "day", "day": {**day, "window_extra_trip_hours": 12}, "night": {**night, "window_extra_trip_hours": 3}}
    assert road_impact.line(small) == "Road impact (modelled): small in both windows (day 12, night 3 trip-hours). Recommended: day."


def test_an_approval_can_be_amended_only_while_it_is_proposed(platform, monkeypatch):
    iid, apr = leak(platform, monkeypatch, None)
    assert platform.approvals.amend(apr["Approval_ID"], {"note": "x"}, " And more.") is True
    row = platform.store.get(S.APPROVALS, apr["Approval_ID"])["attrs"]
    assert json.loads(row["Payload"])["note"] == "x" and row["Expected_Result"].endswith(" And more.") and len(row["Expected_Result"]) <= 255
    assert "AMENDED create_work_order" in [r["Agent_Action"] for r in platform.audit.recent(50, iid)]
    platform.approvals.reject(apr["Approval_ID"])
    assert platform.approvals.amend(apr["Approval_ID"], {"note": "y"}) is False and platform.approvals.amend("APR-9999", {}) is False
    assert json.loads(platform.store.get(S.APPROVALS, apr["Approval_ID"])["attrs"]["Payload"])["note"] == "x"


# ---------------------------------------------------------------- the flow
def test_a_leak_next_to_a_road_gets_the_line_and_a_closure_plan_in_the_pending_approval(platform, monkeypatch):
    road = wide_road()
    iid, apr = leak(platform, monkeypatch, as_found(road))
    rows = impact_rows(platform, iid)
    assert len(rows) == 1 and rows[0]["Status"] == "Completed" and rows[0]["Recommended"] in ("day", "night")
    n = alert(platform, iid)
    assert "Road impact (modelled):" in n["Message"] and f"Recommended: {rows[0]['Recommended']}." in n["Message"] and n["Status"] == "New"
    trail = [t for t in n["Trail"] if t["agent"] != "faisal"]
    assert n["Approval_ID"] == apr["Approval_ID"] and [t["agent"] for t in trail][-3:] == ["turki", "noura", "turki"]
    assert "Road impact (modelled):" in trail[-2]["did"] and "one approval covers both" in trail[-1]["did"]
    now = platform.store.get(S.APPROVALS, apr["Approval_ID"])["attrs"]
    plan = json.loads(now["Payload"])["closure_plan"]
    assert now["Status"] == "Proposed" and plan["corridor"] == road["corridor"] and plan["lanes_closed"] == 2 and plan["full_closure"] is False
    assert plan["segment_ids"] == [road["id"]] and plan["scenario_id"] == rows[0]["Scenario_ID"] and plan["window"] == rows[0]["Recommended"] and plan["start_time"] < plan["end_time"]
    assert "planned closure" in now["Expected_Result"] and len(platform.store.query(S.APPROVALS, Target=iid)) == 1
    assert platform.store.count(S.CLOSURES) == 0                                           # nothing is recorded before the operator approves
    platform.crew.run_cycle(scope=WATER)
    platform.crew.run_cycle()
    assert len(impact_rows(platform, iid)) == 1 and len(platform.store.query(S.APPROVALS, Target=iid)) == 1


def test_one_approval_creates_the_work_order_and_exactly_one_planned_closure(platform, monkeypatch):
    road = wide_road()
    iid, apr = leak(platform, monkeypatch, as_found(road))
    plan = json.loads(platform.store.get(S.APPROVALS, apr["Approval_ID"])["attrs"]["Payload"])["closure_plan"]
    res = platform.approvals.approve(apr["Approval_ID"], "tester")
    assert res["ok"] and res["closure_id"]
    wo = platform.store.query(S.WORK_ORDERS, Incident_ID=iid)
    cls = platform.store.all(S.CLOSURES)
    assert len(wo) == 1 and len(cls) == 1 and cls[0]["id"] == res["closure_id"]
    c = cls[0]["attrs"]
    assert c["Status"] == "Approved" and c["Reason"] == "Water leak repair" and c["Work_Order_ID"] == wo[0]["id"] and c["Incident_ID"] == iid
    assert c["Corridor"] == road["corridor"] and c["Segment_IDs"] == road["id"] and c["Lanes_Closed"] == 2 and c["Full_Closure"] == "No"
    assert (c["Start_Time"], c["End_Time"], c["Scenario_ID"]) == (plan["start_time"], plan["end_time"], plan["scenario_id"])
    assert cls[0]["geom"]["type"] == "LineString" and cls[0]["geom"]["coordinates"] == road["geometry"]["coordinates"]
    assert "Planned closure: 2 lanes of " + road["corridor"] in wo[0]["attrs"]["Instructions"]
    platform.crew.run_cycle()                                                              # the repair's closure is not a closure request: no mobility incident
    assert not [f for f in platform.store.all(S.INCIDENTS) if f["attrs"]["Category"] == "mobility"]


def test_approving_before_the_impact_arrives_creates_no_closure_and_the_line_is_information_only(platform, monkeypatch):
    held, real = [], platform.jobs.submit
    monkeypatch.setattr(platform.jobs, "submit", lambda *a, **k: held.append((a, k)) or "SCN-held")
    iid, apr = leak(platform, monkeypatch, as_found(wide_road()))
    assert len(held) == 1 and held[0][0][0] == "road_impact" and any("calculating the road impact of the repair" in t["did"] for t in alert(platform, iid)["Trail"])
    assert platform.approvals.approve(apr["Approval_ID"])["ok"]                             # the operator does not wait
    args, kw = held[0]
    real(*args, **kw)                                                                      # now the simulation runs and reports
    n = alert(platform, iid)
    assert "Road impact (modelled):" in n["Message"] and "For information" in n["Trail"][-1]["did"]
    assert platform.store.count(S.CLOSURES) == 0 and len(platform.store.query(S.WORK_ORDERS, Incident_ID=iid)) == 1
    assert "closure_plan" not in json.loads(platform.store.get(S.APPROVALS, apr["Approval_ID"])["attrs"]["Payload"])
    assert "Planned closure" not in platform.store.query(S.WORK_ORDERS, Incident_ID=iid)[0]["attrs"]["Instructions"]


def test_a_leak_away_from_any_road_gets_no_road_impact_step(platform, monkeypatch):
    iid, apr = leak(platform, monkeypatch, None)
    n = alert(platform, iid)
    assert impact_rows(platform, iid) == [] and "Road impact" not in n["Message"] and "noura" not in [t["agent"] for t in n["Trail"]]
    assert "closure_plan" not in json.loads(apr["Payload"])


def test_on_a_two_lane_road_the_whole_road_is_closed_and_the_line_says_so(platform, monkeypatch):
    road = wide_road()
    monkeypatch.setattr(rules, "SMALL_IMPACT_TRIP_HOURS", -1)                              # this test is about the wording of the full sentence
    iid, apr = leak(platform, monkeypatch, as_found(road, lanes=2))
    row = platform.jobs.row(impact_rows(platform, iid)[0]["Scenario_ID"])
    assert row["params"]["lanes_closed"] is None and row["summary"]["full_closure"] is True
    msg = alert(platform, iid)["Message"]
    assert f"closing {road['corridor']} 08:00 to 16:00 adds" in msg and "lanes of" not in msg
    plan = json.loads(platform.store.get(S.APPROVALS, apr["Approval_ID"])["attrs"]["Payload"])["closure_plan"]
    assert plan["full_closure"] is True
    assert platform.approvals.approve(apr["Approval_ID"])["ok"] and platform.store.all(S.CLOSURES)[0]["attrs"]["Full_Closure"] == "Yes"


def test_a_failed_road_impact_run_is_reported_and_the_work_order_proposal_is_left_alone(platform, monkeypatch):
    def boom(params, say):
        raise RuntimeError("the road network could not be loaded")

    monkeypatch.setitem(jobsmod.RUNNERS, "road_impact", boom)
    iid, apr = leak(platform, monkeypatch, as_found(wide_road()))
    n = alert(platform, iid)
    assert "Road impact could not be calculated: the road network could not be loaded." in n["Message"]
    now = platform.store.get(S.APPROVALS, apr["Approval_ID"])["attrs"]
    assert now["Status"] == "Proposed" and "closure_plan" not in json.loads(now["Payload"]) and len(platform.store.query(S.APPROVALS, Target=iid)) == 1
    platform.crew.run_cycle(scope=WATER)
    assert len(impact_rows(platform, iid)) == 1                                            # not tried again by the next scan


def test_a_streetlight_incident_never_starts_a_road_impact_run(platform, monkeypatch):
    monkeypatch.setattr(road_impact, "nearest_road", lambda lonlat, radius_m: as_found(wide_road()))
    platform.crew.inject("streetlight_pole")
    assert platform.store.query(S.APPROVALS, Action_Type="create_work_order") and platform.store.count(S.SCENARIOS) == 0


def test_the_repairs_closure_ends_when_its_incident_is_closed(platform, monkeypatch):
    iid, apr = leak(platform, monkeypatch, as_found(wide_road()))
    cid = platform.approvals.approve(apr["Approval_ID"])["closure_id"]
    platform.store.update(S.INCIDENTS, iid, Status="Repair Reported", Verification_Outcome="Confirmed")
    from backend.workflows import actions

    assert actions.close_incident(platform.store, {"incident_id": iid})["ok"]
    assert platform.store.get(S.CLOSURES, cid)["attrs"]["Status"] == "Ended"
