from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.agent.agent import GeoAIAgent


def client(platform):
    return TestClient(create_app(platform, GeoAIAgent(platform)))


def test_health_layers_and_config(platform):
    c = client(platform)
    h = c.get("/api/health").json()
    assert h["status"] == "ok" and h["agent_mode"] == "rules" and h["data_mode"] == "SYNTHETIC-DEMO"
    gj = c.get("/api/layers/Riyadh_Water_Network").json()
    assert gj["type"] == "FeatureCollection" and len(gj["features"]) > 100
    assert c.get("/api/layers/Riyadh_Sim_Ground_Truth").status_code == 404  # simulator truth never exposed
    assert "Olaya" in c.get("/api/config").json()["areas"]
    assert c.get("/api/imagery/Olaya/A.png").headers["content-type"] == "image/png"


def test_legacy_pages_are_gone(platform):
    c = client(platform)
    assert c.get("/classic.html").status_code == 404 and c.get("/operational_dashboard.html").status_code == 404
    assert "classic.html" not in c.get("/index.html").text


def test_home_page_is_named_riyadh_city_view(platform):
    c = client(platform)
    assert "<h1>Falcon Eye</h1>" in c.get("/home.html").text
    assert c.get("/openapi.json").json()["info"]["title"] == "Falcon Eye"


def test_the_server_uses_its_own_port():
    from backend import main
    assert main.PORT == 8020


def on_fake():
    """The app running on ArcGIS Online, with a stand-in for the hosted layers."""
    from backend.platform import Platform
    from config.settings import Settings
    from tests.fakes import FakeGateway
    gw = FakeGateway()
    p = Platform(settings=Settings(store="arcgis", arcgis_username="u", arcgis_password="p", field_sync_seconds=0, field_form=True), gateway=gw)
    p.reset()
    return client(p), p, gw


def test_health_names_the_system_of_record(platform):
    h = client(platform).get("/api/health").json()
    assert h["store"].startswith("memory only") and h["data_ready"] is True and "arcgis_pending_writes" not in h
    c, p, gw = on_fake()
    h = c.get("/api/health").json()
    assert h["store"] == "ArcGIS Online (CityView)" and "last_refresh" in h
    assert c.get("/api/nccc/state").json()["store"] == "ArcGIS Online (CityView)"


def test_a_refused_write_is_a_503_with_a_plain_message_and_the_approval_stays_proposed():
    from backend.gis import schema as S
    from backend.gis.store import StoreWriteError
    c, p, gw = on_fake()
    c.post("/api/nccc/events/olaya_leak")
    apr = p.approvals.pending()[0]["Approval_ID"]
    gw.fail_next = StoreWriteError("the network is down")
    r = c.post(f"/api/approvals/{apr}/approve")
    assert r.status_code == 503 and "ArcGIS Online did not accept the change, so nothing was changed" in r.json()["detail"] and "the network is down" in r.json()["detail"]
    assert p.store.get(S.APPROVALS, apr)["attrs"]["Status"] == "Proposed" and not p.store.all(S.WORK_ORDERS)[-1:] or p.store.get(S.APPROVALS, apr)["attrs"]["Status"] == "Proposed"
    assert c.post(f"/api/approvals/{apr}/approve").status_code == 200          # the same approval works once ArcGIS Online is back
    assert p.store.get(S.APPROVALS, apr)["attrs"]["Status"] == "Executed"


def test_an_automatic_scan_that_arcgis_refuses_is_reported_and_the_loop_survives():
    from backend.gis.store import StoreWriteError
    c, p, gw = on_fake()
    p.crew.autopilot, p.crew.interval = True, 0.0

    def one_pass_then_stop(*a, **k):
        p.crew.autopilot = False                                                 # one pass only
        gw.fail_after(1, StoreWriteError("the network is down"))                 # ArcGIS Online is gone: even the error note cannot be stored
        raise StoreWriteError("the network is down")
    p.crew.run_cycle = one_pass_then_stop
    p.crew._loop()                                                               # must return, not raise
    gw.fail_after(None)
    assert "the network is down" in c.get("/api/nccc/state").json()["crew"]["record_error"]["message"]


def test_rbac_blocks_viewer(platform):
    c = client(platform)
    assert c.post("/api/approvals/APR-0001/approve", headers={"X-Role": "viewer"}).status_code == 403


def test_demo_replays_end_to_end_and_resets(platform):
    c = client(platform)
    for n in range(1, 8):
        r = c.post(f"/api/demo/run/{n}?auto_approve=true").json()
        assert r["complete"], (n, r["narrative"])
    inc = c.get("/api/incidents").json()["result"]["incidents"]
    assert any(i["status"] == "Resolved" for i in inc)
    k = c.get("/api/kpis").json()
    assert k["resolved_incidents"] >= 1
    r8 = c.post("/api/demo/run/8?auto_approve=true").json()
    assert r8["complete"] and any("SIMULATED inspection" in l for l in r8["narrative"])
    # replay: reset then run again
    c.post("/api/demo/reset")
    r1 = c.post("/api/demo/run/1").json()
    assert r1["complete"]
    assert c.get("/api/audit").json()


def test_manual_approval_flow_via_api(platform):
    c = client(platform)
    c.post("/api/demo/run/1"); c.post("/api/demo/run/2"); c.post("/api/demo/run/3"); c.post("/api/demo/run/4")
    r = c.post("/api/demo/run/5").json()
    assert r["awaiting_approval"] and r["pending_approvals"]
    assert c.post(f"/api/approvals/{r['pending_approvals'][0]['Approval_ID']}/approve").status_code == 200
    r = c.post("/api/demo/run/5").json()
    assert r["awaiting_approval"]
    c.post(f"/api/approvals/{r['pending_approvals'][0]['Approval_ID']}/approve")
    r = c.post("/api/demo/run/5").json()
    assert r["complete"]
    w = c.get("/api/workers").json()
    wid = next(x["Worker_ID"] for x in w if x["Open_Tasks"] == 1)
    tasks = c.get(f"/api/field/tasks/{wid}").json()
    assert tasks and tasks[0]["ai_finding"]
    t = tasks[0]
    sub = c.post("/api/field/submit", data={"work_order_id": t["work_order"]["Work_Order_ID"], "worker_id": wid, "status": "Confirmed", "observation": "Water seeping from joint",
                                            "lat": t["location"]["lat"], "lon": t["location"]["lon"]}, files={"photo": ("e.png", b"\x89PNG....", "image/png")})
    assert sub.status_code == 200 and sub.json()["outcome"] == "Confirmed"
    bad = c.post("/api/field/submit", data={"work_order_id": t["work_order"]["Work_Order_ID"], "worker_id": "WRK-099", "status": "Confirmed", "observation": "Water seeping", "lat": 24.7, "lon": 46.7})
    assert bad.status_code == 422


def test_resolved_card_counts_only_work_done_since_the_reset(platform):
    """The seeded history is background for trends and learning; the Resolved card starts at 0 and counts only incidents closed in this run."""
    from backend.gis import schema as S
    c = client(platform)
    assert c.get("/api/nccc/state").json()["kpis"]["resolved"] == 0
    c.post("/api/nccc/events/olaya_leak")
    iid = next(f["id"] for f in platform.store.all(S.INCIDENTS) if f["attrs"]["Status"] == "Open")
    platform.store.update(S.INCIDENTS, iid, Status="Resolved")
    assert c.get("/api/nccc/state").json()["kpis"]["resolved"] == 1
    k = c.get("/api/kpis").json()
    assert k["resolved_incidents"] == 1 and k["total_incidents"] >= 29           # resolution figures are this run's; the totals still include the history


def test_response_time_starts_at_zero_after_a_reset(platform):
    c = client(platform)
    k = c.get("/api/kpis").json()
    assert k["avg_response_time_hours"] is None and k["incident_resolution_rate_pct"] is None and k["resolved_incidents"] == 0 and k["verified_incidents"] == 0
