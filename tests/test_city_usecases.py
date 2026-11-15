"""City-management use cases as crew feeds: visual distortion, streetlight pole monitoring, land use, and the existing water leak flow."""
from backend.gis import schema as S


def _incidents(platform, res, category):
    return [i for i in res["scan"]["new_incidents"] if platform.store.get(S.INCIDENTS, i)["attrs"]["Category"] == category]


def test_new_feeds_are_listed(platform):
    ids = {f["id"] for f in platform.crew.feed_status()}
    assert {"water", "lighting", "distortion", "landuse"} <= ids and "poles" not in ids     # lamps and poles are one use case


def test_quiet_city_raises_nothing_for_new_use_cases(platform):
    platform.crew.run_cycle()
    cats = {d["attrs"]["Category"] for d in platform.store.all(S.DETECTIONS) if d["attrs"]["Source"] != "Historical (seeded)" and d["attrs"]["Source"] != "Historical"}
    assert not cats & {"distortion", "land_use"}
    assert not any("POLE:" in d["attrs"]["Evidence"] for d in platform.store.all(S.DETECTIONS))      # healthy poles raise nothing


def test_pole_decay_is_one_streetlight_use_case_and_goes_through_approval(platform):
    platform.crew.run_cycle()
    res = platform.crew.inject("pole_decay")
    inc = [i for i in _incidents(platform, res, "lighting") if "Pole" in platform.store.get(S.INCIDENTS, i)["attrs"]["Incident_Type"]]
    assert len(inc) == 1                                               # five poles, one cluster incident, same category as lamps
    rec = platform.store.get(S.INCIDENTS, inc[0])["attrs"]
    assert rec["Incident_Type"] == "Streetlight Pole Inspection" and rec["Assigned_Team"] == "Electrical Maintenance" and rec["Category"] == "lighting"
    assert not any(d["attrs"]["Category"] == "pole_health" for d in platform.store.all(S.DETECTIONS))
    assert any(a["Incident_ID"] == inc[0] for a in platform.approvals.pending())     # nothing dispatched without a person
    wo = platform.approvals.pending()
    assert "tilt" in next(a for a in wo if a["Incident_ID"] == inc[0])["Payload"].lower()      # pole-specific instructions


def test_pole_finding_is_added_to_the_lamp_detection_not_duplicated(platform):
    platform.crew.run_cycle()
    platform.crew.inject("pole_decay")
    per_asset: dict = {}
    for d in platform.store.all(S.DETECTIONS):
        if d["attrs"]["Category"] == "lighting":
            per_asset.setdefault(d["attrs"]["Related_Asset_ID"], []).append(d)
    assert all(len(v) == 1 for v in per_asset.values())              # one detection per streetlight, lamp and pole evidence together
    assert any("POLE:" in v[0]["attrs"]["Evidence"] for v in per_asset.values())


def test_distortion_event_flags_buildings_and_the_decoy_is_rejected_in_the_field(platform):
    platform.crew.run_cycle()
    res = platform.crew.inject("distortion_event")
    inc = _incidents(platform, res, "distortion")
    assert len(inc) == 4
    dets = [d for d in platform.store.all(S.DETECTIONS) if d["attrs"]["Category"] == "distortion" and d["attrs"]["Source"].startswith("Imagery")]
    assert all(d["attrs"]["Distortion_Score"] >= 0.45 for d in dets)
    assert "SIMULATED" in dets[0]["attrs"]["Evidence"]


def test_landuse_violation_follows_the_zoning_rules(platform):
    platform.crew.run_cycle()
    res = platform.crew.inject("landuse_violation")
    inc = _incidents(platform, res, "land_use")
    assert inc
    dets = [d for d in platform.store.all(S.DETECTIONS) if d["attrs"]["Category"] == "land_use" and d["attrs"]["Source"].startswith("Imagery")]
    assert dets and all(d["attrs"]["Land_Use_Category"] for d in dets)
    assert all("NOT permitted" in d["attrs"]["Evidence"] for d in dets)
    again = platform.crew.run_cycle()
    assert not [i for i in again["new_incidents"] if platform.store.get(S.INCIDENTS, i)["attrs"]["Category"] == "land_use"]   # idempotent


def test_chat_understands_the_new_use_cases(agent, platform):
    platform.crew.run_cycle()
    platform.crew.inject("pole_decay")
    r = agent.chat("t", "check the poles on King Fahd Road")
    assert r["trace"][0]["tool"] == "monitor_poles" and "predicted" in r["reply"].lower()
    r = agent.chat("t", "any land use violations in King Salman Park?")
    assert r["trace"][0]["tool"] == "analyze_land_use"
    r = agent.chat("t", "visual distortion in Al Malaz")
    assert r["trace"][0]["tool"] == "detect_visual_distortion"


def test_citizen_reports_are_disabled_by_default(platform_default):
    p = platform_default
    assert p.store.count(S.CITIZEN) == 0
    assert "citizen" not in {f["id"] for f in p.crew.feed_status()}
    res = p.crew.inject("olaya_leak")                                   # a leak no longer drags correlated resident reports with it
    assert p.store.count(S.CITIZEN) == 0 and res["scan"]["new_incidents"]
    for name in ("citizen_surge", "citizen_random"):
        try:
            p.crew.inject(name)
            raise AssertionError("citizen event should be refused")
        except ValueError as exc:
            assert "disabled" in str(exc)
    assert not any(n["Kind"] == "corroboration" for n in p.crew.notifications(limit=200))
    p.feeds.tick()
    assert p.store.count(S.CITIZEN) == 0


def test_streetlight_pole_event_moves_lamps_and_poles_together(platform):
    platform.crew.run_cycle()
    res = platform.crew.inject("streetlight_pole")
    assert res["scenario"] == "streetlight_pole" and res["lamps_updated"] > 0 and res["assets"]
    assert res["scan"]["new_incidents"]
    assert all(platform.store.get(S.INCIDENTS, i)["attrs"]["Category"] == "lighting" for i in res["scan"]["new_incidents"] if platform.store.get(S.INCIDENTS, i)["attrs"]["Area_Name"] == res["area"])
    assert any("POLE:" in d["attrs"]["Evidence"] for d in platform.store.all(S.DETECTIONS) if d["attrs"]["Category"] == "lighting")   # pole evidence rides on the streetlight detections
