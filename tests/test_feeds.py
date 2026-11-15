"""Operational data feeds (citizen reports) and how the crew uses them."""
from backend.gis import schema as S


def test_feeds_are_seeded_and_quiet(platform):
    assert platform.store.count(S.CITIZEN) >= 10
    first = platform.crew.run_cycle()
    assert not any(n["Kind"] in ("corroboration",) for n in platform.crew.notifications(limit=200))   # routine noise raises nothing
    assert not any(d["attrs"]["Source"].startswith("Citizen") for d in platform.store.all(S.DETECTIONS))
    assert first["steps"]


def test_citizen_surge_is_found_without_any_sensor(platform):
    platform.crew.run_cycle()
    res = platform.crew.inject("citizen_surge")
    inc = res["scan"]["new_incidents"]
    assert len(inc) == 1
    dets = [d for d in platform.store.all(S.DETECTIONS) if d["attrs"]["Source"].startswith("Citizen")]
    assert len(dets) == 1 and dets[0]["attrs"]["Pipeline_ID"] == ""                   # no sensor, no pipe: only residents
    n = next(n for n in platform.crew.notifications() if n["Incident_ID"] == inc[0])
    assert n["Agent"] == "reem" and "citizen reports clustered" in n["Trail"][0]["did"]
    assert len(platform.store.query(S.CITIZEN, Linked_Incident=inc[0])) == 5
    again = platform.crew.run_cycle()
    assert again["new_incidents"] == []                                               # idempotent: the same reports never open a second incident


def test_reports_back_up_a_sensor_leak(platform):
    platform.crew.run_cycle()
    res = platform.crew.inject("olaya_leak")
    iid = next(i for i in res["scan"]["new_incidents"] if platform.store.get(S.INCIDENTS, i)["attrs"]["Category"] == "water")
    trail = next(n for n in platform.crew.notifications() if n["Incident_ID"] == iid)["Trail"]
    assert any("citizen report" in t["did"] and t["agent"] == "reem" for t in trail)
    assert not any(d["attrs"]["Source"].startswith("Citizen") for d in platform.store.all(S.DETECTIONS))   # the leak is not double-counted


def test_simulated_visit_confirms_a_real_citizen_report(platform):
    platform.crew.inject("citizen_surge")
    for _ in range(4):
        for a in platform.approvals.pending():
            platform.approvals.approve(a["Approval_ID"])
        platform.crew.run_cycle(simulate_field=True)
    assert any(n["Kind"] == "verified" and n["Title"].startswith("Fault confirmed") for n in platform.crew.notifications(limit=200))
