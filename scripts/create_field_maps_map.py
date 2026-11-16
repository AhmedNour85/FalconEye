"""Create the Field Maps web map for the CityView layers, with its task settings.

    python scripts/create_field_maps_map.py --reference <City Investigator Map id>             # DRY RUN: prints the new map, changes nothing
    python scripts/create_field_maps_map.py --reference <id> --apply                           # creates a NEW web map and its tasks-configuration.json, then reads both back
    python scripts/create_field_maps_map.py --reference <id> --update <CityView map id> --apply   # repeat run on the map this script made (a backup is saved first)

The reference map (the working City map) is only READ. The new map points at the CityView layers; nothing of the City project is edited or deleted.
Run scripts/setup_field_tasks_layer.py --apply first: the task settings need the Work Orders layer's task fields.
The new map is private to the signed-in account.
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.gis import schema as S  # noqa: E402
from scripts._guard import own_item_or_exit  # noqa: E402
from scripts.field_maps_plan import MAP_LAYERS, WORK_ORDERS_LAYER_ID, find_existing, plan_tasks_config, plan_web_map  # noqa: E402

TITLE = "CityView Field Maps - Investigator Map"
KEYS = {"work_orders": S.WORK_ORDERS, "verification": S.VERIFICATION, "incidents": S.INCIDENTS, "traffic_incidents": S.TRAFFIC_REPORTS,
        "closures": S.CLOSURES, "event_notices": S.EVENT_NOTICES}
CONFIG = "tasks-configuration.json"


def main(argv=None, gateway=None, settings=None, backups=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--reference", required=True, help="the working City Investigator Map (read only)")
    ap.add_argument("--update", help="id of the CityView map this script made earlier (repeat run)")
    ap.add_argument("--title", default=TITLE)
    args = ap.parse_args(argv)
    if settings is None:
        from config.settings import load_settings
        settings = load_settings()
    if not settings.arcgis_enabled:
        sys.exit("Set ARCGIS_USERNAME / ARCGIS_PASSWORD in .env first.")
    prefix = settings.arcgis_layer_prefix
    if not args.title.startswith(prefix):
        sys.exit(f"Refused: the title {args.title!r} must start with {prefix!r}. This project only creates its own items.")
    if gateway is None:
        from backend.gis.agol import ArcGISGateway
        gateway = ArcGISGateway(settings)
    backups = Path(backups) if backups else ROOT / "data" / "backups"
    gis = gateway.gis

    ref = gis.content.get(args.reference)
    if ref is None or ref.type != "Web Map":
        sys.exit(f"Refused: {args.reference} is not a web map this account can see.")
    ref_data, ref_cfg = ref.get_data(), ref.resources.get(CONFIG, try_json=True)
    if not ref_cfg or not ref_data.get("operationalLayers"):
        sys.exit("Refused: the reference map has no task settings or no layers; use the map that works in Field Maps.")

    wo_fields = list(gateway.layer(S.WORK_ORDERS).properties.fields)
    if not all(any(f["name"] == n for f in wo_fields) for n in ("esritask_type", "esritask_assignee", "esritask_status")):
        print("The Work Orders layer has no task fields yet. Run scripts/setup_field_tasks_layer.py --apply first.")
        return 1
    layers = {}
    for key, name in KEYS.items():
        try:
            layers[key] = {"url": gateway.layer(name).url, "itemId": gateway._item(name).id}
        except Exception as exc:  # a layer that is not hosted yet is left out of the map, and the dry run says so
            print(f"  (not available: {gateway.title(name)}: {exc})")
    new_map, c1 = plan_web_map(ref_data, layers, args.title)
    new_cfg, c2 = plan_tasks_config(ref_cfg, WORK_ORDERS_LAYER_ID, wo_fields)

    existing = find_existing(gis.content.search(f'title:"{args.title}" AND owner:{gateway.owner}', item_type="Web Map", max_items=50), args.title)
    target = None
    if args.update:
        target = own_item_or_exit(gis.content.get(args.update), prefix, args.update, gateway.owner)
    elif existing is not None:
        print(f"A map titled {args.title!r} already exists ({existing.id}). Nothing was created. To change that one, run again with --update {existing.id}.")
        return 1

    print(f"== {'APPLY' if args.apply else 'DRY RUN (nothing is changed)'} == {'update ' + target.id if target else 'create'}: {args.title!r}\n")
    for c in c1 + c2:
        print(" -", c)
    print(" - the map is private to the account; the reference map is only read")
    print(" - note: Field Maps may refuse task settings made by a script. If the phone says 'Tasks couldn't be loaded', the manual way in docs/field_maps.md is the fallback.")
    if not args.apply:
        print("\nDry run only. Run again with --apply.")
        return 0

    text, cfg_text = json.dumps(new_map), json.dumps(new_cfg)
    if target is None:
        props = {"title": args.title, "type": "Web Map", "text": text, "tags": ["CityView", "Field Maps"], "typeKeywords": list(ref.typeKeywords),
                 "snippet": "Investigators see their open assignments, answer them and file field reports (Riyadh City View, synthetic demo data)."}
        item = gis.content.add(item_properties=props)
        item.resources.add(file_name=CONFIG, text=cfg_text)
    else:
        backups.mkdir(parents=True, exist_ok=True)
        stamp = f"{datetime.now():%Y%m%d_%H%M%S}"
        (backups / f"webmap_{target.id}_{stamp}.json").write_text(json.dumps(target.get_data(), ensure_ascii=False), encoding="utf-8")
        (backups / f"tasks-configuration_{target.id}_{stamp}.json").write_text(json.dumps(target.resources.get(CONFIG, try_json=True), ensure_ascii=False), encoding="utf-8")
        target.update(item_properties={"text": text})
        target.resources.update(file_name=CONFIG, text=cfg_text)
        item = target
    back = gis.content.get(item.id)
    got_layers = [l.get("url") for l in (back.get_data() or {}).get("operationalLayers", [])]
    got_cfg = back.resources.get(CONFIG, try_json=True) or {}
    ok = got_layers == [l["url"] for l in new_map["operationalLayers"]] and got_cfg.get("layerId") == WORK_ORDERS_LAYER_ID
    if not ok:
        print(f"READ BACK FAILED for item {item.id}: layers or task settings differ from what was written. Check the item in ArcGIS Online; nothing was deleted.")
        return 1
    print(f"\nRead back: item {item.id} has {len(got_layers)} layers and its task settings point at {WORK_ORDERS_LAYER_ID!r}.")
    print("Next: scripts/setup_field_maps_form.py and scripts/add_task_answer_action.py with --webmap " + item.id + " (each a dry run first).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
