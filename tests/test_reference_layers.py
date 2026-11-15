"""The six mobility reference layers in the system of record: static, published by a script, never emptied by a reset."""
import pytest

from backend.gis import schema as S
from backend.gis.agol import definition
from backend.gis.store import ArcGISStore
from backend.mobility import sources, transit
from scripts import initialize_demo, publish_reference_layers as pub
from tests.fakes import FakeGateway

SMALL = [S.METRO_LINES, S.METRO_STATIONS, S.EMERGENCY]
HAS_NETWORK = sources.NETWORK_FILE.exists()


def filled(layers=SMALL) -> FakeGateway:
    gw = FakeGateway()
    assert pub.main(["--apply", *layers], gateway=gw) == 0
    gw.writes.clear()
    gw.requests.clear()
    return gw


# ---- the data model -----------------------------------------------------------------------------
def test_six_layers_are_static_and_carry_a_credit():
    static = [n for n, d in S.LAYERS.items() if d.static]
    assert static == list(transit.STATIC_LAYERS) and len(static) == 6
    assert all(S.LAYERS[n].credit for n in static)
    assert "OpenStreetMap" in S.LAYERS[S.ROADS].credit and "Royal Commission" in S.LAYERS[S.BUS_STOPS].credit


def test_reference_layers_have_no_attachments_and_numbers_are_numbers():
    d = definition(S.LAYERS[S.ROADS])
    types = {f["name"]: f["type"] for f in d["fields"]}
    assert d["hasAttachments"] is False and d["geometryType"] == "esriGeometryPolyline"
    assert types["Lanes"] == types["Speed_Limit"] == types["Length_Km"] == "esriFieldTypeDouble" and types["Segment_ID"] == "esriFieldTypeString"
    assert definition(S.LAYERS[S.INCIDENTS])["hasAttachments"] is True


def test_the_page_layer_list_does_not_include_reference_layers():
    from backend.api.app import PUBLIC_LAYERS
    assert not set(PUBLIC_LAYERS) & set(transit.STATIC_LAYERS)


# ---- the store ----------------------------------------------------------------------------------
def test_reset_demo_leaves_the_reference_layers_alone():
    gw = filled()
    st = ArcGISStore(gw)
    st.upsert(S.CONFIG, {"Config_ID": "x", "Value": "1", "Updated": ""})
    st.clear()                                                # what Reset demo and initialize_demo --apply do first
    assert st.count(S.METRO_STATIONS) == 94 and st.count(S.EMERGENCY) == 13 and st.count(S.METRO_LINES) == 6
    assert len(gw.ids(S.METRO_STATIONS)) == 94
    assert st.get(S.CONFIG, "x") is None
    truncated = {layer for op, layer, _ in gw.writes if op == "truncate"}
    assert truncated and not truncated & set(transit.STATIC_LAYERS)


def test_a_refresh_never_asks_for_a_reference_layer():
    gw = filled()
    st = ArcGISStore(gw)
    gw.requests.clear()
    for _ in range(ArcGISStore.RECONCILE_EVERY * 2):          # includes the refreshes that look for deleted rows
        st.refresh()
    asked = {layer for _method, layer in gw.requests}
    assert S.WORK_ORDERS in asked and not asked & set(transit.STATIC_LAYERS)


def test_reference_layers_are_read_once_at_start_up():
    gw = filled()
    ArcGISStore(gw)
    assert sum(1 for m, layer in gw.requests if m == "rows" and layer == S.METRO_STATIONS) == 1


def test_the_app_starts_without_the_reference_layers():
    gw = FakeGateway()
    gw.missing = set(transit.STATIC_LAYERS)
    st = ArcGISStore(gw)
    assert all(st.count(n) == 0 for n in transit.STATIC_LAYERS)
    assert not {layer for _m, layer in gw.requests} & set(transit.STATIC_LAYERS)
    assert transit.geojson("metro_stations", st)["read_from"] == "files"


def test_the_map_layers_come_from_the_record_when_it_holds_them():
    st = ArcGISStore(filled())
    gj = transit.geojson("metro_stations", st)
    assert gj["read_from"] == "arcgis" and len(gj["features"]) == 94 and gj["features"][0]["properties"]["Station_ID"]
    hosp = transit.geojson("hospitals", st)
    assert hosp["read_from"] == "arcgis" and len(hosp["features"]) == 8      # the 5 emergency stations are in the layer, not in this map layer


def test_the_engine_reads_hospitals_and_stations_from_the_record():
    st = ArcGISStore(filled())
    sources.configure(st, "skeleton")
    try:
        gw_row = st.get(S.EMERGENCY, "HOSP-01")
        st.upsert(S.EMERGENCY, {**gw_row["attrs"], "Name": "Renamed in ArcGIS Online"}, gw_row["geom"])
        assert "Renamed in ArcGIS Online" in [h["name"] for h in sources.list_hospitals()]
        assert len(sources.list_hospitals()) == 8 and len(sources.list_("MetroStation")) == 94
    finally:
        sources.configure(None, "skeleton")


@pytest.mark.skipif(not HAS_NETWORK, reason="data/mobility/network.json.gz not built")
def test_the_hosted_road_layer_gives_the_same_network_as_the_file():
    st = ArcGISStore(filled([S.ROADS]))
    file_rows = sources._from_file()
    sources.configure(st, "auto")
    try:
        roads, nodes, prov = sources.load_network()
        assert prov["source"] == "arcgis" and prov["layer"] == S.ROADS
        assert len(roads) == len(file_rows[0]) > 10000 and len(nodes) == len(file_rows[1])
        assert prov["fingerprint"] == file_rows[2]["fingerprint"]
        one = next(r for r in roads if r["attributes"]["oneway"])
        assert one["capacity"] == one["lanes"] * sources.CAP_PER_LANE[one["road_class"]] and isinstance(one["lanes"], int)
    finally:
        sources.configure(None, "skeleton")


@pytest.mark.skipif(not HAS_NETWORK, reason="data/mobility/network.json.gz not built")
def test_without_the_hosted_road_layer_auto_uses_the_file():
    gw = FakeGateway()
    sources.configure(ArcGISStore(gw), "auto")
    try:
        assert sources.load_network()[2]["source"] == "file"
    finally:
        sources.configure(None, "skeleton")


# ---- the publish script -------------------------------------------------------------------------
def test_publish_dry_run_writes_nothing_and_shows_the_row_counts(capsys):
    gw = FakeGateway()
    assert pub.main([], gateway=gw) == 0
    out = capsys.readouterr().out
    assert gw.writes == [] and "DRY RUN" in out and "Dry run only" in out
    for title, n in (("CityView_Riyadh_Metro_Lines", "6"), ("CityView_Riyadh_Metro_Stations", "94"), ("CityView_Riyadh_Bus_Routes", "117"),
                     ("CityView_Riyadh_Bus_Stops", "3010"), ("CityView_Riyadh_Emergency_Facilities", "13")):
        line = next(ln for ln in out.splitlines() if title in ln)
        assert n in line.split() and "FILL" in line
    assert "0 row(s) to delete" in out


def test_publish_apply_fills_and_reads_back_and_a_second_run_changes_nothing(capsys):
    gw = FakeGateway()
    assert pub.main(["--apply", *SMALL], gateway=gw) == 0
    assert len(gw.ids(S.METRO_STATIONS)) == 94 and "94 of 94 rows" in capsys.readouterr().out
    gw.writes.clear()
    assert pub.main(["--apply", *SMALL], gateway=gw) == 0
    assert gw.writes == [] and "up to date" in capsys.readouterr().out


def test_a_layer_that_differs_is_left_alone_unless_replace_is_given(capsys):
    gw = filled()
    gw.outside_delete(S.METRO_LINES, "Line1")
    gw.outside_edit(S.METRO_LINES, {"Line_ID": "Line9", "Name": "added by hand"})
    assert pub.main(["--apply", S.METRO_LINES], gateway=gw) == 0
    out = capsys.readouterr().out
    assert gw.writes == [] and "DIFFERS" in out and "1 only hosted, 1 only in the files" in out and "left alone without --replace" in out
    assert pub.main(["--apply", "--replace", S.METRO_LINES], gateway=gw) == 0
    assert gw.ids(S.METRO_LINES) == {"Line1", "Line2", "Line3", "Line4", "Line5", "Line6"}
    assert [op for op, _l, _i in gw.writes] == ["truncate", "many"]


def test_replace_in_a_dry_run_says_what_it_would_delete_and_deletes_nothing(capsys):
    gw = filled()
    gw.outside_delete(S.METRO_LINES, "Line1")
    assert pub.main(["--replace", S.METRO_LINES], gateway=gw) == 0
    assert gw.writes == [] and "6 row(s) to add, 5 row(s) to delete" in capsys.readouterr().out


def test_a_missing_layer_is_named_and_the_others_are_still_written(capsys):
    gw = FakeGateway()
    gw.missing = {S.METRO_LINES}
    assert pub.main(["--apply", *SMALL], gateway=gw) == 3
    out = capsys.readouterr().out
    assert "LAYER MISSING" in out and "create_feature_layers.py" in out and len(gw.ids(S.METRO_STATIONS)) == 94


def test_a_failed_write_is_reported_and_the_run_is_not_called_done(capsys):
    gw = FakeGateway()
    gw.fail_after(1)
    assert pub.main(["--apply", *SMALL], gateway=gw) == 3
    out = capsys.readouterr().out
    assert "FAILED" in out and "Done." not in out and "again is safe" in out


def test_a_name_that_is_not_a_reference_layer_is_refused(capsys):
    gw = FakeGateway()
    assert pub.main(["--apply", S.INCIDENTS], gateway=gw) == 2
    assert gw.writes == [] and "Not a reference layer" in capsys.readouterr().out


def test_repeated_ids_in_the_file_rows_are_refused(monkeypatch, capsys):
    gw = FakeGateway()
    real = transit.rows
    monkeypatch.setattr(transit, "rows", lambda layer: real(layer) + real(layer)[:1] if layer == S.METRO_LINES else real(layer))
    assert pub.main(["--apply", S.METRO_LINES], gateway=gw) == 3
    assert gw.writes == [] and "FILE REFUSED" in capsys.readouterr().out


# ---- the demo-data script ------------------------------------------------------------------------
def test_initialize_demo_does_not_count_or_empty_the_reference_layers(capsys):
    gw = filled()
    gw.missing = {S.ROADS, S.BUS_ROUTES, S.BUS_STOPS}
    from config.settings import Settings
    capsys.readouterr()                                       # drop what filling the stand-in printed
    assert initialize_demo.main([], gateway=gw, settings=Settings(store="arcgis", arcgis_username="u", arcgis_password="p")) == 0
    out = capsys.readouterr().out
    assert "Riyadh_Metro_Stations" not in out and "Riyadh_Roads" not in out and "Riyadh_Work_Orders" in out
    assert not set(initialize_demo.planned_counts(1)) & set(transit.STATIC_LAYERS)
