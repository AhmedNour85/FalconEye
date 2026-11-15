"""Add the two Traffic Response investigators to the hosted Field Workers layer. A DRY RUN unless --apply is given.

    python scripts/add_mobility_demo_rows.py            # dry run: shows which of the two rows are missing
    python scripts/add_mobility_demo_rows.py --apply    # adds the missing rows

It adds at most two rows (WRK-008, WRK-009), changes no existing row and deletes nothing. Running it again is safe.
Only the layer titled <prefix>_Riyadh_Field_Workers and owned by the signed-in account is used. Reset demo and
scripts/initialize_demo.py --apply create the same two rows, so this script is only needed for an account loaded before them.
A running server picks the new rows up at its next refresh.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.gis import schema as S  # noqa: E402
from backend.services import synthetic  # noqa: E402
from config.settings import load_settings  # noqa: E402


def main(argv=None, gateway=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="add the rows (default is a dry run)")
    args = ap.parse_args(argv)
    if gateway is None:
        s = load_settings()
        if not s.arcgis_enabled:
            print("Set ARCGIS_USERNAME / ARCGIS_PASSWORD in .env first (scripts/make_env.py).")
            return 1
        from backend.gis.agol import ArcGISGateway

        gateway = ArcGISGateway(s)
    print(f"== {'APPLY' if args.apply else 'DRY RUN (nothing is changed)'} == account {getattr(gateway, 'owner', '?')}, prefix {gateway.prefix}\n")
    title = gateway.title(S.WORKERS)
    if not gateway.exists(S.WORKERS):
        print(f"  {title}: LAYER MISSING (run scripts/create_feature_layers.py --apply first)")
        return 3
    have = gateway.ids(S.WORKERS)
    rows = synthetic.traffic_response_workers()
    todo = [(a, g) for a, g in rows if a["Worker_ID"] not in have]
    print(f"  {title}: {len(have)} row(s) now")
    for a, _g in rows:
        print(f"    {a['Worker_ID']}  {a['Name']:20s} {a['Team']:18s} {'already there, no change' if a['Worker_ID'] in have else 'ADD'}")
    print(f"\n{len(todo)} to add, 0 to change, 0 to delete.")
    if not args.apply:
        print("Dry run only. Run again with --apply to make these changes.")
        return 0
    if todo:
        try:
            gateway.apply_many(S.WORKERS, todo, [], [])
        except Exception as exc:  # noqa: BLE001
            print(f"  FAILED {title}: {exc}")
            return 3
    back = gateway.ids(S.WORKERS)                              # read back from the record
    missing = [a["Worker_ID"] for a, _g in rows if a["Worker_ID"] not in back]
    if missing:
        print(f"  INCOMPLETE: {', '.join(missing)} not in ArcGIS Online after the write.")
        return 3
    print(f"  {title}: {len(back)} row(s) now. Both investigators are in ArcGIS Online.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
