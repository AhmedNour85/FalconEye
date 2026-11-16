"""The mobility API: reference layers and modelled traffic. Runs on the skeleton network; never contacts ArcGIS Online."""
import pytest
from fastapi.testclient import TestClient

from backend.agent.agent import GeoAIAgent
from backend.api.app import create_app
from backend.mobility import network_model, sources, traffic, transit


@pytest.fixture()
def client(platform):
    return TestClient(create_app(platform, GeoAIAgent(platform)))


@pytest.fixture()
def ready(client):
    traffic.warm(wait=True)
    return client


def test_the_test_platform_runs_on_the_skeleton_and_does_not_build_at_start_up(platform):
    assert platform.settings.mobility_network == "skeleton" and platform.settings.mobility_warm is False
    assert sources.load_network()[2]["source"] == "skeleton"


def test_status_is_ready_once_the_24_hours_are_built(ready):
    st = ready.get("/api/mobility/status").json()
    assert st["ready"] is True and st["hours_ready"] == list(range(24)) and st["segments"] == 73
    assert st["network"]["source"] == "skeleton" and st["error"] is None
    assert "Modelled" in st["labels"]["traffic"] and "RCRC" in st["labels"]["transit"]


def test_the_morning_peak_is_more_congested_than_the_night(ready):
    peak, night = ready.get("/api/mobility/traffic?hour=8").json(), ready.get("/api/mobility/traffic?hour=3").json()
    assert peak["modelled"] is True and peak["hour"] == 8 and peak["default_class"] == "free"
    assert len(peak["segments"]) > len(night["segments"])
    assert peak["totals"]["vehicle_hours"] > night["totals"]["vehicle_hours"]
    counted = sum(peak["counts"].values())   # two skeleton segments join the same two junctions, and the model keeps one of them
    assert 70 <= counted <= 73 and peak["counts"]["free"] == counted - len(peak["segments"])
    for vc, cls in peak["segments"].values():
        assert cls in ("slow", "heavy", "stopped") and vc >= 0.6


@pytest.mark.parametrize("hour", ["24", "-1", "x", "8.5", ""])
def test_an_hour_outside_0_to_23_is_refused(ready, hour):
    assert ready.get(f"/api/mobility/traffic?hour={hour}").status_code == 422


def test_the_hour_is_required(ready):
    assert ready.get("/api/mobility/traffic").status_code == 422


def test_asking_before_the_model_is_built_answers_not_ready_with_progress(client, monkeypatch):
    network_model.invalidate()
    started = []
    monkeypatch.setattr(traffic, "warm", lambda wait=False: started.append(1))   # the build is asked for, and here never finishes
    for url in ("/api/mobility/traffic?hour=8", "/api/mobility/roads"):
        r = client.get(url)
        assert r.status_code == 503 and r.headers["retry-after"] == "3"
        body = r.json()
        assert body["ready"] is False and body["hours_ready"] == [] and body["hours_total"] == 24 and "still being built" in body["detail"]
    assert len(started) == 2
    assert client.get("/api/mobility/status").json()["ready"] is False


def test_a_build_that_failed_is_reported_not_retried_forever(client, monkeypatch):
    network_model.invalidate()
    monkeypatch.setattr(traffic, "warm", lambda wait=False: None)
    monkeypatch.setitem(traffic._s, "error", "RuntimeError: no roads")
    r = client.get("/api/mobility/traffic?hour=8")
    assert r.status_code == 500 and "no roads" in r.json()["detail"]


def test_roads_are_the_segments_the_model_runs_on(ready):
    gj = ready.get("/api/mobility/roads").json()
    assert gj["type"] == "FeatureCollection" and len(gj["features"]) == 73
    ids = {f["id"] for f in gj["features"]}
    assert set(ready.get("/api/mobility/traffic?hour=17").json()["segments"]) <= ids
    f = gj["features"][0]
    assert set(f["properties"]) == {"id", "name", "corridor", "road_class", "lanes"} and f["geometry"]["type"] == "LineString"


@pytest.mark.parametrize("kind,count,geom", [("metro_lines", 6, "LineString"), ("metro_stations", 94, "Point"), ("bus_routes", 117, "LineString"),
                                             ("bus_stops", 3010, "Point"), ("hospitals", 8, "Point")])
def test_each_reference_layer_is_geojson_with_its_source(client, kind, count, geom):
    gj = client.get(f"/api/mobility/layers/{kind}").json()
    assert gj["type"] == "FeatureCollection" and len(gj["features"]) == count
    assert gj["source"] and gj["licence"] and gj["credit"] and gj["read_from"] == "files"
    assert all(f["geometry"]["type"] == geom for f in gj["features"])
    assert len({f["id"] for f in gj["features"]}) == count


def test_metro_and_bus_carry_the_rcrc_credit_and_hospitals_say_approximate(client):
    assert "Royal Commission for Riyadh City" in client.get("/api/mobility/layers/metro_lines").json()["credit"]
    assert "pproximate" in client.get("/api/mobility/layers/hospitals").json()["credit"]


def test_an_unknown_reference_layer_is_404(client):
    assert client.get("/api/mobility/layers/tram").status_code == 404
    assert client.get("/api/mobility/layers/roads").status_code == 404   # roads come from /api/mobility/roads


def test_the_large_layers_are_sent_compressed(client):
    r = client.get("/api/mobility/layers/bus_stops", headers={"Accept-Encoding": "gzip"})
    assert r.headers.get("content-encoding") == "gzip"


def test_arabic_does_not_change_ids_or_numbers(ready):
    en, ar = ready.get("/api/mobility/traffic?hour=8").json(), ready.get("/api/mobility/traffic?hour=8&lang=ar").json()
    assert en["segments"] == ar["segments"] and en["totals"] == ar["totals"]


def test_file_rows_have_the_fields_the_hosted_layers_will_have():
    for layer in transit.STATIC_LAYERS:
        rows = transit.rows(layer)
        if layer == transit.ROADS and not rows:
            continue   # network file not built
        attrs, geom = rows[0]
        assert attrs["Data_Classification"] and geom["type"] in ("Point", "LineString")
        assert all(v is not None for k, v in attrs.items() if k != "Beds")


def test_traffic_state_refuses_a_bad_hour_directly():
    for bad in (24, -1, 8.0, "8", True):
        with pytest.raises(ValueError):
            traffic.state(bad)


# ---------------------------------------------------------------- Plan 3, task 9: closures, simulation results and map drawings
def _closure(platform, cid, status, lanes=1):
    from backend.gis import schema as S
    platform.store.upsert(S.CLOSURES, {"Closure_ID": cid, "Corridor": "King Fahd Road", "Section": "King Fahd Road", "Segment_IDs": "X", "Lanes_Closed": lanes, "Full_Closure": "No",
                                       "Start_Time": "2099-11-17T08:00:00Z", "End_Time": "2099-11-17T16:00:00Z", "Reason": "Water leak repair", "Status": status,
                                       "Incident_ID": "INC-0001", "Data_Classification": S.OPERATIONAL}, {"type": "LineString", "coordinates": [[46.67, 24.70], [46.68, 24.71]]})


def test_the_closures_route_returns_only_closures_that_matter(client, platform):
    for cid, st in (("CLS-0001", "Requested"), ("CLS-0002", "Approved"), ("CLS-0003", "In Place"), ("CLS-0004", "Ended"), ("CLS-0005", "Rejected")):
        _closure(platform, cid, st)
    gj = client.get("/api/mobility/closures").json()
    assert gj["type"] == "FeatureCollection"
    assert sorted(f["id"] for f in gj["features"]) == ["CLS-0001", "CLS-0002", "CLS-0003"]
    p = next(f for f in gj["features"] if f["id"] == "CLS-0002")["properties"]
    assert p["road"] == "King Fahd Road" and p["lanes_closed"] == 1 and p["status"] == "Approved" and p["incident_id"] == "INC-0001" and p["start_time"] and p["end_time"]
    assert next(f for f in gj["features"] if f["id"] == "CLS-0002")["geometry"]["type"] == "LineString"


def _scenario(platform):
    from backend.mobility import network_model
    s = next(x for x in network_model.get_model().segments.values() if x["corridor"] == "King Fahd Road" and int(x["lanes"]) >= 3)
    return platform.jobs.submit("incident", {"segment_id": s["id"], "corridor": s["corridor"], "lanes_blocked": 2}, "INC-0001", "noura")


def test_a_scenario_route_gives_the_stored_row_and_404_for_an_unknown_one(client, platform):
    sid = _scenario(platform)
    r = client.get(f"/api/mobility/scenarios/{sid}").json()
    assert r["Scenario_ID"] == sid and r["Status"] == "Completed" and isinstance(r["summary"], dict) and r["summary"]["lanes_closed"] == 2
    assert r["job"]["status"] == "Completed"
    assert client.get("/api/mobility/scenarios/SCN-9999").status_code == 404


def test_the_map_route_waits_while_the_drawing_is_recalculated_and_404s_for_an_unknown_scenario(client, platform, monkeypatch):
    sid = _scenario(platform)
    first = client.get(f"/api/mobility/scenarios/{sid}/map")
    assert first.status_code == 200 and set(first.json()) == {"closed", "segments", "routes"}
    real = platform.jobs.request_preview
    calls = []                                                           # the preview is no longer held: the first ask starts the recalculation and gets "not yet"
    monkeypatch.setattr(platform.jobs, "request_preview", lambda i: None if not calls.append(1) and len(calls) == 1 else real(i))
    wait = client.get(f"/api/mobility/scenarios/{sid}/map")
    assert wait.status_code == 503 and wait.headers["Retry-After"] == "3" and wait.json()["ready"] is False
    assert client.get(f"/api/mobility/scenarios/{sid}/map").status_code == 200
    assert client.get("/api/mobility/scenarios/SCN-9999/map").status_code == 404


def test_a_scenario_that_did_not_complete_has_no_drawing(client, platform):
    from backend.gis import schema as S
    platform.store.upsert(S.SCENARIOS, {"Scenario_ID": "SCN-0200", "Scenario_Type": "incident", "Status": "Failed", "Subject_ID": "INC-0001", "Error": "x"})
    r = client.get("/api/mobility/scenarios/SCN-0200/map")
    assert r.status_code == 409 and "no result" in r.json()["detail"]


def test_a_notification_about_a_simulated_incident_carries_the_scenario(client, platform):
    client.post("/api/nccc/events/traffic_incident")
    rows = client.get("/api/nccc/state").json()["notifications"]
    n = next(x for x in rows if x["Incident_ID"] and x["scenario_id"])
    assert n["scenario_id"].startswith("SCN-") and n["scenario_status"] == "Completed"
    assert all("scenario_id" in x and "scenario_status" in x for x in rows)
    assert any(x["scenario_id"] == "" for x in rows) or len(rows) == 1


# ---- Plan 5, Task 2: the strategy comparison table ----
def _closure_scenario(platform):
    return platform.jobs.submit("closure", {"corridor": "King Fahd Road"}, "INC-0006", "noura")


def test_the_strategies_route_lists_every_strategy_with_one_recommended(client, platform):
    sid = _closure_scenario(platform)
    r = client.get(f"/api/mobility/scenarios/{sid}/strategies")
    assert r.status_code == 200
    d = r.json()
    assert d["scenario_id"] == sid and d["label"] == "Modelled" and d["assumptions"] and d["verdict"]
    rows = d["strategies"]
    assert len(rows) == 5 and [x["id"] for x in rows].count(d["recommended"]) == 1 and sum(x["recommended"] for x in rows) == 1
    assert next(x for x in rows if x["id"] == "do_nothing")["name"] == "Do nothing"
    assert all({"id", "name", "effort", "skipped", "recommended"} <= set(x) for x in rows)
    assert all("extra_trip_hours" in x and "rank" in x for x in rows if not x["skipped"])


def test_the_strategies_route_404s_unknown_and_409s_when_there_is_no_comparison(client, platform):
    assert client.get("/api/mobility/scenarios/SCN-9999/strategies").status_code == 404
    failed = platform.jobs.submit("closure", {"corridor": "Nonexistent Avenue"}, "INC-0002", "noura")
    assert client.get(f"/api/mobility/scenarios/{failed}/strategies").status_code == 409
    one = _scenario(platform)                                                           # an incident simulation has no strategies to compare
    assert client.get(f"/api/mobility/scenarios/{one}/strategies").status_code == 409


def test_the_strategies_route_answers_in_arabic_when_asked(client, platform):
    import re
    sid = _closure_scenario(platform)
    d = client.get(f"/api/mobility/scenarios/{sid}/strategies?lang=ar").json()
    arabic = re.compile(r"[؀-ۿ]")
    assert all(arabic.search(x["strategy_name"]) for x in d["strategies"]) and arabic.search(d["verdict"])
    assert d["assumptions"] and all(arabic.search(a) for a in d["assumptions"]), d["assumptions"]
    assert d["recommended"] == client.get(f"/api/mobility/scenarios/{sid}/strategies").json()["recommended"]          # codes never change
