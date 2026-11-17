"""Create the web map behind the ArcGIS strategic dashboard: incidents coloured by severity (with a popup), the urban change layer, and a dark basemap.

    python scripts/create_strategic_web_map.py                   # DRY RUN: prints the new web map, changes nothing
    python scripts/create_strategic_web_map.py --apply           # creates ONE new private web map "CityView Strategic Map"
    python scripts/create_strategic_web_map.py --apply --dashboard <id>   # also points that test dashboard's map widget at the new map (backup saved first)

The Field Maps map used by field workers is only READ (for its basemap and view); it is never edited.
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.gis import schema as S  # noqa: E402

TITLE = "CityView Strategic Map"
DASHBOARD_TITLE = "CityView Strategic Dashboard (Arcade test)"
FIELD_MAPS_MAP = "b1e8f3e18def4a53ae6e0cc3a749a0f5"
SEVERITY = [("Critical", [255, 107, 94]), ("High", [255, 154, 61]), ("Medium", [245, 184, 74]), ("Low", [90, 169, 255])]


def _marker(rgb, size=11):
    return {"type": "esriSMS", "style": "esriSMSCircle", "color": rgb + [235], "size": size, "outline": {"type": "esriSLS", "style": "esriSLSSolid", "color": [20, 30, 25, 255], "width": 1}}


def incident_layer(url, item_id):
    renderer = {"type": "uniqueValue", "field1": "Severity", "defaultSymbol": _marker([160, 175, 168]), "defaultLabel": "Other",
                "uniqueValueInfos": [{"value": k, "label": k, "symbol": _marker(c, 14 if k == "Critical" else 11)} for k, c in SEVERITY]}
    popup = {"title": "{Incident_ID} · {Incident_Type}", "fieldInfos": [{"fieldName": f, "label": f.replace("_", " "), "visible": True}
             for f in ("Area_Name", "Severity", "Status", "Priority", "Risk_Score", "Verification_Outcome", "Created_Date", "Last_Updated")],
             "description": None, "showAttachments": False, "mediaInfos": []}
    return {"id": "CityView_incidents", "title": "Incidents", "url": url, "itemId": item_id, "layerType": "ArcGISFeatureLayer", "visibility": True, "opacity": 1,
            "layerDefinition": {"drawingInfo": {"renderer": renderer}}, "popupInfo": popup}


def change_layer(url, item_id):
    sym = {"type": "esriSFS", "style": "esriSFSSolid", "color": [60, 184, 127, 70], "outline": {"type": "esriSLS", "style": "esriSLSSolid", "color": [60, 184, 127, 255], "width": 1.2}}
    popup = {"title": "{Change_Type} · {Area_Name}", "fieldInfos": [{"fieldName": f, "label": f.replace("_", " "), "visible": True}
             for f in ("Change_ID", "Area_Sqm", "Confidence", "Previous_Epoch", "Current_Epoch", "Detection_Date")], "showAttachments": False, "mediaInfos": []}
    return {"id": "CityView_changes", "title": "Urban change", "url": url, "itemId": item_id, "layerType": "ArcGISFeatureLayer", "visibility": True, "opacity": 1,
            "layerDefinition": {"drawingInfo": {"renderer": {"type": "simple", "symbol": sym}}}, "popupInfo": popup}


def data_layer(layer_id, title, url, item_id):
    """A layer the dashboard counts from (its id is what the dashboard widgets point at); it is not drawn on the map."""
    return {"id": layer_id, "title": title, "url": url, "itemId": item_id, "layerType": "ArcGISFeatureLayer", "visibility": False, "opacity": 1}


def build(reference: dict, layers: list) -> dict:
    """The new web map: the Field Maps map's basemap and view, with the strategic layers (changes below incidents)."""
    return {"operationalLayers": layers, "tables": [], "baseMap": reference["baseMap"], "initialState": reference.get("initialState", {}),
            "spatialReference": reference.get("spatialReference", {"wkid": 102100}), "authoringApp": "ArcGISMapViewer", "authoringAppVersion": "",
            "timeZone": "system", "version": "2.31"}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dashboard", help="id of the test dashboard to point at the new map")
    args = ap.parse_args(argv)
    from backend.gis.agol import ArcGISGateway
    from config.settings import load_settings

    settings = load_settings()
    if not TITLE.startswith(settings.arcgis_layer_prefix):
        sys.exit("Refused: the title must start with the project prefix.")
    gw = ArcGISGateway(settings)
    gis = gw.gis
    ref = gis.content.get(FIELD_MAPS_MAP)
    if ref is None or ref.type != "Web Map":
        sys.exit("Refused: the Field Maps web map is not visible to this account.")
    layers = []
    makers = [(change_layer, S.CHANGES), (incident_layer, S.INCIDENTS),
              (lambda u, i: data_layer("WorkOrders_tasks", "Work orders", u, i), S.WORK_ORDERS),
              (lambda u, i: data_layer("CityView_verification", "Field verification", u, i), S.VERIFICATION)]
    for make, name in makers:
        try:
            layers.append(make(gw.layer(name).url, gw._item(name).id))
        except Exception as exc:
            print(f"  (skipped {gw.title(name)}: {exc})")
    new = build(ref.get_data(), layers)
    print("layers:", [(l["title"], l["url"].split("/services/")[-1]) for l in new["operationalLayers"]])
    print("basemap:", new["baseMap"].get("title"))
    if not args.apply:
        print("DRY RUN: nothing was written.")
        return 0
    if gis.content.search(f'title:"{TITLE}" AND owner:{gis.users.me.username}', item_type="Web Map"):
        sys.exit("Refused: the strategic web map already exists. Nothing was changed.")
    item = gis.content.add({"title": TITLE, "type": "Web Map", "tags": "CityView-Riyadh,SYNTHETIC-DEMO,Falcon Eye", "snippet": "Falcon Eye strategic map: incidents by severity and urban change.",
                            "text": json.dumps(new)})
    print("Created web map:", item.id)
    if args.dashboard:
        dash = gis.content.get(args.dashboard)
        if dash is None or dash.title != DASHBOARD_TITLE or dash.owner != gis.users.me.username:
            sys.exit("Refused: --dashboard only changes the test dashboard this project created.")
        data = dash.get_data()
        backup = ROOT / "data" / "backups" / f"dashboard_{dash.id[:8]}_{datetime.now():%Y%m%d_%H%M%S}.json"
        backup.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        text = json.dumps(data, ensure_ascii=False).replace(FIELD_MAPS_MAP, item.id)
        dash.update(data=text)
        print("Dashboard now uses the new map; backup:", backup.name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
