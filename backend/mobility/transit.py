"""The reference layers of the mobility map: roads, metro, bus and emergency facilities.

`rows(layer)` gives each layer as (attributes, geometry) pairs built from the files in data/mobility. The publish script
sends exactly these rows to the hosted layers, and the API serves them when the hosted layer is not there (tests, development).
`geojson(kind, store)` is what the map asks for: the hosted layer when the store holds it, else the files.
The roads the map draws are not served from here: they must be the network the traffic model runs on (`traffic.roads_geojson`).
"""
from __future__ import annotations

from typing import Dict, List, Tuple

from backend.mobility import sources

ROADS, METRO_LINES, METRO_STATIONS = "Riyadh_Roads", "Riyadh_Metro_Lines", "Riyadh_Metro_Stations"
BUS_ROUTES, BUS_STOPS, FACILITIES = "Riyadh_Bus_Routes", "Riyadh_Bus_Stops", "Riyadh_Emergency_Facilities"
STATIC_LAYERS = (ROADS, METRO_LINES, METRO_STATIONS, BUS_ROUTES, BUS_STOPS, FACILITIES)

OSM = "OSM-REAL (c) OpenStreetMap contributors, ODbL"
RCRC = "RCRC-OPEN-DATA (KSA Open Data License)"
APPROX = "REFERENCE-APPROXIMATE"

# what the map asks for -> (layer, source text, licence text)
KINDS: Dict[str, tuple] = {
    "metro_lines": (METRO_LINES, "Royal Commission for Riyadh City (RCRC) open data", "KSA Open Data License"),
    "metro_stations": (METRO_STATIONS, "Royal Commission for Riyadh City (RCRC) open data", "KSA Open Data License"),
    "bus_routes": (BUS_ROUTES, "Royal Commission for Riyadh City (RCRC) open data", "KSA Open Data License"),
    "bus_stops": (BUS_STOPS, "Royal Commission for Riyadh City (RCRC) open data", "KSA Open Data License"),
    "hospitals": (FACILITIES, "Reference list of this project: positions are approximate and bed counts are placeholders", "none"),
}


def _s(v) -> str:
    """Text for a hosted field: None and the files' "NA" become empty."""
    return "" if v is None or v == "NA" else str(v)


def _rcrc(name: str) -> List[dict]:
    fc = sources.rcrc(name)
    return [f for f in (fc or {}).get("features", []) if f.get("geometry")]


def road_attrs(r: dict) -> dict:
    return {"Segment_ID": r["id"], "Name": r["name"], "Corridor": r["corridor"], "Road_Class": r["road_class"], "Lanes": r["lanes"],
            "Speed_Limit": r["speed_limit"], "Length_Km": r["length_km"], "From_Node": r["from_node"], "To_Node": r["to_node"],
            "Oneway": "Yes" if (r.get("attributes") or {}).get("oneway") else "No", "Osm_Name": (r.get("attributes") or {}).get("osm_name", ""),
            "Data_Classification": OSM if str(r["id"]).startswith("osm-") else APPROX}


def rows(layer: str) -> List[Tuple[dict, dict]]:
    """(attributes, GeoJSON geometry) for every row of a reference layer, from the files in data/mobility."""
    if layer == ROADS:
        if not sources.NETWORK_FILE.exists():
            return []
        return [(road_attrs(r), r["geometry"]) for r in (sources.road_row(s) for s in sources.read_network_file()["segments"])]
    if layer == METRO_LINES:
        return [({"Line_ID": _s(p.get("metro_line_cd")), "Name": _s(p.get("metro_line_desc_en")), "Name_AR": _s(p.get("metro_line_desc_ar")),
                  "Color": _s(p.get("metro_line_color_cd")), "Terminals": _s(p.get("metro_terminal_stations")), "Terminals_AR": _s(p.get("metro_terminal_stations_ar")),
                  "Data_Classification": RCRC}, f["geometry"]) for f in _rcrc("metro_lines") for p in [f["properties"]]]
    if layer == METRO_STATIONS:
        # an interchange station is one row per line in the RCRC file (94 rows, 83 station codes), so the id carries the line
        return [({"Station_ID": f"{_s(p.get('metro_station_cd'))}-{_s(p.get('metro_line_cd'))}", "Station_Code": _s(p.get("metro_station_cd")),
                  "Name": _s(p.get("metro_station_desc_en")), "Name_AR": _s(p.get("metro_station_desc_ar")),
                  "Line_ID": _s(p.get("metro_line_cd")), "Line_Name": _s(p.get("metro_line_desc_en")), "Station_Type": _s(p.get("metro_station_type_desc_en")),
                  "Data_Classification": RCRC}, f["geometry"]) for f in _rcrc("metro_stations") for p in [f["properties"]]]
    if layer == BUS_ROUTES:
        return [({"Route_ID": _s(p.get("busroutecode")), "Route_No": _s(p.get("busroute")), "Direction": _s(p.get("direction")), "Origin": _s(p.get("origin")),
                  "Destination": _s(p.get("destination")), "Origin_AR": _s(p.get("originar")), "Destination_AR": _s(p.get("destinationar")),
                  "Data_Classification": RCRC}, f["geometry"]) for f in _rcrc("bus_routes") for p in [f["properties"]]]
    if layer == BUS_STOPS:
        return [({"Stop_ID": _s(p.get("busstopcode")), "Name": _s(p.get("busstopname")), "Name_AR": _s(p.get("busstopnamear")), "Shelter": _s(p.get("bsheltertype")),
                  "Route_ID": _s(p.get("busroutecode")), "Direction": _s(p.get("direction")), "Sequence": p.get("sequence"),
                  "Data_Classification": RCRC}, f["geometry"]) for f in _rcrc("bus_stops") for p in [f["properties"]]]
    if layer == FACILITIES:
        return [({"Facility_ID": f["id"], "Name": f["name"], "Kind": f["kind"], "Beds": f["beds"], "Note": sources.HOSPITAL_NOTE, "Data_Classification": APPROX},
                 f["geometry"]) for f in sources.reference_facilities()]
    raise KeyError(layer)


def geojson(kind: str, store=None) -> dict:
    """FeatureCollection for the map, with `source` and `licence`. The hosted layer is used when the store holds rows of it."""
    layer, source, licence = KINDS[kind]
    held = store.all(layer) if store is not None else []
    if held:
        feats = [{"type": "Feature", "id": r["id"], "geometry": r["geom"], "properties": r["attrs"]} for r in held if r.get("geom")]
        origin = "arcgis"
    else:
        feats = [{"type": "Feature", "id": next(iter(a.values())), "geometry": g, "properties": a} for a, g in rows(layer)]   # the id field comes first
        origin = "files"
    if kind == "hospitals":
        feats = [f for f in feats if f["properties"].get("Kind") == "hospital"]
    return {"type": "FeatureCollection", "features": feats, "source": source, "licence": licence, "read_from": origin,
            "credit": sources.RCRC_ATTRIBUTION if "RCRC" in source else sources.HOSPITAL_NOTE}
