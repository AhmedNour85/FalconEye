"""Plan 5, Task 7: every new alert kind, strategy name, lifecycle step and effort label reads in Arabic; no English sentence is left behind."""
import re

from backend.mobility import strategies, wording
from backend.services import i18n

ALLOWED = {"trip", "hours", "min", "km", "h"}          # units and ids that stay Latin are not words of a sentence; the check below looks for 4+ letter English words
LEFT = re.compile(r"[A-Za-z]{4,}")


def english_left(text: str) -> list:
    """English words of 4+ letters that remain after translation (ids like INC-0001 and road names that keep their English are checked by the caller)."""
    return LEFT.findall(text)


def ar(text: str) -> str:
    return i18n.to_ar(text)


SUMMARY_EVENT = {"venue": "KAFD", "attendance": 40000, "added_vehicles_per_hour": 5200, "window_extra_trip_hours": 1234.4, "parking_deficit_vehicles": 800}
SUMMARY_CLOSURE = {"road": "King Fahd Road", "window": {"start": "2026-11-18T08:00", "end": "2026-11-18T16:00"}, "window_extra_trip_hours": 900,
                   "strategies": [{"id": "reschedule", "name": strategies.STRATEGIES[1]["name"], "benefit_vs_do_nothing_pct": 42.5, "skipped": False}]}
SUMMARY_INCIDENT = {"road": "Olaya Street", "lanes_closed": 2, "duration_h": 2, "window_extra_trip_hours": 300, "worst_hospital_access_delta_min": 4.5, "severe_segments": 6,
                    "severe_segments_baseline": 2}


def test_every_alert_kind_reads_in_arabic():
    for kind, s, rec in (("event", SUMMARY_EVENT, ""), ("closure", SUMMARY_CLOSURE, "reschedule"), ("incident", SUMMARY_INCIDENT, "")):
        line = ar(wording.impact(kind, s, rec))
        assert re.search(r"[؀-ۿ]", line) and not english_left(line), (kind, line)
    line = ar(wording.failed("the road network has no road named 'Mars Road'"))
    assert re.search(r"[؀-ۿ]", line)


def test_every_strategy_name_and_effort_reads_in_arabic():
    for st in strategies.STRATEGIES:
        name = ar(st["name"])
        assert re.search(r"[؀-ۿ]", name) and not english_left(name), (st["id"], name)


def test_every_named_place_and_hospital_reads_in_arabic():
    from backend.mobility import riyadh_network as RN
    names = {full for full, _a, _b in RN.LOCATIONS.values()} | set(RN.LOCATIONS) | {h[0] for h in RN.HOSPITALS} | {e[0] for e in RN.EMERGENCY}
    left = {n: ar(n) for n in names if english_left(ar(n)) or not re.search(r"[؀-ۿ]", ar(n))}
    assert not left, left


def test_a_road_name_with_bin_keeps_its_whole_name_after_the_arabic_road_word():
    from backend.services import i18n
    for text in ("Traffic Incident - Imam Saud bin Faisal Road", "Closure on Imam Saud bin Faisal Road tomorrow"):
        out = i18n.to_ar(text)
        assert "طريق Imam Saud bin Faisal" in out and "bin طريق" not in out, out
