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


FIELD_AR = {"Area_Name": "المنطقة", "Severity": "الخطورة", "Status": "الحالة", "Priority": "الأولوية", "Risk_Score": "درجة المخاطر", "Verification_Outcome": "نتيجة التحقق",
            "Created_Date": "تاريخ الإنشاء", "Last_Updated": "آخر تحديث", "Change_ID": "رقم التغيّر", "Area_Sqm": "المساحة (م²)", "Confidence": "الثقة",
            "Previous_Epoch": "الحقبة السابقة", "Current_Epoch": "الحقبة الحالية", "Detection_Date": "تاريخ الرصد", "Corridor": "المحور", "Road_Class": "فئة الطريق",
            "Level_": "مستوى الازدحام", "VC_Ratio": "نسبة الحجم إلى السعة", "Hour": "الساعة", "Note": "ملاحظة", "Lanes": "المسارات", "Speed_Limit": "السرعة المحددة",
            "Oneway": "اتجاه واحد", "Terminals": "المحطات الطرفية", "Line_Name": "اسم الخط", "Station_Type": "نوع المحطة", "Direction": "الاتجاه", "Origin": "نقطة البداية",
            "Destination": "الوجهة", "Route_ID": "رقم المسار", "Shelter": "مظلة", "Kind": "النوع", "Beds": "الأسرّة", "Section": "المقطع", "Lanes_Closed": "المسارات المغلقة",
            "Full_Closure": "إغلاق كامل", "Start_Time": "وقت البدء", "End_Time": "وقت الانتهاء", "Reason": "السبب", "Venue": "الموقع", "Attendance": "الحضور"}


def _fl(f):
    return FIELD_AR.get(f, f.replace("_", " "))


def _marker(rgb, size=11):
    return {"type": "esriSMS", "style": "esriSMSCircle", "color": rgb + [255], "size": size, "outline": {"type": "esriSLS", "style": "esriSLSSolid", "color": [255, 255, 255, 255], "width": 1}}


def incident_layer(url, item_id):
    # the Strategic page: Critical = red 13, everything else = orange 9, white edge
    renderer = {"type": "uniqueValue", "field1": "Severity", "defaultSymbol": _marker([220, 104, 3], 9), "defaultLabel": "مفتوحة أخرى",
                "uniqueValueInfos": [{"value": "Critical", "label": "حرجة", "symbol": _marker([217, 45, 32], 13)}]}
    popup = {"title": "{Incident_ID} · {Incident_Type}", "fieldInfos": [{"fieldName": f, "label": _fl(f), "visible": True}
             for f in ("Area_Name", "Severity", "Status", "Priority", "Risk_Score", "Verification_Outcome", "Created_Date", "Last_Updated")],
             "description": None, "showAttachments": False, "mediaInfos": []}
    return {"id": "CityView_incidents", "title": "الحوادث", "url": url, "itemId": item_id, "layerType": "ArcGISFeatureLayer", "visibility": True, "opacity": 1,
            "layerDefinition": {"drawingInfo": {"renderer": renderer}}, "popupInfo": popup}


def change_layer(url, item_id):
    def fill(alpha, width):
        return {"type": "esriSFS", "style": "esriSFSSolid", "color": [31, 179, 107, alpha], "outline": {"type": "esriSLS", "style": "esriSLSSolid", "color": [31, 179, 107, 255], "width": width}}

    renderer = {"type": "uniqueValue", "field1": "Significant", "defaultSymbol": fill(38, 0.8), "defaultLabel": "غير جوهري",
                "uniqueValueInfos": [{"value": "Yes", "label": "تغيّر جوهري", "symbol": fill(102, 1.6)}]}
    popup = {"title": "{Change_Type} · {Area_Name}", "fieldInfos": [{"fieldName": f, "label": _fl(f), "visible": True}
             for f in ("Change_ID", "Area_Sqm", "Confidence", "Previous_Epoch", "Current_Epoch", "Detection_Date")], "showAttachments": False, "mediaInfos": []}
    return {"id": "CityView_changes", "title": "التغيّرات العمرانية", "url": url, "itemId": item_id, "layerType": "ArcGISFeatureLayer", "visibility": True, "opacity": 1,
            "layerDefinition": {"drawingInfo": {"renderer": renderer}}, "popupInfo": popup}


def data_layer(layer_id, title, url, item_id):
    """A layer the dashboard counts from (its id is what the dashboard widgets point at); it is not drawn on the map."""
    return {"id": layer_id, "title": title, "url": url, "itemId": item_id, "layerType": "ArcGISFeatureLayer", "visibility": False, "opacity": 1}


OPEN = "Status NOT IN ('Resolved', 'Closed - False Positive')"          # the Strategic page's "open": not closed
COUNT_LAYERS = [   # (layer id, title, source layer, filter): hidden layers the dashboard counts from, so its numbers equal the Strategic page's
    ("AllIncidents", "كل الحوادث (حسب المنطقة)", S.INCIDENTS, "1=1"),
    ("OpenIncidents", "الحوادث المفتوحة", S.INCIDENTS, OPEN),
    ("OpenCritical", "الحوادث الحرجة المفتوحة", S.INCIDENTS, OPEN + " AND Severity = 'Critical'"),
    ("ResolvedLive", "تم حلها (هذه الدورة)", S.INCIDENTS, "Status IN ('Resolved', 'Closed - False Positive') AND Description NOT LIKE 'Historical%'"),
    ("ChangesSignificant", "التغيّرات العمرانية الجوهرية", S.CHANGES, "Significant = 'Yes'"),
]


def count_layer(layer_id, title, url, item_id, where):
    lyr = data_layer(layer_id, title, url, item_id)
    lyr["layerDefinition"] = {"definitionExpression": where}
    return lyr


def _line(rgb, width):
    return {"type": "esriSLS", "style": "esriSLSSolid", "color": rgb, "width": width}


def _pop(title, fields):
    return {"title": title, "fieldInfos": [{"fieldName": f, "label": _fl(f), "visible": True} for f in fields], "showAttachments": False, "mediaInfos": []}


def _layer(layer_id, title, url, item_id, renderer, popup=None, where=None, visible=False, min_scale=None):
    """A transport layer like the ones on the Strategic page: off at start, switched on from the map's layer list."""
    lyr = {"id": layer_id, "title": title, "url": url, "itemId": item_id, "layerType": "ArcGISFeatureLayer", "visibility": visible, "opacity": 1,
           "layerDefinition": {"drawingInfo": {"renderer": renderer}}}
    if where:
        lyr["layerDefinition"]["definitionExpression"] = where
    if min_scale:
        lyr["layerDefinition"]["minScale"] = min_scale
    if popup:
        lyr["popupInfo"] = popup
    return lyr


def _simple(sym):
    return {"type": "simple", "symbol": sym}


def _pt(fill, outline, size, ow=1.5):
    return {"type": "esriSMS", "style": "esriSMSCircle", "color": fill, "size": size, "outline": _line(outline, ow)}


METRO_COLOURS = ["#00ade5", "#43b649", "#984c9d", "#f0493a", "#f68d39", "#ffd105"]
METRO_LINE_COLOURS = {"Line1": "#00ade5", "Line2": "#f0493a", "Line3": "#f68d39", "Line4": "#ffd105", "Line5": "#43b649", "Line6": "#984c9d"}


def _hex(h):
    return [int(h[i:i + 2], 16) for i in (1, 3, 5)] + [255]


TRAFFIC_ITEM = "dc82e177df5445f6a19878681996b620"          # CityView Traffic Congestion (scripts/create_traffic_congestion_layer.py): the modelled congested segments of one hour


def congestion_layer(item):
    """Busy / heavy / severe road segments in the Strategic page's colours and widths (orange 2.6, red 3.2, dark red 3.8), over the green road network."""
    cong = {"type": "uniqueValue", "field1": "Level_", "defaultSymbol": _line(_hex("#dc6803"), 2.6),
            "uniqueValueInfos": [{"value": "Busy", "label": "مزدحم", "symbol": _line(_hex("#dc6803"), 2.6)},
                                 {"value": "Heavy", "label": "كثيف", "symbol": _line(_hex("#d92d20"), 3.2)},
                                 {"value": "Severe", "label": "شديد", "symbol": _line(_hex("#8b1117"), 3.8)}]}
    return _layer("CityView_traffic_congestion", "المرور · الازدحام المُنمذَج", item.layers[0].url, item.id, cong,
                  _pop("{Name}", ("Corridor", "Road_Class", "Level_", "VC_Ratio", "Hour", "Note")), visible=True)


def transport_layers(url_of, traffic_item=None):
    """Traffic (the road network), Metro, Bus, Hospitals and Planned closures, as on the Strategic page. Congestion colours there are modelled live and are not stored."""
    u = url_of
    # the numbers below are the ones frontend/mobility.js draws with. Traffic there is modelled by the hour; stored here it is the road network in the "free flow" green
    roads = _simple(_line([47, 170, 74, 115], 1))
    stations = {"type": "uniqueValue", "field1": "Line_ID", "defaultSymbol": _pt([255, 255, 255, 255], [75, 85, 99, 255], 6.5, 2),
                "uniqueValueInfos": [{"value": lid, "label": lid, "symbol": _pt([255, 255, 255, 255], _hex(c), 6.5, 2)} for lid, c in METRO_LINE_COLOURS.items()]}
    metro = {"type": "uniqueValue", "field1": "Color", "defaultSymbol": _line(_hex("#4b5563"), 3.2),
             "uniqueValueInfos": [{"value": c, "label": c, "symbol": _line(_hex(c), 3.2)} for c in METRO_COLOURS]}
    closure = {"type": "uniqueValue", "field1": "Status", "defaultSymbol": _line(_hex("#b54708"), 5),
               "uniqueValueInfos": [{"value": "Requested", "label": "مطلوب", "symbol": {**_line(_hex("#dc6803"), 5), "style": "esriSLSShortDash"}},
                                    {"value": "Approved", "label": "معتمد", "symbol": _line(_hex("#b54708"), 5)},
                                    {"value": "In Place", "label": "قائم", "symbol": _line(_hex("#d92d20"), 5)}]}
    hospital = {"type": "esriSMS", "style": "esriSMSSquare", "color": [255, 255, 255, 255], "size": 14, "outline": _line(_hex("#d92d20"), 1.6)}
    return [
        _layer("CityView_roads", "المرور · شبكة الطرق", *u(S.ROADS), roads, _pop("{Name}", ("Corridor", "Road_Class", "Lanes", "Speed_Limit", "Oneway")), visible=True),
        congestion_layer(traffic_item),
        _layer("CityView_metro_lines", "خطوط المترو", *u(S.METRO_LINES), metro, _pop("{Name}", ("Terminals",))),
        _layer("CityView_metro_stations", "محطات المترو", *u(S.METRO_STATIONS), stations, _pop("{Name}", ("Line_Name", "Station_Type"))),
        _layer("CityView_bus_routes", "مسارات الحافلات", *u(S.BUS_ROUTES), _simple(_line([56, 189, 248, 191], 1.4)), _pop("المسار {Route_No}", ("Direction", "Origin", "Destination"))),
        _layer("CityView_bus_stops", "محطات الحافلات", *u(S.BUS_STOPS), _simple(_pt([56, 189, 248, 242], [255, 255, 255, 255], 4.5, 0.6)), _pop("{Name}", ("Route_ID", "Direction", "Shelter")), min_scale=90000),
        _layer("CityView_hospitals", "المستشفيات", *u(S.EMERGENCY), _simple(hospital), _pop("{Name}", ("Kind", "Beds", "Note")), where="Kind = 'hospital'"),
        _layer("CityView_closures", "الإغلاقات المخطط لها", *u(S.CLOSURES), closure, _pop("{Corridor} · {Status}", ("Section", "Lanes_Closed", "Full_Closure", "Start_Time", "End_Time", "Reason"))),
        _layer("CityView_events", "إشعارات الفعاليات", *u(S.EVENT_NOTICES), _simple(_pt([181, 23, 158, 235], [255, 255, 255, 255], 11)), _pop("{Name}", ("Venue", "Attendance", "Start_Time", "End_Time", "Status"))),
    ]


def build(reference: dict, layers: list) -> dict:
    """The new web map: the Field Maps map's basemap and view, with the strategic layers (changes below incidents)."""
    return {"operationalLayers": layers, "tables": [], "baseMap": reference["baseMap"], "initialState": reference.get("initialState", {}),
            "spatialReference": reference.get("spatialReference", {"wkid": 102100}), "authoringApp": "ArcGISMapViewer", "authoringAppVersion": "",
            "timeZone": "system", "version": "2.31"}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--update", help="id of the strategic web map this script made earlier: replace its layers (a backup is saved first)")
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
              (lambda u, i: data_layer("WorkOrders_tasks", "أوامر العمل", u, i), S.WORK_ORDERS),
              (lambda u, i: data_layer("CityView_verification", "التحقق الميداني", u, i), S.VERIFICATION)]
    for lid, title, name, where in COUNT_LAYERS:
        makers.append(((lambda u, i, lid=lid, title=title, where=where: count_layer(lid, title, u, i, where)), name))
    def url_of(name):
        return gw.layer(name).url, gw._item(name).id

    layers.extend(transport_layers(url_of, gis.content.get(TRAFFIC_ITEM)))                          # drawn first = underneath, like the Strategic page
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
    if args.update:
        m = gis.content.get(args.update)
        if m is None or m.title != TITLE or m.owner != gis.users.me.username:
            sys.exit("Refused: --update only changes the strategic web map this project created.")
        backup = ROOT / "data" / "backups" / f"webmap_{m.id[:8]}_{datetime.now():%Y%m%d_%H%M%S}.json"
        backup.write_text(json.dumps(m.get_data(), ensure_ascii=False, indent=1), encoding="utf-8")
        m.update(data=json.dumps(new))
        print("Updated web map:", m.id, "backup:", backup.name)
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
