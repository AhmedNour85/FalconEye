"""Reset the demo database to a clean, reproducible state (same effect as the 'Reset demo' button)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.platform import Platform  # noqa: E402

if __name__ == "__main__":
    p = Platform(init=False)
    print(json.dumps(p.reset(), indent=2))
    print("ArcGIS Online mirror:", p.mirror_status)
