"""Push the local store (system of record in demo mode) into the hosted ArcGIS Online layers (replaces layer contents).

Run scripts/create_feature_layers.py first. After this, the running app mirrors every operational write to ArcGIS Online (write-through).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.gis import schema as S  # noqa: E402
from backend.gis.agol import ArcGISOnlineMirror  # noqa: E402
from backend.gis.store import Store  # noqa: E402
from config.settings import load_settings  # noqa: E402

if __name__ == "__main__":
    s = load_settings()
    if not s.arcgis_enabled:
        sys.exit("Set ARCGIS_USERNAME / ARCGIS_PASSWORD in .env first.")
    store, m = Store(s.db_path), ArcGISOnlineMirror(s)
    for name, d in S.LAYERS.items():
        if d.internal or not store.count(name):
            continue
        n = m.bulk_push(name, store.all(name))
        print(f"{name:34s} pushed {n}/{store.count(name)}")
