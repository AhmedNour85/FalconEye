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
