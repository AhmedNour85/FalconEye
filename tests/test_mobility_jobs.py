"""The background worker for long simulations (Plan 3, task 3). Skeleton network; nothing contacts ArcGIS Online."""
import json

import pytest

from backend.gis import schema as S
from backend.gis.store import StoreWriteError
from backend.mobility import network_model
from backend.mobility.jobs import Jobs
from backend.platform import Platform
from config.settings import Settings
from tests.fakes import FakeGateway


def wide_segment(corridor="King Fahd Road", lanes=3):
    return next(s for s in network_model.get_model().segments.values() if s["corridor"] == corridor and int(s["lanes"]) >= lanes)


def incident_params():
    s = wide_segment()
    return {"segment_id": s["id"], "corridor": s["corridor"], "lanes_blocked": 2}


def test_jobs_run_inline_for_a_settings_built_by_hand(platform):
    assert platform.jobs.inline is True and Settings().mobility_jobs_inline is True


def test_an_incident_job_ends_completed_with_the_modelled_numbers(platform):
    seen = []
    sid = platform.jobs.submit("incident", incident_params(), "INC-0001", "noura", on_done=seen.append)
    row = platform.store.get(S.SCENARIOS, sid)["attrs"]
    assert sid.startswith("SCN-") and row["Status"] == "Completed" and row["Scenario_Type"] == "incident" and row["Subject_ID"] == "INC-0001"
    assert row["Data_Classification"] == S.MODELLED and row["Network_Fingerprint"] and row["Completed"] and row["Runtime_S"] >= 0
    summary = json.loads(row["Summary"])
    assert isinstance(summary["window_extra_trip_hours"], (int, float)) and summary["lanes_closed"] == 2 and summary["duration_h"] == 2
    assert "worst_hospital_access_delta_min" in summary and "severe_segments" in summary and summary["road"] == "King Fahd Road"
    assert json.loads(row["Params"])["start_time"]                       # the window is fixed when the job is queued, so a re-run gives the same answer
    assert len(seen) == 1 and seen[0]["Status"] == "Completed" and seen[0]["summary"] == summary and seen[0]["Scenario_ID"] == sid
    st = platform.jobs.status(sid)
    assert (st["id"], st["kind"], st["status"], st["progress"], st["error"]) == (sid, "incident", "Completed", 100, "")


def test_a_closure_on_a_road_the_network_does_not_have_ends_failed_with_the_reason(platform):
    seen = []
    sid = platform.jobs.submit("closure", {"corridor": "Nonexistent Avenue"}, "INC-0002", "noura", on_done=seen.append)
    row = platform.store.get(S.SCENARIOS, sid)["attrs"]
    assert row["Status"] == "Failed" and "no road named 'Nonexistent Avenue'" in row["Error"]
    assert seen[0]["Status"] == "Failed" and platform.jobs.status(sid)["error"] == row["Error"] and platform.jobs.preview(sid) is None


def test_the_next_job_still_runs_after_a_failed_one(platform):
    platform.jobs.submit("closure", {"corridor": "Nonexistent Avenue"}, "INC-0002", "noura")
    sid = platform.jobs.submit("incident", incident_params(), "INC-0003", "noura")
    assert platform.jobs.status(sid)["status"] == "Completed"


def test_the_same_subject_is_not_queued_twice(platform):
    jobs = Jobs(platform, inline=False)
    jobs.pause()
    a = jobs.submit("incident", incident_params(), "INC-0001", "noura")
    b = jobs.submit("incident", incident_params(), "INC-0001", "noura")
    c = jobs.submit("incident", incident_params(), "INC-0009", "noura")
    assert a == b and c != a and jobs.status(a)["status"] == "Queued" and jobs.busy() == 2
    assert platform.store.get(S.SCENARIOS, a)["attrs"]["Status"] == "Queued"
    jobs.resume()
    assert jobs.wait(a, 120)["status"] == "Completed" and jobs.wait(c, 120)["status"] == "Completed" and jobs.busy() == 0
    assert jobs.submit("incident", incident_params(), "INC-0001", "noura") != a          # a finished job does not block a new one


def test_a_row_left_running_by_a_stopped_server_is_marked_interrupted(platform):
    platform.store.upsert(S.SCENARIOS, {"Scenario_ID": "SCN-0100", "Scenario_Type": "incident", "Status": "Running", "Subject_ID": "INC-0001"})
    platform.store.upsert(S.SCENARIOS, {"Scenario_ID": "SCN-0101", "Scenario_Type": "closure", "Status": "Queued", "Subject_ID": "INC-0002"})
    platform.store.upsert(S.SCENARIOS, {"Scenario_ID": "SCN-0102", "Scenario_Type": "event", "Status": "Completed", "Subject_ID": "INC-0003"})
    assert platform.jobs.recover() == ["SCN-0100", "SCN-0101"]
    assert [platform.store.get(S.SCENARIOS, i)["attrs"]["Status"] for i in ("SCN-0100", "SCN-0101", "SCN-0102")] == ["Interrupted", "Interrupted", "Completed"]
    assert "stopped" in platform.store.get(S.SCENARIOS, "SCN-0100")["attrs"]["Error"]
    assert platform.jobs.status("SCN-0100")["status"] == "Interrupted" and platform.jobs.recover() == []


def test_a_result_the_system_of_record_refuses_is_reported_as_failed_and_nothing_is_kept():
    gw = FakeGateway()
    p = Platform(settings=Settings(store="arcgis", arcgis_username="u", arcgis_password="p"), gateway=gw, init=False)
    seen = []
    gw.fail_after(2)                      # the row is queued; every write after that is refused
    sid = p.jobs.submit("incident", incident_params(), "INC-0001", "noura", on_done=seen.append)
    gw.fail_after(None)
    assert seen[0]["Status"] == "Failed" and "ArcGIS Online" in seen[0]["Error"]
    assert p.jobs.status(sid)["status"] == "Failed" and p.jobs.preview(sid) is None
    assert gw.rows(S.SCENARIOS)[0]["attrs"]["Status"] == "Queued"        # what ArcGIS Online holds is what the app shows after a restart
    p.store.release()


def test_a_job_arcgis_online_will_not_even_queue_raises_and_leaves_nothing():
    gw = FakeGateway()
    p = Platform(settings=Settings(store="arcgis", arcgis_username="u", arcgis_password="p"), gateway=gw, init=False)
    gw.fail_next = StoreWriteError("offline")
    with pytest.raises(StoreWriteError):
        p.jobs.submit("incident", incident_params(), "INC-0001", "noura")
    assert gw.rows(S.SCENARIOS) == [] and p.jobs.busy() == 0
    p.store.release()


def test_the_map_preview_is_kept_for_a_fresh_run_only(platform):
    sid = platform.jobs.submit("incident", incident_params(), "INC-0001", "noura")
    pv = platform.jobs.preview(sid)
    assert set(pv) == {"closed", "segments", "routes"} and pv["segments"]["type"] == "FeatureCollection" and pv["closed"]["geometry"]
    assert platform.jobs.preview("SCN-9999") is None and platform.jobs.status("SCN-9999") is None


def test_an_event_job_reports_the_added_vehicles_and_an_unknown_venue_is_refused(platform):
    sid = platform.jobs.submit("event", {"place": "KAFD", "attendance": 30000}, "INC-0004", "noura")
    summary = json.loads(platform.store.get(S.SCENARIOS, sid)["attrs"]["Summary"])
    assert summary["added_vehicles_per_hour"] > 0 and summary["attendance"] == 30000 and "parking_deficit_vehicles" in summary and summary["venue"] == "KAFD"
    bad = platform.jobs.submit("event", {"place": "Atlantis", "attendance": 100}, "INC-0005", "noura")
    assert platform.jobs.status(bad)["status"] == "Failed" and "Atlantis" in platform.jobs.status(bad)["error"]


def test_a_closure_job_compares_the_strategies_and_recommends_one(platform):
    sid = platform.jobs.submit("closure", {"corridor": "King Fahd Road"}, "INC-0006", "noura")
    row = platform.store.get(S.SCENARIOS, sid)["attrs"]
    summary = json.loads(row["Summary"])
    assert row["Status"] == "Completed" and row["Recommended"] in {s["id"] for s in summary["strategies"]} and row["Verdict"]
    assert [s["id"] for s in summary["strategies"]] == ["do_nothing", "reschedule", "divert", "demand_shift", "combined"]
    assert summary["assumptions"] and len(row["Summary"]) < 4000 and len(row["Params"]) < 4000
    assert set(platform.jobs.preview(sid)) == {"closed", "segments", "routes"}


def test_a_job_with_missing_inputs_is_refused_before_anything_is_written(platform):
    with pytest.raises(ValueError):
        platform.jobs.submit("incident", {"corridor": "King Fahd Road"}, "INC-0001", "noura")
    with pytest.raises(ValueError):
        platform.jobs.submit("teleport", {}, "INC-0001", "noura")
    assert platform.store.count(S.SCENARIOS) == 0
