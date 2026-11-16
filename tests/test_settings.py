"""Configuration rules that keep the Agentic_AI_City hosted layers safe and make ArcGIS Online the system of record."""
import pytest

from backend.gis import schema as S
from backend.gis.store import ArcGISStore, Store, StoreWriteError
from backend.platform import Platform
from config.settings import ConfigError, Settings, load_settings
from tests.fakes import FakeGateway

HOSTED = dict(store="arcgis", arcgis_username="u", arcgis_password="p", field_sync_seconds=0)


def not_the_lock(gw):
    return [w for w in gw.writes if w[2] != "server.lock"]


def test_default_prefix_is_cityview(monkeypatch):
    monkeypatch.delenv("ARCGIS_LAYER_PREFIX", raising=False)
    assert load_settings().arcgis_layer_prefix == "CityView" and Settings().arcgis_layer_prefix == "CityView"


@pytest.mark.parametrize("prefix", ["GeoAIOps", "geoaiops", "GEOAIOPS", " GeoAIOps ", ""])
def test_the_city_projects_prefix_is_refused(monkeypatch, prefix):
    monkeypatch.setenv("ARCGIS_LAYER_PREFIX", prefix)
    with pytest.raises(ConfigError, match="GeoAIOps"):
        load_settings()


def test_a_hand_built_settings_object_with_the_city_prefix_is_refused_too():
    with pytest.raises(ConfigError, match="GeoAIOps"):
        Platform(settings=Settings(**HOSTED, arcgis_layer_prefix="GeoAIOps"), gateway=FakeGateway())


def test_the_app_runs_on_arcgis_online_unless_told_otherwise(monkeypatch):
    monkeypatch.delenv("GEOAI_STORE", raising=False)
    assert load_settings().store == "arcgis"
    monkeypatch.setenv("GEOAI_STORE", "sqlite")
    with pytest.raises(ConfigError, match="GEOAI_STORE"):
        load_settings()


def test_arcgis_mode_without_credentials_does_not_start():
    with pytest.raises(ConfigError, match="ARCGIS_USERNAME"):
        Platform(settings=Settings(store="arcgis", arcgis_username="", arcgis_password=""))


def test_memory_mode_generates_demo_data_on_start():
    p = Platform(settings=Settings(store="memory"))
    assert type(p.store) is Store and p.store.count(S.INFRA) > 0 and p.data_ready


def test_arcgis_mode_never_fills_the_record_by_itself():
    gw = FakeGateway()                                   # the hosted layers exist and are empty
    p = Platform(settings=Settings(**HOSTED), gateway=gw)
    assert isinstance(p.store, ArcGISStore) and p.data_ready is False and not_the_lock(gw) == []


def test_arcgis_mode_starts_on_the_data_the_record_holds_and_writes_nothing():
    gw = FakeGateway()
    first = Platform(settings=Settings(**HOSTED), gateway=gw)
    counts = first.reset()                               # the first fill (scripts/initialize_demo.py --apply)
    incidents = [f["id"] for f in first.store.all(S.INCIDENTS)]
    first.store.release()
    n = len(gw.writes)
    again = Platform(settings=Settings(**HOSTED), gateway=gw)          # a restart
    assert again.data_ready and again.store.count(S.INFRA) == counts[S.INFRA]
    assert [f["id"] for f in again.store.all(S.INCIDENTS)] == incidents
    assert not_the_lock(gw)[n:] == [] or [w for w in gw.writes[n:] if w[2] != "server.lock"] == []


def test_reset_fills_arcgis_online_layer_by_layer_not_row_by_row():
    gw = FakeGateway()
    p = Platform(settings=Settings(**HOSTED), gateway=gw)
    p.reset()
    writes = not_the_lock(gw)
    singles = [w for w in writes if w[0] not in ("truncate", "many")]
    assert len(singles) <= 2, singles                    # the "environment regenerated" event row; never thousands of single edits
    assert len(gw.rows(S.SENSORS)) >= 1000 and len(writes) < 100


def test_a_crew_scan_runs_on_arcgis_online_and_survives_a_restart():
    gw = FakeGateway()
    p = Platform(settings=Settings(**HOSTED), gateway=gw)
    p.reset()
    res = p.crew.inject("olaya_leak")
    assert res["scan"]["new_incidents"]
    iid = res["scan"]["new_incidents"][0]
    p.store.release()
    again = Platform(settings=Settings(**HOSTED), gateway=gw)
    assert again.store.get(S.INCIDENTS, iid) and any(n["Incident_ID"] == iid for n in again.crew.notifications(limit=100))


def test_arcgis_dropping_mid_scan_stops_the_scan_and_the_next_one_runs():
    gw = FakeGateway()
    p = Platform(settings=Settings(**HOSTED), gateway=gw)
    p.reset()
    p.sim.scenario("olaya_leak")
    gw.fail_after(3)
    with pytest.raises(StoreWriteError):
        p.crew.run_cycle()
    gw.fail_after(None)
    assert p.crew.run_cycle()["new_incidents"]           # nothing was half-done in a way that blocks the next scan


def test_a_crew_scan_reaches_arcgis_online_as_one_request_per_layer():
    gw = FakeGateway()
    p = Platform(settings=Settings(**HOSTED), gateway=gw)
    p.reset()
    p.sim.scenario("olaya_leak")
    n = len(gw.writes)
    res = p.crew.run_cycle()
    scan = gw.writes[n:]
    first = next((i for i, w in enumerate(scan) if w[1] == "Riyadh_Mobility_Scenarios"), len(scan))
    batch, after = scan[:first], scan[first:]            # the scan's own batch, then the road-impact run of the repair (a background job writes its own row)
    assert res["new_incidents"] and batch and all(w[0] == "many" for w in batch), batch
    assert len({w[1] for w in batch}) == len(batch)      # each layer once: not one request per row
    assert all(w[1] in ("Riyadh_Mobility_Scenarios", "Riyadh_Approvals", "Riyadh_Notifications", "Riyadh_Agent_Audit_Log", "Riyadh_Mobility_Closures") for w in after), after


def test_a_scan_arcgis_refuses_is_undone_as_a_whole():
    gw = FakeGateway()
    p = Platform(settings=Settings(**HOSTED), gateway=gw)
    p.reset()
    p.sim.scenario("olaya_leak")
    before = (p.store.count(S.INCIDENTS), p.store.count(S.NOTIFICATIONS))
    gw.fail_after(1)                                     # the very first request of the scan's batch is refused
    with pytest.raises(StoreWriteError):
        p.crew.run_cycle()
    gw.fail_after(None)
    assert (p.store.count(S.INCIDENTS), p.store.count(S.NOTIFICATIONS)) == before
