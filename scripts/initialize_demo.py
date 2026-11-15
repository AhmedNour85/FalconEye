"""Fill the hosted layers with a clean, reproducible set of demo data. A DRY RUN unless --apply is given.

    python scripts/initialize_demo.py            # dry run: rows each layer holds now, and rows it would hold afterwards
    python scripts/initialize_demo.py --apply    # DELETES every row of the CityView layers, then loads the demo data

--apply has the same effect as the Reset demo button. It removes rows; it never removes a layer, a field or an item.
The mobility reference layers (roads, metro, bus, emergency facilities) are not touched.
Stop the app first: only one server may work on the layers at a time.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.gis import schema as S  # noqa: E402
from backend.gis.store import Store, StoreLockedError  # noqa: E402
from backend.services import synthetic  # noqa: E402
from config.settings import load_settings  # noqa: E402


DEMO_LAYERS = [n for n, d in S.LAYERS.items() if not d.static]   # the mobility reference layers are filled by publish_reference_layers.py and never emptied here


def planned_counts(seed: int) -> dict[str, int]:
    """Row count per layer of the demo data, worked out in memory. Nothing is sent anywhere."""
    st = Store()
    synthetic.generate(st, seed)
    return {name: st.count(name) for name in DEMO_LAYERS}


def main(argv=None, gateway=None, settings=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="delete the rows and load the demo data (default is a dry run)")
    args = ap.parse_args(argv)
    s = settings or load_settings()
    if gateway is None:
        if not s.arcgis_enabled:
            print("Set ARCGIS_USERNAME / ARCGIS_PASSWORD in .env first (scripts/make_env.py).")
            return 1
        from backend.gis.agol import ArcGISGateway

        gateway = ArcGISGateway(s)
    print(f"== {'APPLY' if args.apply else 'DRY RUN (nothing is changed)'} == account {getattr(gateway, 'owner', '?')}, prefix {gateway.prefix}\n")
    want = planned_counts(s.seed)
    if not args.apply:
        print(f"  {'layer':46s} {'rows now':>9s} {'rows after':>11s}")
        total_now = 0
        for name in DEMO_LAYERS:
            now = len(gateway.ids(name))
            total_now += now
            print(f"  {gateway.title(name):46s} {now:9d} {want[name]:11d}")
        print(f"\n--apply would DELETE {total_now} row(s) and load {sum(want.values())}. Rows added later by the app (alerts, audit log) are not counted in 'rows after'.")
        print("Dry run only. Run again with --apply to do it.")
        return 0
    from dataclasses import replace

    from backend.platform import Platform

    try:
        p = Platform(settings=replace(s, store="arcgis", field_sync_seconds=0), gateway=gateway, init=False)
    except StoreLockedError as exc:
        print(f"Refused: {exc}")
        return 5
    try:
        p.reset()
        print(f"  {'layer':46s} {'rows in ArcGIS Online':>22s}")
        for name in DEMO_LAYERS:
            n = len(gateway.ids(name))                     # read back from the record, not from memory
            if n:
                print(f"  {gateway.title(name):46s} {n:22d}")
    finally:
        p.store.release()
    print("\nDone. The demo data is in ArcGIS Online.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
