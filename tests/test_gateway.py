"""ArcGISGateway against stand-ins for the ArcGIS API for Python objects. No test contacts ArcGIS Online."""
from types import SimpleNamespace

import pytest

from backend.gis import schema as S
from backend.gis.agol import ArcGISGateway, definition
from backend.gis.store import StoreWriteError
from config.settings import ConfigError, Settings

PT = {"type": "Point", "coordinates": [46.7, 24.7]}


class FakeLayer:
    """Mimics arcgis.features.FeatureLayer: properties.fields, query, edit_features, delete_features, manager."""

    def __init__(self, layer, tracked=True, long=4000):
        d = S.LAYERS[layer]
        fields = [{"name": "OBJECTID", "type": "esriFieldTypeOID"}]
        fields += [{"name": f, "type": "esriFieldTypeString", "length": long if f in ("Trail", "Payload", "Observation") else 255} for f in d.fields]
        if tracked:
            fields.append({"name": "EditDate", "type": "esriFieldTypeDate"})
        self.properties = SimpleNamespace(fields=fields)
        self.features: list[dict] = []          # {"attributes": {...}, "geometry": {...}}
        self.queries: list[dict] = []
        self.edits: list[dict] = []
        self.reject = False
        self.offline = False
        self.reported_count = None
        self.definitions: list[dict] = []
        self.manager = SimpleNamespace(add_to_definition=self.definitions.append, update_definition=self.definitions.append)
        self._oid = 0

    def query(self, **kw):
        if kw.get("return_count_only"):
            return self.reported_count if self.reported_count is not None else len(self.features)
        self.queries.append(kw)
        return SimpleNamespace(features=[SimpleNamespace(attributes=dict(f["attributes"]), geometry=f.get("geometry")) for f in self.features])

    def edit_features(self, adds=None, updates=None, deletes=None):
        if self.offline:
            raise ConnectionError("getaddrinfo failed")
        self.edits.append({"adds": adds, "updates": updates, "deletes": deletes})
        res = {"addResults": [], "updateResults": [], "deleteResults": []}
        for f in adds or []:
            self._oid += 1
            if not self.reject:
                self.features.append({"attributes": {**f["attributes"], "OBJECTID": self._oid}, "geometry": f.get("geometry")})
            res["addResults"].append({"objectId": self._oid, "success": not self.reject, "error": {"description": "rejected by a field domain"} if self.reject else None})
        for f in updates or []:
            res["updateResults"].append({"objectId": f["attributes"]["OBJECTID"], "success": not self.reject})
        return res

    def delete_features(self, where=None):
        self.edits.append({"delete_where": where})
        self.features = []


class FakeGIS:
    def __init__(self, username="city.owner"):
        self.properties = SimpleNamespace(user=SimpleNamespace(username=username))
        self.items: list = []
        self.searches: list[str] = []
        self.created: list[str] = []
        self.content = SimpleNamespace(search=self._search, create_service=self._create)

    def add_item(self, title, owner, layer=None):
        fl = FakeLayer(layer) if layer else None
        item = SimpleNamespace(title=title, owner=owner, id=f"item-{len(self.items)}", layers=[fl] if fl else [], tables=[], fl=fl)
        self.items.append(item)
        return item

    def _search(self, query, max_items=10):
        self.searches.append(query)
        return [i for i in self.items if f'"{i.title}"' in query]

    def _create(self, title, **kw):
        self.created.append(title)
        return self.add_item(title, self.properties.user.username)


def gateway(gis=None, **settings):
    return ArcGISGateway(Settings(**settings), gis=gis or FakeGIS())


def with_layer(layer, **kw):
    gis = FakeGIS()
    item = gis.add_item(f"CityView_{layer}", "city.owner", layer)
    if kw:
        item.fl.__init__(layer, **kw)
        item.layers = [item.fl]
    return gateway(gis), item.fl


def test_the_gateway_refuses_the_city_projects_prefix():
    with pytest.raises(ConfigError, match="GeoAIOps"):
        gateway(arcgis_layer_prefix="GeoAIOps")


def test_titles_carry_the_cityview_prefix():
    assert gateway().title(S.WORK_ORDERS) == "CityView_Riyadh_Work_Orders"


def test_only_items_owned_by_the_signed_in_account_are_used():
    gis = FakeGIS()
    gis.add_item("CityView_Riyadh_Field_Workers", "someone.else", S.WORKERS)      # same title, another owner
    gw = gateway(gis)
    with pytest.raises(RuntimeError, match="not found"):
        gw.layer(S.WORKERS)
    assert "owner:city.owner" in gis.searches[-1] and 'title:"CityView_Riyadh_Field_Workers"' in gis.searches[-1]


def test_rows_keep_only_the_data_model_fields_and_turn_null_text_into_empty_text():
    gw, fl = with_layer(S.WORKERS)
    fl.features = [{"attributes": {"OBJECTID": 7, "Worker_ID": "WRK-001", "Name": None, "Open_Tasks": None, "EditDate": 1700000000000, "Creator": "x"},
                    "geometry": {"x": 46.7, "y": 24.7}}]
    assert gw.rows(S.WORKERS) == [{"id": "WRK-001", "attrs": {"Worker_ID": "WRK-001", "Name": "", "Open_Tasks": None}, "geom": PT, "oid": 7, "edited_ms": 1700000000000}]


def test_rows_since_asks_only_for_rows_edited_after_that_time():
    gw, fl = with_layer(S.WORKERS)
    gw.rows(S.WORKERS, since_ms=1700000000000)
    assert fl.queries[-1]["where"] == "EditDate > timestamp '2023-11-14 22:13:20'"


def test_a_layer_without_edit_tracking_is_read_in_full():
    gw, fl = with_layer(S.WORKERS, tracked=False)
    gw.rows(S.WORKERS, since_ms=1700000000000)
    assert fl.queries[-1]["where"] == "1=1" and gw.tracks_edits(S.WORKERS) is False


def test_the_audit_log_can_be_read_from_a_date():
    gw, fl = with_layer(S.AUDIT)
    gw.rows(S.AUDIT, newer_than=("Timestamp", "2026-11-08T00:00:00Z"))
    assert fl.queries[-1]["where"] == "Timestamp >= '2026-11-08T00:00:00Z'"


def test_add_returns_the_row_number_and_sends_esri_geometry():
    gw, fl = with_layer(S.WORKERS)
    assert gw.add(S.WORKERS, {"Worker_ID": "WRK-001", "Name": "Nawaf", "Not_In_The_Hosted_Layer": 1}, PT) == 1
    sent = fl.edits[-1]["adds"][0]
    assert sent["attributes"] == {"Worker_ID": "WRK-001", "Name": "Nawaf"} and sent["geometry"] == {"x": 46.7, "y": 24.7, "spatialReference": {"wkid": 4326}}


def test_an_update_carries_the_row_number():
    gw, fl = with_layer(S.WORKERS)
    gw.update(S.WORKERS, 7, {"Worker_ID": "WRK-001", "Name": "Nawaf"}, PT)
    assert fl.edits[-1]["updates"][0]["attributes"]["OBJECTID"] == 7


def test_a_rejected_edit_raises_and_names_the_layer():
    gw, fl = with_layer(S.WORK_ORDERS)
    fl.reject = True
    with pytest.raises(StoreWriteError, match="Riyadh_Work_Orders.*rejected by a field domain") as e:
        gw.add(S.WORK_ORDERS, {"Work_Order_ID": "WO-0001"}, PT)
    assert e.value.layer == S.WORK_ORDERS


def test_a_lost_connection_becomes_a_store_write_error():
    gw, fl = with_layer(S.WORKERS)
    fl.offline = True
    with pytest.raises(StoreWriteError, match="could not be reached"):
        gw.add(S.WORKERS, {"Worker_ID": "WRK-001"}, PT)


def test_text_longer_than_the_hosted_field_is_refused_before_anything_is_sent():
    gw, fl = with_layer(S.NOTIFICATIONS)
    with pytest.raises(StoreWriteError, match="Trail has 4001 characters and the hosted field holds 4000"):
        gw.add(S.NOTIFICATIONS, {"Notif_ID": "NTF-0001", "Trail": "x" * 4001}, None)
    assert fl.edits == []


def test_apply_many_sends_requests_of_200_rows_and_returns_the_row_numbers():
    gw, fl = with_layer(S.WORKERS)
    oids = gw.apply_many(S.WORKERS, [({"Worker_ID": f"WRK-{n:03d}"}, PT) for n in range(450)], [], [])
    assert oids == list(range(1, 451)) and [len(e["adds"]) for e in fl.edits] == [200, 200, 50]


def test_a_batch_that_fails_part_way_says_how_far_it_got():
    gw, fl = with_layer(S.WORKERS)
    real = fl.edit_features

    def second_request_fails(**kw):
        if len(fl.edits) >= 1:
            raise ConnectionError("timed out")
        return real(**kw)
    fl.edit_features = second_request_fails
    with pytest.raises(StoreWriteError, match="200 of 450 changes to this layer had already been written"):
        gw.apply_many(S.WORKERS, [({"Worker_ID": f"WRK-{n:03d}"}, PT) for n in range(450)], [], [])


def test_truncate_empties_the_layer_and_keeps_the_service():
    gw, fl = with_layer(S.WORKERS)
    fl.features = [{"attributes": {"OBJECTID": 1, "Worker_ID": "WRK-001"}}]
    gw.truncate(S.WORKERS)
    assert fl.edits[-1] == {"delete_where": "1=1"} and fl.features == []


def test_create_layers_dry_run_lists_every_layer_and_changes_nothing():
    gis = FakeGIS()
    plan = gateway(gis).create_layers(dry_run=True)
    assert {p["action"] for p in plan} == {"create"} and len(plan) == len(S.LAYERS) and gis.created == []
    assert all(p["title"].startswith("CityView_") for p in plan)
    assert {S.NOTIFICATIONS, S.TRUTH} <= {p["layer"] for p in plan}            # the two the City project kept local are hosted too


def test_create_layers_reports_existing_layers_and_missing_fields():
    gis = FakeGIS()
    item = gis.add_item("CityView_Riyadh_Field_Workers", "city.owner", S.WORKERS)
    item.fl.properties.fields = [f for f in item.fl.properties.fields if f["name"] != "ArcGIS_Username"]
    plan = {p["layer"]: p for p in gateway(gis).create_layers(only=[S.WORKERS, S.FACILITIES], dry_run=True)}
    assert plan[S.WORKERS]["action"] == "add_fields" and plan[S.WORKERS]["fields"] == ["ArcGIS_Username"]
    assert plan[S.FACILITIES]["action"] == "create" and item.fl.definitions == []


def test_create_layers_apply_creates_only_cityview_titles_with_editor_tracking():
    gis = FakeGIS()
    gw = gateway(gis)
    flcs = []

    def collection(item):
        added, updated = [], []
        flcs.append((added, updated))
        return SimpleNamespace(properties={}, manager=SimpleNamespace(add_to_definition=added.append, update_definition=updated.append))
    gw._collection = collection
    plan = gw.create_layers(only=[S.WORKERS, S.APPROVALS], dry_run=False)
    assert gis.created == ["CityView_Riyadh_Field_Workers", "CityView_Riyadh_Approvals"] and all(p["item_id"] for p in plan)
    layer_def, table_def = flcs[0][0][0]["layers"][0], flcs[1][0][0]["tables"][0]
    assert layer_def["geometryType"] == "esriGeometryPoint" and table_def["type"] == "Table"
    assert "editorTrackingInfo" not in layer_def                                  # a setting of the service, not of the layer
    assert all(updated == [{"editorTrackingInfo": {**updated[0]["editorTrackingInfo"], "enableEditorTracking": True}}] for _added, updated in flcs)
    assert layer_def["fields"][[f["name"] for f in layer_def["fields"]].index("Name")]["length"] == 255
    trail = next(f for f in definition(S.LAYERS[S.NOTIFICATIONS])["fields"] if f["name"] == "Trail")
    assert trail["length"] == 16000                                               # long text is not limited to 4,000: that is only the limit for an indexed field


def test_a_full_read_that_comes_back_short_stops_instead_of_starting_on_part_of_the_data():
    gw, fl = with_layer(S.WORKERS)
    fl.features = [{"attributes": {"OBJECTID": 1, "Worker_ID": "WRK-001"}, "geometry": {"x": 46.7, "y": 24.7}}]
    fl.reported_count = 1329
    with pytest.raises(RuntimeError, match="reports 1329 rows but 1 were returned"):
        gw.rows(S.WORKERS)


def test_an_existing_layer_without_edit_tracking_gets_it_switched_on_when_applying():
    gis = FakeGIS()
    item = gis.add_item("CityView_Riyadh_Field_Workers", "city.owner", S.WORKERS)
    item.fl.__init__(S.WORKERS, tracked=False)
    item.layers = [item.fl]
    gw = gateway(gis)
    updates = []
    gw._collection = lambda it: SimpleNamespace(properties={"layers": [1]}, manager=SimpleNamespace(update_definition=updates.append))
    assert gw.create_layers(only=[S.WORKERS], dry_run=True)[0]["tracking"] is False and updates == []
    step = gw.create_layers(only=[S.WORKERS], dry_run=False)[0]
    assert updates and updates[0]["editorTrackingInfo"]["enableEditorTracking"] is True
    assert step["tracking"] is False                                              # read back: this stand-in did not gain an EditDate, and the plan says so


def test_task_fields_are_left_to_field_maps():
    assert not any(f["name"].startswith("esritask_") for f in definition(S.LAYERS[S.WORK_ORDERS])["fields"])
