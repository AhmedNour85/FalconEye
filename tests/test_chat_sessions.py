"""Each Operation page tab has its own chat session: a bare "approve" in one tab never acts on another tab's proposal."""
from fastapi.testclient import TestClient

from backend.agent.agent import GeoAIAgent
from backend.api.app import create_app


def _setup(platform):
    ag = GeoAIAgent(platform)
    c = TestClient(create_app(platform, ag))
    c.post("/api/nccc/events/olaya_leak")
    for a in c.get("/api/approvals?pending=true").json():
        c.post(f"/api/approvals/{a['Approval_ID']}/reject")
    iid = next(f["id"] for f in platform.store.all("Riyadh_Operational_Incidents") if f["attrs"]["Status"] == "Open")
    return c, ag, iid


def test_approve_in_one_tab_does_not_act_on_another_tabs_proposal(platform):
    c, ag, iid = _setup(platform)
    c.post("/api/nccc/ask", json={"message": f"create a work order for {iid}", "session_id": "op-tabA"})
    pend = c.get("/api/approvals?pending=true").json()
    assert len(pend) == 1 and pend[0]["Session_ID"] == "op-tabA"
    before = len(platform.store.all("Riyadh_Work_Orders"))
    c.post("/api/nccc/ask", json={"message": "approve", "session_id": "op-tabB"})
    assert [a["Approval_ID"] for a in c.get("/api/approvals?pending=true").json()] == [pend[0]["Approval_ID"]]
    assert len(platform.store.all("Riyadh_Work_Orders")) == before
    c.post("/api/nccc/ask", json={"message": "approve", "session_id": "op-tabA"})       # the tab that asked can still approve it
    assert not c.get("/api/approvals?pending=true").json()
    assert len(platform.store.all("Riyadh_Work_Orders")) == before + 1


def test_session_ids_must_be_short_and_plain(platform):
    c, _, _ = _setup(platform)
    for bad in ["", "a" * 65, "tab one", "x<script>", "../etc"]:
        assert c.post("/api/nccc/ask", json={"message": "hello", "session_id": bad}).status_code == 422, bad
    assert c.post("/api/nccc/ask", json={"message": "hello", "session_id": "op-" + "a" * 24}).status_code == 200


def test_old_sessions_are_dropped_least_recently_used_first(platform):
    ag = GeoAIAgent(platform)
    ag.MAX_SESSIONS = 3
    for sid in ["a", "b", "c"]:
        ag.session(sid)
    ag.session("a")                       # "a" is used again, so "b" is now the oldest
    ag.session("d")
    assert list(ag.sessions) == ["c", "a", "d"]
