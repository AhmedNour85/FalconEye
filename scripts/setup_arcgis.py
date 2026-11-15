"""Check the ArcGIS Online sign-in and what the account may do. Read-only: nothing is created or changed.

Needs `pip install arcgis six` and ARCGIS_USERNAME / ARCGIS_PASSWORD in .env (scripts/make_env.py writes it).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import ConfigError, load_settings  # noqa: E402

NEEDED = ("portal:user:createItem", "portal:publisher:publishFeatures")


def main(argv=None) -> int:
    try:
        s = load_settings()
    except ConfigError as exc:
        print(f"Configuration refused: {exc}")
        return 1
    if not s.arcgis_enabled:
        print("ARCGIS_USERNAME / ARCGIS_PASSWORD are not set in .env. Run scripts/make_env.py first.")
        return 1
    try:
        from arcgis.gis import GIS
    except ImportError:
        print("The 'arcgis' package is not installed: pip install arcgis six")
        return 2
    gis = GIS(s.arcgis_url, s.arcgis_username, s.arcgis_password)
    me = gis.users.me
    print(f"Signed in as {me.username} (role: {me.role}, user type: {getattr(me, 'userLicenseTypeId', 'n/a')}, organisation: {gis.properties.get('name', 'n/a')})")
    priv = set(me.privileges or [])
    ok = True
    for p in NEEDED:
        has = p in priv
        ok = ok and has
        print(f"  privilege {p}: {'yes' if has else 'NO'}")
    mine = gis.content.search(f'title:"{s.arcgis_layer_prefix}_" AND owner:{me.username}', max_items=100)
    mine = [i for i in mine if i.title.startswith(s.arcgis_layer_prefix + "_")]
    print(f"  items of yours titled {s.arcgis_layer_prefix}_*: {len(mine)}")
    print("  layer prefix this project will use:", s.arcgis_layer_prefix)
    print("The account can create the hosted layers." if ok else "The account CANNOT create hosted feature layers: ask an administrator for a publisher role.")
    return 0 if ok else 3


if __name__ == "__main__":
    sys.exit(main())
