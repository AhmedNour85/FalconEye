"""Prepare the hosted Work Orders layer for ArcGIS Field Maps Tasks: add the esritask_* fields (with their task type, assignee, status and priority lists).

    python scripts/setup_field_tasks_layer.py            # DRY RUN: prints what would be added, changes nothing
    python scripts/setup_field_tasks_layer.py --apply    # adds the missing fields (the layer definition is saved in data/backups first), then reads them back

Only the missing fields are added; nothing existing is altered or deleted. Safe to run again. Work orders already in the layer keep their values.
The assignee list holds the logins from GEOAI_FIELD_USERS, or the signed-in account when none are set (the City project's test setup).
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.gis import schema as S  # noqa: E402
from backend.services import tasks  # noqa: E402
from scripts.field_maps_plan import plan_task_fields  # noqa: E402


def _definition(layer) -> dict:
    return json.loads(json.dumps(dict(layer.properties), default=str))


def main(argv=None, gateway=None, settings=None, backups=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args(argv)
    if settings is None:
        from config.settings import load_settings
        settings = load_settings()
    if not settings.arcgis_enabled:
        print("Set ARCGIS_USERNAME / ARCGIS_PASSWORD in .env first.")
        return 1
    if gateway is None:
        from backend.gis.agol import ArcGISGateway
        gateway = ArcGISGateway(settings)
    backups = Path(backups) if backups else ROOT / "data" / "backups"
    layer = gateway.layer(S.WORK_ORDERS)
    users = {u: u for u in (settings.field_users or {}).values()} or {gateway.owner: gateway.owner}
    fields, changes = plan_task_fields(list(layer.properties.fields), tasks.TASK_TYPES, users)
    print(f"== {'APPLY' if args.apply else 'DRY RUN (nothing is changed)'} == {gateway.title(S.WORK_ORDERS)}\n")
    print(f"Task titles ({len(tasks.TASK_TYPES)}): " + ", ".join(tasks.TASK_TYPES[-3:]) + " are the mobility ones;", f"assignees: {', '.join(sorted(users))}")
    for c in changes or ["nothing to add: the layer already has every task field"]:
        print(" -", c)
    if not fields:
        return 0
    if not args.apply:
        print("\nDry run only. Run again with --apply.")
        return 0
    backups.mkdir(parents=True, exist_ok=True)
    path = backups / f"work_orders_definition_{datetime.now():%Y%m%d_%H%M%S}.json"
    path.write_text(json.dumps(_definition(layer), ensure_ascii=False), encoding="utf-8")
    print(f"\nlayer definition saved: {path}")
    layer.manager.add_to_definition({"fields": fields})
    gateway._forget(S.WORK_ORDERS)
    have = {f["name"] for f in gateway.layer(S.WORK_ORDERS).properties.fields}
    missing = [f["name"] for f in fields if f["name"] not in have]
    if missing:
        print("READ BACK FAILED: these fields are still missing on the hosted layer: " + ", ".join(missing))
        print("Nothing else was changed. Restore from the saved definition above if needed.")
        return 1
    print(f"Read back: all {len(fields)} task fields are on the hosted layer.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
