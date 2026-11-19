"""Add the Falcon Eye icon (data/falcon-eye-icon.png, drawn from frontend/falcon-eye.svg in the dashboard's brand green) as ONE private Image item, used as the dashboard header logo.

    python scripts/create_falcon_icon_item.py           # DRY RUN
    python scripts/create_falcon_icon_item.py --apply   # creates the private image item "CityView Falcon Eye Icon" (nothing is shared)
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
TITLE = "CityView Falcon Eye Icon"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args(argv)
    from backend.gis.agol import ArcGISGateway
    from config.settings import load_settings

    gis = ArcGISGateway(load_settings()).gis
    found = gis.content.search(f'title:"{TITLE}" AND owner:{gis.users.me.username}', item_type="Image")
    if found:
        print("Exists:", found[0].id)
        return 0
    if not args.apply:
        print("DRY RUN: would create the private image item", TITLE)
        return 0
    item = gis.content.add({"title": TITLE, "type": "Image", "tags": "CityView-Riyadh,Falcon Eye", "snippet": "Falcon Eye icon for the ArcGIS dashboard header."},
                           data=str(ROOT / "data" / "falcon-eye-icon.png"))
    print("Created:", item.id, item.access)
    return 0


if __name__ == "__main__":
    sys.exit(main())
