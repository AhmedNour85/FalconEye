"""Imagery epoch comparison: the data behind the 'Compare imagery' viewer."""
from fastapi.testclient import TestClient

from backend.agent.agent import GeoAIAgent
from backend.api.app import create_app
from backend.gis import schema as S


def client(platform):
    return TestClient(create_app(platform, GeoAIAgent(platform)))


def test_unscanned_area_reports_no_changes_but_has_both_epochs(platform):
    c = client(platform)
    d = c.get("/api/nccc/imagery/Olaya").json()
    assert d["scanned"] is False and d["changes"] == [] and d["simulated"] is True
    assert d["before"] != d["after"] and d["bounds"]["xmax"] > d["bounds"]["xmin"]
    assert c.get("/api/imagery/Olaya/A.png").status_code == 200 and c.get("/api/imagery/Olaya/Bn.png").status_code == 200
    assert c.get("/api/nccc/imagery/Nowhere").status_code == 404


def test_scan_finds_change_events_and_links_incidents(platform):
    c = client(platform)
    r = c.post("/api/nccc/imagery/Olaya/scan").json()
    assert any(s["agent"] == "zayed" and "Olaya" in s["detail"] for s in r["steps"])
    d = c.get("/api/nccc/imagery/Olaya").json()
    assert d["scanned"] and d["changes"]
    b = d["bounds"]
    for ch in d["changes"]:
        assert len(ch["ring"]) >= 3 and all(b["xmin"] <= p[0] <= b["xmax"] and b["ymin"] <= p[1] <= b["ymax"] for p in ch["ring"])   # polygons sit inside the scene
    sig = [ch for ch in d["changes"] if ch["significant"]]
    assert sig and all(ch["incident_id"] for ch in sig)                                                                               # significant changes became incidents
    assert d["changes"][0]["significant"]                                                                                             # significant ones are listed first
    assert platform.store.get(S.INCIDENTS, sig[0]["incident_id"])["attrs"]["Category"] == "change"


def test_rescan_keeps_incident_links(platform):
    c = client(platform)
    c.post("/api/nccc/imagery/KAFD/scan")
    first = {ch["id"]: ch["incident_id"] for ch in c.get("/api/nccc/imagery/KAFD").json()["changes"]}
    c.post("/api/nccc/imagery/KAFD/scan")
    second = {ch["id"]: ch["incident_id"] for ch in c.get("/api/nccc/imagery/KAFD").json()["changes"]}
    assert first == second
