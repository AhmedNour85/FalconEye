"""Give the Field Maps task a radio-button answer and a comment box (like the in-app investigator form).

What it prepares on the hosted Work Orders layer and in the Field Maps web map(s):

  * fields  Field_Verdict  (radio buttons: Yes, confirmed / Not found / Need to look again / Escalate / Repaired)
            Field_Comment  (multi-line text: "What did you see?")
  * form    the two fields are added to the Work Orders layer form, both required, so the investigator answers them before tapping Finish.

The server then uses these two fields as the report when the task is finished (a typed Note still works as a fallback).

    python scripts/setup_field_maps_form.py                       # DRY RUN: reads your ArcGIS account and prints what it would change; changes nothing
    python scripts/setup_field_maps_form.py --apply               # makes the changes (a JSON backup of each web map is saved first)
    python scripts/setup_field_maps_form.py --webmap <item id>    # a web map other than the defaults (repeat for several)
    python scripts/setup_field_maps_form.py --lang both           # choice labels in English, Arabic, or both ("Yes, confirmed / نعم، مؤكد")

It also makes the Field verification report form bilingual (heading, questions, hint and the radio choices) when --lang is ar or both. The saved codes
(Confirmed, Rejected, ...) never change, only what the worker reads.

Existing form elements (including the Field Maps task fields) are kept; only missing elements are added. Safe to run again.
"""
import argparse
import copy
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.gis import schema as S  # noqa: E402
from backend.gis.agol import ArcGISGateway  # noqa: E402
from scripts._guard import own_item_or_exit  # noqa: E402
from backend.services import i18n  # noqa: E402
from config.settings import load_settings  # noqa: E402

# No default web map: an id must be given, and only a web map titled with this project's prefix is accepted.
REQUIRED = "expr/geoai-required"


# one example for a city service and one for a road task: the same comment box serves both crews
HINT = ("For example: water seeping through the asphalt near the valve chamber, or barriers and signs in place on the road",
        "مثلًا: مياه تتسرب عبر الأسفلت قرب غرفة الصمامات، أو حواجز ولوحات مثبتة على الطريق")


def coded_values(lang: str) -> list[dict]:
    return [{"name": i18n.verdict_label(code, lang), "code": code} for code, *_ in i18n.VERDICT_CHOICES]


def form_elements(lang: str) -> list[dict]:
    title = {"en": "Confirm the incident", "ar": "أكّد الحادثة", "both": "Confirm the incident / أكّد الحادثة"}[lang]
    comment = {"en": "What did you see?", "ar": "ماذا رأيت؟", "both": "What did you see? / ماذا رأيت؟"}[lang]
    hint = {"en": HINT[0], "ar": HINT[1], "both": f"{HINT[0]} / {HINT[1]}"}[lang]
    return [
        {"type": "field", "fieldName": "Field_Verdict", "label": title, "editableExpression": "expr/geoai-editable", "requiredExpression": REQUIRED,
         "inputType": {"type": "radio-buttons", "showNoValueOption": False}},
        {"type": "field", "fieldName": "Field_Comment", "label": comment, "hint": hint, "editableExpression": "expr/geoai-editable", "requiredExpression": REQUIRED,
         "inputType": {"type": "text-area", "maxLength": 1000, "minLength": 0}},
    ]


def expression_infos() -> list[dict]:
    return [{"name": "geoai-required", "title": "Required", "expression": "true", "returnType": "boolean"},
            {"name": "geoai-editable", "title": "Editable", "expression": "true", "returnType": "boolean"}]


REPORT_TEXT = {   # label key -> (English, Arabic)
    "title": ("Confirm the incident", "أكّد الحادثة"),
    "Work_Order_ID": ("Work order (leave blank to match by location)", "أمر العمل (اتركه فارغًا ليُطابق حسب الموقع)"),
    "Verification_Status": ("What did you find?", "ماذا وجدت؟"),
    "Observation": ("What did you see?", "ماذا رأيت؟"),
    "Photo": ("Photo (optional)", "صورة (اختياري)"),
    "hint": HINT,
}


def _t(key: str, lang: str) -> str:
    en, ar = REPORT_TEXT[key]
    return ar if lang == "ar" else f"{en} / {ar}" if lang == "both" else en


def plan_report_form(form: dict | None, lang: str) -> tuple[dict | None, list[str]]:
    """The report form with bilingual wording; only labels and hints change, never fields, inputs or order."""
    if not form:
        return form, []
    form = copy.deepcopy(form)
    changes = []

    def set_(obj, key, value, what):
        if obj.get(key) != value:
            obj[key] = value
            changes.append(f"{what}: {value!r}")

    set_(form, "title", _t("title", lang), "form title")
    for el in form.get("formElements", []):
        name = el.get("fieldName") or el.get("label") or ""
        if el.get("type") == "field" and name in ("Work_Order_ID", "Verification_Status", "Observation"):
            set_(el, "label", _t(name, lang), f"label of {name}")
            if name == "Observation":
                set_(el, "hint", _t("hint", lang), "hint of Observation")
        elif el.get("type") == "attachment":
            set_(el, "label", _t("Photo", lang), "label of the photo")
    return form, changes


def plan_form(form: dict | None, lang: str) -> tuple[dict, list[str]]:
    """The form with our two elements added (nothing else touched), and a list of what changed."""
    form = copy.deepcopy(form) if form else {"type": "formInfo", "title": "{Work_Order_ID}", "formElements": []}
    elements = form.setdefault("formElements", [])
    have = {e.get("fieldName") for e in elements if e.get("type") == "field"}
    changes = []
    for el in form_elements(lang):
        if el["fieldName"] not in have:
            elements.append(el)
            changes.append(f"add form element {el['fieldName']} ({el['inputType']['type']}, required)")
    exprs = form.setdefault("expressionInfos", [])
    names = {e.get("name") for e in exprs}
    for e in expression_infos():
        if e["name"] not in names:
            exprs.append(e)
            changes.append(f"add expression {e['name']}")
    return form, changes


def find_layers(data: dict, service_url: str, item_id: str):
    """operationalLayers entries that point at the hosted Work Orders layer."""
    out = []
    for lyr in data.get("operationalLayers", []):
        url = (lyr.get("url") or "").lower()
        if lyr.get("itemId") == item_id or url.startswith(service_url.lower()):
            out.append(lyr)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="make the changes (default is a dry run)")
    ap.add_argument("--webmap", action="append", required=True, help="web map item id (repeatable, required)")
    ap.add_argument("--lang", choices=["en", "ar", "both"], help="choice labels (default: GEOAI_FIELD_LANG)")
    args = ap.parse_args(argv)

    s = load_settings()
    if not s.arcgis_enabled:
        sys.exit("Set ARCGIS_USERNAME / ARCGIS_PASSWORD in .env first (see .env.example).")
    lang = args.lang or s.field_lang
    mirror = ArcGISGateway(s)
    fl = mirror.layer(S.WORK_ORDERS)
    svc = fl.container.url if hasattr(fl, "container") else fl.url.rsplit("/", 1)[0]
    item_id = fl.container.properties.get("serviceItemId", "") if hasattr(fl, "container") else ""
    mode = "APPLY" if args.apply else "DRY RUN (nothing is changed)"
    print(f"== {mode} == layer {mirror.title(S.WORK_ORDERS)}  labels: {lang}\n")

    # ---- 1. hosted layer fields and the radio choices
    have = {f["name"]: f for f in fl.properties.fields}
    todo_fields = [n for n in ("Field_Verdict", "Field_Comment") if n not in have]
    want = coded_values(lang)
    dom = (have.get("Field_Verdict") or {}).get("domain") or {}
    domain_ok = [(c["name"], c["code"]) for c in dom.get("codedValues", [])] == [(c["name"], c["code"]) for c in want]
    print("Hosted layer:")
    print("  fields to add      :", todo_fields or "none (already there)")
    print("  radio choices      :", "already set" if domain_ok and "Field_Verdict" in have else "will be set to " + ", ".join(c["name"] for c in want))
    if args.apply:
        if todo_fields:
            print("  added              :", mirror.ensure_fields(S.WORK_ORDERS))
        fl = mirror.layer(S.WORK_ORDERS)
        if not domain_ok:
            fl.manager.update_definition({"fields": [{"name": "Field_Verdict", "domain": {"type": "codedValue", "name": "GeoAI_FieldVerdict", "codedValues": want}}]})
            print("  radio choices set")

    # ---- 1b. the report layer's radio choices (Field Verification)
    report_on = lang in ("ar", "both")
    vl = mirror.layer(S.VERIFICATION)
    vdom = ({f["name"]: f for f in vl.properties.fields}.get("Verification_Status") or {}).get("domain") or {}
    vwant = coded_values(lang)
    vok = [(c["name"], c["code"]) for c in vdom.get("codedValues", [])] == [(c["name"], c["code"]) for c in vwant]
    print("Field Verification layer:")
    print("  radio choices      :", "already set" if vok else "will be set to " + ", ".join(c["name"] for c in vwant))
    if args.apply and not vok:
        vl.manager.update_definition({"fields": [{"name": "Verification_Status", "domain": {"type": "codedValue", "name": vdom.get("name") or "GeoAI_VerificationStatus", "codedValues": vwant}}]})
        print("  radio choices set")
    vsvc = vl.container.url if hasattr(vl, "container") else vl.url.rsplit("/", 1)[0]
    vitem = vl.container.properties.get("serviceItemId", "") if hasattr(vl, "container") else ""

    # ---- 2. the web map forms
    for wid in args.webmap:
        item = own_item_or_exit(mirror.gis.content.get(wid), s.arcgis_layer_prefix, wid, mirror.owner)
        print(f"\nWeb map {wid}:")
        if item is None:
            print("  not found or not visible to this account; skipped")
            continue
        print(f"  title: {item.title!r}  owner: {item.owner}")
        data = item.get_data()
        layers = find_layers(data, svc, item_id)
        rlayers = find_layers(data, vsvc, vitem) if report_on else []
        if not layers and not rlayers:
            print("  does not contain the Work Orders or the Field Verification layer; skipped")
            continue
        changed = False
        for lyr in rlayers:
            form, changes = plan_report_form(lyr.get("formInfo"), lang)
            print(f"  report layer {lyr.get('title')!r}: " + ("; ".join(changes) if changes else "wording already bilingual"))
            if changes:
                lyr["formInfo"] = form
                changed = True
        for lyr in layers:
            form, changes = plan_form(lyr.get("formInfo"), lang)
            keys = sorted(k for k in (lyr.get("formInfo") or {}))
            print(f"  layer {lyr.get('title')!r}: existing form keys {keys or 'none'}; " + ("; ".join(changes) if changes else "already has both elements"))
            if changes:
                lyr["formInfo"] = form
                changed = True
        if changed and args.apply:
            backup = ROOT / "data" / "backups" / f"webmap_{wid}_{datetime.now():%Y%m%d_%H%M%S}.json"
            backup.parent.mkdir(parents=True, exist_ok=True)
            backup.write_text(json.dumps(item.get_data(), ensure_ascii=False), encoding="utf-8")     # the version BEFORE the change
            item.update(item_properties={"text": json.dumps(data)})
            print(f"  updated. backup of the previous version: {backup}")
    print("\nDone." if args.apply else "\nDry run only. Run again with --apply to make these changes. Then re-sync the map on the phone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
