"""Build the mobility reference data from the Agentic_AI_Transportation project's files. Reads only; writes to data/mobility/.

    python scripts/build_mobility_data.py                          # the Transportation project next to this one
    python scripts/build_mobility_data.py --transportation <path>

Writes:
    data/mobility/network.json.gz           main roads of Riyadh as a routable network (from OpenStreetMap)
    data/mobility/rcrc/*.geojson            metro lines and stations, bus routes and stops (RCRC open data), unchanged
    data/mobility/NOTICE.md                 where each file comes from and under which licence

Nothing is sent to ArcGIS Online here. `scripts/publish_reference_layers.py` does that, as a dry run first.
"""
import argparse
import datetime as dt
import gzip
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.mobility import osm_network, sources  # noqa: E402

RCRC_FILES = ("metro_lines", "metro_stations", "bus_routes", "bus_stops")
KEEP = ("id", "corridor", "road_class", "lanes", "speed_limit", "length_km", "from_node", "to_node", "coords", "oneway", "osm_name")


def build_network(raw_path: Path, out: Path) -> dict:
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    net = osm_network.build(raw)
    doc = {"source": "OpenStreetMap via Overpass (file data_store/overpass_raw.json of Agentic_AI_Transportation)", "attribution": sources.ATTRIBUTION,
           "built_at": dt.datetime.utcnow().isoformat(timespec="seconds") + "Z", "stats": net["stats"],
           "segments": [{k: s[k] for k in KEEP} for s in sorted(net["segments"], key=lambda s: s["id"])]}
    out.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(out, "wt", encoding="utf-8", compresslevel=9) as f:
        json.dump(doc, f, separators=(",", ":"))
    return net["stats"]


def copy_rcrc(src: Path, out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    counts = {}
    for name in RCRC_FILES:
        p = src / f"{name}.geojson"
        counts[name] = len(json.loads(p.read_text(encoding="utf-8"))["features"])
        shutil.copyfile(p, out / p.name)
    return counts


def notice(stats: dict, counts: dict, rcrc_notice: dict) -> str:
    rows = "\n".join(f"| `rcrc/{n}.geojson` | {c:,} | RCRC open data | {rcrc_notice.get('license', 'KSA Open Data License')} |" for n, c in counts.items())
    return f"""# Mobility reference data

Built by `scripts/build_mobility_data.py` on {dt.date.today().isoformat()} from the files of the `Agentic_AI_Transportation` project.

| File | Rows | Source | Licence |
|---|---|---|---|
| `network.json.gz` | {stats['segments']:,} road segments, {stats['nodes']:,} junctions | OpenStreetMap, main roads only (motorway to secondary, with their ramps) | ODbL. Credit: {sources.ATTRIBUTION} |
{rows}

RCRC is the Royal Commission for Riyadh City. Licence text: {rcrc_notice.get('license_url', '')}. The files were retrieved on {rcrc_notice.get('retrieved', 'an unknown date')}.
Credit to show wherever this data is displayed: "{rcrc_notice.get('attribution', sources.RCRC_ATTRIBUTION)}".

Not in these files: hospital and emergency-station positions. Those are approximate reference positions kept in
`backend/mobility/riyadh_network.py`, and bed counts are placeholders.

Traffic volumes and speeds are not data. The model calculates them from this network and a synthetic demand profile.
"""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--transportation", default=str(ROOT.parent / "Agentic_AI_Transportation"), help="folder of the Agentic_AI_Transportation project")
    ap.add_argument("--out", default=str(sources.DATA), help="output folder (default data/mobility)")
    args = ap.parse_args(argv)
    src, out = Path(args.transportation), Path(args.out)
    raw, rcrc = src / "data_store" / "overpass_raw.json", src / "backend" / "data" / "rcrc"
    missing = [str(p) for p in [raw] + [rcrc / f"{n}.geojson" for n in RCRC_FILES] if not p.exists()]
    if missing:
        print("Missing source files:\n  " + "\n  ".join(missing))
        return 1
    stats = build_network(raw, out / "network.json.gz")
    counts = copy_rcrc(rcrc, out / "rcrc")
    np_ = rcrc / "NOTICE.json"
    (out / "NOTICE.md").write_text(notice(stats, counts, json.loads(np_.read_text(encoding="utf-8")) if np_.exists() else {}), encoding="utf-8")
    print(f"network.json.gz    {stats['segments']:,} road segments, {stats['nodes']:,} junctions (from {stats['ways']:,} OpenStreetMap ways; "
          f"{stats['dropped_not_strongly_connected']:,} segments dropped as duplicates or not connected)")
    for n, c in counts.items():
        print(f"rcrc/{n + '.geojson':24s} {c:,} features")
    print(f"\nLicences: roads {sources.ATTRIBUTION}; metro and bus: {sources.RCRC_ATTRIBUTION}.")
    print(f"Written to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
