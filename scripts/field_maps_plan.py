"""Pure planning code for Field Maps Tasks on the CityView layers. No network: the scripts feed it what they read and apply what it returns.

The field definitions, domain values and task settings copy what the working City project's Work Orders layer and Investigator Map hold
(read once, read-only); only the names and ids are new.
"""
from __future__ import annotations

import copy
import uuid

WORK_ORDERS_LAYER_ID = "WorkOrders_tasks"      # the id of the Work Orders layer inside the new web map; tasks-configuration.json points at it

STATUS_VALUES = ["Unassigned", "Assigned", "In Progress", "Completed"]
PRIORITY_VALUES = ["None", "Low", "Medium", "High", "Critical"]

# layers of the new map, in drawing order: (key, title in the map). The first two come with the reference map's form; the rest are context.
MAP_LAYERS = [("work_orders", "Work orders (tasks)"), ("verification", "Field verification (add a report here)"), ("incidents", "Incidents"),
              ("traffic_incidents", "Traffic incidents"), ("closures", "Planned closures"), ("event_notices", "Event notices")]


def _domain(kind: str, values: list[dict], make_id) -> dict:
    return {"type": "codedValue", "name": f"ESRITASK_{kind.upper()}_DOMAIN_{make_id()}", "codedValues": values}


def _field(name: str, ftype: str, alias: str, length: int | None = None, default=None, domain: dict | None = None) -> dict:
    f = {"name": name, "type": ftype, "alias": alias, "sqlType": "sqlTypeOther", "nullable": True, "editable": True, "defaultValue": default}
    if length:
        f["length"] = length
    if domain:
        f["domain"] = domain
    return f


def plan_task_fields(existing_fields: list[dict], types: list[str], users: dict[str, str], make_id=lambda: str(uuid.uuid4())) -> tuple[list[dict], list[str]]:
    """The esritask_* field definitions the layer is still missing (never alters an existing field) and a plain-language change list."""
    if not users:
        raise ValueError("the assignee list is empty: at least one ArcGIS login is needed")
    have = {f["name"] for f in existing_fields}
    wanted = [
        ("esritask_type", lambda: _field("esritask_type", "esriFieldTypeInteger", "Task Type", domain=_domain("type", [{"name": n, "code": i} for i, n in enumerate(types)], make_id))),
        ("esritask_assignee", lambda: _field("esritask_assignee", "esriFieldTypeString", "Assignee", 255,
                                             domain=_domain("assignee", [{"name": n, "code": u} for u, n in sorted(users.items())], make_id))),
        ("esritask_status", lambda: _field("esritask_status", "esriFieldTypeInteger", "Status", default=0,
                                           domain=_domain("status", [{"name": n, "code": i} for i, n in enumerate(STATUS_VALUES)], make_id))),
        ("esritask_priority", lambda: _field("esritask_priority", "esriFieldTypeInteger", "Priority",
                                             domain=_domain("priority", [{"name": n, "code": i} for i, n in enumerate(PRIORITY_VALUES)], make_id))),
        ("esritask_duedate", lambda: {**_field("esritask_duedate", "esriFieldTypeDate", "Due Date", 8), "precision": 1}),
        ("esritask_description", lambda: _field("esritask_description", "esriFieldTypeString", "Description", 4000)),
        ("esritask_notes", lambda: _field("esritask_notes", "esriFieldTypeString", "Notes", 4000)),
    ]
    out = [make() for name, make in wanted if name not in have]
    changes = [f"add field {f['name']} ({f['alias']})" + (f" with {len(f['domain']['codedValues'])} choices" if f.get("domain") else "") for f in out]
    return out, changes


def _domain_name(fields: list[dict], field: str) -> str:
    f = next((x for x in fields if x["name"] == field), None)
    if not f or not (f.get("domain") or {}).get("name"):
        raise ValueError(f"{field} has no domain: the task settings cannot point at it")
    return f["domain"]["name"]


def plan_web_map(reference: dict, layers: dict[str, dict], title: str) -> tuple[dict, list[str]]:
    """A NEW web map definition: the reference map's basemap, view and the form of its two task layers, with the CityView layers.

    layers: key -> {"url": feature layer url, "itemId": hosted item id}. Nothing of the reference's items, urls or login filters is carried over.
    """
    ref = copy.deepcopy(reference)
    ref_layers = ref["operationalLayers"]
    forms = {"work_orders": ref_layers[0], "verification": ref_layers[1]}
    ops, changes = [], []
    for key, label in MAP_LAYERS:
        spec = layers.get(key)
        if not spec:
            changes.append(f"skip {label}: the hosted layer is not there")
            continue
        base = forms.get(key)
        lyr = copy.deepcopy(base) if base else {"layerType": "ArcGISFeatureLayer", "opacity": 1, "visibility": True}
        lyr.update({"id": WORK_ORDERS_LAYER_ID if key == "work_orders" else f"CityView_{key}", "title": label, "url": spec["url"]})
        if spec.get("itemId"):
            lyr["itemId"] = spec["itemId"]
        else:
            lyr.pop("itemId", None)
        if "layerDefinition" in lyr:
            lyr["layerDefinition"] = {k: v for k, v in lyr["layerDefinition"].items() if k != "definitionExpression"}      # no login is written into the map
        ops.append(lyr)
        changes.append(f"add layer {label!r} -> {spec['url'].split('/services/')[-1]}")
    m = {"operationalLayers": ops, "tables": [], "baseMap": ref["baseMap"], "authoringApp": ref.get("authoringApp", "FieldMapsDesigner"),
         "authoringAppVersion": ref.get("authoringAppVersion", ""), "initialState": ref.get("initialState", {}), "spatialReference": ref.get("spatialReference", {"wkid": 102100}),
         "timeZone": ref.get("timeZone", "system"), "version": ref.get("version", "2.31")}
    changes.insert(0, f"new web map {title!r}: basemap {ref['baseMap'].get('title', '')!r} and view copied from the reference")
    return m, changes


def plan_tasks_config(reference_cfg: dict, work_orders_layer_id: str, fields: list[dict]) -> tuple[dict, list[str]]:
    """The hidden tasks-configuration.json for the new map: the reference's actions, layouts and lists, pointing at the new layer and its domains."""
    cfg = copy.deepcopy(reference_cfg)
    cfg["layerId"] = work_orders_layer_id
    fs = cfg["fieldSchema"]
    fs["assigneeField"]["codedValueDomain"]["name"] = _domain_name(fields, "esritask_assignee")
    fs["statusField"]["codedValueDomain"]["name"] = _domain_name(fields, "esritask_status")
    fs["taskTypeField"]["codedValueDomain"]["name"] = _domain_name(fields, "esritask_type")
    return cfg, [f"task settings point at layer id {work_orders_layer_id!r}", "task settings point at the new layer's three domains (type, assignee, status)"]


def find_existing(items, title: str):
    """The item whose title is exactly this one, or None."""
    return next((i for i in items if i.title == title), None)
