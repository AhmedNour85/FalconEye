"""Plan 5, Task 4: mobility questions in "Ask the crew", English and Arabic. Each question runs one registry tool; the reply is written from the tool's numbers."""
import re

import pytest

from backend.agent import mobility_questions as MQ
from backend.gis import schema as S
from backend.mobility import traffic
from backend.services import i18n


@pytest.fixture()
def ready(platform):
    traffic.warm(wait=True)
    return platform


def ask(agent, text, sid="q"):
    return agent.chat(sid, text)


def digits(text: str) -> set:
    """Every number written in a reply, thousands separators removed."""
    return {n.replace(",", "") for n in re.findall(r"\d[\d,]*(?:\.\d+)?", text)}


def known_numbers(result, out=None):
    out = set() if out is None else out
    if isinstance(result, dict):
        for v in result.values():
            known_numbers(v, out)
    elif isinstance(result, list):
        for v in result:
            known_numbers(v, out)
    elif isinstance(result, (int, float)) and not isinstance(result, bool):
        for d in (0, 1, 2):
            out.add(MQ.fmt(result, d).replace(",", ""))
        out.add(MQ.fmt(100 * result).replace(",", ""))                   # a share shown as a percent
    elif isinstance(result, str):
        out.update(n.replace(",", "") for n in re.findall(r"\d[\d,]*(?:\.\d+)?", result))
    return out


def only_modelled_numbers(reply, result):
    """Every number in the reply is in the tool result (or is a time, a count in a list, or the 15-minute target)."""
    allowed = known_numbers(result) | {"15", "1", "2", "3", "4", "5"}
    stray = {n for n in digits(reply) if n not in allowed and not re.fullmatch(r"\d{4}|\d{1,2}", n)}
    assert not stray, f"numbers in the reply that the tool did not return: {stray}"


# ---------------------------------------------------------------------------------------------- parsing (no simulation)
def test_a_closure_question_names_the_road_and_the_window(ready):
    q = MQ.parse("What happens if King Fahd Road is closed tomorrow from 8 to 4?")
    assert q["intent"] == "closure_impact" and q["args"]["corridor"] == "King Fahd Road"
    assert q["args"]["start_time"].endswith("T08:00") and q["args"]["end_time"].endswith("T16:00")
    assert q["args"]["start_time"][:10] == q["args"]["end_time"][:10]


def test_lanes_and_best_response_are_read(ready):
    q = MQ.parse("What is the best response if Olaya Street loses 2 lanes tomorrow?")
    assert q["intent"] == "best_response" and q["args"]["corridor"] == "Olaya Street" and q["args"]["lanes_closed"] == 2


def test_event_attendance_formats(ready):
    for text, n in (("40,000", 40000), ("40k", 40000), ("40 thousand", 40000), ("٤٠٬٠٠٠", 40000)):
        q = MQ.parse(f"What will an event at KAFD with {text} people do to traffic?")
        assert q and q["intent"] == "event_impact" and q["args"]["place"] == "KAFD" and q["args"]["attendance"] == n, text


def test_a_question_that_is_not_about_mobility_is_left_alone(ready):
    assert MQ.parse("Check the water network for potential leaks.") is None
    assert MQ.parse("How many incidents are open?") is None
    assert MQ.parse("") is None


# ---------------------------------------------------------------------------------------------- one test per intent, English then Arabic
def test_closure_question_english(ready, agent):
    r = ask(agent, "What happens if King Fahd Road is closed tomorrow from 8 to 4?")
    assert [t["tool"] for t in r["trace"]] == ["simulate_closure"] and r["trace"][0]["input"]["corridor"] == "King Fahd Road"
    res = agent.session("q").ctx.state.get("last_scenario")
    assert res and "Modelled" in r["reply"] and "King Fahd Road" in r["reply"] and not r["pending_approvals"]
    only_modelled_numbers(r["reply"], r["trace"][0]["result"])


def test_closure_question_arabic(ready, agent):
    road = i18n.to_ar("King Fahd Road")
    r = ask(agent, f"ماذا يحدث لو أُغلق {road} غدا من 8 إلى 4؟")
    assert [t["tool"] for t in r["trace"]] == ["simulate_closure"] and r["trace"][0]["input"]["corridor"] == "King Fahd Road"
    assert road in r["reply"] and "محسوبة" in r["reply"] and not re.search(r"[A-Za-z]{4,}", r["reply"].replace("Modelled", ""))
    only_modelled_numbers(r["reply"], r["trace"][0]["result"])


def test_best_response_english(ready, agent):
    r = ask(agent, "What is the best response if Olaya Street is closed tomorrow from 8 to 4?")
    assert r["trace"][0]["tool"] == "compare_closure_strategies"
    result = r["trace"][0]["result"]
    assert "Recommended response" in r["reply"] and "Modelled" in r["reply"] and "assumptions" in r["reply"]
    assert result["recommended"] and not r["pending_approvals"]


def test_event_question_english_and_arabic(ready, agent):
    r = ask(agent, "What will an event at KAFD with 40,000 people do to traffic?")
    assert r["trace"][0]["tool"] == "simulate_event" and r["trace"][0]["input"]["attendance"] == 40000
    assert "40,000" in r["reply"] and "Modelled" in r["reply"]
    only_modelled_numbers(r["reply"], r["trace"][0]["result"])
    place = i18n.to_ar("KAFD")
    r = ask(agent, f"ما أثر فعالية في {place} بحضور 40000 شخص على المرور؟", "q2")
    assert r["trace"][0]["tool"] == "simulate_event" and r["trace"][0]["input"]["place"] == "KAFD"
    assert "40,000" in r["reply"] and "محسوبة" in r["reply"]


def test_demand_growth_question_runs_the_demand_simulation(ready, agent):
    r = ask(agent, "What if demand grows 20% near KAFD?")
    assert r["trace"][0]["tool"] == "simulate_demand_growth" and r["trace"][0]["input"] == {"place": "KAFD", "growth_pct": 20.0}
    assert "20%" in r["reply"] and "Modelled" in r["reply"]
    only_modelled_numbers(r["reply"], r["trace"][0]["result"])
    row = ready.store.get(S.SCENARIOS, r["trace"][0]["result"]["scenario_id"])
    assert row["attrs"]["Scenario_Type"] == "demand" and row["attrs"]["Status"] == "Completed"


def test_hospital_access_question(ready, agent):
    r = ask(agent, "How long does it take to reach a hospital right now?")
    assert r["trace"][0]["tool"] == "hospital_access" and "Modelled" in r["reply"]
    only_modelled_numbers(r["reply"], r["trace"][0]["result"])
    r = ask(agent, "كم يستغرق الوصول إلى المستشفى؟", "q2")
    assert r["trace"][0]["tool"] == "hospital_access" and "محسوبة" in r["reply"]


def test_maintenance_priority_question(ready, agent):
    r = ask(agent, "Which roads need maintenance first?")
    assert r["trace"][0]["tool"] == "road_safety_context"
    rows = r["trace"][0]["result"]["maintenance_priority"]
    assert rows and rows[0]["segment_id"] in r["reply"] and "Synthetic" in r["reply"]
    r = ask(agent, "أي الطرق تحتاج صيانة أولا؟", "q2")
    assert r["trace"][0]["tool"] == "road_safety_context" and "اصطناعية" in r["reply"]


def test_traffic_now_question(ready, agent):
    r = ask(agent, "How is the traffic right now?")
    assert r["trace"][0]["tool"] == "traffic_state" and "Modelled" in r["reply"]
    only_modelled_numbers(r["reply"], r["trace"][0]["result"])
    r = ask(agent, "كيف حالة المرور الآن؟", "q2")
    assert r["trace"][0]["tool"] == "traffic_state" and "محسوبة" in r["reply"]


# ---------------------------------------------------------------------------------------------- safety
def test_an_unknown_road_is_reported_not_guessed(ready, agent):
    r = ask(agent, "What happens if Mars Boulevard is closed tomorrow from 8 to 4?")
    assert r["trace"] == [] and "could not find" in r["reply"] and "King Fahd Road" in r["reply"]
    assert not any(ch.isdigit() for ch in r["reply"].replace("King Fahd Road", ""))
    r = ask(agent, "ماذا يحدث لو أُغلق شارع المريخ غدا من 8 إلى 4؟", "q2")
    assert r["trace"] == [] and "لم أجد" in r["reply"]


def test_an_unknown_place_is_reported_not_guessed(ready, agent):
    r = ask(agent, "What will an event at Atlantis with 40,000 people do to traffic?")
    assert r["trace"] == [] and "could not find" in r["reply"]


def test_a_closure_question_creates_no_approval_and_no_record_to_act_on(ready, agent):
    n_ap, n_wo = len(ready.approvals.pending()), ready.store.count(S.WORK_ORDERS)
    ask(agent, "What happens if King Fahd Road is closed tomorrow from 8 to 4?")
    assert len(ready.approvals.pending()) == n_ap and ready.store.count(S.WORK_ORDERS) == n_wo


# ---------------- QA-05: the plan's stadium question, and lists a person can read ----------------
def test_the_plans_stadium_question_is_an_event_at_king_fahd_stadium():
    for q in ("What happens to traffic if 40,000 people attend an event at King Fahd Stadium?",
              "ماذا يحدث للمرور إذا حضر 40000 شخص مباراة في ملعب الملك فهد؟"):
        p = MQ.parse(q)
        assert p and p["intent"] == "event_impact", (q, p)
        assert p["args"]["place"] == "King Fahd International Stadium" and p["args"]["attendance"] == 40000


@pytest.fixture()
def stadium_on_this_network(monkeypatch):
    """The tests run on the 73-section skeleton, which does not reach east Riyadh: put the venue on one of its junctions.
    (On the full network the stadium resolves to a junction about 0.4 km away; checked by hand 2026-11-17.)"""
    from backend.mobility import network_model
    from backend.mobility import riyadh_network as RN
    m = network_model.get_model()
    lon, lat = m.node_ll(m.zones["Malaz"])
    full, _lon, _lat, other = RN.EVENT_VENUES["KingFahdStadium"]
    monkeypatch.setitem(RN.EVENT_VENUES, "KingFahdStadium", (full, lon + 0.001, lat, other))
    return m


def test_the_stadium_is_an_event_venue_only_and_does_not_change_the_model_zones(stadium_on_this_network):
    from backend.mobility import riyadh_network as RN
    m = stadium_on_this_network
    assert "King Fahd International Stadium" in {v[0] for v in RN.EVENT_VENUES.values()}
    assert set(m.zones) == set(RN.LOCATIONS)                              # demand zones and hospital-access districts are as before
    assert m.resolve_place("King Fahd International Stadium") in m.G
    assert m.resolve_place("King Fahd Stadium") in m.G


def test_a_venue_the_road_network_does_not_reach_is_not_resolved(monkeypatch):
    from backend.mobility import network_model
    from backend.mobility import riyadh_network as RN
    full, _lon, _lat, other = RN.EVENT_VENUES["KingFahdStadium"]
    monkeypatch.setitem(RN.EVENT_VENUES, "KingFahdStadium", (full, 47.5, 25.5, other))      # far outside Riyadh
    assert network_model.get_model().resolve_place(full) is None


def test_the_stadium_event_runs(ready, agent, stadium_on_this_network):
    r = ask(agent, "What happens to traffic if 40,000 people attend an event at King Fahd Stadium?")
    assert [t["tool"] for t in r["trace"]] == ["simulate_event"] and r["trace"][0]["ok"], r["reply"]
    assert "King Fahd International Stadium" in r["reply"]


def test_the_list_of_known_places_uses_full_names_not_codes():
    text = MQ.known_list("place", "en")
    assert "King Abdullah Financial District" in text and "King Fahd International Stadium" in text
    for code in ("KAHC", "KAPark", "RiyadhFront", "KKIA"):
        assert not re.search(rf"\b{code}\b", text), code


def test_the_list_of_known_roads_starts_with_main_named_roads(monkeypatch):
    full = ["40", "500", "509", "AL Hair", "Abdul Rahman Bin Owf St", "King Fahd Road", "Olaya Street", "unnamed primary", "Zahra Street"]   # as on the full network
    monkeypatch.setattr(MQ, "known_roads", lambda: full)
    text = MQ.known_list("road", "en")
    shown = text.split("include: ", 1)[1].rstrip(".").split(", ")
    assert not any(re.match(r"^\d", r) or r.lower().startswith("unnamed") for r in shown), shown
    assert "King Fahd Road" in shown[:6], shown
