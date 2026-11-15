"""Create this project's .env from the ArcGIS Online sign-in lines of another .env, without showing any value.

    python scripts/make_env.py C:\\path\\to\\other\\.env          # writes .env in this project
    python scripts/make_env.py other.env --out somewhere\\.env

Only ARCGIS_URL, ARCGIS_USERNAME and ARCGIS_PASSWORD are copied. Everything else in the new file is this project's own:
the layer prefix is CityView (never the other project's), and there is no database path because there is no local database.
An existing .env is never overwritten.
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COPIED = ("ARCGIS_URL", "ARCGIS_USERNAME", "ARCGIS_PASSWORD")

TEMPLATE = """# Riyadh City View. Never commit this file.

# ---- ArcGIS Online: the system of record. The app cannot start without these. ----
{arcgis}
# Hosted layers are titled <prefix>_<layer>. "GeoAIOps" (the Agentic_AI_City project's layers) is refused by the app.
ARCGIS_LAYER_PREFIX=CityView
# Optional publishable, scoped API key for Esri basemaps in the browser map
ARCGIS_JS_API_KEY=

# ---- Where the records live: arcgis (default) or memory (development only; nothing is kept) ----
GEOAI_STORE=arcgis

# ---- App ----
GEOAI_SEED=20260101
GEOAI_CITIZEN_REPORTS=0
GEOAI_FIELD_FORM=1
GEOAI_FIELD_LANG=en
# Each investigator's ArcGIS Online (Field Maps) username: worker id = username, comma separated.
# GEOAI_FIELD_USERS=WRK-001=nawaf.harbi,WRK-002=khalid.otaibi

# ---- Planner (optional). Without a key the crew uses the offline rule planner. ----
# ANTHROPIC_API_KEY=
# GEOAI_PLANNER=
"""


def read_keys(path: Path) -> dict[str, str]:
    found = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        key, sep, value = line.partition("=")
        if sep and key.strip() in COPIED and not line.lstrip().startswith("#"):
            found[key.strip()] = value.strip()
    return found


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", help="the .env to copy the three ArcGIS Online lines from")
    ap.add_argument("--out", default=str(ROOT / ".env"), help="where to write (default: this project's .env)")
    args = ap.parse_args(argv)
    src, out = Path(args.source), Path(args.out)
    if not src.is_file():
        print(f"Not found: {src}")
        return 2
    if out.exists():
        print(f"{out} already exists and is not overwritten. Remove it yourself first if you want a new one.")
        return 3
    found = read_keys(src)
    missing = [k for k in ("ARCGIS_USERNAME", "ARCGIS_PASSWORD") if not found.get(k)]
    if missing:
        print(f"{src} has no value for: {', '.join(missing)}. Nothing was written.")
        return 4
    found.setdefault("ARCGIS_URL", "https://www.arcgis.com")
    out.write_text(TEMPLATE.format(arcgis="\n".join(f"{k}={found[k]}" for k in COPIED)), encoding="utf-8")
    print(f"Wrote {out}")
    print("Copied (values not shown): " + ", ".join(COPIED))
    print("Set by this project: ARCGIS_LAYER_PREFIX=CityView, GEOAI_STORE=arcgis")
    return 0


if __name__ == "__main__":
    sys.exit(main())
