"""The four mobility layers of Plan 3 in the data model (traffic reports, planned closures, event notices, scenario results)."""
import pytest

from backend.gis import agol
from backend.gis import schema as S
from backend.gis.store import ArcGISStore, Store, StoreWriteError
from tests import fakes
from tests.fakes import FakeGateway

PT = {"type": "Point", "coordinates": [46.7, 24.7]}
LINE = {"type": "LineString", "coordinates": [[46.70, 24.70], [46.71, 24.71]]}


def test_the_four_layers_exist_with_their_id_fields():
    want = {S.TRAFFIC_REPORTS: ("Report_ID", "Point"), S.CLOSURES: ("Closure_ID", "Polyline"),
            S.EVENT_NOTICES: ("Event_ID", "Point"), S.SCENARIOS: ("Scenario_ID", None)}
    for name, (id_field, geom) in want.items():
        d = S.LAYERS[name]
        assert (d.id_field, d.geometry, d.static, d.internal) == (id_field, geom, False, False)
        assert "Data_Classification" in d.fields
    assert S.LAYERS[S.TRAFFIC_REPORTS].name == "Riyadh_Traffic_Incidents"
    assert S.CATEGORY_OF_TYPE["mobility"] == "Mobility"
    assert S.MODELLED == "MODELLED-ESTIMATE"


def test_long_and_numeric_fields_are_declared_the_same_in_the_gateway_and_the_stand_in():
    for f in ("Params", "Segment_IDs", "Verdict", "Summary", "Description"):
        assert f in agol.LONG_TEXT and f in fakes.LONG_TEXT
    for f in ("Lanes_Blocked", "Lanes_Closed", "Attendance", "Runtime_S"):
        assert f in agol.NUMERIC


def test_long_params_are_accepted_and_text_over_the_limit_is_refused_not_cut():
    gw = FakeGateway()
    s = ArcGISStore(gw, lock=False)
    s.upsert(S.SCENARIOS, {"Scenario_ID": "SCN-0001", "Params": "x" * 3000})
    assert len(gw.rows(S.SCENARIOS)[0]["attrs"]["Params"]) == 3000
    with pytest.raises(StoreWriteError):
        s.upsert(S.SCENARIOS, {"Scenario_ID": "SCN-0002", "Params": "x" * 17000})
    assert s.get(S.SCENARIOS, "SCN-0002") is None


def test_a_reset_empties_the_four_layers():
    s = Store()
    s.upsert(S.TRAFFIC_REPORTS, {"Report_ID": "TRF-0001"}, PT)
    s.upsert(S.CLOSURES, {"Closure_ID": "CLS-0001"}, LINE)
    s.upsert(S.EVENT_NOTICES, {"Event_ID": "EVN-0001"}, PT)
    s.upsert(S.SCENARIOS, {"Scenario_ID": "SCN-0001"})
    s.clear(None)
    assert [s.count(n) for n in (S.TRAFFIC_REPORTS, S.CLOSURES, S.EVENT_NOTICES, S.SCENARIOS)] == [0, 0, 0, 0]


def test_scenario_ids_continue_after_a_restart():
    gw = FakeGateway()
    ArcGISStore(gw, lock=False).upsert(S.SCENARIOS, {"Scenario_ID": "SCN-0007"})
    assert ArcGISStore(gw, lock=False).next_id("SCN") == "SCN-0008"
