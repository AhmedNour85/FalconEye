"""The eight mobility tools (Plan 3, task 4). Skeleton network, simulations run in the caller's thread."""
import json

from backend.gis import schema as S
from backend.mobility import network_model
from backend.tools import registry as R

PT = {"type": "Point", "coordinates": [46.6753, 24.7136]}


def run(ctx, name, **args):
    return R.execute(ctx, name, args)


def wide_segment(corridor="King Fahd Road", lanes=3):
    return next(s for s in network_model.get_model().segments.values() if s["corridor"] == corridor and int(s["lanes"]) >= lanes)


def add_report(platform, rid="TRF-0001", blocked=2):
    s = wide_segment()
    c = s["geometry"]["coordinates"][0]
    platform.store.upsert(S.TRAFFIC_REPORTS, {"Report_ID": rid, "Report_Type": "Crash", "Segment_ID": s["id"], "Corridor": s["corridor"], "Road_Class": s["road_class"],
                                              "Lanes": int(s["lanes"]), "Lanes_Blocked": blocked, "Reported_At": "2026-11-16T08:00:00Z", "Source": "Road report (SYNTHETIC)",
                                              "Status": "New", "Detection_ID": "", "Description": "Crash blocking lanes", "Data_Classification": S.SYNTHETIC},
                         {"type": "Point", "coordinates": [c[0], c[1]]})
    return s


def mobility_incident(platform, ctx):
    add_report(platform)
    run(ctx, "detect_traffic_incidents")
    return run(ctx, "create_incidents_from_detections")["result"]["created"][0]["incident_id"]


def test_the_eight_tools_are_registered_and_the_slow_one_is_hidden_from_language_models():
    names = {"traffic_state", "detect_traffic_incidents", "simulate_closure", "compare_closure_strategies", "simulate_event", "hospital_access", "road_safety_context",
             "propose_traffic_plan"}
    assert names <= set(R.BY_NAME)
    offered = {s["name"] for s in R.schemas()}
    assert "compare_closure_strategies" not in offered and names - {"compare_closure_strategies"} <= offered
    assert R.BY_NAME["propose_traffic_plan"].consequential and not R.BY_NAME["simulate_closure"].consequential


def test_traffic_state_gives_modelled_totals_and_the_most_loaded_sections(ctx):
    r = run(ctx, "traffic_state", hour=8, top_n=3)["result"]
    assert r["hour"] == 8 and len(r["worst"]) <= 3 and "Modelled" in r["label"] and set(r["counts"]) == {"free", "slow", "heavy", "stopped"}
    assert r["worst"] == sorted(r["worst"], key=lambda x: -x["load"])
    one = run(ctx, "traffic_state", hour=8, corridor="King Fahd Road")["result"]
    assert all(w["road"] == "King Fahd Road" for w in one["worst"])
    assert "no road named 'Atlantis Way'" in run(ctx, "traffic_state", corridor="Atlantis Way")["error"]
    assert "0 to 23" in run(ctx, "traffic_state", hour=30)["error"]


def test_each_road_report_becomes_one_detection_and_is_evaluated_once(ctx, platform):
    s = add_report(platform)
    r = run(ctx, "detect_traffic_incidents")["result"]
    assert (r["reports_evaluated"], r["detected"]) == (1, 1)
    d = platform.store.get(S.DETECTIONS, r["detections"][0]["detection_id"])["attrs"]
    assert d["Category"] == "mobility" and d["Detection_Type"] == "Traffic Incident" and d["Related_Asset_ID"] == "TRF-0001" and d["Area_Name"] == s["corridor"]
    assert d["Status"] == "Suspected" and "SYNTHETIC" in d["Evidence"] and "Modelled load" in d["Evidence"] and 40 <= d["Risk_Score"] <= 95
    rep = platform.store.get(S.TRAFFIC_REPORTS, "TRF-0001")["attrs"]
    assert rep["Status"] == "Detected" and rep["Detection_ID"] == r["detections"][0]["detection_id"]
    again = run(ctx, "detect_traffic_incidents")["result"]
    assert (again["reports_evaluated"], again["detected"]) == (0, 0)
    assert len(platform.store.query(S.DETECTIONS, Category="mobility")) == 1


def test_a_report_is_still_detected_while_the_traffic_model_is_being_built(ctx, platform, monkeypatch):
    from backend.tools import mobility

    monkeypatch.setattr(mobility, "model_ready", lambda *_: False)
    add_report(platform)
    d = run(ctx, "detect_traffic_incidents")["result"]["detections"][0]
    assert d["load_now"] is None and "not known yet" in platform.store.get(S.DETECTIONS, d["detection_id"])["attrs"]["Evidence"]
    assert "still being built" in run(ctx, "traffic_state")["error"] and "still being built" in run(ctx, "hospital_access")["error"]


def test_simulate_closure_stores_a_scenario_and_refuses_zero_lanes_with_the_reason(ctx, platform):
    r = run(ctx, "simulate_closure", corridor="King Fahd Road", lanes_closed=1)["result"]
    row = platform.store.get(S.SCENARIOS, r["scenario_id"])["attrs"]
    assert row["Status"] == "Completed" and row["Scenario_Type"] == "closure_run" and r["summary"]["lanes_closed"] == 1 and "Modelled" in r["label"]
    assert isinstance(r["summary"]["window_extra_trip_hours"], (int, float))
    n = platform.store.count(S.SCENARIOS)
    bad = run(ctx, "simulate_closure", corridor="King Fahd Road", lanes_closed=0)
    assert bad["ok"] is False and "lanes_closed must be 1 or more" in bad["error"] and platform.store.count(S.SCENARIOS) == n
    unknown = run(ctx, "simulate_closure", corridor="Atlantis Way")
    assert unknown["ok"] is False and "no road named 'Atlantis Way'" in unknown["error"]
    assert "missing required parameter 'corridor'" in run(ctx, "simulate_closure")["error"]


def test_compare_closure_strategies_still_runs_through_the_registry(ctx):
    r = run(ctx, "compare_closure_strategies", corridor="King Fahd Road")["result"]
    assert r["recommended"] in {s["id"] for s in r["strategies"]} and len(r["strategies"]) == 5 and r["assumptions"] and r["verdict"]


def test_simulate_event_and_hospital_access(ctx):
    e = run(ctx, "simulate_event", place="KAFD", attendance=30000)["result"]
    assert e["summary"]["added_vehicles_per_hour"] > 0 and e["event"]["venue"] == "KAFD"
    assert "Atlantis" in run(ctx, "simulate_event", place="Atlantis", attendance=10)["error"]
    h = run(ctx, "hospital_access", hour=8)["result"]
    assert h["worst"]["minutes"] >= h["mean_min"] > 0 and h["rows"][0] == h["worst"] and "approximate" in h["label"]


def test_road_safety_context_is_labelled_synthetic(ctx):
    s = wide_segment()
    one = run(ctx, "road_safety_context", segment_id=s["id"])["result"]
    road = run(ctx, "road_safety_context", corridor="King Fahd Road", top_n=3)["result"]
    assert "SYNTHETIC" in one["label"] and one["accidents"]["label"] == one["label"] and len(road["maintenance_priority"]) == 3
    assert all(r["corridor"] == "King Fahd Road" for r in road["maintenance_priority"])
    assert run(ctx, "road_safety_context")["result"]["scope"] == "the whole road network"


def test_a_traffic_plan_is_only_a_proposal_and_needs_a_completed_simulation(ctx, platform):
    iid = mobility_incident(platform, ctx)
    inc = platform.store.get(S.INCIDENTS, iid)["attrs"]
    assert inc["Category"] == "mobility" and inc["Incident_Type"] == "Traffic Incident" and inc["Assigned_Team"] == "Traffic Response"
    early = run(ctx, "propose_traffic_plan", incident_id=iid)
    assert early["ok"] is False and "no completed simulation" in early["error"]
    s = wide_segment()
    platform.jobs.submit("incident", {"segment_id": s["id"], "corridor": s["corridor"], "lanes_blocked": 2}, iid, "noura")
    r = run(ctx, "propose_traffic_plan", incident_id=iid)
    assert r["ok"] and r["result"]["status"] == "AWAITING_APPROVAL" and r["result"]["kind"] == "incident"
    pend = [a for a in platform.approvals.pending() if a["Incident_ID"] == iid]
    assert len(pend) == 1 and pend[0]["Action_Type"] == "apply_traffic_plan" and pend[0]["Team"] == "Traffic Response"
    payload = json.loads(pend[0]["Payload"])
    assert payload["task_type"] == "Confirm the road is clear" and payload["scenario_id"].startswith("SCN-") and "trip-hours" in payload["instructions"]
    assert platform.store.count(S.WORK_ORDERS) == len([w for w in platform.store.all(S.WORK_ORDERS) if w["attrs"]["Incident_ID"] != iid])     # nothing created yet
    run(ctx, "propose_traffic_plan", incident_id=iid)
    assert len([a for a in platform.approvals.pending() if a["Incident_ID"] == iid]) == 1                                                  # asked twice: one proposal


def test_a_traffic_plan_is_refused_for_a_closed_or_a_non_mobility_incident(ctx, platform):
    iid = mobility_incident(platform, ctx)
    platform.store.update(S.INCIDENTS, iid, Status="Resolved")
    assert "is Resolved" in run(ctx, "propose_traffic_plan", incident_id=iid)["error"]
    other = next(f["id"] for f in platform.store.all(S.INCIDENTS) if f["attrs"]["Category"] != "mobility")
    assert "not a mobility incident" in run(ctx, "propose_traffic_plan", incident_id=other)["error"]


def test_every_mobility_tool_call_is_written_to_the_audit_log(ctx, platform):
    run(ctx, "traffic_state", hour=3)
    run(ctx, "road_safety_context")
    names = [a["Tool_Name"] for a in platform.audit.recent(10)]
    assert "traffic_state" in names and "road_safety_context" in names
