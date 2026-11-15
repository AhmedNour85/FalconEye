"""Everything the mobility engine reads from outside itself.

In Agentic_AI_Transportation the engine read a SQLite database (`backend.gis.store`), a hosted-layer reader
(`network_source`, `feature_source`) and two service modules. Here those are one module:

  * the road network: the hosted road layer when the store holds it, else `data/mobility/network.json.gz`
    (built from OpenStreetMap by `scripts/build_mobility_data.py`), else the 73-segment hand-placed skeleton;
  * hospitals and metro stations, for accessibility and for "what is near this closure";
  * the hourly demand profile and the distance function;
  * a small archive of scenario results, in memory. Nothing is written to this computer.
"""
from __future__ import annotations

import datetime as dt
import gzip
import hashlib
import json
import math
import threading
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from backend.mobility import riyadh_network as RN

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "mobility"
NETWORK_FILE = DATA / "network.json.gz"
RCRC_DIR = DATA / "rcrc"

ATTRIBUTION = "© OpenStreetMap contributors (ODbL)"
RCRC_ATTRIBUTION = "Source: Royal Commission for Riyadh City (RCRC) open data, KSA Open Data License"
HOSPITAL_NOTE = "Approximate reference positions; bed counts are placeholders"

ROADS_LAYER = "Riyadh_Roads"
FACILITIES_LAYER = "Riyadh_Emergency_Facilities"
STATIONS_LAYER = "Riyadh_Metro_Stations"

CAP_PER_LANE = {"motorway": 1800, "arterial": 1500, "collector": 1200}
ARCHIVE_LIMIT = 50   # scenario results kept per kind

# Hourly demand factor (1.0 = peak). Riyadh working week Sun-Thu, weekend Fri-Sat (reduced).
HOURLY = [0.25, 0.15, 0.10, 0.10, 0.15, 0.30, 0.60, 0.90, 1.00, 0.85, 0.70, 0.70, 0.75, 0.80, 0.75, 0.80, 0.95,
          1.00, 0.98, 0.90, 0.80, 0.65, 0.50, 0.35]

_lock = threading.RLock()
_cfg: Dict = {"store": None, "network": "auto"}
_net: Optional[tuple] = None                 # (segments, nodes, provenance)
_inter: Optional[List[dict]] = None
_archive: Dict[str, Dict[str, dict]] = {}
_counters: Dict[str, int] = {}


# ---------------------------------------------------------------- small functions the engine imports
def haversine_km(a, b) -> float:
    (x1, y1), (x2, y2) = a, b
    p1, p2 = math.radians(y1), math.radians(y2)
    dphi, dl = p2 - p1, math.radians(x2 - x1)
    h = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371.0088 * 2 * math.asin(math.sqrt(h))


def demand_factor(hour: float, weekend: bool = False) -> float:
    h = hour % 24
    i, f = int(h), h - int(h)
    v = HOURLY[i] * (1 - f) + HOURLY[(i + 1) % 24] * f
    return v * (0.75 if weekend else 1.0)


# ---------------------------------------------------------------- configuration
def configure(store=None, network: str = "auto", force: bool = False) -> None:
    """`network`: "auto" (hosted layer, else the file, else the skeleton), "file" or "skeleton".
    A change that affects the roads drops the cached network and the cached model; `force` drops them anyway."""
    if network not in ("auto", "file", "skeleton"):
        raise ValueError('network must be "auto", "file" or "skeleton"')
    global _net, _inter
    with _lock:
        same = network == _cfg["network"] and (network != "auto" or store is _cfg["store"])   # only "auto" reads the roads from the store
        _cfg["store"], _cfg["network"] = store, network
        if same and not force:
            return
        _net = _inter = None
    from backend.mobility import network_model
    network_model.invalidate()


def _hosted(layer: str) -> List[dict]:
    """Rows of a hosted reference layer as flat dicts with a `geometry`, or [] when there is no store or the layer is empty."""
    store = _cfg["store"]
    if store is None:
        return []
    return [{**r["attrs"], "geometry": r["geom"]} for r in store.all(layer)]


# ---------------------------------------------------------------- the road network
def capacity(road_class: str, lanes: int) -> float:
    return float(CAP_PER_LANE.get(road_class, 1000) * lanes)


def road_row(s: dict) -> dict:
    """A builder segment (osm_network.build / build_network.build) as the row the model reads."""
    osm = str(s["id"]).startswith("osm-")
    attrs = {"oneway": bool(s.get("oneway"))}
    if osm:
        attrs["osm_name"] = s.get("osm_name") or ""
    else:
        attrs["geometry_note"] = "Approximate schematic alignment, not survey-grade"
    return {"id": s["id"], "name": s.get("name") or f"{s['corridor']} #{s['id'][-6:] if osm else s['id'][-2:]}",
            "corridor": s["corridor"], "road_class": s["road_class"], "lanes": int(s["lanes"]),
            "speed_limit": float(s["speed_limit"]), "length_km": float(s["length_km"]),
            "from_node": s["from_node"], "to_node": s["to_node"], "capacity": capacity(s["road_class"], int(s["lanes"])),
            "geometry": {"type": "LineString", "coordinates": s["coords"]}, "attributes": attrs}


def _end_nodes(segments: List[dict]) -> Dict[str, tuple]:
    """Junctions are the ends of the road segments; there is no separate junction layer."""
    nodes: Dict[str, tuple] = {}
    for s in segments:
        c = s["geometry"]["coordinates"]
        nodes.setdefault(s["from_node"], (c[0][0], c[0][1]))
        nodes.setdefault(s["to_node"], (c[-1][0], c[-1][1]))
    return nodes


def fingerprint(roads: List[dict]) -> str:
    """12-hex digest of the routing-relevant attributes; two copies of the network that agree give the same value."""
    rows = sorted((r["id"], r["lanes"], round(r["speed_limit"]), round(r["length_km"], 2), r["from_node"], r["to_node"]) for r in roads)
    return hashlib.sha1(json.dumps(rows, default=str).encode()).hexdigest()[:12]


def _provenance(source: str, roads: List[dict], nodes: dict, **more) -> dict:
    return {"source": source, "road_features": len(roads), "intersections": len(nodes), "fingerprint": fingerprint(roads),
            "loaded_at": dt.datetime.utcnow().isoformat(timespec="seconds") + "Z", **more}


def _skeleton() -> tuple:
    from backend.mobility import build_network
    roads = [road_row(s) for s in build_network.build()["segments"]]
    nodes = _end_nodes(roads)
    return roads, nodes, _provenance("skeleton", roads, nodes, label="Hand-placed corridor skeleton (approximate)",
                                     licence="none: drawn for this project")


def read_network_file(path: Path = NETWORK_FILE) -> dict:
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.load(f)


def _from_file() -> tuple:
    raw = read_network_file()
    roads = [road_row(s) for s in raw["segments"]]
    nodes = _end_nodes(roads)
    return roads, nodes, _provenance("file", roads, nodes, label="OpenStreetMap main roads", licence=ATTRIBUTION,
                                     built_at=raw.get("built_at"))


def _from_store() -> Optional[tuple]:
    rows = _hosted(ROADS_LAYER)
    if not rows:
        return None
    roads = []
    for r in rows:
        g = r.get("geometry") or {}
        coords = g.get("coordinates") or []
        if g.get("type") == "MultiLineString":
            coords = coords[0] if coords else []
        if len(coords) < 2 or not r.get("Segment_ID") or not r.get("From_Node") or not r.get("To_Node"):
            continue
        roads.append(road_row({"id": r["Segment_ID"], "name": r.get("Name"), "corridor": r.get("Corridor") or "", "road_class": r.get("Road_Class") or "collector",
                               "lanes": int(r.get("Lanes") or 1), "speed_limit": float(r.get("Speed_Limit") or 50), "length_km": float(r.get("Length_Km") or 0),
                               "from_node": r["From_Node"], "to_node": r["To_Node"], "coords": [[c[0], c[1]] for c in coords],
                               "oneway": str(r.get("Oneway")).strip().lower() in ("1", "true", "yes"), "osm_name": r.get("Osm_Name") or ""}))
    if not roads:
        return None
    nodes = _end_nodes(roads)
    return roads, nodes, _provenance("arcgis", roads, nodes, label="OpenStreetMap main roads (hosted layer)", licence=ATTRIBUTION, layer=ROADS_LAYER)


def load_network() -> Tuple[List[dict], Dict[str, tuple], dict]:
    """(road rows, {node id: (lon, lat)}, provenance). Cached until `configure` is called again."""
    global _net
    with _lock:
        if _net is None:
            mode = _cfg["network"]
            net = None
            if mode == "auto":
                net = _from_store()
            if net is None and mode in ("auto", "file") and NETWORK_FILE.exists():
                net = _from_file()
            if net is None:
                if mode == "file":
                    raise RuntimeError(f"{NETWORK_FILE} is missing: run scripts/build_mobility_data.py")
                net = _skeleton()
            _net = net
        return _net


# ---------------------------------------------------------------- what the engine used to read from the database
def list_hospitals() -> List[dict]:
    rows = [r for r in _hosted(FACILITIES_LAYER) if r.get("Kind") == "hospital" and r.get("geometry")]
    if rows:
        return [{"id": r["Facility_ID"], "name": r.get("Name") or r["Facility_ID"], "geometry": r["geometry"]} for r in rows]
    return [f for f in reference_facilities() if f["kind"] == "hospital"]


def reference_facilities() -> List[dict]:
    """Hospitals and emergency stations of the reference list, in the shape `list_hospitals` returns plus `kind`."""
    out = [{"id": f"HOSP-{i:02d}", "name": n, "kind": "hospital", "beds": beds, "geometry": {"type": "Point", "coordinates": [lon, lat]}}
           for i, (n, lon, lat, beds) in enumerate(RN.HOSPITALS, 1)]
    out += [{"id": f"EMS-{i:02d}", "name": n, "kind": kind, "beds": None, "geometry": {"type": "Point", "coordinates": [lon, lat]}}
            for i, (n, kind, lon, lat) in enumerate(RN.EMERGENCY, 1)]
    return out


def rcrc(name: str) -> Optional[dict]:
    """One of the RCRC open-data files (metro_lines, metro_stations, bus_routes, bus_stops), or None when it is not there."""
    p = RCRC_DIR / f"{name}.geojson"
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def _metro_stations() -> List[dict]:
    rows = [r for r in _hosted(STATIONS_LAYER) if r.get("geometry")]
    if rows:
        return [{"id": r["Station_ID"], "name": r.get("Name") or r["Station_ID"], "geometry": r["geometry"]} for r in rows]
    fc = rcrc("metro_stations")
    if fc:
        return [{"id": str(f["properties"].get("metro_station_cd") or i), "name": f["properties"].get("metro_station_desc_en") or "", "geometry": f["geometry"]}
                for i, f in enumerate(fc["features"]) if f.get("geometry")]
    return [{"id": f"{code}-{i}", "name": n, "geometry": {"type": "Point", "coordinates": [lon, lat]}}
            for code, _, _, stations in RN.METRO for i, (n, lon, lat) in enumerate(stations)]


def _intersections() -> List[dict]:
    global _inter
    with _lock:
        if _inter is None:
            roads, nodes, _ = load_network()
            names: Dict[str, list] = {}
            for s in roads:
                for n in (s["from_node"], s["to_node"]):
                    c = names.setdefault(n, [])
                    if s["corridor"] not in c:
                        c.append(s["corridor"])
            _inter = [{"id": n, "name": " x ".join(sorted(names.get(n, []))[:2]), "geometry": {"type": "Point", "coordinates": list(p)}} for n, p in nodes.items()]
        return _inter


def list_(kind: str) -> List[dict]:
    if kind == "Intersection":
        return _intersections()
    if kind == "MetroStation":
        return _metro_stations()
    with _lock:
        return list(_archive.get(kind, {}).values())


# ---------------------------------------------------------------- scenario archive (memory only)
def new_id(prefix: str) -> str:
    with _lock:
        _counters[prefix] = _counters.get(prefix, 0) + 1
        return f"{prefix}-{_counters[prefix]:04d}"


def upsert_many(kind: str, rows: List[dict]) -> int:
    with _lock:
        box = _archive.setdefault(kind, {})
        for r in rows:
            box.pop(r["id"], None)
            box[r["id"]] = r
        while len(box) > ARCHIVE_LIMIT:
            box.pop(next(iter(box)))
    return len(rows)


def get(kind: str, id_: str) -> Optional[dict]:
    with _lock:
        return _archive.get(kind, {}).get(id_)


def audit(*_args, **_kw) -> None:
    """The Transportation engine wrote an audit row here. In Riyadh City View the crew writes the audit trail (Plan 3)."""
