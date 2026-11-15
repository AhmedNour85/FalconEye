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
