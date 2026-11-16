"""ArcGIS Field Maps "Tasks": the fields Field Maps adds to a layer (esritask_*) are derived from our work orders.

In the mobile app the task title is the coded-value NAME of esritask_type, the group (Unassigned / Assigned ...) comes from esritask_status and
esritask_assignee, and the sort order from esritask_priority. We own the mapping so an assignment approved in the command center shows up as a task.
"""
from __future__ import annotations

from datetime import datetime, timezone

from backend.services import visual_types

# esritask_type: one coded value per incident type the crew can raise (the code is the index). Anything else maps to "Other".
TASK_TYPES = ["Water Leak (Suspected)", "Water Leak", "Streetlight Failure (Predicted)", "Streetlight Failure", "Streetlight Cluster Maintenance", "Streetlight Pole Inspection",
              "Visual Distortion Review", "Visual Distortion", "Urban Change Review", "Urban Change", "Land-Use Violation Review", "Urban Case", "Other"]
TASK_TYPES += [v["name"] for v in visual_types.VISUAL_TYPES.values()]          # appended after "Other": the codes of the existing types stay the same
TASK_TYPES += ["Traffic Incident", "Planned Road Closure", "Major Event Traffic Plan"]          # the mobility crew's types, appended last for the same reason
DESCRIPTION_LIMIT = 4000          # the hosted esritask_description field
# the coded values Field Maps creates for esritask_status and esritask_priority
STATUS = {"Created": 0, "Assigned": 1, "In Progress": 2, "Completed": 3, "Cancelled": 3}
STATUS_NAMES = {0: "Unassigned", 1: "Assigned", 2: "In Progress", 3: "Completed"}
PRIORITY = {"P1": 4, "P2": 3, "P3": 2, "P4": 1}
FIELDS = ("esritask_type", "esritask_assignee", "esritask_status", "esritask_priority", "esritask_duedate", "esritask_description", "esritask_notes")


def type_code(incident_type: str) -> int:
    t = (incident_type or "").strip()
    return TASK_TYPES.index(t) if t in TASK_TYPES else TASK_TYPES.index("Other")


def iso_ms(iso: str | None) -> int | None:
    """Field Maps stores esritask_duedate as a date: epoch milliseconds."""
    if not iso:
        return None
    try:
        return int(datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp() * 1000)
    except ValueError:
        return None


HOW_TO_ANSWER = ("Choose your answer (Yes, confirmed / Not found / Need to look again / Escalate), write what you saw in the comment, then tap Finish. "
                 "If you only see Notes, start the note with Confirmed, Not found, Need to look again or Escalate.")


LANG = "en"        # task text language on the investigators' phones: en | ar | both (GEOAI_FIELD_LANG; set by the Platform at start-up)


def _description_en(wo: dict, finding: str = "") -> str:
    head = " · ".join(x for x in (wo.get("Work_Order_ID", ""), wo.get("Task_Type", "")) if x)
    lines = [f"Work order: {head}" if head else "", f"Incident: {wo.get('Incident_ID', '')} · {wo.get('Area_Name', '')}".strip(" ·")
             if wo.get("Incident_ID") or wo.get("Area_Name") else "",
             f"WHAT THE AI FOUND (not confirmed): {finding}" if finding else "",
             f"YOUR TASK: {(wo.get('Instructions') or 'Inspect the location and confirm or reject the AI finding.')[:900]}", f"HOW TO ANSWER: {HOW_TO_ANSWER}"]
    return "\n\n".join(x for x in lines if x)


def _description_ar(wo: dict, finding: str = "") -> str:
    from backend.services import i18n

    head = " · ".join(x for x in (wo.get("Work_Order_ID", ""), i18n.to_ar(wo.get("Task_Type", ""))) if x)
    area = i18n.to_ar(wo.get("Area_Name", ""))
    task = i18n.to_ar((wo.get("Instructions") or "Inspect the location and confirm or reject the AI finding.")[:900])
    lines = [f"أمر العمل: {head}" if head else "", f"الحادثة: {wo.get('Incident_ID', '')} · {area}".strip(" ·") if wo.get("Incident_ID") or area else "",
             f"ما وجده الذكاء الاصطناعي (غير مؤكد): {i18n.to_ar(finding)}" if finding else "", f"مهمتك: {task}", f"كيف تجيب: {i18n.HOW_TO_ANSWER_AR}"]
    # each Arabic paragraph is an isolated right-to-left run (RLI ... PDI): on a left-to-right screen the colon, ids and numbers then keep their right order
    return "\n\n".join("⁧" + x + "⁩" for x in lines if x)


def _fit(text: str) -> str:
    """Never longer than the hosted field: a longer text is cut at the last sentence end (or space) and marked with an ellipsis, not rejected."""
    if len(text) <= DESCRIPTION_LIMIT:
        return text
    cut = text[:DESCRIPTION_LIMIT - 1]
    stop = max(cut.rfind(". "), cut.rfind("\n"))
    if stop > DESCRIPTION_LIMIT // 2:
        cut = cut[:stop + 1]
    elif " " in cut:
        cut = cut[:cut.rfind(" ")]
    return cut.rstrip() + "…"


def description(wo: dict, finding: str = "") -> str:
    """The task text shown in Field Maps, laid out like the in-app investigator card (English, Arabic, or Arabic then English)."""
    if LANG == "ar":
        return _fit(_description_ar(wo, finding))
    if LANG == "both":
        return _fit(_description_ar(wo, finding) + "\n\n――――――――\n\n" + _description_en(wo, finding))
    return _fit(_description_en(wo, finding))


def task_fields(wo: dict, finding: str = "") -> dict:
    """The esritask_* values for a work order's attributes. Unassigned work orders have no assignee; an assignee needs the investigator's ArcGIS login."""
    status = STATUS.get(wo.get("Status", ""), 0)
    assignee = (wo.get("Assigned_To_Username") or None) if wo.get("Assigned_Worker") else None
    if status == 1 and not assignee:
        status = 0                      # nobody to hand it to in Field Maps yet: it stays in the Unassigned list
    desc = description(wo, finding)
    return {"esritask_type": type_code(wo.get("Incident_Type", "")), "esritask_assignee": assignee, "esritask_status": status,
            "esritask_priority": PRIORITY.get(wo.get("Priority", ""), 0), "esritask_duedate": iso_ms(wo.get("Due_Date")),
            "esritask_description": desc, "esritask_notes": wo.get("esritask_notes") or ""}
