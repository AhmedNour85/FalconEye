"""The eight visual-distortion types (urban visual pollution) raised as incidents by the visual-distortion use case."""
import re

from fastapi.testclient import TestClient

from backend.agent.agent import GeoAIAgent
from backend.api.app import create_app
from backend.gis import schema as S
from backend.services import i18n, tasks, visual_types

ARABIC = re.compile(r"[؀-ۿ]")


def client(platform):
    return TestClient(create_app(platform, GeoAIAgent(platform)))


def test_eight_types_with_arabic_and_instructions():
    assert len(visual_types.VISUAL_TYPES) == 8
    for k, v in visual_types.VISUAL_TYPES.items():
        assert v["name"] and ARABIC.search(v["ar"]) and ARABIC.search(v["what_ar"]) and ARABIC.search(v["instr_ar"]) and v["instr"].endswith(".")
        assert visual_types.by_name(v["name"] + " (Candidate)")["ar"] == v["ar"] and visual_types.by_key(k)["name"] == v["name"]
        assert i18n.to_ar(v["name"]) == v["ar"] and i18n.to_ar(v["instr"]) == v["instr_ar"]


def test_the_event_raises_incidents_of_the_new_types(platform):
    c = client(platform)
    res = c.post("/api/nccc/events/distortion_event").json()
    incs = [platform.store.get(S.INCIDENTS, i)["attrs"] for i in res["scan"]["new_incidents"]]
    assert len(incs) == 4                                                           # three real findings and the false-positive decoy
    names = [i["Incident_Type"] for i in incs]
    assert all(n in visual_types.NAMES for n in names) and len(set(names)) == 4     # four different kinds
    assert all(i["Category"] == "distortion" for i in incs)
    assert all("visual-distortion score" in i["Description"] and "SIMULATED" in i["Description"] for i in incs)    # candidates, never presented as confirmed


def test_work_order_and_task_type_for_a_new_kind(platform):
    c = client(platform)
    c.post("/api/nccc/events/distortion_event")
    a = next(x for x in c.get("/api/approvals?pending=true").json() if x["Action_Type"] == "create_work_order")
    c.post(f"/api/approvals/{a['Approval_ID']}/approve")
    wo = platform.store.all(S.WORK_ORDERS)[-1]["attrs"]
    vt = visual_types.by_name(wo["Incident_Type"])
    assert vt and wo["Instructions"] == vt["instr"]                                  # the instruction is specific to the kind
    assert tasks.TASK_TYPES[wo["esritask_type"]] == vt["name"]                       # it has its own Field Maps task type, not "Other"


def test_task_type_codes_of_the_old_types_did_not_move():
    assert tasks.TASK_TYPES[:13] == ["Water Leak (Suspected)", "Water Leak", "Streetlight Failure (Predicted)", "Streetlight Failure", "Streetlight Cluster Maintenance",
                                     "Streetlight Pole Inspection", "Visual Distortion Review", "Visual Distortion", "Urban Change Review", "Urban Change", "Land-Use Violation Review",
                                     "Urban Case", "Other"]
    assert tasks.type_code("Something unknown") == 12 and tasks.type_code("Construction Waste") == 13


def test_arabic_alerts_and_chat_for_the_new_types(platform):
    c = client(platform)
    c.post("/api/nccc/events/distortion_event")
    ar = c.get("/api/nccc/state?lang=ar").json()
    faults = [n for n in ar["notifications"] if n["Kind"] == "fault"]
    assert faults and all(ARABIC.search(n["Title"]) and not re.search(r"[A-Za-z]{5,}", re.sub(r"\([^)]*\)|INC-\d+|\w+-\w+", "", n["Title"])) for n in faults), [n["Title"] for n in faults]
    assert all("SIMULATED" not in n["Message"] and "Needs a field" not in n["Message"] for n in faults), faults[0]["Message"]
    reply = c.post("/api/nccc/ask", json={"message": "اكشف التشوه البصري في الملز", "session_id": "v"}).json()["reply"]
    assert "درجة التشوّه البصري" in reply and "edge-warp" not in reply
    en = c.post("/api/nccc/ask", json={"message": "detect visual distortion in Al Malaz", "session_id": "e"}).json()["reply"]
    assert "visual-distortion score" in en
