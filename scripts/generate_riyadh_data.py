"""Regenerate the synthetic Riyadh environment and export every layer as GeoJSON/JSON under data/synthetic/.

    python scripts/generate_riyadh_data.py --seed 20260101 [--db data/geoai.sqlite] [--no-history]
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.gis import schema as S  # noqa: E402
from backend.gis.store import Store  # noqa: E402
from backend.services import synthetic  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=20260101)
    ap.add_argument("--db", default=str(ROOT / "data" / "geoai.sqlite"))
    ap.add_argument("--out", default=str(ROOT / "data" / "synthetic"))
    ap.add_argument("--no-history", action="store_true")
    a = ap.parse_args()
    store = Store(a.db)
    counts = synthetic.generate(store, a.seed, with_history=not a.no_history)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    for name, d in S.LAYERS.items():
        if d.internal or not store.count(name):
            continue
        if d.geometry:
            (out / f"{name}.geojson").write_text(json.dumps(store.geojson(name)), encoding="utf-8")
        else:
            (out / f"{name}.json").write_text(json.dumps([f["attrs"] for f in store.all(name)], indent=1), encoding="utf-8")
    print(json.dumps(counts, indent=2))
    print(f"seed={a.seed} db={a.db} exports={out}")


if __name__ == "__main__":
    main()
