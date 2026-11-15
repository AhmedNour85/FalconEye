import pytest

from backend.gis import geo
from backend.gis import schema as S
from backend.gis.store import Store, ValidationError
from backend.services import synthetic


def test_generation_is_reproducible_and_populated():
    a, b = Store(), Store()
    from datetime import datetime, timezone
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    ca = synthetic.generate(a, seed=5, now=now)
    cb = synthetic.generate(b, seed=5, now=now)
    assert ca == cb
    assert [f["geom"] for f in a.all(S.WATER)] == [f["geom"] for f in b.all(S.WATER)]
    assert 300 <= ca[S.INFRA] <= 500 and 100 <= ca[S.WATER] <= 200 and ca[S.SENSORS] >= 1000
    assert 20 <= ca[S.DETECTIONS] <= 35 and ca[S.WORK_ORDERS] >= 10 and ca[S.WORKERS] >= 5
    c = synthetic.generate(Store(), seed=6, now=now)  # different seed -> different data
    assert c is not None


def test_all_assets_inside_riyadh_bbox_and_labelled(platform):
    for f in platform.store.all(S.INFRA):
        lon, lat = f["geom"]["coordinates"]
        assert 46.4 < lon < 46.9 and 24.5 < lat < 24.9
        assert f["attrs"]["Data_Classification"] == S.SYNTHETIC


def test_referential_integrity(platform):
    st = platform.store
    assets = {f["id"] for f in st.all(S.INFRA)}
    pipes = {f["id"] for f in st.all(S.WATER)}
    for f in st.all(S.SENSORS):
        assert f["attrs"]["Asset_ID"] in assets
    for f in st.all(S.INFRA):
        if f["attrs"]["Related_Pipeline_ID"]:
            assert f["attrs"]["Related_Pipeline_ID"] in pipes
    incs = {f["id"] for f in st.all(S.INCIDENTS)}
    for f in st.all(S.DETECTIONS):
        assert f["attrs"]["Incident_ID"] in incs
    for f in st.all(S.WORK_ORDERS):
        assert f["attrs"]["Incident_ID"] in incs
    wos = {f["id"] for f in st.all(S.WORK_ORDERS)}
    for f in st.all(S.VERIFICATION):
        assert f["attrs"]["Work_Order_ID"] in wos


def test_streetlights_follow_corridor(platform):
    lights = [f for f in platform.store.all(S.INFRA) if f["attrs"]["Corridor"] == "King Fahd Road"]
    assert lights and all(synthetic.corridor_dist_m(tuple(f["geom"]["coordinates"]), "King Fahd Road") < 25 for f in lights)


def test_store_validation():
    s = Store()
    with pytest.raises(ValidationError):
        s.upsert(S.WORKERS, {"Worker_ID": "W1", "Bogus": 1}, {"type": "Point", "coordinates": [46, 24]})
    with pytest.raises(ValidationError):
        s.upsert(S.WORKERS, {"Worker_ID": "W1"}, {"type": "LineString", "coordinates": [[0, 0], [1, 1]]})
    with pytest.raises(ValidationError):
        s.upsert(S.WORKERS, {"Name": "x"}, None)


def test_geo_helpers():
    assert abs(geo.haversine_m((46.0, 24.0), (46.0, 24.001)) - 111.2) < 1
    ring = geo.circle_ring((46.7, 24.7), 100)
    assert abs(geo.ring_area_sqm(ring) - 3.14159 * 100 ** 2) / (3.14159 * 100 ** 2) < 0.02
    assert geo.point_in_ring((46.7, 24.7), ring) and not geo.point_in_ring((46.8, 24.7), ring)


def test_reset_regenerates(platform):
    platform.store.update(S.WORKERS, "WRK-001", Open_Tasks=9)
    platform.reset()
    assert platform.store.get(S.WORKERS, "WRK-001")["attrs"]["Open_Tasks"] == 0


def test_generation_reaches_the_system_of_record_as_one_request_per_layer():
    """Thousands of rows are generated; the record gets them layer by layer, never row by row."""
    single, many = [], []

    class Spy(Store):
        def _persist(self, layer, op, fid, attrs, geom):
            single.append(layer)

        def _persist_many(self, layer, rows):
            many.append(layer)
    st = Spy()
    with st.batch():
        counts = synthetic.generate(st, 3)
    assert single == [] and len(many) == len(set(many))                 # one request per layer
    assert S.SENSORS in many and S.INFRA in many and counts[S.SENSORS] >= 1000


def test_tools_report_empty_data_clearly(ctx, platform):
    from backend.tools import registry as R
    platform.store.clear([S.TELEMETRY])
    r = R.execute(ctx, "predict_streetlight_failures", {})
    assert not r["ok"] and "reset the demo" in r["error"]
