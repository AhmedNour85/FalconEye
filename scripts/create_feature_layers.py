"""Create the hosted feature layers (one per data-model layer) in ArcGIS Online. Idempotent: reuses layers with the same title.

    python scripts/create_feature_layers.py            # create all
    python scripts/create_feature_layers.py Riyadh_Work_Orders ...
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.gis.agol import ArcGISOnlineMirror  # noqa: E402
from config.settings import load_settings  # noqa: E402

if __name__ == "__main__":
    s = load_settings()
    if not s.arcgis_enabled:
        sys.exit("Set ARCGIS_USERNAME / ARCGIS_PASSWORD in .env first (see .env.example).")
    m = ArcGISOnlineMirror(s)
    ids = m.create_layers(sys.argv[1:] or None)
    for name, item in ids.items():
        print(f"{name:34s} {m.title(name):44s} item {item}")
