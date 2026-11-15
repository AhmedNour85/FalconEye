"""Create the hosted feature layers (one per data-model layer) in ArcGIS Online. A DRY RUN unless --apply is given.

    python scripts/create_feature_layers.py                      # dry run: lists what would be created or changed
    python scripts/create_feature_layers.py --apply              # creates the missing layers and adds missing fields
    python scripts/create_feature_layers.py Riyadh_Work_Orders   # only these layers

Only items titled <prefix>_<layer> and owned by the signed-in account are looked at. Existing rows are never touched and
nothing is ever deleted.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import load_settings  # noqa: E402

WORDS = {"create": "CREATE", "define": "DEFINE (empty service)", "add_fields": "ADD FIELDS", "exists": "exists, no change"}


def main(argv=None, gateway=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("layers", nargs="*", help="layer names (default: all)")
    ap.add_argument("--apply", action="store_true", help="make the changes (default is a dry run)")
    args = ap.parse_args(argv)
    if gateway is None:
        s = load_settings()
        if not s.arcgis_enabled:
            print("Set ARCGIS_USERNAME / ARCGIS_PASSWORD in .env first (scripts/make_env.py).")
            return 1
        from backend.gis.agol import ArcGISGateway

        gateway = ArcGISGateway(s)
    print(f"== {'APPLY' if args.apply else 'DRY RUN (nothing is changed)'} == account {getattr(gateway, 'owner', '?')}, prefix {gateway.prefix}\n")
    plan = gateway.create_layers(args.layers or None, dry_run=not args.apply)
    for p in plan:
        extra = f" {p['fields']}" if p["action"] == "add_fields" else f" ({len(p['fields'])} fields)" if p["action"] in ("create", "define") else ""
        track = "  NO EDIT TRACKING" if p.get("tracking") is False else ""
        print(f"  {WORDS[p['action']]:24s} {p['title']:46s}{extra}{'  item ' + p['item_id'] if p.get('item_id') else ''}{track}")
    if any(p.get("tracking") is False for p in plan):
        print("\n  Layers marked NO EDIT TRACKING have no EditDate. " + ("Switching it on did not take effect; the app will read those layers in full on each refresh."
                                                                         if args.apply else "--apply switches it on and reads the result back."))
    counts = {a: sum(1 for p in plan if p["action"] == a) for a in WORDS}
    print(f"\n{counts['create']} to create, {counts['define']} to define, {counts['add_fields']} to add fields to, {counts['exists']} unchanged.")
    if not args.apply:
        print("Dry run only. Run again with --apply to make these changes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
