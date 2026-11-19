"""Mobility questions for "Ask the crew", English and Arabic. `parse` turns a question into one registry tool call; `answer` writes the reply
from the tool's own numbers. Nothing here calculates a traffic figure, and no question creates an approval: the answers are information."""
from __future__ import annotations

import datetime as dt
import re

from backend.services import i18n

INTENTS = ("closure_impact", "best_response", "event_impact", "demand_growth", "hospital_access", "maintenance_priority", "traffic_now")
TOOL = {"closure_impact": "simulate_closure", "best_response": "compare_closure_strategies", "event_impact": "simulate_event", "demand_growth": "simulate_demand_growth",
        "hospital_access": "hospital_access", "maintenance_priority": "road_safety_context", "traffic_now": "traffic_state"}
DEFAULT_ATTENDANCE = 30000
DEFAULT_GROWTH = 20.0

_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩٬٫", "0123456789,.")


def fmt(x, digits: int = 1) -> str:
    """One number the way the answers print it: thousands separated, at most one decimal, no trailing .0."""
    if x is None:
        return "-"
    f = round(float(x), digits)
    return f"{f:,.0f}" if f == int(f) else f"{f:,.{digits}f}"


def _norm(text: str) -> str:
    return re.sub("[ً-ْـ]", "", (text or "").translate(_AR_DIGITS)).lower().replace("أ", "ا").replace("إ", "ا").replace("آ", "ا").replace("ة", "ه").replace("ى", "ي")


def _has(t: str, *words: str) -> bool:
    return any(_norm(w) in t for w in words)


# ---------------------------------------------------------------------------------------------- what the crew knows by name
def known_roads() -> list[str]:
    from backend.mobility import network_model

    return sorted({s["corridor"] for s in network_model.get_model().segments.values() if s.get("corridor")})


def known_places() -> dict:
    """needle (lower-case, English or Arabic) -> the place name the traffic model resolves."""
    from backend.mobility import riyadh_network as RN

    out = {}
    for key, (full, _lon, _lat) in RN.LOCATIONS.items():
        for needle in {key, full, i18n.to_ar(key), i18n.to_ar(full), full.split("(")[0].strip(), full.replace("Al ", "").strip()}:
            if needle and len(needle) > 2:
                out[_norm(needle)] = key
        for inner in re.findall(r"\(([^()]+)\)", i18n.to_ar(key)):
            out[_norm(inner)] = key
    for _key, (full, _lon, _lat, other) in RN.EVENT_VENUES.items():      # event venues are asked for by their full name
        for needle in {full, i18n.to_ar(full), *other}:
            out[_norm(needle)] = full
    return out


def place_names() -> list[str]:
    """The places a person can ask about, by their full names (the model's short keys such as KAHC mean nothing to an operator)."""
    from backend.mobility import riyadh_network as RN

    return sorted({v[0] for v in RN.LOCATIONS.values()} | {v[0] for v in RN.EVENT_VENUES.values()})


def main_roads_first(roads: list[str]) -> list[str]:
    """Named roads only (no bare numbers, no 'unnamed …'); the main corridors that have an Arabic name first, then the rest A to Z."""
    named = [r for r in roads if r and not re.match(r"^\d", r) and not r.lower().startswith("unnamed") and "synthetic" not in r.lower()]
    return sorted(named, key=lambda r: (r not in i18n.TERMS, r.lower()))


def _find_road(t: str) -> str | None:
    best = None
    for road in known_roads():
        for needle in (road, i18n.to_ar(road)):
            n = _norm(needle).strip()
            if n and n in t and (best is None or len(n) > best[0]):
                best = (len(n), road)
    return best[1] if best else None


def _find_place(t: str) -> str | None:
    best = None
    for needle, key in known_places().items():
        if needle in t and (best is None or len(needle) > best[0]):
            best = (len(needle), key)
    return best[1] if best else None


# ---------------------------------------------------------------------------------------------- time and numbers
def riyadh_now() -> dt.datetime:
    return dt.datetime.utcnow() + dt.timedelta(hours=3)


def _clock(h: int, ampm: str | None, other_ampm: str | None = None) -> int:
    ap = ampm or other_ampm
    if ap in ("pm", "م") and h < 12:
        return h + 12
    if ap in ("am", "ص") and h == 12:
        return 0
    return h


def parse_window(text: str, now: dt.datetime | None = None) -> dict:
    """"tomorrow from 8 to 4" -> {"start_time": "<tomorrow>T08:00", "end_time": "<tomorrow>T16:00"}. No times: {} (the tools use their own default window)."""
    t = _norm(text)
    m = re.search(r"(?:from|between|من)?\s*\b(\d{1,2})(?::(\d{2}))?\s*(am|pm|ص|م)?\s*(?:to|until|till|and|-|الي|حتي)\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm|ص|م)?\b", t)
    if not m:
        return {}
    h1, m1, a1, h2, m2, a2 = int(m.group(1)), int(m.group(2) or 0), m.group(3), int(m.group(4)), int(m.group(5) or 0), m.group(6)
    if h1 > 24 or h2 > 24:
        return {}
    s, e = _clock(h1, a1, a2), _clock(h2, a2, a1)
    if not a1 and not a2 and e <= s and e < 12 and s < 12:
        e += 12                                                     # "8 to 4" means 08:00 to 16:00
    day = (now or riyadh_now()).replace(hour=0, minute=0, second=0, microsecond=0)
    if not _has(t, "today", "tonight", "اليوم", "الليله"):
        day += dt.timedelta(days=1)                                 # a window with no day is tomorrow, as the crew's own closure requests
    start = day.replace(hour=s % 24, minute=m1)
    end = day.replace(hour=e % 24, minute=m2) + dt.timedelta(days=1 if e % 24 <= s % 24 and (e, m2) <= (s, m1) else 0)
    return {"start_time": start.strftime("%Y-%m-%dT%H:%M"), "end_time": end.strftime("%Y-%m-%dT%H:%M")}


def parse_attendance(text: str) -> int | None:
    t = _norm(text)
    m = re.search(r"(\d[\d,]*(?:\.\d+)?)\s*(k|الف|thousand)?\b", re.sub(r"(?<=\d),(?=\d{3}\b)", ",", t))
    for m in re.finditer(r"(\d[\d,]*(?:\.\d+)?)\s*(k\b|الف|thousand)?", t):
        raw = float(m.group(1).replace(",", ""))
        n = raw * 1000 if m.group(2) else raw
        if n >= 100 and not re.match(r"\s*(?:%|percent|بالمئه|٪)", t[m.end():]):
            return int(n)
    return None


def parse_percent(text: str) -> float | None:
    t = _norm(text)
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:%|percent|بالمئه|٪|في المئه)", t)
    return float(m.group(1)) if m else None


# ---------------------------------------------------------------------------------------------- parsing
_CLOSE = ("closed", "closure", "close ", "closing", "shut", "اغلاق", "اغلق", "يغلق", "تغلق", "مغلق", "سد ")
_BEST = ("best response", "best strategy", "best way to respond", "how should we respond", "how to respond", "response to", "افضل استجابه", "افضل استراتيجيه", "كيف نستجيب", "افضل رد", "افضل طريقه")
_EVENT = ("event", "match", "concert", "festival", "stadium", "attend", "فعاليه", "مباراه", "حفل", "مهرجان", "حضر", "يحضر", "ملعب")
_ROADWORD = ("road", "street", "avenue", "boulevard", "ring", "highway", "طريق", "شارع")


def parse(text: str) -> dict | None:
    """{"intent", "args"} for a mobility question, {"intent": "unknown_road"|"unknown_place", "args": {}} when it names something the model does not have, else None."""
    t = _norm(text)
    if not t.strip():
        return None
    road, place = _find_road(t), _find_place(t)
    if _has(t, "hospital", "مستشفى", "مستشفيات", "اسعاف") and _has(t, "reach", "access", "how long", "time", "minutes", "الوصول", "كم", "زمن", "وقت", "يستغرق", "تاخر"):
        return {"intent": "hospital_access", "args": {}}
    if _has(t, "maintenance", "صيانه") and _has(t, "road", "segment", "street", "طرق", "طريق", "مقاطع", "شوارع", "اولا", "first", "priority"):
        return {"intent": "maintenance_priority", "args": {"top_n": 5}}
    if _has(t, "demand", "growth", "grow", "grows", "increase in trips", "الطلب", "نمو", "زياده الطلب", "زاد") and (_has(t, "demand", "الطلب") or _has(t, "growth", "grow", "نمو")):
        pct = parse_percent(text) or DEFAULT_GROWTH
        if not place:
            return {"intent": "unknown_place", "args": {}}
        return {"intent": "demand_growth", "args": {"place": place, "growth_pct": pct}}
    event_like = _has(t, *_EVENT) and (parse_attendance(text) is not None or _has(t, "event", "فعاليه", "stadium", "ملعب", "مباراه", "حفل"))
    if event_like and not _has(t, *_CLOSE):
        if not place:
            return {"intent": "unknown_place", "args": {}}
        args = {"place": place, "attendance": parse_attendance(text) or DEFAULT_ATTENDANCE}
        args.update(_event_window(text))
        return {"intent": "event_impact", "args": args}
    if _has(t, *_CLOSE) or (_has(t, *_BEST) and _has(t, *_ROADWORD)):
        if not road:
            return {"intent": "unknown_road", "args": {}} if _has(t, *_ROADWORD) else None
        args = {"corridor": road, **parse_window(text)}
        lanes = re.search(r"(\d+)\s*(?:lanes?|مسار|مسارات|حارات|حارة)", t)
        if lanes:
            args["lanes_closed"] = int(lanes.group(1))
        return {"intent": "best_response" if _has(t, *_BEST) else "closure_impact", "args": args}
    if _has(t, "traffic", "congestion", "congested", "المرور", "الحركه", "الازدحام", "زحمه") and _has(t, "now", "current", "currently", "right now", "today", "how is", "how's", "الان", "حاليا", "اليوم", "حاله", "كيف") \
            or _norm(text).strip(" ?!.؟") in ("traffic", "traffic now", "المرور", "حاله المرور", "حاله المرور الان"):
        return {"intent": "traffic_now", "args": {"top_n": 3}}
    return None


def _event_window(text: str) -> dict:
    w = parse_window(text)
    if w and not _has(_norm(text), "tomorrow", "غدا", "بكره"):
        today = riyadh_now().strftime("%Y-%m-%d")
        w = {k: today + v[10:] if v.startswith((riyadh_now() + dt.timedelta(days=1)).strftime("%Y-%m-%d")) else v for k, v in w.items()}
    return w


# ---------------------------------------------------------------------------------------------- answers
def _ar(s: str) -> str:
    return i18n.to_ar(s)


def _window_text(w: dict | None, lang: str) -> str:
    if not w or not w.get("start") or not w.get("end"):
        return ""
    s, e = str(w["start"]).replace("T", " ")[:16], str(w["end"]).replace("T", " ")[:16]
    return f"من {s} إلى {e}" if lang == "ar" else f"from {s} to {e}"


def known_list(kind: str, lang: str) -> str:
    items = main_roads_first(known_roads()) if kind == "road" else place_names()
    shown = ", ".join(_ar(i) if lang == "ar" else i for i in items[:14])
    if lang == "ar":
        return f"لم أجد {'هذا الطريق' if kind == 'road' else 'هذا المكان'} في نموذج المرور. {'الطرق' if kind == 'road' else 'الأماكن'} التي أعرفها: {shown}."
    return f"I could not find that {kind} in the traffic model. The {'roads' if kind == 'road' else 'places'} I know include: {shown}."


def answer(intent: str, result: dict, lang: str = "en", args: dict | None = None) -> str:
    """The reply, built only from the tool's result. Every figure is printed with `fmt`; the label says the numbers are modelled."""
    ar = lang == "ar"
    label = "محسوبة من شبكة الطرق وطلب افتراضي، وليست قياسات فعلية." if ar else "Modelled: calculated from the road network and synthetic demand, not measured."
    if intent == "closure_impact":
        s = result["summary"]
        road = _ar(s["road"]) if ar else s["road"]
        lanes = ("إغلاق كامل" if ar else "a full closure") if s.get("full_closure") else (f"إغلاق {s.get('lanes_closed')} مسار" if ar else f"{s.get('lanes_closed')} lane(s) closed")
        win = _window_text(s.get("window"), lang)
        if ar:
            return (f"{road} ({lanes}) {win}: يضيف {fmt(s['window_extra_trip_hours'])} ساعة رحلة إضافية، ويزيد أسوأ زمن للوصول إلى مستشفى {fmt(s['worst_hospital_access_delta_min'])} دقيقة، "
                    f"وتصبح {fmt(s['severe_segments'])} مقاطع طرق شديدة الازدحام أو متوقفة (المتأثر {fmt(s['affected_segments'])}). {label} المحاكاة {result['scenario_id']}.")
        return (f"{road} ({lanes}) {win}: adds {fmt(s['window_extra_trip_hours'])} trip-hours, makes the worst hospital access {fmt(s['worst_hospital_access_delta_min'])} min longer, "
                f"and leaves {fmt(s['severe_segments'])} road sections heavy or stopped ({fmt(s['affected_segments'])} affected). {label} Simulation {result['scenario_id']}.")
    if intent == "best_response":
        rec = next((x for x in result["strategies"] if x["id"] == result["recommended"]), None)
        name = (_ar(rec["name"]) if ar else rec["name"]) if rec else result["recommended"]
        dn = result["do_nothing"]
        rows = [f"- {_ar(x['name']) if ar else x['name']}: " + (("غير منطبقة" if ar else "not applicable") if x.get("skipped") else
                f"{fmt(x['extra_trip_hours'])} {'ساعة رحلة إضافية' if ar else 'extra trip-hours'} ({fmt(x['benefit_vs_do_nothing_pct'])}% {'أقل تأخيرًا' if ar else 'less delay'})")
                for x in result["strategies"]]
        head = (f"الاستجابة الموصى بها: {name}. دون أي إجراء: {fmt(dn['window_extra_trip_hours'])} ساعة رحلة إضافية." if ar
                else f"Recommended response: {name}. Doing nothing costs {fmt(dn['window_extra_trip_hours'])} extra trip-hours.")
        verdict = _ar(result["verdict"]) if ar else result["verdict"]
        return head + "\n" + "\n".join(rows) + f"\n{verdict}\n" + (f"افتراضات الاستراتيجيات مذكورة مع النتيجة. {label} المحاكاة {result['scenario_id']}." if ar
                                                                  else f"Strategy effects are assumptions, listed with the result. {label} Simulation {result['scenario_id']}.")
    if intent == "event_impact":
        s = result["summary"]
        venue = _ar(s["venue"]) if ar else s["venue"]
        if ar:
            return (f"فعالية في {venue} بحضور {fmt(s['attendance'])} شخص: تضيف نحو {fmt(s['added_vehicles_per_hour'])} مركبة في الساعة، ونقص مواقف بنحو {fmt(s['parking_deficit_vehicles'])} مركبة، "
                    f"و{fmt(s['window_extra_trip_hours'])} ساعة رحلة إضافية، وتصبح {fmt(s['severe_segments'])} مقاطع طرق شديدة الازدحام. {label} المحاكاة {result['scenario_id']}.")
        return (f"An event at {venue} with {fmt(s['attendance'])} attendees: adds about {fmt(s['added_vehicles_per_hour'])} vehicles per hour, a parking gap of {fmt(s['parking_deficit_vehicles'])} vehicles, "
                f"{fmt(s['window_extra_trip_hours'])} extra trip-hours, and {fmt(s['severe_segments'])} road sections heavy or stopped. {label} Simulation {result['scenario_id']}.")
    if intent == "demand_growth":
        s = result["summary"]
        place = _ar(s["place"]) if ar else s["place"]
        if ar:
            return (f"نمو الطلب بنسبة {fmt(s['growth_pct'])}% قرب {place}: {fmt(s['window_extra_trip_hours'])} ساعة رحلة إضافية، وأسوأ زمن للوصول إلى مستشفى يزيد {fmt(s['worst_hospital_access_delta_min'])} دقيقة، "
                    f"وتصبح {fmt(s['severe_segments'])} مقاطع شديدة الازدحام. {label} المحاكاة {result['scenario_id']}.")
        return (f"Demand growing {fmt(s['growth_pct'])}% near {place}: {fmt(s['window_extra_trip_hours'])} extra trip-hours, the worst hospital access gets {fmt(s['worst_hospital_access_delta_min'])} min longer, "
                f"and {fmt(s['severe_segments'])} road sections become heavy or stopped. {label} Simulation {result['scenario_id']}.")
    if intent == "hospital_access":
        w = result.get("worst") or {}
        zone = _ar(w.get("zone", "")) if ar else w.get("zone", "")
        hosp = _ar(w.get("nearest_hospital") or "") if ar else (w.get("nearest_hospital") or "")
        if ar:
            return (f"عند الساعة {result['hour']}:00 أبعد حي هو {zone} ويستغرق {fmt(w.get('minutes'))} دقيقة للوصول إلى {hosp}. المتوسط {fmt(result['mean_min'])} دقيقة، "
                    f"و{fmt(100 * result['share_within_15_min'])}% من الأحياء ضمن 15 دقيقة. {label} مواقع المستشفيات تقريبية.")
        return (f"At {result['hour']}:00 the slowest district is {zone}: {fmt(w.get('minutes'))} min to {hosp}. The average is {fmt(result['mean_min'])} min and "
                f"{fmt(100 * result['share_within_15_min'])}% of districts are within 15 minutes. {label} Hospital positions are approximate.")
    if intent == "maintenance_priority":
        rows = result["maintenance_priority"]
        lines = [f"{i}. {(_ar(r['corridor'] or r['name']) if ar else (r['corridor'] or r['name']))} ({r['segment_id']}): {'الأولوية' if ar else 'priority'} {fmt(r['priority_score'])}, "
                 f"{'الحالة' if ar else 'condition'} {fmt(r['condition'])}/100" for i, r in enumerate(rows, 1)]
        head = "مقاطع الطرق الأولى بالصيانة:" if ar else "Road sections to maintain first:"
        return head + "\n" + "\n".join(lines) + "\n" + ("بيانات اصطناعية: " if ar else "Synthetic data: ") + str(result.get("label", ""))
    if intent == "traffic_now":
        c, tot = result["counts"], result["totals"]
        worst = ", ".join(f"{_ar(w['road']) if ar else w['road']} ({fmt(w['load'], 2)})" for w in result["worst"][:3])
        if ar:
            return (f"حركة المرور عند الساعة {result['hour']}:00: متوسط السرعة {fmt(tot['avg_speed_kph'])} كم/س، {fmt(c.get('heavy', 0))} مقاطع مزدحمة و{fmt(c.get('stopped', 0))} متوقفة. "
                    f"الأكثر تحميلًا: {worst}. {label}")
        return (f"Traffic at {result['hour']}:00: average speed {fmt(tot['avg_speed_kph'])} km/h, {fmt(c.get('heavy', 0))} road sections heavy and {fmt(c.get('stopped', 0))} stopped. "
                f"Most loaded: {worst}. {label}")
    raise ValueError(f"unknown mobility intent {intent!r}")
