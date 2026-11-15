"""The working copy in memory (Store). ArcGIS Online persistence is tested in test_arcgis_store.py."""
import pytest

from backend.gis import geo
from backend.gis import schema as S
from backend.gis.store import Store, StoreWriteError, ValidationError


def worker(wid, **more):
    return {"Worker_ID": wid, **more}


def test_rows_come_back_ordered_by_id():
    s = Store()
    s.upsert(S.WORKERS, worker("WRK-002"))
    s.upsert(S.WORKERS, worker("WRK-001"))
    assert [f["id"] for f in s.all(S.WORKERS)] == ["WRK-001", "WRK-002"]


def test_next_id_counts_up_per_prefix():
    s = Store()
    assert [s.next_id("INC"), s.next_id("INC"), s.next_id("LOG", 6)] == ["INC-0001", "INC-0002", "LOG-000001"]


def test_a_failed_write_changes_nothing():
    class Failing(Store):
        def _persist(self, layer, op, fid, attrs, geom):
            raise StoreWriteError("ArcGIS Online is unreachable", layer=layer, fid=fid)

    s = Failing()
    with pytest.raises(StoreWriteError) as e:
        s.upsert(S.WORKERS, worker("WRK-001"))
    assert s.get(S.WORKERS, "WRK-001") is None
    assert e.value.layer == S.WORKERS and e.value.fid == "WRK-001"


def test_persist_is_called_before_the_copy_changes():
    seen = []

    class Spy(Store):
        def _persist(self, layer, op, fid, attrs, geom):
            seen.append((op, fid, self.get(layer, fid) is None))

    s = Spy()
    s.upsert(S.WORKERS, worker("WRK-001"))
    s.update(S.WORKERS, "WRK-001", Name="Nawaf")
    s.delete(S.WORKERS, "WRK-001")
    assert seen == [("add", "WRK-001", True), ("update", "WRK-001", False), ("delete", "WRK-001", False)]
    assert s.get(S.WORKERS, "WRK-001") is None


def test_persist_false_skips_the_persist_hook_and_the_write_hooks():
    """Rows that came from ArcGIS Online are stored as they are and are not sent back."""
    seen = []

    class Spy(Store):
        def _persist(self, layer, op, fid, attrs, geom):
            seen.append(fid)

    s = Spy()
    s.write_hooks[S.WORKERS] = lambda a: {**a, "Name": "changed by the hook"}
    s.upsert(S.WORKERS, worker("WRK-001", Name="from ArcGIS"), persist=False)
    assert seen == [] and s.get(S.WORKERS, "WRK-001")["attrs"]["Name"] == "from ArcGIS"
    s.upsert(S.WORKERS, worker("WRK-002", Name="local"))
    assert seen == ["WRK-002"] and s.get(S.WORKERS, "WRK-002")["attrs"]["Name"] == "changed by the hook"


def test_batch_sends_one_persist_many_per_layer_and_no_single_persists():
    single, many = [], []

    class Spy(Store):
        def _persist(self, layer, op, fid, attrs, geom):
            single.append(fid)

        def _persist_many(self, layer, rows):
            many.append((layer, [(op, fid) for op, fid, _a, _g in rows]))

    s = Spy()
    with s.batch():
        s.upsert(S.WORKERS, worker("WRK-001"))
        s.upsert(S.WORKERS, worker("WRK-002"))
        s.upsert(S.FACILITIES, {"Facility_ID": "FAC-001"}, geo.point(46.7, 24.7))
        assert s.count(S.WORKERS) == 2                      # readable inside the batch
    assert single == []
    assert dict(many) == {S.WORKERS: [("add", "WRK-001"), ("add", "WRK-002")], S.FACILITIES: [("add", "FAC-001")]} and len(many) == 2


def test_a_batch_that_arcgis_refuses_is_rolled_back():
    class Failing(Store):
        def _persist_many(self, layer, rows):
            raise StoreWriteError("offline", layer=layer)

    s = Failing()
    s.upsert(S.WORKERS, worker("WRK-000", Name="before"), persist=False)
    with pytest.raises(StoreWriteError):
        with s.batch():
            s.upsert(S.WORKERS, worker("WRK-000", Name="changed"))
            s.upsert(S.WORKERS, worker("WRK-001"))
    assert s.get(S.WORKERS, "WRK-000")["attrs"]["Name"] == "before" and s.get(S.WORKERS, "WRK-001") is None


def test_bbox_query_returns_only_rows_in_the_box():
    s = Store()
    s.upsert(S.FACILITIES, {"Facility_ID": "IN"}, geo.point(46.70, 24.70))
    s.upsert(S.FACILITIES, {"Facility_ID": "OUT"}, geo.point(46.90, 24.90))
    assert [f["id"] for f in s.bbox_query(S.FACILITIES, 46.6, 24.6, 46.8, 24.8)] == ["IN"]


def test_rows_handed_out_are_copies():
    s = Store()
    s.upsert(S.WORKERS, worker("WRK-001", Name="Nawaf"))
    s.get(S.WORKERS, "WRK-001")["attrs"]["Name"] = "tampered"
    s.all(S.WORKERS)[0]["attrs"]["Name"] = "tampered"
    assert s.get(S.WORKERS, "WRK-001")["attrs"]["Name"] == "Nawaf"


def test_validation_is_unchanged():
    s = Store()
    with pytest.raises(ValidationError):
        s.upsert("No_Such_Layer", {"x": 1})
    with pytest.raises(ValidationError):
        s.upsert(S.WORKERS, {"Worker_ID": "WRK-001", "Not_A_Field": 1})
    with pytest.raises(ValidationError):
        s.upsert(S.APPROVALS, {"Approval_ID": "APR-0001"}, geo.point(46.7, 24.7))       # a table takes no geometry


def test_clear_removes_rows_and_counters_and_tells_the_persist_hook():
    cleared = []

    class Spy(Store):
        def _persist_clear(self, layers):
            cleared.append(layers)

    s = Spy()
    s.upsert(S.WORKERS, worker("WRK-001"))
    s.next_id("INC")
    s.clear()
    assert s.count(S.WORKERS) == 0 and s.next_id("INC") == "INC-0001" and cleared == [None]
    s.upsert(S.WORKERS, worker("WRK-001"))
    s.clear([S.WORKERS])
    assert s.count(S.WORKERS) == 0 and cleared[-1] == [S.WORKERS]


def test_the_plain_store_is_not_hosted():
    assert Store().is_hosted is False


def test_an_upsert_that_changes_nothing_is_not_sent():
    seen = []

    class Spy(Store):
        def _persist(self, layer, op, fid, attrs, geom):
            seen.append(op)

    s = Spy()
    s.upsert(S.WORKERS, worker("WRK-001", Name="Nawaf"), geo.point(46.7, 24.7))
    s.upsert(S.WORKERS, worker("WRK-001", Name="Nawaf"), geo.point(46.7, 24.7))
    s.update(S.WORKERS, "WRK-001", Name="Nawaf")
    assert seen == ["add"]
    s.update(S.WORKERS, "WRK-001", Name="Khalid")
    assert seen == ["add", "update"]


def test_another_threads_write_waits_for_an_open_batch():
    """A write from another thread must never be swept into someone else's batch, or rolled back with it."""
    import threading
    import time

    s, order, started = Store(), [], threading.Event()

    def other():
        started.set()
        s.upsert(S.WORKERS, worker("WRK-002"))
        order.append("other")

    with s.batch():
        t = threading.Thread(target=other)
        t.start()
        started.wait(2)
        time.sleep(0.2)
        s.upsert(S.WORKERS, worker("WRK-001"))
        order.append("batch")
    t.join(2)
    assert order == ["batch", "other"] and s.count(S.WORKERS) == 2
