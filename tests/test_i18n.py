"""English / Arabic: backend sentence translation, the ?lang=ar API switch, Field Maps task text, Arabic verdict words and the front-end dictionary."""
import re
from pathlib import Path

from fastapi.testclient import TestClient

from backend.agent.agent import GeoAIAgent
from backend.api.app import create_app
from backend.services import i18n, tasks

ROOT = Path(__file__).resolve().parent.parent
ARABIC = re.compile(r"[؀-ۿ]")


def client(platform):
    return TestClient(create_app(platform, GeoAIAgent(platform)))


def test_pick_normalises_language():
    assert i18n.pick("ar") == "ar" and i18n.pick("AR-SA") == "ar" and i18n.pick("en-US") == "en"
    assert i18n.pick(None) == "en" and i18n.pick("fr") == "en"


def test_sentences_names_and_numbers():
    ar = i18n.to_ar("Dispatch Nawaf Al-Harbi to INC-0042")
    assert "INC-0042" in ar and "نواف الحربي" in ar and "Dispatch" not in ar
    ar = i18n.to_ar("Create P1 work order for INC-0042 (Water Leak (Suspected), Olaya)")
    assert "P1" in ar and "العليا" in ar and "Create" not in ar
    ar = i18n.to_ar("SUSPECTED leak (not confirmed). Pressure on SNS-0012 fell 31.5% vs the same hours yesterday (412.0->283.0 kPa, z=4.2); flow changed +18.5%.")
    assert "SNS-0012" in ar and "31.5" in ar and "+18.5" in ar and "SUSPECTED" not in ar
    assert i18n.to_ar("Something nobody translated") == "Something nobody translated"      # unknown text is left alone, never broken


def test_severity_words_are_not_translated_inside_sentences():
    assert i18n.to_ar("High") == "High"                       # stored values are translated by the page, which compares them in English
    assert "تكليف" in i18n.to_ar("Dispatch Sarah to INC-1")


def test_localize_only_touches_text_fields():
    row = {"Severity": "Critical", "Status": "Open", "Title": "Executive brief", "Name": "Sarah", "Incident_ID": "INC-0001", "Trail": [{"agent": "sarah", "did": "Detected: Water Leak (Suspected) in KAFD"}]}
    out = i18n.localize(row, "ar")
    assert out["Severity"] == "Critical" and out["Status"] == "Open" and out["Incident_ID"] == "INC-0001"      # codes and ids never change
    assert ARABIC.search(out["Title"]) and out["Name"] == "سارة" and out["Trail"][0]["agent"] == "sarah" and ARABIC.search(out["Trail"][0]["did"])
    assert i18n.localize(row, "en") is row


def test_api_returns_arabic_only_when_asked(platform):
    c = client(platform)
    c.post("/api/nccc/events/olaya_leak")
    en = c.get("/api/nccc/state").json()
    ar = c.get("/api/nccc/state?lang=ar").json()
    assert en["notifications"] and not any(ARABIC.search(n["Title"]) for n in en["notifications"])
    assert all(ARABIC.search(n["Title"]) for n in ar["notifications"])
    assert [n["Notif_ID"] for n in en["notifications"]] == [n["Notif_ID"] for n in ar["notifications"]]
    assert [n["Severity"] for n in en["notifications"]] == [n["Severity"] for n in ar["notifications"]]          # logic fields are unchanged
    assert ar["crew"]["agents"][0]["name"] == "فيصل" and en["crew"]["agents"][0]["name"] == "Faisal"
    assert c.get("/api/nccc/state", headers={"X-Lang": "ar"}).json()["crew"]["agents"][0]["name"] == "فيصل"
    pend = [n["approval"] for n in ar["notifications"] if n["approval"] and n["approval"]["status"] == "Proposed"]
    assert pend and all(ARABIC.search(a["summary"]) for a in pend)


def test_every_scenario_alert_translates(platform):
    c = client(platform)
    for ev in ("olaya_leak", "streetlight_pole", "distortion_event", "landuse_violation"):
        c.post(f"/api/nccc/events/{ev}")
    for n in c.get("/api/nccc/state?lang=ar").json()["notifications"]:
        assert not re.search(r"[A-Za-z]{4,} [A-Za-z]{4,} [A-Za-z]{4,}", re.sub(r"\([^)]*\)|INC-\d+|[A-Z]{2,}-[\w-]+", "", n["Title"])), n["Title"]   # no long untranslated English titles


def test_field_maps_task_text_language(platform):
    wo = {"Work_Order_ID": "WO-1", "Task_Type": "Inspect & Verify", "Incident_ID": "INC-1", "Area_Name": "Olaya", "Instructions": "Inspect the location and confirm or reject the AI finding."}
    try:
        tasks.LANG = "en"
        assert "YOUR TASK" in tasks.description(wo) and not ARABIC.search(tasks.description(wo))
        tasks.LANG = "ar"
        ar = tasks.description(wo, "SUSPECTED leak (not confirmed).")
        assert "مهمتك" in ar and "YOUR TASK" not in ar and "WO-1" in ar and "العليا" in ar
        tasks.LANG = "both"
        both = tasks.description(wo)
        assert "مهمتك" in both and "YOUR TASK" in both and both.index("مهمتك") < both.index("YOUR TASK")
    finally:
        tasks.LANG = "en"


def test_arabic_verdict_words():
    assert i18n.verdict_from_note("تم التأكيد: شقوق في الجدار الشمالي") == "Confirmed"
    assert i18n.verdict_from_note("لم يتم العثور على شيء") == "Rejected"
    assert i18n.verdict_from_note("أحتاج إلى معاينة أخرى") == "Needs Further Inspection"
    assert i18n.verdict_from_note("تم الإصلاح") == "Repaired" and i18n.verdict_from_note("تصعيد: خطر") == "Escalate"
    assert i18n.verdict_from_note("hello") is None and i18n.verdict_from_note("") is None


def test_field_lang_setting():
    assert i18n.field_lang("AR") == "ar" and i18n.field_lang("both") == "both" and i18n.field_lang("xx") == "en" and i18n.field_lang(None) == "en"


# ---------------------------------------------------------------- the front end
def _dictionary():
    js = (ROOT / "frontend" / "i18n.js").read_text(encoding="utf-8")
    body = js[js.index("const AR = {"):js.index("};", js.index("const AR = {"))]
    return set(re.findall(r'^\s*"((?:[^"\\]|\\.)+)":\s*"', body, re.M)) | set(re.findall(r',\s*"((?:[^"\\]|\\.)+)":\s*"', body))


def test_pages_load_the_language_files():
    for page in ("home.html", "index.html", "strategic_dashboard.html", "field.html"):
        html = (ROOT / "frontend" / page).read_text(encoding="utf-8")
        assert "i18n.js" in html and "rtl.css" in html, page
        assert html.index("i18n.js") < (html.index("js.arcgis.com/4.30/\"") if "js.arcgis.com/4.30/\"" in html else 10 ** 9), page      # before the map SDK


def test_every_translated_call_has_an_arabic_entry():
    have = _dictionary()
    assert len(have) > 250
    missing = []
    for f in ("nccc.js", "strategic_dashboard.js", "field.html"):
        src = (ROOT / "frontend" / f).read_text(encoding="utf-8")
        for m in re.finditer(r'\bT\(\s*"((?:[^"\\]|\\.)*)"', src):
            key = m.group(1).replace('\\"', '"')
            if key not in have:
                missing.append((f, key))
        for m in re.finditer(r'\bT\(\s*`([^`$]*)`', src):
            if m.group(1) not in have:
                missing.append((f, m.group(1)))
    assert not missing, missing[:10]


# ---------------------------------------------------------------- the offline planner in Arabic
QUESTIONS = ["اكشف التسرّبات المحتملة في العليا", "كم حادثة مفتوحة وأين؟", "أي الحوادث تتطلب تدخلًا فوريًا؟", "اعرض الموجز التنفيذي", "تحقق من أعمدة الإنارة",
             "اكشف التشوه البصري في الملز", "ما مخالفات استخدام الأراضي في الحي الدبلوماسي؟", "قارن الصور في العليا", "ماذا يبلغ السكان؟", "اعرض الحوادث المفتوحة",
             "اعرض الموافقات المعلّقة", "قيّم أداء النموذج", "تنبأ بأعطال الإنارة في كافد"]
ENGLISH_MARKERS = ("I evaluated", "I scored", "I compared", "_Next:_", "Nothing has been created", "Top of", "Open incidents", "Executive overview", "I checked")


def _arabic_agent(platform):
    from backend.agent.ar import augment  # noqa: F401  (imported to make sure the module loads)
    c = client(platform)
    for ev in ("olaya_leak", "streetlight_pole", "distortion_event", "landuse_violation"):
        c.post(f"/api/nccc/events/{ev}")
    return c


def test_arabic_questions_get_arabic_answers(platform):
    c = _arabic_agent(platform)
    for q in QUESTIONS:
        r = c.post("/api/nccc/ask", json={"message": q, "session_id": "ar"}).json()
        assert ARABIC.search(r["reply"]), (q, r["reply"][:120])
        assert not any(m in r["reply"] for m in ENGLISH_MARKERS), (q, r["reply"][:200])
        assert "I'm the GeoAI" not in r["reply"] and "المساعد" not in r["reply"][:3], q


def test_arabic_intents_match_the_english_ones(platform):
    from backend.agent import ar
    pairs = {"كم حادثة مفتوحة؟": "how many", "أنشئ أمر عمل": "work order", "كلّف محققًا": "assign", "أغلق الحادثة": "close", "السياق المكاني حول العليا": "olaya"}
    for q, kw in pairs.items():
        assert kw in ar.augment(q).lower(), (q, kw)
    assert ar.augment("hello") == "hello"


def test_arabic_suggestions_round_trip(platform):
    c = _arabic_agent(platform)
    r = c.post("/api/nccc/ask?lang=ar", json={"message": "اعرض الموجز التنفيذي", "session_id": "s"}).json()
    assert r["suggestions"] and all(ARABIC.search(s) for s in r["suggestions"])
    for sug in r["suggestions"]:
        reply = c.post("/api/nccc/ask?lang=ar", json={"message": sug, "session_id": "s"}).json()["reply"]
        assert ARABIC.search(reply) and "جرّب أحد الاقتراحات" not in reply, (sug, reply[:150])


def test_arabic_approval_by_chat(platform):
    c = _arabic_agent(platform)
    pend = c.get("/api/approvals?pending=true").json()
    assert pend
    r = c.post("/api/nccc/ask", json={"message": "موافقة " + pend[0]["Approval_ID"], "session_id": "ap"}).json()
    assert "نُفِّذ" in r["reply"] and pend[0]["Approval_ID"] in r["reply"]
    r = c.post("/api/nccc/ask", json={"message": "رفض", "session_id": "ap"}).json()
    assert "رفض" in r["reply"] or "لا يوجد" in r["reply"]


def test_english_chat_is_unchanged(platform):
    c = _arabic_agent(platform)
    r = c.post("/api/nccc/ask", json={"message": "How many incidents are open, and where?", "session_id": "en"}).json()
    assert not ARABIC.search(r["reply"]) and "open" in r["reply"].lower()


def test_notes_and_caveats_translate(platform):
    c = client(platform)
    c.post("/api/nccc/events/landuse_violation")
    rows = c.get("/api/layers/Riyadh_Change_Detection?lang=ar").json()["features"]
    notes = [f["properties"]["Notes"] for f in rows if f["properties"].get("Notes")]
    assert notes and all(ARABIC.search(n) and "SIMULATED" not in n and "Index-differencing" not in n for n in notes), notes[:1]
    assert "SIMULATED" in c.get("/api/layers/Riyadh_Change_Detection").json()["features"][0]["properties"]["Notes"]        # English is untouched
    for t in ("SIMULATED pole telemetry. Detections are PREDICTIONS for field inspection, not confirmed failures.", "Citizen reports are a SIMULATED feed in this demo."):
        assert ARABIC.search(i18n.to_ar(t)) and "SIMULATED" not in i18n.to_ar(t)


def test_simulated_crew_sentences_translate():
    assert "عامل محاكى" in i18n.to_ar("[SIMULATED WORKER] Fault repaired and tested; area made safe.") and "SIMULATED" not in i18n.to_ar("[SIMULATED WORKER] Fault repaired and tested; area made safe.")
    ar = i18n.to_ar("Illegal Graffiti confirmed from street level: unlicensed drawings or writing on walls. Photographed and noted for the notice to the owner.")
    assert "الكتابات الجدارية العشوائية" in ar and "Photographed" not in ar
