"""Field reports come from ArcGIS Field Maps; the in-app investigator form is disabled by default."""
from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.gis import schema as S
from backend.platform import Platform
from backend.agent.agent import GeoAIAgent
from config.settings import Settings


class FakeFieldMaps:
    """Stands in for the ArcGIS Online mirror: a worker adds a report on the Field Verification layer in Field Maps."""

    def __init__(self, rows):
        self.rows = rows                  # list of (attrs, geom) waiting in "ArcGIS Online"

    def apply(self, *a):
        pass

    def pull_updates(self, layer, since, store):
        n = 0
        if layer == S.VERIFICATION:
            for i, (attrs, geom) in enumerate(self.rows):
                fid = attrs.get("Verification_ID") or store.next_id("VER")
                attrs = {**attrs, "Verification_ID": fid}
                self.rows[i] = (attrs, geom)              # like the real adapter, the id is written back to ArcGIS Online
                if not store.get(layer, fid):
                    store.upsert(layer, attrs, geom, persist=False)
                    n += 1
        return n


def _assigned_work_order(platform):
    platform.crew.run_cycle()
    res = platform.crew.inject("olaya_leak")
    iid = next(i for i in res["scan"]["new_incidents"] if platform.store.get(S.INCIDENTS, i)["attrs"]["Category"] == "water")
    for a in list(platform.approvals.pending()):
        if a["Incident_ID"] == iid:
            platform.approvals.approve(a["Approval_ID"], actor="t")
    platform.crew.run_cycle()
    for a in list(platform.approvals.pending()):
        if a["Incident_ID"] == iid:
            platform.approvals.approve(a["Approval_ID"], actor="t")
    wo = platform.store.query(S.WORK_ORDERS, Incident_ID=iid)[-1]
    assert wo["attrs"]["Assigned_Worker"]
    return iid, wo


def test_field_maps_report_is_assessed_and_the_operator_is_told(platform):
    iid, wo = _assigned_work_order(platform)
    inc = platform.store.get(S.INCIDENTS, iid)
    lon, lat = inc["geom"]["coordinates"]
    # the worker's report as Field Maps writes it: no id, no assessment, no distance, GPS from the phone
    report = {"Work_Order_ID": wo["id"], "Observation": "Wet asphalt and a visible leak at the valve.", "Verification_Status": "Confirmed"}
    platform.mirror = FakeFieldMaps([(report, {"type": "Point", "coordinates": [lon + 0.0001, lat]})])
    out = platform.pull_field_updates()
    assert out["pulled"] == 1 and out["assessed"] == 1
    v = platform.store.query(S.VERIFICATION, Incident_ID=iid)[-1]["attrs"]
    assert v["Agent_Assessment"] and v["Worker_ID"] == wo["attrs"]["Assigned_Worker"] and v["Simulated_Worker"] == "No" and v["Distance_To_Detection_M"] < 50
    assert platform.store.get(S.INCIDENTS, iid)["attrs"]["Verification_Outcome"] == "Confirmed"
    assert any(n["Kind"] == "verified" and n["Incident_ID"] == iid for n in platform.crew.notifications(limit=100))     # the operator sees it without a scan
    assert platform.pull_field_updates()["assessed"] == 0                                                                    # idempotent


def test_report_without_gps_or_valid_status_is_never_strong_evidence(platform):
    iid, wo = _assigned_work_order(platform)
    platform.mirror = FakeFieldMaps([({"Work_Order_ID": wo["id"], "Observation": "ok", "Verification_Status": "looks fine"}, None)])
    platform.pull_field_updates()
    v = platform.store.query(S.VERIFICATION, Incident_ID=iid)[-1]["attrs"]
    assert v["Verification_Status"] == "Needs Further Inspection"
    assert platform.store.get(S.INCIDENTS, iid)["attrs"]["Status"] == "Requires Further Inspection"


def test_report_for_an_unknown_work_order_is_left_alone(platform):
    platform.mirror = FakeFieldMaps([({"Work_Order_ID": "WO-9999", "Observation": "x", "Verification_Status": "Confirmed"}, None)])
    out = platform.pull_field_updates()
    assert out["assessed"] == 0


def test_investigator_form_is_disabled_by_default(tmp_path):
    s = Settings(anthropic_api_key="", arcgis_username="", arcgis_password="")
    assert s.field_form is False
    p = Platform(settings=s)
    c = TestClient(create_app(p, GeoAIAgent(p)))
    r = c.post("/api/field/submit", data={"work_order_id": "WO-1", "worker_id": "WRK-001", "status": "Confirmed", "observation": "anything", "lat": 24.7, "lon": 46.7})
    assert r.status_code == 410 and "Field Maps" in r.json()["detail"]
    assert c.post("/api/field/accept", data={"work_order_id": "WO-1", "worker_id": "WRK-001"}).status_code == 410
    page = c.get("/field.html")
    assert page.status_code == 200 and "Field Maps" in page.text and "<form" not in page.text
    assert c.get("/api/health").json()["field_form"] is False


def test_assignment_is_sent_to_field_maps_with_the_investigators_login(tmp_path):
    s = Settings(anthropic_api_key="", arcgis_username="", arcgis_password="", field_users={"WRK-001": "nawaf.harbi", "WRK-002": "khalid.otaibi", "WRK-003": "saad.qahtani", "WRK-004": "hamad.ghamdi", "WRK-005": "yousef.dosari", "WRK-006": "ibrahim.shehri", "WRK-007": "majed.mutairi"})
    platform = Platform(settings=s)
    pushed = []
    platform.apply_field_users()
    platform.store.is_hosted = True                                           # as when the rows live in ArcGIS Online
    platform.store._persist_many = lambda layer, rows: pushed.extend((layer, fid, dict(attrs)) for _op, fid, attrs, _g in rows)
    platform.store._persist = lambda layer, op, fid, attrs, geom: pushed.append((layer, fid, dict(attrs)))
    iid, wo = _assigned_work_order(platform)
    wo = platform.store.get(S.WORK_ORDERS, wo["id"])["attrs"]
    last = [a for layer, fid, a in pushed if layer == S.WORK_ORDERS and a.get("Work_Order_ID") == wo["Work_Order_ID"]][-1]
    assert last["Assigned_Worker"] and last["Assigned_Worker_Name"] and last["Assigned_At"]
    assert last["Field_Maps_Status"] == "Sent to ArcGIS Field Maps"
    assert last["Incident_Type"] and last["Area_Name"]
    assert last["Assigned_To_Username"] == s.field_users[last["Assigned_Worker"]]


def test_field_maps_acceptance_notifies_the_operator(platform):
    iid, wo = _assigned_work_order(platform)

    class Accepting(FakeFieldMaps):
        def pull_updates(self, layer, since, store):
            if layer == S.WORK_ORDERS:
                store.update(S.WORK_ORDERS, wo["id"], Accepted_At="2026-01-01T10:00:00Z")      # the worker tapped Accept in Field Maps
                return 1
            return 0
    platform.mirror = Accepting([])
    platform.pull_field_updates()
    assert any(n["Kind"] == "accepted" and n["Incident_ID"] == iid for n in platform.crew.notifications(limit=100))


def test_task_fields_follow_the_work_order_lifecycle(tmp_path):
    from backend.services import tasks
    s = Settings(anthropic_api_key="", arcgis_username="", arcgis_password="",
                 field_users={f"WRK-{i:03d}": "story_viewer" for i in range(1, 8)})
    p = Platform(settings=s)
    iid, wo = _assigned_work_order(p)
    a = p.store.get(S.WORK_ORDERS, wo["id"])["attrs"]
    assert tasks.TASK_TYPES[a["esritask_type"]] == a["Incident_Type"] or a["esritask_type"] == tasks.TASK_TYPES.index("Other")     # the title Field Maps shows
    assert a["esritask_assignee"] == "story_viewer" and a["esritask_status"] == 1 and a["esritask_priority"] in (1, 2, 3, 4)
    assert a["esritask_duedate"] and wo["id"] in a["esritask_description"]
    # the operator verifies -> the task moves on
    p.simulate_field_response(wo["id"])
    assert p.store.get(S.WORK_ORDERS, wo["id"])["attrs"]["esritask_status"] == 2
    # a work order nobody can be handed to in Field Maps yet stays in the Unassigned list
    assert tasks.task_fields({"Status": "Assigned", "Assigned_Worker": "WRK-001", "Assigned_To_Username": "", "Incident_Type": "Water Leak"})["esritask_status"] == 0
    assert tasks.task_fields({"Status": "Created", "Incident_Type": "Something new"})["esritask_type"] == tasks.TASK_TYPES.index("Other")


def test_starting_the_task_in_field_maps_accepts_the_assignment(tmp_path):
    s = Settings(anthropic_api_key="", arcgis_username="", arcgis_password="",
                 field_users={f"WRK-{i:03d}": "story_viewer" for i in range(1, 8)})
    p = Platform(settings=s)
    iid, wo = _assigned_work_order(p)

    class Starting(FakeFieldMaps):
        def pull_updates(self, layer, since, store):
            if layer == S.WORK_ORDERS:
                cur = store.get(S.WORK_ORDERS, wo["id"])
                store.upsert(S.WORK_ORDERS, {**cur["attrs"], "esritask_status": 2}, cur["geom"], persist=False)      # the worker tapped Start on the task
                return 1
            return 0
    p.mirror = Starting([])
    p.pull_field_updates()
    a = p.store.get(S.WORK_ORDERS, wo["id"])["attrs"]
    assert a["Status"] == "In Progress" and a["Accepted_At"] and a["esritask_status"] == 2
    assert any(n["Kind"] == "accepted" and n["Incident_ID"] == iid for n in p.crew.notifications(limit=100))


def test_report_without_a_work_order_id_is_matched_to_the_one_the_worker_is_standing_at(platform):
    iid, wo = _assigned_work_order(platform)
    lon, lat = platform.store.get(S.INCIDENTS, iid)["geom"]["coordinates"]
    platform.mirror = FakeFieldMaps([({"Work_Order_ID": "", "Observation": "Leak confirmed at the valve.", "Verification_Status": "Confirmed"},
                                      {"type": "Point", "coordinates": [lon + 0.0002, lat]})])
    out = platform.pull_field_updates()
    assert out["assessed"] == 1
    v = platform.store.query(S.VERIFICATION, Incident_ID=iid)[-1]["attrs"]
    assert v["Work_Order_ID"] == wo["id"] and v["Agent_Assessment"]
    assert any(n["Kind"] == "verified" and n["Incident_ID"] == iid for n in platform.crew.notifications(limit=100))


class _Finishing(FakeFieldMaps):
    def __init__(self, wo_id, notes=""):
        super().__init__([])
        self.wo_id, self.notes = wo_id, notes

    def pull_updates(self, layer, since, store):
        if layer == S.WORK_ORDERS:
            cur = store.get(S.WORK_ORDERS, self.wo_id)
            store.upsert(S.WORK_ORDERS, {**cur["attrs"], "esritask_status": 3, "esritask_notes": self.notes}, cur["geom"], persist=False)      # Note, then Finish
            return 1
        return 0


def test_finish_with_a_note_is_the_report(platform):
    iid, wo = _assigned_work_order(platform)
    platform.mirror = _Finishing(wo["id"], "Confirmed: cracks and a bulging wall on the north side")
    platform.pull_field_updates()
    v = platform.store.query(S.VERIFICATION, Incident_ID=iid)
    assert len(v) == 1 and v[0]["attrs"]["Verification_Status"] == "Confirmed" and v[0]["attrs"]["Agent_Assessment"]
    assert v[0]["attrs"]["Observation"].startswith("[Field Maps task]") and v[0]["attrs"]["Investigator_Name"]
    assert platform.store.get(S.INCIDENTS, iid)["attrs"]["Verification_Outcome"] == "Confirmed"
    kinds = {n["Kind"] for n in platform.crew.notifications(limit=100) if n["Incident_ID"] == iid}
    assert "verified" in kinds and "field_done" not in kinds                      # one alert, the verified one
    platform.pull_field_updates()
    assert len(platform.store.query(S.VERIFICATION, Incident_ID=iid)) == 1        # once only


def test_finish_without_a_verdict_word_needs_a_further_inspection(platform):
    iid, wo = _assigned_work_order(platform)
    platform.mirror = _Finishing(wo["id"], "")
    platform.pull_field_updates()
    assert platform.store.query(S.VERIFICATION, Incident_ID=iid)[-1]["attrs"]["Verification_Status"] == "Needs Further Inspection"
    assert platform.store.get(S.INCIDENTS, iid)["attrs"]["Status"] == "Requires Further Inspection"


def test_finish_does_not_duplicate_a_report_the_worker_already_filed(platform):
    iid, wo = _assigned_work_order(platform)
    lon, lat = platform.store.get(S.INCIDENTS, iid)["geom"]["coordinates"]
    platform.mirror = FakeFieldMaps([({"Work_Order_ID": wo["id"], "Observation": "Leak at the valve.", "Verification_Status": "Confirmed"}, {"type": "Point", "coordinates": [lon, lat]})])
    platform.pull_field_updates()
    platform.mirror = _Finishing(wo["id"], "Rejected")
    platform.pull_field_updates()
    v = platform.store.query(S.VERIFICATION, Incident_ID=iid)
    assert len(v) == 1 and v[0]["attrs"]["Verification_Status"] == "Confirmed"      # the filed report stands
    assert any(n["Kind"] == "field_done" and n["Incident_ID"] == iid for n in platform.crew.notifications(limit=100))


class _FinishingWithForm(FakeFieldMaps):
    """Finish on the task after answering the radio buttons and the comment box (Field_Verdict / Field_Comment on the work order)."""

    def __init__(self, wo_id, **fields):
        super().__init__([])
        self.wo_id, self.fields = wo_id, fields

    def pull_updates(self, layer, since, store):
        if layer == S.WORK_ORDERS:
            cur = store.get(S.WORK_ORDERS, self.wo_id)
            store.upsert(S.WORK_ORDERS, {**cur["attrs"], "esritask_status": 3, **self.fields}, cur["geom"], persist=False)
            return 1
        return 0


def test_finish_uses_the_radio_answer_and_the_comment(platform):
    iid, wo = _assigned_work_order(platform)
    platform.mirror = _FinishingWithForm(wo["id"], Field_Verdict="Rejected", Field_Comment="Dry asphalt, no valve chamber leak at all.")
    platform.pull_field_updates()
    v = platform.store.query(S.VERIFICATION, Incident_ID=iid)
    assert len(v) == 1 and v[0]["attrs"]["Verification_Status"] == "Rejected"
    assert v[0]["attrs"]["Observation"] == "[Field Maps task] Dry asphalt, no valve chamber leak at all."
    assert platform.store.get(S.INCIDENTS, iid)["attrs"]["Verification_Outcome"] == "Rejected"


def test_the_radio_answer_wins_over_a_note_and_the_note_still_works_alone(platform):
    iid, wo = _assigned_work_order(platform)
    platform.mirror = _FinishingWithForm(wo["id"], Field_Verdict="Escalate", Field_Comment="", esritask_notes="Confirmed: something else")
    platform.pull_field_updates()
    v = platform.store.query(S.VERIFICATION, Incident_ID=iid)[-1]["attrs"]
    assert v["Verification_Status"] == "Escalate" and "something else" in v["Observation"]        # no comment: the note is the text
    p2 = type(platform)(settings=platform.settings)
    iid2, wo2 = _assigned_work_order(p2)
    p2.mirror = _FinishingWithForm(wo2["id"], Field_Verdict="not a real code", esritask_notes="Not found: nothing there")
    p2.pull_field_updates()
    assert p2.store.query(S.VERIFICATION, Incident_ID=iid2)[-1]["attrs"]["Verification_Status"] == "Rejected"    # an unknown answer falls back to the note


def test_form_choices_match_the_in_app_form():
    from backend.services import field, i18n

    assert [c[0] for c in i18n.VERDICT_CHOICES] == list(field.STATUSES) or set(c[0] for c in i18n.VERDICT_CHOICES) == set(field.STATUSES)
    assert i18n.verdict_label("Confirmed") == "Yes, confirmed" and i18n.verdict_label("Rejected", "ar") == "لم يتم العثور"
    assert i18n.verdict_label("Escalate", "both") == "Escalate / تصعيد"
    assert "Field_Verdict" in S.LAYERS[S.WORK_ORDERS].fields and "Field_Comment" in S.LAYERS[S.WORK_ORDERS].fields


# ---- Plan 4, Task 1: mobility task types, nine assignees, safe text length ----
MOBILITY_TYPES = ["Traffic Incident", "Planned Road Closure", "Major Event Traffic Plan"]


def test_mobility_task_types_are_appended_and_existing_codes_are_unchanged():
    from backend.services import tasks
    assert tasks.TASK_TYPES[:13] == ["Water Leak (Suspected)", "Water Leak", "Streetlight Failure (Predicted)", "Streetlight Failure", "Streetlight Cluster Maintenance",
                                     "Streetlight Pole Inspection", "Visual Distortion Review", "Visual Distortion", "Urban Change Review", "Urban Change",
                                     "Land-Use Violation Review", "Urban Case", "Other"]
    assert tasks.TASK_TYPES[-3:] == MOBILITY_TYPES
    for t in MOBILITY_TYPES:
        assert tasks.TASK_TYPES[tasks.task_fields({"Status": "Created", "Incident_Type": t})["esritask_type"]] == t


def test_a_mobility_task_for_an_investigator_without_a_login_stays_unassigned():
    from backend.services import tasks
    wo = {"Status": "Assigned", "Assigned_Worker": "WRK-008", "Incident_Type": "Planned Road Closure"}
    f = tasks.task_fields({**wo, "Assigned_To_Username": ""})
    assert f["esritask_status"] == 0 and f["esritask_assignee"] is None
    f = tasks.task_fields({**wo, "Assigned_To_Username": "bandar.shehri"})
    assert f["esritask_status"] == 1 and f["esritask_assignee"] == "bandar.shehri"


def test_the_assignee_list_covers_all_nine_workers():
    users = {f"WRK-{i:03d}": f"user{i}" for i in range(1, 10)}
    p = Platform(settings=Settings(anthropic_api_key="", arcgis_username="", arcgis_password="", field_users=users))
    seen = {}

    class Rec:
        def ensure_task_domains(self, layer, types, u):
            seen.update(types=list(types), users=dict(u))
            return True
    p.gateway = Rec()
    assert p.setup_field_tasks() is True
    assert len(seen["users"]) == 9 and seen["types"][-3:] == MOBILITY_TYPES


def test_a_bilingual_description_never_passes_the_hosted_limit():
    from backend.services import tasks
    old = tasks.LANG
    tasks.LANG = "both"
    try:
        wo = {"Work_Order_ID": "WO-1", "Task_Type": "Confirm the closure is in place", "Instructions": "Confirm the closure is set up."}
        d = tasks.description(wo, "The road section is blocked by a crash. " * 120)
        assert len(d) <= tasks.DESCRIPTION_LIMIT == 4000 and d.rstrip().endswith("…")
        assert tasks.description({"Work_Order_ID": "WO-1"}, "") .rstrip()[-1] != "…"          # a short text is never marked as cut
    finally:
        tasks.LANG = old


# ---- Plan 4, Task 2: answers on mobility tasks ----
import json as _json

import pytest as _pytest


def _mobility_task(platform, name):
    """A dispatched mobility task: (event id, incident id, work order id)."""
    out = platform.crew.inject(name)
    iid = out["scan"]["new_incidents"][0]
    apr = next(p for p in platform.approvals.pending() if p["Incident_ID"] == iid and p["Action_Type"] == "apply_traffic_plan")
    assert platform.approvals.approve(apr["Approval_ID"])["ok"]
    wo = platform.store.query(S.WORK_ORDERS, Incident_ID=iid)[0]["id"]
    platform.crew.run_cycle(scope=frozenset({"mobility"}))
    a = next(p for p in platform.approvals.pending() if p["Action_Type"] == "assign_worker" and _json.loads(p["Payload"])["work_order_id"] == wo)
    assert platform.approvals.approve(a["Approval_ID"])["ok"]
    return out["id"], iid, wo


def _status(platform, iid):
    return platform.store.get(S.INCIDENTS, iid)["attrs"]["Status"]


@_pytest.mark.parametrize("name", ["road_closure", "major_event"])
def test_finishing_a_plan_task_in_field_maps_with_yes_confirmed_confirms_it_and_needs_no_repair_visit(platform, name):
    _eid, iid, wo = _mobility_task(platform, name)
    platform.mirror = _FinishingWithForm(wo, Field_Verdict="Confirmed", Field_Comment="Signs and barriers are in place as approved.")
    platform.pull_field_updates()
    assert _status(platform, iid) == "Confirmed" and len(platform.store.query(S.VERIFICATION, Incident_ID=iid)) == 1
    platform.crew.run_cycle(scope=frozenset({"mobility"}))
    assert len(platform.store.query(S.VERIFICATION, Incident_ID=iid)) == 1          # nothing to repair: no second visit is asked for


def test_finishing_a_traffic_incident_task_confirms_it_and_the_road_is_cleared_in_a_later_visit(platform):
    _eid, iid, wo = _mobility_task(platform, "traffic_incident")
    platform.mirror = _FinishingWithForm(wo, Field_Verdict="Confirmed", Field_Comment="Two vehicles blocking the left lanes.")
    platform.pull_field_updates()
    assert _status(platform, iid) == "Confirmed"


def test_finishing_with_not_found_does_not_confirm_a_mobility_task(platform):
    _eid, iid, wo = _mobility_task(platform, "road_closure")
    platform.mirror = _FinishingWithForm(wo, Field_Verdict="Rejected", Field_Comment="No barriers on the road.")
    platform.pull_field_updates()
    assert _status(platform, iid) != "Confirmed"
    assert platform.store.query(S.VERIFICATION, Incident_ID=iid)[-1]["attrs"]["Verification_Status"] == "Rejected"


def test_a_note_alone_still_works_on_a_mobility_task(platform):
    _eid, iid, wo = _mobility_task(platform, "major_event")
    platform.mirror = _FinishingWithForm(wo, esritask_notes="Confirmed: marshals and signs are in position")
    platform.pull_field_updates()
    assert _status(platform, iid) == "Confirmed"


def test_the_task_text_of_a_mobility_task_is_bilingual(platform):
    import re
    from backend.services import tasks
    old = tasks.LANG
    tasks.LANG = "both"
    try:
        _eid, iid, wo = _mobility_task(platform, "road_closure")
        a = platform.store.get(S.WORK_ORDERS, wo)["attrs"]
        d = tasks.description(a, "")
        ar, _sep, en = d.partition("――――――――")
        assert "Confirm" in en and re.search(r"[؀-ۿ]{4,}", ar)
        latin_sentences = re.findall(r"\b[a-z]{4,} [a-z]{4,} [a-z]{4,}\b", ar)          # no run of three plain English words in the Arabic half
        assert not latin_sentences, latin_sentences
    finally:
        tasks.LANG = old


def test_start_up_gives_every_investigator_a_login_and_repairs_assigned_tasks(tmp_path):
    p = Platform(settings=Settings(anthropic_api_key="", arcgis_username="", arcgis_password=""))          # no logins known yet
    iid, wo = _assigned_work_order(p)
    a = p.store.get(S.WORK_ORDERS, wo["id"])["attrs"]
    assert not a["Assigned_To_Username"] and a["esritask_status"] == 0
    object.__setattr__(p.settings, "field_users", {f"WRK-{i:03d}": "story_viewer" for i in range(1, 10)})                          # the logins arrive in .env, the server restarts
    p.prepare_field_channel()
    assert all(w["attrs"]["ArcGIS_Username"] == "story_viewer" for w in p.store.all(S.WORKERS))
    a = p.store.get(S.WORK_ORDERS, wo["id"])["attrs"]
    assert a["Assigned_To_Username"] == "story_viewer" and a["esritask_assignee"] == "story_viewer" and a["esritask_status"] == 1


def _unassigned_finished(platform):
    """A work order made by 'Request inspection': nobody is assigned in the app, and the Field Maps user took the task and finished it."""
    iid, wo = _assigned_work_order(platform)
    platform.store.update(S.WORK_ORDERS, wo["id"], Assigned_Worker="", Assigned_Worker_Name="", Assigned_To_Username="", Status="Created")
    return iid, wo


def test_a_task_finished_by_someone_nobody_assigned_is_still_the_report(platform):
    iid, wo = _unassigned_finished(platform)
    platform.mirror = _FinishingWithForm(wo["id"], Field_Verdict="Confirmed", Field_Comment="Exposed wiring on the building front.", esritask_assignee="story_viewer")
    out = platform.pull_field_updates()
    assert out["assessed"] == 1
    v = platform.store.query(S.VERIFICATION, Incident_ID=iid)
    assert len(v) == 1 and v[0]["attrs"]["Verification_Status"] == "Confirmed" and v[0]["attrs"]["Agent_Assessment"]
    assert v[0]["attrs"]["Investigator_Name"] == "story_viewer"                  # the Field Maps account that finished it
    assert platform.store.get(S.INCIDENTS, iid)["attrs"]["Verification_Outcome"] == "Confirmed"
    assert any(n["Kind"] == "verified" and n["Incident_ID"] == iid for n in platform.crew.notifications(limit=100))
    platform.pull_field_updates()
    assert len(platform.store.query(S.VERIFICATION, Incident_ID=iid)) == 1        # once only


def test_a_task_already_finished_before_the_app_looked_is_picked_up_too(platform):
    """The server was restarted after the finish: the row is already 'done' when it is first read, so there is no change to notice."""
    iid, wo = _unassigned_finished(platform)
    cur = platform.store.get(S.WORK_ORDERS, wo["id"])
    platform.store.upsert(S.WORK_ORDERS, {**cur["attrs"], "esritask_status": 3, "Field_Verdict": "Confirmed", "Field_Comment": "Seen and confirmed."}, cur["geom"], persist=False)
    platform.mirror = FakeFieldMaps([])
    platform.pull_field_updates()
    assert len(platform.store.query(S.VERIFICATION, Incident_ID=iid)) == 1


def test_a_misspelled_arabic_confirmed_in_the_note_still_confirms():
    from backend.services import i18n
    assert i18n.verdict_from_note("موكد") == "Confirmed" and i18n.verdict_from_note("موكد، أسلاك مكشوفة") == "Confirmed"


def test_the_startup_repair_never_overwrites_a_task_finished_in_field_maps(platform):
    wo = platform.store.get(S.WORK_ORDERS, "WO-0001")
    hook = platform.store.write_hooks.pop(S.WORK_ORDERS)             # what a pull from ArcGIS Online does: take the values as they are
    platform.store.upsert(S.WORK_ORDERS, {**wo["attrs"], "esritask_status": 3, "Status": "Created"}, wo["geom"], persist=False)
    platform.store.write_hooks[S.WORK_ORDERS] = hook
    platform.backfill_investigator_names()
    assert platform.store.get(S.WORK_ORDERS, "WO-0001")["attrs"]["esritask_status"] == 3
