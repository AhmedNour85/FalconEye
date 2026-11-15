"""Record ids typed in chat are understood on their own ("INC-0027", "WO-0003", unknown ids)."""
from backend.gis import schema as S


def test_bare_incident_id_returns_its_details(platform, agent):
    platform.crew.run_cycle()
    iid = platform.store.all(S.INCIDENTS)[-1]["id"]
    for text in (iid, f"tell me about {iid}", f"what is {iid.lower()}?"):
        r = agent.chat("t", text)
        assert iid in r["reply"] and "GeoAI Operations Agent" not in r["reply"]
        assert r["trace"][0]["tool"] == "get_incident"


def test_unknown_id_is_reported_plainly(agent):
    r = agent.chat("t", "INC-9999")
    assert "can't find" in r["reply"] and "INC-9999" in r["reply"]


def test_actions_on_a_named_incident_use_that_incident(platform, agent):
    platform.crew.run_cycle()
    inc = next(i for i in platform.store.all(S.INCIDENTS) if i["attrs"]["Status"] == "Open")
    r = agent.chat("t", f"create a work order for {inc['id']}")
    assert [t["tool"] for t in r["trace"]] == ["propose_work_order"]
    assert any(a["Incident_ID"] == inc["id"] for a in platform.approvals.pending())
    r2 = agent.chat("t", f"what is around {inc['id']}?")
    assert r2["trace"][0]["tool"] == "spatial_analysis"
