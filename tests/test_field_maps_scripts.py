"""Plan 4: the planners and scripts that prepare the Work Orders layer and the new Field Maps web map. Nothing here contacts ArcGIS Online."""
import copy
import json
from pathlib import Path

import pytest

from scripts import field_maps_plan as P

REF = json.loads((Path(__file__).parent / "fixtures" / "field_maps_reference.json").read_text(encoding="utf-8"))
TYPES = ["Water Leak", "Other", "Traffic Incident", "Planned Road Closure", "Major Event Traffic Plan"]
USERS = {"story_viewer": "story_viewer"}
LAYERS = {k: {"url": f"https://example.test/arcgis/rest/services/CityView_{k}/FeatureServer/0", "itemId": f"id{k}"}
          for k in ("work_orders", "verification", "incidents", "traffic_incidents", "closures", "event_notices")}
TASK_NAMES = ["esritask_type", "esritask_assignee", "esritask_status", "esritask_priority", "esritask_duedate", "esritask_description", "esritask_notes"]


def test_task_fields_are_planned_only_when_missing():
    fields, changes = P.plan_task_fields([{"name": "OBJECTID"}, {"name": "Work_Order_ID"}], TYPES, USERS)
    assert [f["name"] for f in fields] == TASK_NAMES and changes
    by = {f["name"]: f for f in fields}
    assert by["esritask_status"]["domain"]["codedValues"] == [{"name": n, "code": c} for c, n in enumerate(["Unassigned", "Assigned", "In Progress", "Completed"])]
    assert [c["name"] for c in by["esritask_priority"]["domain"]["codedValues"]] == ["None", "Low", "Medium", "High", "Critical"]
    assert [c["name"] for c in by["esritask_type"]["domain"]["codedValues"]] == TYPES and by["esritask_assignee"]["domain"]["codedValues"] == [{"name": "story_viewer", "code": "story_viewer"}]
    assert by["esritask_description"]["length"] == 4000 and by["esritask_duedate"]["type"] == "esriFieldTypeDate"
    assert by["esritask_status"]["defaultValue"] == 0 and by["esritask_assignee"]["length"] == 255
    assert P.plan_task_fields(fields, TYPES, USERS)[0] == []                                  # all present: nothing to add
    part, _ = P.plan_task_fields([f for f in fields if f["name"] != "esritask_notes"], TYPES, USERS)
    assert [f["name"] for f in part] == ["esritask_notes"]


def test_the_new_map_points_only_at_cityview_layers():
    m, changes = P.plan_web_map(REF["map"], LAYERS, "CityView Field Maps - Investigator Map")
    text = json.dumps(m)
    assert "GeoAIOps" not in text and "07fb979378b94c91ab463d8c17601bd0" not in text
    urls = [l["url"] for l in m["operationalLayers"]]
    assert len(urls) == 6 and all("CityView_" in u for u in urls) and changes
    wo = m["operationalLayers"][0]
    assert wo["id"] == P.WORK_ORDERS_LAYER_ID and wo["url"] == LAYERS["work_orders"]["url"] and wo["itemId"] == "idwork_orders" and wo["formInfo"]
    assert "definitionExpression" not in json.dumps(wo.get("layerDefinition", {}))          # no login is written into the map
    assert m["baseMap"] == REF["map"]["baseMap"]


def test_the_task_settings_point_at_the_new_work_orders_layer():
    fields, _ = P.plan_task_fields([], TYPES, USERS)
    cfg, changes = P.plan_tasks_config(REF["cfg"], P.WORK_ORDERS_LAYER_ID, fields)
    assert cfg["layerId"] == P.WORK_ORDERS_LAYER_ID and changes
    by = {f["name"]: f["domain"]["name"] for f in fields if f.get("domain")}
    fs = cfg["fieldSchema"]
    assert fs["assigneeField"]["codedValueDomain"]["name"] == by["esritask_assignee"]
    assert fs["statusField"]["codedValueDomain"]["name"] == by["esritask_status"] and fs["statusField"]["codedValueDomain"]["keyMap"]["inProgress"] == "In Progress"
    assert fs["taskTypeField"]["codedValueDomain"]["name"] == by["esritask_type"]
    assert "ESRITASK_TYPE_DOMAIN_2dfd8564" not in json.dumps(cfg)                              # none of the City layer's domain names


def test_the_planner_does_not_change_its_input():
    before = copy.deepcopy(REF)
    P.plan_web_map(REF["map"], LAYERS, "t")
    P.plan_tasks_config(REF["cfg"], P.WORK_ORDERS_LAYER_ID, P.plan_task_fields([], TYPES, USERS)[0])
    assert REF == before


def test_an_existing_map_with_the_title_is_found_so_nothing_is_created_twice():
    class It:
        def __init__(self, title, id):
            self.title, self.id = title, id
    items = [It("CityView Field Maps - Investigator Map (old)", "a"), It("CityView Field Maps - Investigator Map", "b")]
    assert P.find_existing(items, "CityView Field Maps - Investigator Map").id == "b"
    assert P.find_existing(items, "Something else") is None


def test_users_are_required_for_the_assignee_list():
    with pytest.raises(ValueError):
        P.plan_task_fields([], TYPES, {})


# ---- scripts, run against recording stand-ins ----
from backend.gis import schema as S


class Props(dict):
    __getattr__ = dict.__getitem__


class FakeLayer:
    def __init__(self, fields, url="https://example.test/arcgis/rest/services/CityView_Riyadh_Work_Orders/FeatureServer/0"):
        self.properties = Props(fields=list(fields), name="Work Orders")
        self.url = url
        self.added = []
        self.manager = self

    def add_to_definition(self, d):
        self.added.append(d)
        self.properties["fields"].extend(d.get("fields", []))


class FakeResources:
    def __init__(self, store):
        self.store = store

    def get(self, name, try_json=False):
        return copy.deepcopy(self.store.get(name))

    def add(self, file_name, text):
        self.store[file_name] = json.loads(text)

    def update(self, file_name, text):
        self.store[file_name] = json.loads(text)


class FakeItem:
    def __init__(self, id, title, type="Web Map", owner="story_viewer", data=None, res=None):
        self.id, self.title, self.type, self.owner = id, title, type, owner
        self.typeKeywords, self.tags, self.snippet = ["Field Maps", "Tasks", "Web Map"], ["Field Maps"], "x"
        self._data, self.res = data, dict(res or {})
        self.resources = FakeResources(self.res)
        self.updated = []
        self.layers = [FakeLayer([], url=f"https://example.test/arcgis/rest/services/{title}/FeatureServer/0")]

    def get_data(self):
        return copy.deepcopy(self._data)

    def update(self, item_properties=None, **kw):
        self.updated.append(item_properties)
        if item_properties and "text" in item_properties:
            self._data = json.loads(item_properties["text"])
        return True


class FakeContent:
    def __init__(self, items):
        self.items, self.created = {i.id: i for i in items}, []

    def get(self, id):
        return self.items.get(id)

    def search(self, query, item_type=None, max_items=100, **kw):
        return [i for i in self.items.values() if (item_type is None or i.type == item_type)]

    def add(self, item_properties, **kw):
        it = FakeItem(f"new{len(self.created) + 1}", item_properties["title"], data=json.loads(item_properties.get("text", "{}")))
        it.typeKeywords = item_properties.get("typeKeywords", [])
        self.created.append(item_properties)
        self.items[it.id] = it
        return it


class FakeGis:
    def __init__(self, items):
        self.content = FakeContent(items)


class FakeGateway:
    def __init__(self, wo_fields=(), extra_items=()):
        ref = FakeItem("REF1", "GeoAI Field Maps - Investigator Map", data=REF["map"], res={"tasks-configuration.json": REF["cfg"]}, owner="story_viewer")
        self.gis, self.owner, self.prefix = FakeGis([ref, *extra_items]), "story_viewer", "CityView"
        self.wo = FakeLayer([{"name": "OBJECTID"}, *wo_fields])
        self.items = {}
        for key, name in {"work_orders": S.WORK_ORDERS, "verification": S.VERIFICATION, "incidents": S.INCIDENTS, "traffic_incidents": S.TRAFFIC_REPORTS,
                          "closures": S.CLOSURES, "event_notices": S.EVENT_NOTICES}.items():
            self.items[name] = FakeItem(f"item_{key}", f"CityView_{name}", type="Feature Service")
        self.forgotten = []

    def title(self, name):
        return f"CityView_{name}"

    def layer(self, name):
        return self.wo if name == S.WORK_ORDERS else self.items[name].layers[0]

    def _item(self, name):
        return self.items[name]

    def _forget(self, name):
        self.forgotten.append(name)


class Settings:
    arcgis_enabled, arcgis_layer_prefix, field_users = True, "CityView", {"WRK-001": "story_viewer"}


def ready_fields():
    """The task fields as they stand on a layer that setup_field_tasks_layer has already prepared."""
    return P.plan_task_fields([], TYPES, USERS)[0]


def test_dry_run_changes_nothing(tmp_path, capsys):
    from scripts import create_field_maps_map as M, setup_field_tasks_layer as L
    gw = FakeGateway()
    assert L.main([], gateway=gw, settings=Settings(), backups=tmp_path) == 0 and gw.wo.added == []
    out = capsys.readouterr().out
    assert "DRY RUN" in out and "esritask_type" in out and not list(tmp_path.iterdir())
    gw2 = FakeGateway(wo_fields=ready_fields())
    assert M.main(["--reference", "REF1"], gateway=gw2, settings=Settings(), backups=tmp_path) == 0
    assert gw2.gis.content.created == [] and "DRY RUN" in capsys.readouterr().out and not list(tmp_path.iterdir())


def test_apply_adds_fields_then_reads_them_back(tmp_path, capsys):
    from scripts import setup_field_tasks_layer as L
    gw = FakeGateway()
    assert L.main(["--apply"], gateway=gw, settings=Settings(), backups=tmp_path) == 0
    assert len(gw.wo.added) == 1 and [f["name"] for f in gw.wo.added[0]["fields"]] == TASK_NAMES and gw.forgotten
    assert len(list(tmp_path.glob("work_orders_definition_*.json"))) == 1                       # the definition was saved before the change
    assert "read back" in capsys.readouterr().out.lower()
    assert L.main(["--apply"], gateway=gw, settings=Settings(), backups=tmp_path) == 0 and len(gw.wo.added) == 1       # run again: nothing more to add


def test_a_read_back_mismatch_stops_and_says_so(tmp_path, capsys):
    from scripts import setup_field_tasks_layer as L
    gw = FakeGateway()
    gw.wo.add_to_definition = lambda d: gw.wo.added.append(d)            # the service accepts the call but the fields never appear
    assert L.main(["--apply"], gateway=gw, settings=Settings(), backups=tmp_path) == 1
    assert "esritask_type" in capsys.readouterr().out


def test_the_map_script_refuses_a_layer_without_task_fields(tmp_path, capsys):
    from scripts import create_field_maps_map as M
    gw = FakeGateway()
    assert M.main(["--reference", "REF1", "--apply"], gateway=gw, settings=Settings(), backups=tmp_path) == 1
    assert gw.gis.content.created == [] and "setup_field_tasks_layer" in capsys.readouterr().out


def test_apply_creates_the_map_with_its_task_settings_and_reads_it_back(tmp_path, capsys):
    from scripts import create_field_maps_map as M
    gw = FakeGateway(wo_fields=ready_fields())
    assert M.main(["--reference", "REF1", "--apply"], gateway=gw, settings=Settings(), backups=tmp_path) == 0
    made = gw.gis.content.created
    assert len(made) == 1 and made[0]["title"] == "CityView Field Maps - Investigator Map" and "Tasks" in made[0]["typeKeywords"] and "Field Maps" in made[0]["typeKeywords"]
    new = gw.gis.content.items["new1"]
    assert new.res["tasks-configuration.json"]["layerId"] == P.WORK_ORDERS_LAYER_ID and "GeoAIOps" not in json.dumps(new.get_data())
    assert gw.gis.content.items["REF1"].updated == []                                           # the reference was only read


def test_the_map_script_refuses_a_second_map_with_the_same_title(tmp_path, capsys):
    from scripts import create_field_maps_map as M
    existing = FakeItem("MAP9", "CityView Field Maps - Investigator Map")
    gw = FakeGateway(wo_fields=ready_fields(), extra_items=[existing])
    assert M.main(["--reference", "REF1", "--apply"], gateway=gw, settings=Settings(), backups=tmp_path) == 1
    out = capsys.readouterr().out
    assert gw.gis.content.created == [] and "MAP9" in out and "--update" in out


def test_update_changes_only_the_named_cityview_map_and_saves_a_backup(tmp_path, capsys):
    from scripts import create_field_maps_map as M
    existing = FakeItem("MAP9", "CityView Field Maps - Investigator Map", data={"operationalLayers": []}, res={"tasks-configuration.json": {"layerId": "old"}})
    gw = FakeGateway(wo_fields=ready_fields(), extra_items=[existing])
    assert M.main(["--reference", "REF1", "--update", "MAP9", "--apply"], gateway=gw, settings=Settings(), backups=tmp_path) == 0
    assert existing.res["tasks-configuration.json"]["layerId"] == P.WORK_ORDERS_LAYER_ID and gw.gis.content.created == []
    assert list(tmp_path.glob("webmap_MAP9_*.json")) and list(tmp_path.glob("tasks-configuration_MAP9_*.json"))


def test_the_scripts_refuse_a_geoaiops_item_and_a_missing_reference(tmp_path, capsys):
    from scripts import create_field_maps_map as M
    other = FakeItem("CITY1", "GeoAI Field Maps - Investigator Map")
    gw = FakeGateway(wo_fields=ready_fields(), extra_items=[other])
    with pytest.raises(SystemExit):
        M.main(["--reference", "NOPE"], gateway=gw, settings=Settings(), backups=tmp_path)
    with pytest.raises(SystemExit):
        M.main(["--reference", "REF1", "--update", "CITY1", "--apply"], gateway=gw, settings=Settings(), backups=tmp_path)       # not a CityView map
    with pytest.raises(SystemExit):
        M.main(["--reference", "REF1", "--title", "GeoAIOps Map"], gateway=gw, settings=Settings(), backups=tmp_path)


# ---- the form and the Answer button (carried from the City project) ----
def test_the_form_plan_is_bilingual_when_asked():
    from scripts import setup_field_maps_form as F
    form, changes = F.plan_form(None, "both")
    labels = {e["fieldName"]: e["label"] for e in form["formElements"]}
    assert len(changes) >= 2 and all(" / " in v for v in labels.values())
    choices = F.coded_values("both")
    assert [c["code"] for c in choices] == ["Confirmed", "Rejected", "Needs Further Inspection", "Escalate", "Repaired"] and all(" / " in c["name"] for c in choices)
    assert F.plan_form(form, "both")[1] == []                                                 # nothing more to add the second time
    en, _ = F.plan_report_form(REF["map"]["operationalLayers"][1]["formInfo"], "en")
    rep, rc = F.plan_report_form(en, "both")
    assert rc and any("/" in r for r in rc)
    assert F.plan_report_form(rep, "both")[1] == []


def test_the_answer_hint_suits_city_and_road_tasks():
    from scripts import setup_field_maps_form as F
    for lang in ("en", "ar", "both"):
        hint = next(e["hint"] for e in F.form_elements(lang) if e["fieldName"] == "Field_Comment")
        assert (("water" in hint and "road" in hint) if lang != "ar" else "الطريق" in hint), hint


def test_the_answer_action_is_added_once_after_finish():
    from scripts import add_task_answer_action as A
    cfg = copy.deepcopy(REF["cfg"])
    cfg["featureActions"] = [a for a in cfg["featureActions"] if a.get("promptField") != "Field_Verdict"]
    for lay in cfg["featureActionLayouts"]:
        ids = {a["id"] for a in REF["cfg"]["featureActions"] if a.get("promptField") == "Field_Verdict"}
        lay["actions"] = [x for x in lay["actions"] if x["featureActionId"] not in ids]
    once, c1 = A.plan_tasks_config(cfg)
    twice, c2 = A.plan_tasks_config(once)
    assert c1 and c2 == [] and sum(a.get("promptField") == "Field_Verdict" for a in twice["featureActions"]) == 1
    in_progress = next(l for l in twice["featureActionLayouts"] if l["title"].lower() == "in progress")
    answer = next(a for a in twice["featureActions"] if a.get("promptField") == "Field_Verdict")
    ids = [x["featureActionId"] for x in in_progress["actions"]]
    assert ids.count(answer["id"]) == 1 and ids.index(answer["id"]) == 1                          # right after Finish


def test_the_scripts_refuse_an_item_without_the_prefix():
    from scripts._guard import own_item_or_exit
    with pytest.raises(SystemExit):
        own_item_or_exit(FakeItem("CITY1", "GeoAI Field Maps - Investigator Map"), "CityView", "CITY1", "story_viewer")
    with pytest.raises(SystemExit):
        own_item_or_exit(FakeItem("X", "CityView map", owner="someone_else"), "CityView", "X", "story_viewer")
