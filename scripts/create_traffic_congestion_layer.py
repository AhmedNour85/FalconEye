"""Publish the modelled traffic of ONE hour as a NEW hosted layer, so the ArcGIS dashboard map can draw congestion like the Strategic page does.

    python scripts/create_traffic_congestion_layer.py --hour 12            # DRY RUN: builds the model, prints the counts, writes nothing
    python scripts/create_traffic_congestion_layer.py --hour 12 --apply    # creates ONE new private hosted layer (CityView Traffic Congestion)
    python scripts/create_traffic_congestion_layer.py --hour 12 --apply --refresh <item id>   # replaces the features of that layer (same layer, new hour)

Only the congested segments (busy, heavy, severe) are stored; free-flowing roads stay the green network drawn by the roads layer. The data is MODELLED, not measured.
Nothing else in ArcGIS Online is changed, and the app's own layers are not touched (this layer is not part of the app's schema).
"""
import argparse
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TITLE = "CityView Traffic Congestion"
SERVICE = "CityView_Traffic_Congestion"
TAGS = "CityView-Riyadh,SYNTHETIC-DEMO,Falcon Eye,modelled traffic"
LEVEL = {"slow": "Busy", "heavy": "Heavy", "stopped": "Severe"}          # the Strategic page's own words for the three congested classes
FIELDS = [("Segment_ID", "esriFieldTypeString", 64), ("Name", "esriFieldTypeString", 200), ("Corridor", "esriFieldTypeString", 200), ("Road_Class", "esriFieldTypeString", 40),
          ("Level", "esriFieldTypeString", 16), ("VC_Ratio", "esriFieldTypeDouble", None), ("Hour", "esriFieldTypeInteger", None), ("Modelled_At", "esriFieldTypeString", 40),
          ("Note", "esriFieldTypeString", 200)]
NOTE = "Modelled, not measured: a static traffic assignment of synthetic demand on the road network"


def build(hour: int) -> dict:
    """GeoJSON of the congested segments at `hour` (pure of ArcGIS: it only runs the local traffic model)."""
    from backend.mobility import traffic

    roads = {f["id"]: f for f in traffic.roads_geojson()["features"]}
    st = traffic.state(hour)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    feats = []
    for sid, (vc, cls) in st["segments"].items():
        r = roads.get(sid)
        if not r:
            continue
        p = r["properties"]
        feats.append({"type": "Feature", "geometry": r["geometry"],
                      "properties": {"Segment_ID": sid, "Name": p.get("name") or "", "Corridor": p.get("corridor") or "", "Road_Class": p.get("road_class") or "",
                                     "Level": LEVEL[cls], "VC_Ratio": vc, "Hour": hour, "Modelled_At": now, "Note": NOTE}})
    return {"type": "FeatureCollection", "features": feats, "counts": st["counts"]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--hour", type=int, default=12)
    ap.add_argument("--all-hours", action="store_true", help="store all 24 hours (the dashboard then picks one with a selector on the Hour field)")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--refresh", help="id of the congestion layer this script made earlier: replace its features")
    args = ap.parse_args(argv)
    from backend.mobility import traffic
    traffic.warm(wait=False)
    hours = range(24) if args.all_hours else [args.hour]
    gj = {"type": "FeatureCollection", "features": []}
    for h in hours:
        g = build(h)
        gj["features"] += g["features"]
        by = {}
        for f in g["features"]:
            by[f["properties"]["Level"]] = by.get(f["properties"]["Level"], 0) + 1
        print(f"hour {h:02d}:00 -> {len(g['features'])} congested segments {by}")
    gj["counts"] = {}
    print("total features:", len(gj["features"]))
    if not args.apply:
        print("DRY RUN: nothing was written.")
        return 0
    from backend.gis.agol import ArcGISGateway
    from config.settings import load_settings

    settings = load_settings()
    if not TITLE.startswith(settings.arcgis_layer_prefix):
        sys.exit("Refused: the title must start with the project prefix.")
    gis = ArcGISGateway(settings).gis
    me = gis.users.me.username
    path = Path(tempfile.mkdtemp()) / f"{SERVICE}.geojson"
    path.write_text(json.dumps({"type": "FeatureCollection", "features": gj["features"]}), encoding="utf-8")
    if args.refresh:
        item = gis.content.get(args.refresh)
        if item is None or item.title != TITLE or item.owner != me:
            sys.exit("Refused: --refresh only replaces the congestion layer this script created (matching title and owner).")
        layer = item.layers[0]
        old = layer.query(where="1=1", return_ids_only=True)["objectIds"]
        if old:
            layer.delete_features(deletes=",".join(str(i) for i in old))
        def paths(g):          # GeoJSON LineString -> one path, MultiLineString -> several
            return [g["coordinates"]] if g["type"] == "LineString" else g["coordinates"]

        feats = [{"attributes": {("Level_" if k == "Level" else k): v for k, v in f["properties"].items()},          # ArcGIS stores the field as Level_ (Level is reserved)
                   "geometry": {"paths": paths(f["geometry"]), "spatialReference": {"wkid": 4326}}} for f in gj["features"]]
        for i in range(0, len(feats), 500):
            layer.edit_features(adds=feats[i:i + 500])
        print("Refreshed:", item.id, "features:", len(feats))
        return 0
    if gis.content.search(f'title:"{TITLE}" AND owner:{me}', item_type="Feature Service"):
        sys.exit("Refused: the congestion layer already exists (use --refresh <id>). Nothing was changed.")
    src = gis.content.add({"title": SERVICE + "_source", "type": "GeoJson", "tags": TAGS}, data=str(path))
    try:
        item = src.publish(publish_parameters={"name": SERVICE, "locationType": "none", "hasStaticData": False, "layerInfo": {"capabilities": "Query"}}, file_type="geojson")
    finally:
        src.delete()                                              # the temporary GeoJSON item this script just created
    item.update({"title": TITLE, "tags": TAGS, "snippet": "Modelled traffic congestion for one hour (busy, heavy, severe). Synthetic demo data, not measured."})
    print("Created:", item.id, item.url)
    return 0


if __name__ == "__main__":
    sys.exit(main())
