"""Add an "Answer" button to the Field Maps task: it opens a pick list of the investigator's answers (Yes, confirmed / Not found / ...).

Field Maps tasks cannot show radio buttons on Finish or Note (Esri: edit actions cannot prompt for multiple-choice form elements), so the answer is
chosen with a manual edit action on `Field_Verdict`, the same way the built-in "Status" button works:

    Finish | Answer | Note | Attach        (Answer picks the verdict, Note writes what was seen, Finish completes the task)

What it changes on the web map(s) (a backup of each file is saved in data/backups first):
  * resource tasks-configuration.json : a new action "Answer" (prompts Field_Verdict) in the "In progress" layout, after Finish
  * web map form of the Work orders layer : Field_Verdict becomes a pick list (combo box) instead of radio buttons;
    Field_Verdict is required only when the task is Completed, Field_Comment is no longer required (the Note carries the comment)

    python scripts/add_task_answer_action.py                         # DRY RUN: prints the plan, changes nothing
    python scripts/add_task_answer_action.py --apply                 # makes the change
    python scripts/add_task_answer_action.py --apply --webmap <id>   # another map (default: GeoAI Field Maps - Investigator Map)
Safe to run again. To undo, restore the saved backup files (see the printed paths).
"""
import argparse
import copy
import json
import sys
import uuid
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.gis.agol import ArcGISGateway  # noqa: E402
from scripts._guard import own_item_or_exit  # noqa: E402
from config.settings import load_settings  # noqa: E402

# No default web map: an id must be given, and only a web map titled with this project's prefix is accepted.
ACTION_TITLE = "Answer"
REQUIRED_WHEN_DONE = {"name": "geoai-required-when-completed", "title": "Required when completed", "expression": "$feature.esritask_status == 3", "returnType": "boolean"}


def plan_tasks_config(cfg: dict) -> tuple[dict, list[str]]:
    cfg = copy.deepcopy(cfg)
    changes = []
    actions = cfg.setdefault("featureActions", [])
    action = next((a for a in actions if a.get("promptField") == "Field_Verdict"), None)
    if action is None:
        action = {"id": str(uuid.uuid4()), "type": "edit", "title": ACTION_TITLE, "icon": "list-bullet", "promptField": "Field_Verdict", "updateType": "manual", "updates": []}
        actions.append(action)
        changes.append(f"add action {ACTION_TITLE!r} (pick list for Field_Verdict)")
    layout = next((l for l in cfg.get("featureActionLayouts", []) if (l.get("title") or "").lower() == "in progress"), None)
    if layout is None:
        changes.append("WARNING: no 'In progress' layout found; the action was not placed")
        return cfg, changes
    if not any(x.get("featureActionId") == action["id"] for x in layout["actions"]):
        pos = next((i + 1 for i, x in enumerate(layout["actions"]) if x.get("predominant")), 0)          # right after Finish
        layout["actions"].insert(pos, {"featureActionId": action["id"], "id": str(uuid.uuid4())})
        changes.append("place it after Finish in the 'In progress' layout")
    return cfg, changes


def plan_form(form: dict | None) -> tuple[dict | None, list[str]]:
    if not form:
        return form, []
    form = copy.deepcopy(form)
    changes = []
    exprs = form.setdefault("expressionInfos", [])
    if not any(e.get("name") == REQUIRED_WHEN_DONE["name"] for e in exprs):
        exprs.append(dict(REQUIRED_WHEN_DONE))
        changes.append("add expression required-when-completed")
    for el in form.get("formElements", []):
        if el.get("type") != "field":
            continue
        if el.get("fieldName") == "Field_Verdict":
            if (el.get("inputType") or {}).get("type") != "combo-box":
                el["inputType"] = {"type": "combo-box", "showNoValueOption": True, "noValueOptionLabel": "No value"}
                changes.append("Field_Verdict: radio buttons -> pick list")
            if el.get("requiredExpression") != f"expr/{REQUIRED_WHEN_DONE['name']}":
                el["requiredExpression"] = f"expr/{REQUIRED_WHEN_DONE['name']}"
                changes.append("Field_Verdict: required only when Completed")
        if el.get("fieldName") == "Field_Comment" and el.get("requiredExpression") != "expr/system/false":
            el["requiredExpression"] = "expr/system/false"
            changes.append("Field_Comment: not required (the Note carries the comment)")
    return form, changes


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--webmap", required=True, help="web map item id (required)")
    args = ap.parse_args(argv)
    s = load_settings()
    if not s.arcgis_enabled:
        sys.exit("Set ARCGIS_USERNAME / ARCGIS_PASSWORD in .env first.")
    mirror = ArcGISGateway(s)
    item = own_item_or_exit(mirror.gis.content.get(args.webmap), s.arcgis_layer_prefix, args.webmap, mirror.owner)
    if item is None:
        sys.exit("web map not found")
    print(f"== {'APPLY' if args.apply else 'DRY RUN (nothing is changed)'} == {item.title!r} ({args.webmap})\n")
    stamp = f"{datetime.now():%Y%m%d_%H%M%S}"
    backups = ROOT / "data" / "backups"
    backups.mkdir(parents=True, exist_ok=True)

    cfg = item.resources.get("tasks-configuration.json", try_json=True)
    new_cfg, c1 = plan_tasks_config(cfg)
    print("Task settings (tasks-configuration.json):", "; ".join(c1) or "already has the Answer action")

    data = item.get_data()
    c2 = []
    for lyr in data["operationalLayers"]:
        if lyr.get("id") == cfg.get("layerId") or "Work orders" in (lyr.get("title") or ""):
            form, ch = plan_form(lyr.get("formInfo"))
            c2 += ch
            if ch:
                lyr["formInfo"] = form
    print("Work orders form:", "; ".join(c2) or "already set")

    if args.apply:
        if c1:
            (backups / f"tasks-configuration_{args.webmap}_{stamp}.json").write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
            item.resources.update(file_name="tasks-configuration.json", text=json.dumps(new_cfg))
            print(f"  task settings updated (backup: data/backups/tasks-configuration_{args.webmap}_{stamp}.json)")
        if c2:
            (backups / f"webmap_{args.webmap}_{stamp}.json").write_text(json.dumps(item.get_data(), ensure_ascii=False), encoding="utf-8")
            item.update(item_properties={"text": json.dumps(data)})
            print(f"  web map form updated (backup: data/backups/webmap_{args.webmap}_{stamp}.json)")
        print("\nDone. Re-sync the map on the phone.")
    else:
        print("\nDry run only. Run again with --apply.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
