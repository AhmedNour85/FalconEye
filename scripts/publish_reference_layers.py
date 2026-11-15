"""Fill the hosted mobility reference layers from the files in data/mobility. A DRY RUN unless --apply is given.

    python scripts/publish_reference_layers.py                 # dry run: rows in each hosted layer now, rows in the files, what would happen
    python scripts/publish_reference_layers.py --apply         # fills the layers that are empty
    python scripts/publish_reference_layers.py --apply --replace   # also empties and refills a layer whose rows differ from the files
    python scripts/publish_reference_layers.py Riyadh_Bus_Stops    # only these layers

The six layers: roads, metro lines, metro stations, bus routes, bus stops, emergency facilities. They must exist first
(scripts/create_feature_layers.py --apply). Only layers titled <prefix>_<layer> and owned by the signed-in account are used.
Without --replace no row is ever deleted. A running server reads these layers at start-up only: restart it afterwards.
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.gis.schema import LAYERS  # noqa: E402
from backend.mobility import transit  # noqa: E402
from config.settings import load_settings  # noqa: E402


def plan(gateway, only=None) -> list[dict]:
    """What each layer holds now and what the files hold. Reads only."""
    out = []
    for layer in transit.STATIC_LAYERS:
        if only and layer not in only:
            continue
        rows = transit.rows(layer)
        ids = [str(a[LAYERS[layer].id_field]) for a, _g in rows]
        step = {"layer": layer, "title": gateway.title(layer), "file_rows": len(rows), "rows": rows, "hosted_rows": None}
        if len(set(ids)) != len(ids):
            step["action"] = "bad_file"
            step["why"] = f"{len(ids) - len(set(ids))} repeated id(s) in the file rows"
        elif not rows:
            step["action"] = "no_file"
        elif not gateway.exists(layer):
            step["action"] = "missing"
        else:
            hosted = gateway.ids(layer)
            step["hosted_rows"] = len(hosted)
            if not hosted:
                step["action"] = "fill"
            elif hosted == set(ids):
                step["action"] = "same"
            else:
                step["action"] = "differs"
                step["only_hosted"], step["only_file"] = len(hosted - set(ids)), len(set(ids) - hosted)
        out.append(step)
    return out


WORDS = {"fill": "FILL", "same": "up to date, no change", "differs": "DIFFERS", "missing": "LAYER MISSING", "no_file": "NO FILE", "bad_file": "FILE REFUSED"}


def main(argv=None, gateway=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("layers", nargs="*", help="layer names (default: all six)")
    ap.add_argument("--apply", action="store_true", help="make the changes (default is a dry run)")
    ap.add_argument("--replace", action="store_true", help="with --apply: empty and refill a layer whose rows differ from the files")
    args = ap.parse_args(argv)
    unknown = [n for n in args.layers if n not in transit.STATIC_LAYERS]
    if unknown:
        print(f"Not a reference layer: {', '.join(unknown)}. Choose from: {', '.join(transit.STATIC_LAYERS)}")
        return 2
    if gateway is None:
        s = load_settings()
        if not s.arcgis_enabled:
            print("Set ARCGIS_USERNAME / ARCGIS_PASSWORD in .env first (scripts/make_env.py).")
            return 1
        from backend.gis.agol import ArcGISGateway

        gateway = ArcGISGateway(s)
    print(f"== {'APPLY' if args.apply else 'DRY RUN (nothing is changed)'} == account {getattr(gateway, 'owner', '?')}, prefix {gateway.prefix}\n")
    steps = plan(gateway, args.layers or None)
    print(f"  {'layer':40s} {'rows now':>9s} {'rows in files':>14s}  action")
    for st in steps:
        now = "-" if st["hosted_rows"] is None else str(st["hosted_rows"])
        note = {"differs": f" ({st.get('only_hosted', 0)} only hosted, {st.get('only_file', 0)} only in the files; " + ("will be emptied and refilled" if args.replace else "left alone without --replace") + ")",
                "missing": " (run scripts/create_feature_layers.py --apply first)", "no_file": " (run scripts/build_mobility_data.py first)",
                "bad_file": f" ({st.get('why')})"}.get(st["action"], "")
        print(f"  {st['title']:40s} {now:>9s} {st['file_rows']:14d}  {WORDS[st['action']]}{note}")
    todo = [st for st in steps if st["action"] == "fill" or (st["action"] == "differs" and args.replace)]
    adds = sum(st["file_rows"] for st in todo)
    deletes = sum(st["hosted_rows"] or 0 for st in todo if st["action"] == "differs")
    print(f"\n{len(todo)} layer(s) to write: {adds:,} row(s) to add, {deletes:,} row(s) to delete.")
    if not args.apply:
        print("Dry run only. Run again with --apply to make these changes.")
        return 0
    failed = 0
    for st in todo:
        layer, t0 = st["layer"], time.time()
        try:
            if st["action"] == "differs":
                gateway.truncate(layer)
            gateway.apply_many(layer, st["rows"], [], [])
            back = len(gateway.ids(layer))               # read back from the record
        except Exception as exc:  # noqa: BLE001  one layer failing must not hide the state of the others
            failed += 1
            print(f"  FAILED {st['title']}: {exc}")
            continue
        ok = back == st["file_rows"]
        failed += 0 if ok else 1
        print(f"  {'wrote ' if ok else 'INCOMPLETE '}{st['title']:40s} {back:,} of {st['file_rows']:,} rows in ArcGIS Online ({time.time() - t0:.0f} s)")
    blocked = [st for st in steps if st["action"] in ("missing", "no_file", "bad_file")]
    if failed or blocked:
        print(f"\nNot complete: {failed} layer(s) failed or are incomplete, {len(blocked)} could not be started. Running the script again is safe: it only fills empty layers.")
        return 3
    print("\nDone. Restart the app so it reads the reference layers.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
