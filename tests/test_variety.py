"""Events spread across the city, and the chat can count and locate incidents."""
from backend.gis import schema as S


def test_random_leaks_land_in_different_areas(platform):
    platform.crew.run_cycle()
    areas = []
    for _ in range(4):
        res = platform.crew.inject("leak_random")
        areas.append(res["area"])
    assert len(set(areas)) >= 3 and all(a != b for a, b in zip(areas, areas[1:]))      # new leaks go to the quietest areas, not one place


def test_random_lights_find_a_new_cluster_in_the_chosen_area(platform):
    platform.crew.run_cycle()
    res = platform.crew.inject("lights_random")
    area = res["area"]
    new = [platform.store.get(S.INCIDENTS, i)["attrs"] for i in res["scan"]["new_incidents"]]
    assert any(a["Category"] == "lighting" and a["Area_Name"] == area for a in new), (area, new)


def test_random_city_activity_spreads(platform):
    platform.crew.run_cycle()
    for _ in range(6):
        platform.crew.inject("random")
    open_areas = {f["attrs"]["Area_Name"] for f in platform.store.all(S.INCIDENTS) if f["attrs"]["Status"] not in ("Resolved", "Closed - False Positive")}
    assert len(open_areas) >= 5


def test_chat_counts_incidents_by_area(platform, agent):
    platform.crew.run_cycle()
    platform.crew.inject("leak_kafd")
    r = agent.chat("t", "how many incidents are open?")
    assert "open incidents" in r["reply"] and "By area" in r["reply"] and "KAFD" in r["reply"]
    assert [t["tool"] for t in r["trace"]] == ["count_incidents"]
    r2 = agent.chat("t", "how many critical water leaks are there in KAFD?")
    assert "KAFD" in r2["reply"]
    r3 = agent.chat("t", "what are residents reporting?")
    assert "citizen reports" in r3["reply"]
