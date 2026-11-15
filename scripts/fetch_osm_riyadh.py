"""Download REAL OpenStreetMap roads and building footprints for the demo areas (and the King Fahd Road / Olaya Street corridors)
and cache them in data/samples/osm_riyadh.json.gz. The app reads only this cache at runtime (no live OSM dependency).

    python scripts/fetch_osm_riyadh.py [--radius 1450]

Data (c) OpenStreetMap contributors, licensed ODbL: https://www.openstreetmap.org/copyright
"""
import argparse
import gzip
import json
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.gis import geo  # noqa: E402
from backend.services.synthetic import AREAS  # noqa: E402

ENDPOINTS = ["https://overpass.openstreetmap.fr/api/interpreter", "https://overpass.osm.ch/api/interpreter", "https://overpass-api.de/api/interpreter"]
HEADERS = {"User-Agent": "geoai-riyadh-demo/1.0"}
HIGHWAYS = "motorway|trunk|primary|secondary|tertiary|unclassified|residential|service|living_street|motorway_link|trunk_link|primary_link|secondary_link|tertiary_link"
CORRIDOR_QUERIES = {
    "King Fahd Road": '["name:en"~"King Fahd R",i]',
    "King Fahd Road (ar)": '["name"~"طريق الملك فهد"]',
    "Olaya Street": '["name:en"~"Olaya (Street|St)",i]',
    "Olaya Street (ar)": '["name"~"شارع العليا"]',
}


def overpass(query: str) -> dict:
    last = None
    for attempt in range(3):
        for ep in ENDPOINTS:
            try:
                req = urllib.request.Request(ep, data=urllib.parse.urlencode({"data": query}).encode(), headers=HEADERS)
                with urllib.request.urlopen(req, timeout=120) as r:
                    return json.loads(r.read())
            except Exception as exc:  # try the next mirror
                last = f"{ep}: {exc}"
                print("  ", last, file=sys.stderr)
        time.sleep(5 * (attempt + 1))
    raise SystemExit(f"all Overpass endpoints failed; last: {last}")


def way_coords(el: dict) -> list[list[float]]:
    return [[round(p["lon"], 6), round(p["lat"], 6)] for p in el.get("geometry", []) if p]


def way_nodes(el: dict) -> list[int]:
    """Node ids aligned with way_coords (points clipped by the bbox come back as null and are dropped from both)."""
    return [n for n, p in zip(el.get("nodes", []), el.get("geometry", [])) if p]


def parse(data: dict, roads: dict, buildings: dict) -> None:
    for el in data.get("elements", []):
        if el.get("type") != "way" or "geometry" not in el:
            continue
        t = el.get("tags", {})
        c = way_coords(el)
        if "highway" in t and len(c) >= 2:
            roads[el["id"]] = {"id": el["id"], "highway": t["highway"], "name": t.get("name:en") or t.get("name") or "", "name_ar": t.get("name", ""),
                               "oneway": t.get("oneway", ""), "coords": c, "nodes": way_nodes(el)}
        elif "building" in t and len(c) >= 4 and c[0] == c[-1]:
            if len(c) > 14:  # keep the file small: thin out vertices of complex footprints
                step = max(1, len(c) // 12)
                c = c[::step] + [c[0]]
            buildings[el["id"]] = {"id": el["id"], "name": t.get("name:en") or t.get("name") or "", "type": t["building"], "ring": c}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--radius", type=float, default=1450.0)
    a = ap.parse_args()
    roads: dict = {}
    buildings: dict = {}
    area_ids: dict[str, dict] = {}
    for name, ar in AREAS.items():
        sw, ne = geo.offset(ar["center"], -a.radius, -a.radius), geo.offset(ar["center"], a.radius, a.radius)
        bb = f"{sw[1]:.5f},{sw[0]:.5f},{ne[1]:.5f},{ne[0]:.5f}"
        print(f"{name}: bbox {bb}")
        q = f'[out:json][timeout:150];(way["highway"~"^({HIGHWAYS})$"]({bb});way["building"]({bb}););out geom;'
        r0, b0 = len(roads), len(buildings)
        parse(overpass(q), roads, buildings)
        print(f"   +{len(roads) - r0} road ways, +{len(buildings) - b0} buildings")
        time.sleep(2)
    corridors: dict[str, list[int]] = {}
    for label, flt in CORRIDOR_QUERIES.items():
        key = label.split(" (")[0]
        print(f"corridor {label}")
        d = overpass(f'[out:json][timeout:150];way["highway"]{flt}(24.50,46.50,24.90,46.85);out geom;')
        before = set(roads)
        parse(d, roads, buildings)
        corridors.setdefault(key, [])
        corridors[key] += [el["id"] for el in d.get("elements", []) if el.get("type") == "way" and el["id"] in roads]
        print(f"   {len(corridors[key])} ways")
        time.sleep(2)
    out = {"source": "OpenStreetMap contributors (ODbL)", "fetched": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "radius_m": a.radius,
           "roads": list(roads.values()), "buildings": list(buildings.values()), "corridors": {k: sorted(set(v)) for k, v in corridors.items()}}
    if not roads or not buildings:
        raise SystemExit("download returned no roads/buildings - not saving an empty cache")
    p = ROOT / "data" / "samples" / "osm_riyadh.json.gz"
    p.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(p, "wt", encoding="utf-8") as f:
        json.dump(out, f, separators=(",", ":"))
    print(f"saved {p} ({p.stat().st_size / 1e6:.1f} MB): {len(roads)} roads, {len(buildings)} buildings, corridors { {k: len(v) for k, v in out['corridors'].items()} }")


if __name__ == "__main__":
    main()
