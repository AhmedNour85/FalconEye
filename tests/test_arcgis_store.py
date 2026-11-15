"""ArcGIS Online as the system of record: ArcGISStore over a stand-in gateway (no test contacts the account)."""
import json

import pytest

from backend.gis import schema as S
from backend.gis.store import ArcGISStore, StoreLockedError, StoreWriteError
from tests.fakes import FakeGateway

PT = {"type": "Point", "coordinates": [46.7, 24.7]}


def store(gw=None, **kw):
    kw.setdefault("lock", False)
    return ArcGISStore(gw or FakeGateway(), **kw)


def test_the_arcgis_store_is_hosted():
    assert store().is_hosted is True


def test_a_write_goes_to_arcgis_online_and_restart_reloads_the_same_data():
    gw = FakeGateway()
    a = store(gw)
    a.upsert(S.WORKERS, {"Worker_ID": "WRK-001", "Name": "Nawaf"}, PT)
    a.update(S.WORKERS, "WRK-001", Open_Tasks=2)
    assert gw.writes == [("add", S.WORKERS, "WRK-001"), ("update", S.WORKERS, "WRK-001")]
    b = store(gw)                                                    # a new process: nothing but what ArcGIS Online holds
    assert b.get(S.WORKERS, "WRK-001") == {"id": "WRK-001", "attrs": {"Worker_ID": "WRK-001", "Name": "Nawaf", "Open_Tasks": 2}, "geom": PT}


def test_a_write_arcgis_refuses_leaves_the_copy_unchanged():
    gw = FakeGateway()
    s = store(gw)
    gw.fail_next = StoreWriteError("offline")
    with pytest.raises(StoreWriteError):
        s.upsert(S.WORKERS, {"Worker_ID": "WRK-001"}, PT)
    assert s.get(S.WORKERS, "WRK-001") is None and gw.rows(S.WORKERS) == []


def test_any_gateway_failure_becomes_a_store_write_error_that_names_the_row():
    gw = FakeGateway()
    s = store(gw)
    gw.fail_next = ConnectionError("getaddrinfo failed")
    with pytest.raises(StoreWriteError, match="ArcGIS Online did not accept the change") as e:
        s.upsert(S.WORKERS, {"Worker_ID": "WRK-001"}, PT)
    assert e.value.layer == S.WORKERS and e.value.fid == "WRK-001"


def test_text_longer_than_the_field_is_refused_not_cut():
    s = store()
    with pytest.raises(StoreWriteError, match="Trail.*4000"):
        s.upsert(S.NOTIFICATIONS, {"Notif_ID": "NTF-0001", "Trail": "x" * 4001})
    assert s.get(S.NOTIFICATIONS, "NTF-0001") is None


def test_an_outside_edit_shows_after_refresh():
    gw = FakeGateway()
    s = store(gw)
    s.upsert(S.WORK_ORDERS, {"Work_Order_ID": "WO-0001", "Status": "Assigned"}, PT)
    assert s.refresh() == {}                                         # our own write is not news
    gw.outside_edit(S.WORK_ORDERS, {"Work_Order_ID": "WO-0001", "Field_Verdict": "Confirmed"})
    assert s.refresh() == {S.WORK_ORDERS: ["WO-0001"]}
    assert s.get(S.WORK_ORDERS, "WO-0001")["attrs"]["Field_Verdict"] == "Confirmed"
    assert gw.writes[-1][0] == "add"                                 # the refresh wrote nothing back


def test_a_row_added_outside_shows_after_refresh():
    gw = FakeGateway()
    s = store(gw)
    gw.outside_edit(S.FACILITIES, {"Facility_ID": "FAC-900", "Name": "Added in Map Viewer"}, PT)
    assert s.refresh() == {S.FACILITIES: ["FAC-900"]} and s.get(S.FACILITIES, "FAC-900")["geom"] == PT


def test_a_field_maps_report_without_an_id_gets_one_and_it_is_written_back():
    gw = FakeGateway()
    s = store(gw)
    gw.outside_edit(S.VERIFICATION, {"Verification_ID": "", "Work_Order_ID": "WO-0001", "Verification_Status": "Confirmed"}, PT)
    assert s.refresh() == {S.VERIFICATION: ["VER-0001"]}
    assert [r["attrs"]["Verification_ID"] for r in gw.rows(S.VERIFICATION)] == ["VER-0001"]


def test_an_outside_delete_leaves_the_copy_within_four_refreshes():
    gw = FakeGateway()
    s = store(gw)
    s.upsert(S.WORKERS, {"Worker_ID": "WRK-001"}, PT)
    gw.outside_delete(S.WORKERS, "WRK-001")
    seen = [s.refresh() for _ in range(4)]
    assert s.get(S.WORKERS, "WRK-001") is None and {S.WORKERS: ["WRK-001"]} in seen


def test_ids_continue_after_a_restart():
    gw = FakeGateway()
    a = store(gw)
    for _ in range(7):
        a.upsert(S.INCIDENTS, {"Incident_ID": a.next_id("INC")}, PT)
    assert store(gw).next_id("INC") == "INC-0008"


def test_the_audit_log_loads_seven_days_but_its_counter_uses_the_highest_id():
    gw = FakeGateway()
    gw.outside_edit(S.AUDIT, {"Log_ID": "LOG-000041", "Timestamp": "2020-01-01T00:00:00Z"})
    gw.outside_edit(S.AUDIT, {"Log_ID": "LOG-000042", "Timestamp": "2099-01-01T00:00:00Z"})
    s = store(gw)
    assert [f["id"] for f in s.all(S.AUDIT)] == ["LOG-000042"] and s.next_id("LOG", 6) == "LOG-000043"


def test_a_layer_with_more_than_one_page_loads_completely():
    gw = FakeGateway(page_size=2000)
    for n in range(2800):
        gw.outside_edit(S.SENSORS, {"Reading_ID": f"R-{n:05d}"}, PT)
    assert store(gw).count(S.SENSORS) == 2800


def test_a_batch_is_one_request_per_layer_and_keeps_the_row_numbers():
    gw = FakeGateway()
    s = store(gw)
    with s.batch():
        s.upsert(S.WORKERS, {"Worker_ID": "WRK-001"}, PT)
        s.upsert(S.WORKERS, {"Worker_ID": "WRK-002"}, PT)
    assert gw.writes == [("many", S.WORKERS, "2+0-0")]
    s.update(S.WORKERS, "WRK-002", Name="Khalid")                     # needs the row number the batch add returned
    assert store(gw).get(S.WORKERS, "WRK-002")["attrs"]["Name"] == "Khalid"


def test_a_refused_batch_reloads_the_layers_from_arcgis_online():
    gw = FakeGateway()
    s = store(gw)
    s.upsert(S.WORKERS, {"Worker_ID": "WRK-001", "Name": "before"}, PT)
    gw.fail_next = StoreWriteError("offline")
    with pytest.raises(StoreWriteError):
        with s.batch():
            s.update(S.WORKERS, "WRK-001", Name="changed")
    assert s.get(S.WORKERS, "WRK-001")["attrs"]["Name"] == "before"
    s.update(S.WORKERS, "WRK-001", Name="after")                      # the store still works
    assert store(gw).get(S.WORKERS, "WRK-001")["attrs"]["Name"] == "after"


def test_clear_empties_the_hosted_layers():
    gw = FakeGateway()
    s = store(gw)
    s.upsert(S.WORKERS, {"Worker_ID": "WRK-001"}, PT)
    s.clear([S.WORKERS])
    assert gw.rows(S.WORKERS) == [] and ("truncate", S.WORKERS, "") in gw.writes


def test_a_second_server_refuses_to_start():
    gw = FakeGateway()
    first = ArcGISStore(gw)
    with pytest.raises(StoreLockedError, match="already running"):
        ArcGISStore(gw)
    first.release()
    ArcGISStore(gw)                                                   # after a clean stop the next one starts


def test_a_stale_lock_does_not_block_start_up():
    gw = FakeGateway()
    gw.outside_edit(S.CONFIG, {"Config_ID": "server.lock", "Value": json.dumps({"owner": "old-host:1:abc", "heartbeat": 0})})
    ArcGISStore(gw)


def test_a_photo_is_kept_as_an_attachment():
    gw = FakeGateway()
    s = store(gw)
    s.upsert(S.VERIFICATION, {"Verification_ID": "VER-0001"}, PT)
    s.add_attachment(S.VERIFICATION, "VER-0001", "leak.jpg", b"\xff\xd8jpeg")
    assert gw.attachments[(S.VERIFICATION, "VER-0001")] == {"leak.jpg": b"\xff\xd8jpeg"}
    assert store(gw).attachment(S.VERIFICATION, "VER-0001", "leak.jpg") == b"\xff\xd8jpeg"


def test_a_lock_left_by_a_killed_server_on_this_computer_is_taken_over_at_once():
    import socket
    import time
    gw = FakeGateway()
    dead = f"{socket.gethostname()}:999999:abc123"          # no such process
    gw.outside_edit(S.CONFIG, {"Config_ID": "server.lock", "Value": json.dumps({"owner": dead, "heartbeat": time.time()})})
    ArcGISStore(gw)


def test_a_live_server_on_this_computer_still_blocks_a_second_one():
    import os
    import socket
    import time
    gw = FakeGateway()
    alive = f"{socket.gethostname()}:{os.getpid()}:other1"   # this very process: certainly running
    gw.outside_edit(S.CONFIG, {"Config_ID": "server.lock", "Value": json.dumps({"owner": alive, "heartbeat": time.time()})})
    with pytest.raises(StoreLockedError, match="already running"):
        ArcGISStore(gw)


def test_a_fresh_lock_from_another_computer_blocks_and_an_old_one_does_not():
    import time
    gw = FakeGateway()
    gw.outside_edit(S.CONFIG, {"Config_ID": "server.lock", "Value": json.dumps({"owner": "another-host:4321:zzz", "heartbeat": time.time() - 100})})
    with pytest.raises(StoreLockedError):
        ArcGISStore(gw)                                      # 100 s old: the heartbeat comes about every 60 s, so the server may well be alive
    gw.outside_edit(S.CONFIG, {"Config_ID": "server.lock", "Value": json.dumps({"owner": "another-host:4321:zzz", "heartbeat": time.time() - 200})})
    ArcGISStore(gw)
