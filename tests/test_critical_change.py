"""Large new construction on top of a critical facility is a Critical urban-change event."""
from backend.gis import schema as S


def test_construction_near_critical_facilities_is_critical(platform):
    platform.crew.run_cycle()
    res = platform.crew.inject("imagery_critical")
    new = [platform.store.get(S.INCIDENTS, i)["attrs"] for i in res["scan"]["new_incidents"]]
    crit = [a for a in new if a["Category"] == "change" and a["Severity"] == "Critical"]
    assert len(crit) >= 2 and {a["Area_Name"] for a in crit} == {"Diplomatic Quarter", "Diriyah"}
    assert all(a["Priority"] == "P1" for a in crit)
    dets = [d["attrs"] for d in platform.store.all(S.DETECTIONS) if d["attrs"]["Category"] == "change" and d["attrs"]["Severity"] == "Critical"]
    assert all("CRITICAL because possible construction" in d["Evidence"] for d in dets)
    alerts = [n for n in platform.crew.notifications(limit=200) if n["Kind"] == "change" and n["Severity"] == "Critical"]
    assert len(alerts) >= 2 and all(any(t["agent"] == "faisal" for t in n["Trail"]) for n in alerts)      # escalated to the executive agent
    assert any(p["Priority"] == "P1" for p in platform.approvals.pending())                                  # and a work order is waiting for approval


def test_ordinary_construction_stays_below_critical(platform):
    platform.crew.run_cycle(deep="Olaya")
    sev = [i["attrs"]["Severity"] for i in platform.store.all(S.INCIDENTS) if i["attrs"]["Category"] == "change" and i["attrs"]["Area_Name"] == "Olaya" and i["id"] >= "INC-0023"]
    assert sev and "Critical" not in sev
