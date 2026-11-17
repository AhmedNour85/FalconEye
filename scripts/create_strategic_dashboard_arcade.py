"""Create a SEPARATE test dashboard with Arcade data expressions and a map (the first dashboard item is not touched).

    python scripts/create_strategic_dashboard_arcade.py            # DRY RUN: prints the definition, writes nothing
    python scripts/create_strategic_dashboard_arcade.py --apply    # creates ONE new private item "CityView Strategic Dashboard (Arcade test)"

Esri does not document how data expressions are stored in a dashboard item, so this is a best-effort format: open the new item to check it.
"""
import argparse
import copy
import json
import re
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TITLE = "CityView Strategic Dashboard (Arcade test)"
SOURCE = ROOT / "data" / "backups" / "dashboard_b70d972b_original.json"
WEB_MAP = "b1e8f3e18def4a53ae6e0cc3a749a0f5"
INCIDENTS = "1514541f9358445ba3269ef20a83c381"
PORTAL = "https://esrisaudi-ai.maps.arcgis.com"

KPI_SCRIPT = f"""var fs = FeatureSetByPortalItem(Portal('{PORTAL}'), '{INCIDENTS}', 0, ['Status', 'Severity', 'Created_Date', 'Last_Updated'], false)
var open = 0, crit = 0, res = 0, hrs = 0
for (var f in fs) {{
  if (f.Status == 'Resolved') {{ res += 1; hrs += DateDiff(Date(f.Last_Updated), Date(f.Created_Date), 'hours') }}
  else if (f.Status != 'Closed - False Positive') {{ open += 1; if (f.Severity == 'Critical') {{ crit += 1 }} }}
}}
return FeatureSet(Text({{ fields: [{{ name: 'open', type: 'esriFieldTypeInteger' }}, {{ name: 'critical_open', type: 'esriFieldTypeInteger' }},
    {{ name: 'resolved', type: 'esriFieldTypeInteger' }}, {{ name: 'avg_hours', type: 'esriFieldTypeDouble' }}],
  geometryType: '', features: [{{ attributes: {{ open: open, critical_open: crit, resolved: res, avg_hours: IIf(res > 0, Round(hrs / res, 1), 0) }} }}] }}))"""
KPIS = [("open", "Open incidents · الحوادث المفتوحة"), ("critical_open", "Critical open · حرجة مفتوحة"),
        ("resolved", "Resolved · تم حلها"), ("avg_hours", "Hours to resolve · ساعات الحل")]


def build(original: dict) -> dict:
    d = copy.deepcopy(original)
    tmpl = next(w for w in d["widgets"] if w["type"] == "indicatorWidget")
    pies = [w for w in d["widgets"] if w["type"] == "pieChartWidget"]
    lst = next(w for w in d["widgets"] if w["type"] == "listWidget")
    for p in pies:
        p["category"]["sliceProperties"] = []                      # the sample slices from the Python library did not match the data
    d["dataExpressions"] = [{"name": "expression/kpis", "title": "KPIs", "script": KPI_SCRIPT, "returnType": "featureSet"}]
    widgets = []
    for field, caption in KPIS:
        w = copy.deepcopy(tmpl)
        w.update(id=str(uuid.uuid4()), name=field, caption=caption, valueType="field", valueField=field)
        w["defaultSettings"]["topSection"]["textInfo"] = {"text": caption}
        w["datasets"] = [{"type": "serviceDataset", "dataSource": {"type": "expressionDataSource", "dataSourceName": "expression/kpis"}, "outFields": ["*"],
                          "groupByFields": [], "orderByFields": [], "statisticDefinitions": [], "returnGeometry": False, "clientSideStatistics": False, "name": "main"}]
        widgets.append(w)
    map_w = {"type": "mapWidget", "id": str(uuid.uuid4()), "name": "Map", "itemId": WEB_MAP, "showPopup": True, "legend": {"enabled": True}, "events": []}
    d["widgets"] = widgets + [map_w] + pies[:2] + [lst]
    ids = [w["id"] for w in d["widgets"]]
    cell = lambda i, w, h: {"type": "itemLayoutElement", "id": i, "width": w, "height": h}
    d["layout"] = {"rootElement": {"type": "stackLayoutElement", "orientation": "row", "width": 1, "height": 1, "elements": [
        {"type": "stackLayoutElement", "orientation": "col", "width": 1, "height": 0.25, "elements": [cell(i, 0.25, 1) for i in ids[:4]]},
        {"type": "stackLayoutElement", "orientation": "col", "width": 1, "height": 0.45, "elements": [cell(ids[4], 0.6, 1), cell(ids[7], 0.4, 1)]},
        {"type": "stackLayoutElement", "orientation": "col", "width": 1, "height": 0.3, "elements": [cell(ids[5], 0.5, 1), cell(ids[6], 0.5, 1)]}]}}
    return d


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args(argv)
    new = build(json.loads(SOURCE.read_text(encoding="utf-8")))
    print(json.dumps({"dataExpressions": [{k: (v[:80] + "…" if k == "script" else v) for k, v in e.items()} for e in new["dataExpressions"]],
                      "widgets": [(w["type"], w.get("name")) for w in new["widgets"]], "layout": new["layout"]}, indent=1, ensure_ascii=False))
    if not args.apply:
        print("\nDRY RUN: nothing was written.")
        return 0
    from backend.gis.agol import ArcGISGateway
    from config.settings import load_settings
    settings = load_settings()
    if not TITLE.startswith(settings.arcgis_layer_prefix):
        sys.exit("Refused: the title must start with the project prefix.")
    gis = ArcGISGateway(settings).gis
    if gis.content.search(f'title:"{TITLE}" AND owner:{gis.users.me.username}', item_type="Dashboard"):
        sys.exit("Refused: the test dashboard already exists. Nothing was changed.")
    item = gis.content.add({"title": TITLE, "type": "Dashboard", "typeKeywords": "Dashboard,Operations Dashboard,Arcade", "tags": "CityView-Riyadh,SYNTHETIC-DEMO,Falcon Eye",
                            "snippet": "Falcon Eye strategic overview with Arcade data expressions and a map (test, synthetic demo data).", "text": json.dumps(new, ensure_ascii=False)})
    print("Created:", item.id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
