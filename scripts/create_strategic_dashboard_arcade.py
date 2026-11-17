"""Build the Falcon Eye strategic dashboard in the style of an existing ArcGIS Dashboards design (a docking layout with a map, indicators, pie charts and
Arcade-formatted lists), and write it to a SEPARATE test item. The first dashboard item is never touched.

    python scripts/create_strategic_dashboard_arcade.py                          # DRY RUN: checks the definition, writes nothing
    python scripts/create_strategic_dashboard_arcade.py --apply                  # creates the item "CityView Strategic Dashboard (Arcade test)"
    python scripts/create_strategic_dashboard_arcade.py --apply --update <id>    # replaces the content of that test item (a backup is saved first)

The widget formats come from a reference dashboard saved in data/backups (read only), so the JSON follows the schema the current ArcGIS Dashboards writes.
"""
import argparse
import copy
import json
import sys
import uuid
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TITLE = "CityView Strategic Dashboard (Arcade test)"
REFERENCE = ROOT / "data" / "backups" / "reference_dashboard_05c6992a.json"
WEB_MAP = "558e75041aa445289ad4db29e51f95a9"                     # CityView Strategic Map (made by create_strategic_web_map.py): the layers and counts the widgets read
INC, WO, VER = "CityView_incidents", "WorkOrders_tasks", "CityView_verification"
TYPES = ["Water Leak", "Streetlight Failure", "Urban Change", "Urban Case", "Unlicensed Canopies and Hangars", "Unregulated Street Vendors", "Neglected Vacant Land",
         "Exposed Wiring and Neglected Utilities", "Abandoned Vehicles", "Illegal Graffiti", "Non-compliant Billboards", "Construction Waste"]
PALETTE = ["#4cc9f0", "#f9c74f", "#90be6d", "#43aa8b", "#f94144", "#f3722c", "#f8961e", "#b5179e", "#7209b7", "#577590", "#e5989b", "#c9ada7"]
RED = "#ff6b5e"
AREAS = ["Al Malaz", "Diplomatic Quarter", "Diriyah", "KAFD", "King Salman Park", "Olaya"]
GREEN, AMBER, BLUE = "#3cb87f", "#ff9a3d", "#5aa9ff"

LIST_EXPRESSION = """var sev = $datapoint.Severity
var color = Decode(sev, 'Critical', '#ff6b5e', 'High', '#ff9a3d', 'Medium', '#f5b84a', '#5aa9ff')
var closed = $datapoint.Status == 'Resolved' || Find('Closed', $datapoint.Status) == 0
return {
  textColor: '', backgroundColor: '', separatorColor: '', selectionColor: '', selectionTextColor: '',
  attributes: { id: $datapoint.Incident_ID, kind: $datapoint.Incident_Type, area: $datapoint.Area_Name, sev: sev, status: $datapoint.Status,
                color: IIf(closed, '#7f9488', color) }
}
"""
LIST_TEXT = ('<div style="background-color:#363636; border-left:10px solid {expression/color}; margin:5px; padding:6px 10px; width:100%">'
             '<span style="color:white; font-size:16px"><strong>{expression/id}</strong> · {expression/kind}</span><br>'
             '<span style="color:#cbd8d0; font-size:13px">{expression/area} · {expression/sev} · {expression/status}</span></div>')


def _ds(layer, group=(), order=(), stats=None, max_features=None):
    d = {"type": "serviceDataset", "name": "main", "dataSource": {"type": "layerDataSource", "itemId": WEB_MAP, "layerId": layer}, "groupByFields": list(group),
         "orderByFields": list(order), "statisticDefinitions": stats or [], "clientSideStatistics": False, "outFields": ["*"], "returnDistinctValues": False,
         "allowSourceDownload": False, "allowSummaryDownload": False}
    if max_features:
        d["maxFeatures"] = max_features
    return d


def _count(field="OBJECTID"):
    return [{"onStatisticField": field, "outStatisticFieldName": "value", "statisticType": "count"}]


def build(ref: dict) -> dict:
    view = ref["desktopView"]
    ind_t = next(w for w in view["widgets"] if w["type"] == "indicatorWidget")
    pie_t = next(w for w in view["widgets"] if w["type"] == "pieChartWidget")
    list_t = next(w for w in view["widgets"] if w["type"] == "listWidget")
    map_t = next(w for w in view["widgets"] if w["type"] == "mapWidget")
    new_id = lambda: str(uuid.uuid4())

    def indicator(name, caption, layer, color):
        w = copy.deepcopy(ind_t)
        w.update(id=new_id(), name=name, datasets=[_ds(layer, stats=_count())], events=[], valueType="statistic")
        ds = w["defaultSettings"]
        ds["caption"] = f'<p><span style="font-size:22px"><strong>{caption}</strong></span></p>'
        ds["topSection"] = {"fontSize": 80, "textInfo": {}}
        ds["middleSection"] = {"fontSize": 160, "textInfo": {"text": "{value}", "fillColor": color}}
        ds["bottomSection"] = {"fontSize": 80, "textInfo": {"text": None}}
        return w

    def pie(name, caption, field, colours=(), layer=INC):
        w = copy.deepcopy(pie_t)
        w.update(id=new_id(), name=name, caption=f"<h3><strong>{caption}</strong></h3>\n", datasets=[_ds(layer, group=[field], stats=_count())], events=[])
        w["category"]["fieldName"] = field                          # the reference chart groups by its own field; ours group by this one
        w["caption"] = f'<p><span style="font-size:22px"><strong>{caption}</strong></span></p>'
        w["category"]["sliceProperties"] = [{"key": k, "label": k, "color": c} for k, c in colours]
        # vivid donut with a dark outline between slices and a larger legend with the counts
        w["pie"].update(alpha=1, outlineAlpha=1, outlineColor="#2b2b2b", outlineThickness=2, innerRadius=55, fontSize=16)
        w["legend"].update(enabled=True, position="right", markerSize=20, format="value")
        return w

    def lst(name, order):
        w = copy.deepcopy(list_t)
        w.update(id=new_id(), name=name, datasets=[_ds(INC, order=order, max_features=100)], events=[], expression=LIST_EXPRESSION, text=LIST_TEXT)
        return w

    # the same four numbers as the Strategic page (open, not closed; "resolved" counts this run's work only; significant urban changes)
    k_crit = indicator("Critical incidents", "Critical incidents · الحوادث الحرجة", "OpenCritical", RED)
    k_chg = indicator("Urban changes", "Urban changes · التغيّرات العمرانية", "ChangesSignificant", BLUE)
    k_res = indicator("Resolved", "Resolved · تم حلها", "ResolvedLive", GREEN)
    k_open = indicator("Open incidents", "Open incidents · الحوادث المفتوحة", "OpenIncidents", AMBER)
    p_sev = pie("Open by severity", "Open by severity · المفتوحة حسب الخطورة", "Severity", [("Critical", "#ff6b5e"), ("High", "#ff9a3d"), ("Medium", "#f5b84a"), ("Low", "#5aa9ff")], layer="OpenIncidents")
    p_area = pie("Open by area", "Hotspots: open by area · البؤر حسب المنطقة", "Area_Name", list(zip(AREAS, PALETTE)), layer="OpenIncidents")
    p_type = pie("Open by type", "Open by type · المفتوحة حسب النوع", "Incident_Type", list(zip(TYPES, PALETTE)), layer="OpenIncidents")
    l_new = lst("Latest incidents", ["Created_Date DESC"])
    m = copy.deepcopy(map_t)
    m.update(id=new_id(), name="Operations map", itemId=WEB_MAP)
    follow = [l_new, k_crit, k_chg, k_res, k_open, p_sev, p_area, p_type]
    m["events"] = [{"type": "extentChanged", "actions": [{"type": "filter", "targets": [{"targetId": w["id"] + "#main", "by": "geometry", "requiresSelection": False} for w in follow]}]}]
    widgets = [m] + follow

    def item(w, h, wid, tab=None):
        e = {"width": w, "height": h, "type": "itemLayoutElement", "id": wid}
        if tab:
            e["tabName"] = tab
        return e

    def box(w, h, kids, orient):
        return {"width": w, "height": h, "id": new_id(), "elements": kids, "type": "stackLayoutElement", "orientation": orient}

    def tabs(w, h, kids):
        return {"width": w, "height": h, "id": new_id(), "elements": kids, "type": "tabsLayoutElement"}

    # left: the latest incidents; centre: the map; right: the widgets (the three counts side by side, then the three charts)
    top = box(1, 0.2, [item(0.25, 1, k_crit["id"]), item(0.25, 1, k_chg["id"]), item(0.25, 1, k_res["id"]), item(0.25, 1, k_open["id"])], "col")      # the four counts across the top
    left = box(0.24, 1, [item(1, 1, l_new["id"])], "row")
    centre = box(0.44, 1, [item(1, 1, m["id"])], "row")
    right = box(0.32, 1, [item(1, 0.3, p_sev["id"]), item(1, 0.3, p_area["id"]), item(1, 0.4, p_type["id"])], "row")
    body = box(1, 0.8, [left, centre, right], "col")
    out = copy.deepcopy(ref)
    header = {**view["header"], "title": "Falcon Eye · عيون الصقر — Strategic Dashboard · لوحة القيادة الاستراتيجية", "showSignOutMenu": False}
    header.pop("logoImageURL", None)
    out["desktopView"] = {"widgets": widgets, "header": header, "layout": {"type": "dockingLayout", "rootElement": box(1, 1, [top, body], "row")},
                          "type": "desktop", "settings": view["settings"]}
    return out


def check(d: dict) -> list:
    """Offline checks: every layout item is a widget, every widget is placed exactly once, every event target exists."""
    v = d["desktopView"]
    ids = {w["id"] for w in v["widgets"]}
    placed = []

    def walk(e):
        if e.get("type") == "itemLayoutElement":
            placed.append(e["id"])
        for c in e.get("elements", []):
            walk(c)

    walk(v["layout"]["rootElement"])
    problems = [f"layout item {i} is not a widget" for i in placed if i not in ids] + [f"widget {i} is placed {placed.count(i)} times" for i in ids if placed.count(i) != 1]
    for w in v["widgets"]:
        for ev in w.get("events", []):
            for a in ev.get("actions", []):
                problems += [f"event target {t['targetId']} is not a widget" for t in a.get("targets", []) if t["targetId"].split("#")[0] not in ids]
    return problems


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--update", help="id of the test item this script created earlier")
    args = ap.parse_args(argv)
    new = build(json.loads(REFERENCE.read_text(encoding="utf-8")))
    problems = check(new)
    print("widgets:", [(w["type"], w["name"]) for w in new["desktopView"]["widgets"]])
    print("checks:", problems or "layout and event targets are consistent")
    if problems:
        return 1
    if not args.apply:
        print("DRY RUN: nothing was written.")
        return 0
    from backend.gis.agol import ArcGISGateway
    from config.settings import load_settings

    settings = load_settings()
    gis = ArcGISGateway(settings).gis
    if args.update:
        item = gis.content.get(args.update)
        if item is None or item.title != TITLE or item.owner != gis.users.me.username:
            sys.exit("Refused: --update only replaces the test item this script created (matching title and owner).")
        backup = ROOT / "data" / "backups" / f"dashboard_{item.id[:8]}_{datetime.now():%Y%m%d_%H%M%S}.json"
        backup.write_text(json.dumps(item.get_data(), ensure_ascii=False, indent=1), encoding="utf-8")
        item.update(data=json.dumps(new, ensure_ascii=False))
        print("Updated:", item.id, "backup:", backup.name)
        return 0
    if not TITLE.startswith(settings.arcgis_layer_prefix):
        sys.exit("Refused: the title must start with the project prefix.")
    if gis.content.search(f'title:"{TITLE}" AND owner:{gis.users.me.username}', item_type="Dashboard"):
        sys.exit("Refused: the test dashboard already exists (use --update <id>). Nothing was changed.")
    item = gis.content.add({"title": TITLE, "type": "Dashboard", "typeKeywords": "Dashboard,Operations Dashboard,Arcade", "tags": "CityView-Riyadh,SYNTHETIC-DEMO,Falcon Eye",
                            "snippet": "Falcon Eye strategic overview (test, synthetic demo data)."}, data=json.dumps(new, ensure_ascii=False))
    print("Created:", item.id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
