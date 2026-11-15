"""Check ArcGIS Online connectivity and permissions (needs `pip install arcgis` and ARCGIS_USERNAME/ARCGIS_PASSWORD in .env).

Prints who you are, whether you can create hosted feature layers, and whether the public basemap/imagery items are reachable.
Nothing is created or modified.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import load_settings  # noqa: E402


def main() -> int:
    s = load_settings()
    if not s.arcgis_enabled:
        print("ARCGIS_USERNAME / ARCGIS_PASSWORD are not set in .env - the app will run in local demo mode.")
        return 1
    try:
        from arcgis.gis import GIS
    except ImportError:
        print("The 'arcgis' package is not installed: pip install arcgis")
        return 2
    gis = GIS(s.arcgis_url, s.arcgis_username, s.arcgis_password)
    me = gis.users.me
    print(f"Signed in as {me.username} (role: {me.role}, org: {gis.properties.get('name', 'n/a')})")
    priv = set(me.privileges or [])
    for p in ("portal:user:createItem", "portal:publisher:publishFeatures"):
        print(f"  privilege {p}: {'yes' if p in priv else 'NO'}")
    for q in ("World Imagery", "Sentinel-2 Views"):
        res = gis.content.search(q, outside_org=True, max_items=3)
        print(f"  Living Atlas search '{q}': {len(res)} item(s) {[r.title for r in res]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
