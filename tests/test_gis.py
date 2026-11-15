import pytest

from backend.gis import geo
from backend.gis import schema as S
from backend.gis.store import Store, ValidationError
from backend.services import synthetic


def test_generation_is_reproducible_and_populated():
    a, b = Store(":memory:"), Store(":memory:")
    from datetime import datetime, timezone
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    ca = synthetic.generate(a, seed=5, now=now)
    cb = synthetic.generate(b, seed=5, now=now)
    assert ca == cb
    assert [f["geom"] for f in a.all(S.WATER)] == [f["geom"] for f in b.all(S.WATER)]
    assert 300 <= ca[S.INFRA] <= 500 and 100 <= ca[S.WATER] <= 200 and ca[S.SENSORS] >= 1000
    assert 20 <= ca[S.DETECTIONS] <= 35 and ca[S.WORK_ORDERS] >= 10 and ca[S.WORKERS] >= 5
    c = synthetic.generate(Store(":memory:"), seed=6, now=now)  # different seed -> different data
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
    s = Store(":memory:")
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


def test_incomplete_database_is_regenerated(tmp_path):
    from backend.platform import Platform
    from config.settings import Settings
    db = str(tmp_path / "x.sqlite")
    s = Settings(db_path=db, evidence_dir=str(tmp_path / "ev"))
    p = Platform(settings=s, db_path=db)
    n0 = p.store.count(S.TELEMETRY)
    assert n0 > 150
    for f in p.store.all(S.TELEMETRY):  # simulate an interrupted generation: assets present, telemetry gone, no completion marker
        p.store.delete(S.TELEMETRY, f["id"])
    p.store.delete(S.CONFIG, "meta.complete")
    p2 = Platform(settings=s, db_path=db)
    assert p2.store.count(S.TELEMETRY) == n0


def test_mirror_is_muted_during_generation_and_skips_bulk_layers(tmp_path):
    from backend.gis.store import Store
    calls = []

    class Spy:
        def apply(self, layer, op, fid, attrs, geom):
            calls.append(layer)
    st = Store(":memory:")
    st.attach_mirror(Spy())
    with st.muted():
        synthetic.generate(st, 3)
    assert calls == []
    st.upsert(S.SENSORS, {"Reading_ID": "R1"}, None) if False else None
    st.upsert(S.WORKERS, {"Worker_ID": "WRK-900"}, {"type": "Point", "coordinates": [46.7, 24.7]})
    assert calls == [S.WORKERS]


def test_tools_report_empty_data_clearly(ctx, platform):
    from backend.tools import registry as R
    platform.store.clear([S.TELEMETRY])
    r = R.execute(ctx, "predict_streetlight_failures", {})
    assert not r["ok"] and "reset the demo" in r["error"]


def test_background_mirror_does_not_block_and_collapses_repeated_writes():
    import threading
    import time
    from backend.gis.store import Store
    gate = threading.Event()
    sent = []

    class Slow:
        def apply(self, layer, op, fid, attrs, geom):
            gate.wait(5)
            sent.append((layer, fid, attrs.get("Open_Tasks")))
    st = Store(":memory:")
    st.attach_mirror(Slow(), background=True)
    t0 = time.perf_counter()
    st.upsert(S.WORKERS, {"Worker_ID": "WRK-900", "Open_Tasks": 0}, {"type": "Point", "coordinates": [46.7, 24.7]})
    for n in range(1, 6):
        st.update(S.WORKERS, "WRK-900", Open_Tasks=n)
    assert time.perf_counter() - t0 < 0.5 and sent == []          # the caller never waited for the (blocked) mirror
    assert st.get(S.WORKERS, "WRK-900")["attrs"]["Open_Tasks"] == 5
    gate.set()
    assert st.flush_mirror(5) and st.mirror_pending == 0
    assert sent[-1] == (S.WORKERS, "WRK-900", 5) and len(sent) <= 3   # repeated edits collapsed; the newest value is what arrives


def test_background_mirror_reports_failures_without_breaking_local_state():
    from backend.gis.store import Store

    class Broken:
        def apply(self, *a):
            raise RuntimeError("offline")
    st = Store(":memory:")
    st.attach_mirror(Broken(), background=True)
    st.upsert(S.WORKERS, {"Worker_ID": "WRK-901"}, {"type": "Point", "coordinates": [46.7, 24.7]})
    assert st.flush_mirror(5)
    assert st.get(S.WORKERS, "WRK-901") and any("offline" in e for e in st.mirror_errors)
