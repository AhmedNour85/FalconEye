"""Arabic for the offline (rule-based) planner: it understands Arabic questions and answers in Arabic.

* `augment(text)` appends the English keywords that Arabic words stand for, so the planner's intent rules work unchanged on Arabic input.
* `COMPOSERS_AR` has an Arabic version of every reply in `compose.py` (same data, same names). Numbers, ids and tool results are never altered.
"""
from __future__ import annotations

import re

from backend.services import i18n

# ---------------------------------------------------------------------------------------------------- understanding Arabic
HINTS: list[tuple[str, str]] = [
    (r"تسر[بّ]|تسري[بّ]|تسرّب|تسريب|ضغط", "leak water pressure"), (r"مياه|ماء|مواسير|أنابيب|انابيب|المياه", "water pipe"),
    (r"إنارة|انارة|الإنارة|مصابيح|مصباح|أضواء", "streetlight lamp lighting"), (r"عمود|أعمدة|اعمدة|ميلان|تآكل", "pole tilt corrosion"),
    (r"تشو[هّ]|انتفاخ|الواجهة|واجهة|هبوط المبنى", "distortion facade"),
    (r"استخدام الأراضي|استخدام الاراضي|استخدام أراضي|التقسيم|تقسيم|مخالف|تعدي|تعدٍّ", "land use zoning violation"),
    (r"الصور|صور|الأقمار|الاقمار|تغي[رّ]|التغير|التغيّر|فترات", "imagery change"), (r"قارن|مقارنة", "compare"),
    (r"كم\b|عدد|كمية", "how many"), (r"أين|اين|وين", "where"), (r"حادثة|حوادث|الحوادث|الحادثة|حادث", "incident"),
    (r"مفتوح", "open"), (r"حرج|الحرجة|حرجة", "critical"), (r"عالي|عالية", "high"),
    (r"الأولوية|أولوية|الاولوية|الأهم|الاهم|عاجل|ترتيب|رتّب|رتب|أي حادثة|اي حادثة|أيها|اي واحدة|أي واحدة|التدخل الفوري|تدخل فوري|تدخلًا فوريًا|تدخلا فوريا|فوريًا|فوري|الحوادث الأهم|أي الحوادث|اي الحوادث", "priority urgent rank which incident"),
    (r"أمر عمل|أوامر عمل|أمر العمل|اوامر عمل", "work order"), (r"أنشئ|انشئ|إنشاء|انشاء|جهّز|جهز|أعدّ|اعد", "create prepare"),
    (r"محاكاة|حاكِ|محاكى|محاكي", "simulate"), (r"إصلاح|اصلاح|الإصلاح|تصليح|أصلح", "repair"),
    (r"كلّف|كلف|تكليف|عيّن|عين|أرسل|ارسل|مُحقق|محقق|فريق ميداني|عامل ميداني", "assign field worker dispatch"),
    (r"أغلق|اغلق|إغلاق|اغلاق", "close"), (r"تحقق|التحقق|الدليل الميداني|دليل ميداني|نتيجة الفحص|النتيجة", "verify verification outcome"),
    (r"تقييم|قيّم|أداء النموذج|اداء النموذج|إنذار كاذب|انذار كاذب|دقة|معايرة", "evaluate model performance false positive precision"),
    (r"المجاور|المحيط|حول|السياق|الأثر|المتأثر|القريب", "nearby around context impact"),
    (r"موجز|ملخص|نظرة عامة|المؤشرات|النقاط الساخنة|تنفيذي|لوحة", "executive summary overview hotspot"),
    (r"مواطن|المواطنين|سكان|السكان|بلاغ|بلاغات|شكاوى|شكوى", "citizen resident report"),
    (r"معلق|معلّق|بانتظار الموافقة|الموافقات", "pending approval"), (r"استخراج|استخرج", "extract"), (r"حس[اّ]س|حساسات|مستشعر", "sensor"),
    (r"اعرض|أظهر|اظهر|قائمة|عرض", "show list"), (r"تفاصيل|أخبرني|اخبرني|حالة", "detail tell me status"),
]
AREA_AR = {"Diplomatic Quarter": ("الحي الدبلوماسي", "دبلوماسي"), "King Salman Park": ("حديقة الملك سلمان",), "Al Malaz": ("الملز",), "Olaya": ("العليا",),
           "KAFD": ("كافد", "المركز المالي"), "Diriyah": ("الدرعية",)}
_AR_RE = re.compile(r"[؀-ۿ]")
APPROVE_AR = re.compile(r"^\s*(نعم[,،.!\s]*)?(من فضلك\s+)?(موافقة|وافق|أوافق|موافق|نفّذ|نفذ|تابع|استمر)(?P<rest>.*)$")
REJECT_AR = re.compile(r"^\s*(لا[,،.!\s]*)?(من فضلك\s+)?(رفض|ارفض|مرفوض|لا أوافق|ألغِ|الغ)(?P<rest>.*)$")
ALL_AR = re.compile(r"الكل|جميع")


def augment(text: str) -> str:
    """The message with English intent keywords appended for the Arabic words it contains (unchanged when it has no Arabic)."""
    if not _AR_RE.search(text):
        return text
    extra = [en for pat, en in HINTS if re.search(pat, text)]
    for en, names in AREA_AR.items():
        if any(n in text for n in names):
            extra.append(en)
    if "طريق الملك فهد" in text:
        extra.append("king fahd")
    if "شارع العليا" in text:
        extra.append("olaya street")
    return text + " " + " ".join(extra)


# ---------------------------------------------------------------------------------------------------- values
VALUES = {"Open": "مفتوحة", "Assigned": "مُكلَّفة", "In Progress": "قيد التنفيذ", "Resolved": "تم الحل", "Confirmed": "مؤكدة", "Rejected": "مرفوضة", "Escalated": "مصعَّدة",
          "Critical": "حرج", "High": "عالٍ", "Medium": "متوسط", "Low": "منخفض", "Info": "معلومة", "Suspected": "مشتبه به", "Predicted": "متوقع", "Candidate": "مرشّح",
          "Repaired": "تم الإصلاح", "Escalate": "تصعيد", "None": "لا شيء", "none": "لا شيء", "Moderate": "متوسط", "Severe": "شديد", "moderate": "متوسط", "severe": "شديد", "low": "خفيف",
          "water": "المياه", "lighting": "الإنارة", "change": "التغيّر العمراني", "distortion": "التشوّه البصري", "land_use": "استخدام الأراضي", "mobility": "المرور والتنقّل", "other": "أخرى",
          "New": "جديد", "Linked": "مرتبط", "pending": "قيد الانتظار"}
NAMES = {"water": "مياه", "lighting": "إنارة", "change": "تغيّر عمراني", "distortion": "تشوّه بصري", "land_use": "استخدام أراضٍ", "mobility": "مرور وتنقّل"}


def tv(v) -> str:
    """Arabic for a stored value (status, area, type ...). Numbers and unknown text are returned as they are."""
    s = str(v)
    return VALUES.get(s) or i18n.TERMS.get(s) or i18n.to_ar(s)


def _tx(s) -> str:                         # a sentence written by a tool
    return i18n.to_ar(str(s))


def _join(items) -> str:
    return "، ".join(str(i) for i in items)


def _fmt(v):
    return "غير متاح" if v is None else v


# ---------------------------------------------------------------------------------------------------- composers
def detect_water_leaks(r):
    if not r["suspected_leaks"]:
        lines = [f"قيّمتُ {r['sensors_evaluated']} حسّاس ضغط/تدفق ({tv(r['scope'])}) ولم أجد **أي تسرّب مشتبه به** حاليًا - لا شيء يستوفي القاعدة "
                 f"(انخفاض الضغط {r['rule']['min_pressure_drop_pct']:g}٪ على الأقل عن نفس الساعات أمس مع z لا يقل عن {r['rule']['min_z_score']})."]
        for c in r.get("closest_candidates", []):
            lines.append(f"- الأقرب: {c['sensor_id']} ({tv(c['area'])}، {c['pipeline_id']}): الضغط {c['pressure_drop_pct']:+}٪ مقارنة بالأمس، z={c['z_score']} - تذبذب طبيعي.")
        lines.append("\nلن يغيّر خفض عتبة الخطورة هذه النتيجة: فهو يخفي الرصودات فقط بعد انطباق القاعدة.")
        lines.append("_لرؤية رصد:_ شغّل سيناريو «تسرّب مياه» من قائمة «محاكاة حدث».")
        return "\n".join(lines)
    lines = [f"قيّمتُ {r['sensors_evaluated']} حسّاسًا ({tv(r['scope'])}) ووجدت **{r['suspected_leaks']} تسرّبًا مشتبهًا به** - مشتبه به وليس مؤكدًا:"]
    for d in r["detections"][:5]:
        loc = d["probable_location"]
        lines.append(f"- **{d['detection_id']}** {tv(d['area'])} / {d['pipeline_id']}: الخطورة **{d['risk_score']}** ({tv(d['severity'])})، الضغط -{d['pressure_drop_pct']}٪، التدفق {d['flow_change_pct']:+}٪ "
                     f"(الحسّاس {d['sensor_id']}، {len(d['corroborating_sensors'])} حسّاسات مؤيِّدة). الموقع المرجَّح {loc['lat']}, {loc['lon']} (±{loc['uncertainty_radius_m']} م).")
    lines.append(f"\n**لماذا هو مشبوه:** {_tx(r['detections'][0]['why_suspicious'])}")
    lines.append("\n_التالي:_ اسأل أيها الأكثر حرجًا، أو قل «أنشئ حوادث».")
    return "\n".join(lines)


def predict_streetlight_failures(r):
    if not r["predicted_failures"]:
        return f"قيّمتُ {r['lights_evaluated']} مصباح إنارة؛ لا يتجاوز أي منها عتبة احتمال العطل {r['threshold']:.2f}."
    lines = [f"قيّمتُ {r['lights_evaluated']} مصباح إنارة و**{r['predicted_failures']}** منها يتجاوز عتبة الاحتمال {r['threshold']:.2f}. هذه أعطال **متوقعة** وليست مؤكدة."]
    for c in r["clusters"]:
        lines.append(f"- **المجموعة {c['cluster_id']}** على {tv(c['corridor'])} ({tv(c['area'])}): {c['lights']} مصباح، متوسط الاحتمال {c['mean_probability']:.0%}، أعلى درجة أولوية {c['max_priority_score']}.")
    for d in r["detections"][:5]:
        dr = d["drivers"]
        lines.append(f"- {d['asset_id']} p={d['probability']:.0%} الخطورة {d['risk_score']} (الأهمية {tv(d['criticality'])}) - انحراف الطاقة {dr['power_trend_pct']:+}٪، {dr['flicker_30d']} وميض/30 يومًا، {dr['faults_12m']} عطل/12 شهرًا")
    lines.append(f"\n_النموذج:_ {r['model']}.\n_التالي:_ قل «أنشئ حوادث» لتجميع المجموعة في حادثة صيانة وقائية.")
    return "\n".join(lines)


def detect_imagery_changes(r):
    lines = [f"قارنتُ **{r['previous_epoch']}** بـ **{r['current_epoch']}** في {tv(r['area'])}. الصور والمعالجة **محاكاة**؛ والنتائج مرشّحات وليست إنشاءات مؤكدة.",
             f"الطريقة: {_tx(r['method'])} (العتبة {r['threshold']})."]
    for c in r["changes"]:
        lines.append(f"- **{c['change_id']}** {tv(c['type'])}: {c['area_sqm']:,} م²، الثقة {c['confidence']}" + (" - **جوهري**" if c["significant"] else " - غير جوهري"))
    lines.append(f"\n**{r['significant_count']} مرشّحًا جوهريًا.** لا تُحتسب الفروق النباتية فقط لأنها قد تكون موسمية.")
    chk = r["simulation_check"]
    lines.append(f"_فحص المحاكاة:_ استُرجع {chk['recovered']} من {chk['injected_real_changes']} تغيّرًا حقيقيًا مُدخلًا.")
    lines.append("_التالي:_ «استخرج المباني والطرق حول التغيّرات المرصودة».")
    return "\n".join(lines)


def extract_geoai_features(r):
    return (f"للتغيّر **{r['change_id']}** ({tv(r['area'])}) وجد الاستخراج المحاكى **{len(r['buildings'])} بصمة مبنى** (المجموع {r['tot_building_area_sqm']:,} م²) "
            f"و**{len(r['roads'])} مقطع طريق** (المجموع {r['tot_road_length_m']:,} م). المصدر: {_tx(r['source'])}. لم يُشغَّل أي نموذج تعلّم عميق.\n"
            "_التالي:_ شغّل تحليلًا مكانيًا لمعرفة الأصول والمرافق القريبة.")


def spatial_analysis(r):
    t = r["target"]
    pa = r["potentially_affected"]
    lines = [f"تحليل مكاني حول **{tv(t['type'])} {t['id']}** (نصف القطر {r['radius_m']:.0f} م)" + (f"، المساحة {t['area_sqm']:,} م²" if "area_sqm" in t else "") + ":",
             f"- أنابيب المياه: **{pa['pipes']}**؛ إنارة الشوارع: **{pa['lights']}**؛ مبانٍ حقيقية: **{pa.get('buildings', 0)}**؛ مرافق: **{pa['facilities']}**؛ ممرات الطرق: {_join(r['road_corridors']) or 'لا يوجد قريبًا'}"]
    for f in r["facilities"][:4]:
        lines.append(f"  - {f['name']} ({tv(f['type'])}) {f['distance_m']} م")
    for p in r["water_pipes"][:3]:
        lines.append(f"  - الأنبوب {p['pipeline_id']} {p['diameter_mm']} مم {p['material']} على بُعد {p['distance_m']} م")
    if r["open_incidents_nearby"]:
        lines.append("- حوادث مفتوحة قريبة: " + _join(f"{i['incident_id']} ({tv(i['type'])}، {i['distance_m']} م)" for i in r["open_incidents_nearby"][:4]))
    if r["extracted_features"]:
        lines.append(f"- معالم مستخرجة قريبة: {len(r['extracted_features'])} (محاكاة)")
    lines.append(f"_{_tx(r['note'])}_")
    return "\n".join(lines)


def executive_summary(r):
    k = r["kpis"]
    lines = ["**نظرة تنفيذية عامة (محسوبة من السجلات المخزنة)**",
             f"- حوادث مفتوحة **{k['open_incidents']}** من {k['total_incidents']} (حرجة: **{k['critical_incidents']}**) | أوامر عمل مفتوحة **{k['open_work_orders']}** | غير مكلَّفة **{k['unassigned_work_orders']}**",
             f"- تسرّبات مشتبه بها **{k['suspected_water_leaks']}** | أعطال إنارة متوقعة **{k['predicted_streetlight_failures']}** | تغيّرات عمرانية جوهرية **{k['detected_urban_changes']}**",
             f"- معدل التحقق **{_fmt(k['verification_rate_pct'])}٪** | معدل الحل **{_fmt(k['incident_resolution_rate_pct'])}٪** | متوسط الاستجابة **{_fmt(k['avg_response_time_hours'])} ساعة**"]
    if r["hotspots"]:
        lines.append("- النقاط الساخنة: " + "؛ ".join(f"{tv(h['area'])} ({h['score']})" for h in r["hotspots"][:3]))
    if r["recommendations"]:
        lines.append("\n**أولويات التدخل**")
        for x in r["recommendations"][:4]:
            lines.append(f"{x['rank']}. {x['incident_id']} ({x['priority']}، {tv(x['area'])}): {_tx(x['recommended_action'])} - {'؛ '.join(_tx(e) for e in x['evidence'])}")
    return "\n".join(lines)


def rank_incidents(r):
    if not r["ranked"]:
        return "لا توجد حوادث مفتوحة."
    lines = [f"أعلى **{r['open_total']}** حادثة مفتوحة حسب الاستعجال ({_tx(r['ordering'])}):"]
    for x in r["ranked"]:
        lines.append(f"{x['rank']}. **{x['incident_id']}** {tv(x['type'])} - {x['priority']}، الخطورة {x['risk_score']}، {tv(x['area'])}، الحالة {tv(x['status'])} ({'؛ '.join(_tx(e) for e in x['evidence'])})")
    lines.append(f"\nالأكثر حرجًا: **{r['ranked'][0]['incident_id']}**. _التالي:_ «أنشئ أمر عمل لهذه الحادثة».")
    return "\n".join(lines)


def create_incidents_from_detections(r):
    if not r["created"] and not r["already_existing"]:
        return _tx(r.get("message")) if r.get("message") else "لا توجد رصودات لتحويلها. شغّل عملية رصد أولًا."
    lines = []
    if r["created"]:
        lines.append(f"أُنشئت **{len(r['created'])} حادثة** (الحالة مفتوحة؛ لم يُتخذ أي إجراء خارجي):")
        for c in r["created"]:
            lines.append(f"- **{c['incident_id']}** {tv(c['type'])} - {c['priority']} / {tv(c['severity'])}، الخطورة {c['risk_score']}، {tv(c['area'])}، الفريق: {tv(c['assigned_team'])}")
    if r["already_existing"]:
        lines.append(f"لديها حوادث بالفعل (دون تكرار): {_join(r['already_existing'])}.")
    lines.append("_التالي:_ «أيها الأكثر حرجًا؟» أو «أنشئ أمر عمل لهذه الحادثة».")
    return "\n".join(lines)


def list_incidents(r):
    if not r["count"]:
        return "لا توجد حوادث مطابقة."
    lines = [f"**{r['count']}** حادثة (المعروض {len(r['incidents'])}):"]
    for x in r["incidents"]:
        lines.append(f"- {x['incident_id']} {tv(x['type'])} {x['priority']} الخطورة {x['risk_score']} {tv(x['area'])} - {tv(x['status'])}" + (f" / التحقق: {tv(x['verification'])}" if x["verification"] else ""))
    return "\n".join(lines)


def get_incident(r):
    i = r["incident"]
    return (f"**{i['Incident_ID']}** {tv(i['Incident_Type'])} - {i['Priority']}/{tv(i['Severity'])} الخطورة {i['Risk_Score']} في {tv(i['Area_Name'])}؛ الحالة **{tv(i['Status'])}**؛ الفريق {tv(i['Assigned_Team'])}.\n"
            f"الرصودات: {_join(d['id'] for d in r['detections'])}؛ أوامر العمل: {_join(w['Work_Order_ID'] + ' (' + tv(w['Status']) + ')' for w in r['work_orders']) or 'لا يوجد'}؛ "
            f"عمليات التحقق: {len(r['verifications'])}.")


def _approval_block(a):
    return (f"**طلب موافقة - {a['Approval_ID']}**\n- الإجراء: {_tx(a['Summary'])}\n- الهدف: {a['Target']} | الموقع: {tv(a['Location']) or 'غير متاح'} | الأولوية: {a['Priority'] or 'غير متاح'} | الفريق: {tv(a['Team']) if a['Team'] else 'غير متاح'}\n"
            f"- النتيجة المتوقعة: {_tx(a['Expected_Result'])}\n\n**لم يُنشأ شيء بعد.** اكتب **موافقة** (أو استخدم لوحة الموافقات) للتنفيذ، أو **رفض**.")


def propose_work_order(r):
    return _approval_block(r["approval"])


def propose_work_orders_bulk(r):
    lines = [f"جُهِّزت **{len(r['proposals'])}** مقترحات لأوامر العمل؛ لا وجود لأي منها حتى الموافقة:"]
    for a in r["proposals"]:
        lines.append(f"- {a['Approval_ID']}: {_tx(a['Summary'])}")
    for s in r["skipped"]:
        lines.append(f"- تم تخطي {s['incident_id']}: {_tx(s['reason'])}")
    lines.append("\nاكتب **موافقة على الكل** لتنفيذها، أو وافق على كل واحد من لوحة الموافقات.")
    return "\n".join(lines)


def propose_field_assignment(r):
    w = r["recommended_worker"]
    return f"المحقق المقترح: **{tv(w['name'])}** ({tv(w['team'])})، الدرجة {w['score']} - {_tx(w['rationale'])}.\n\n" + _approval_block(r["approval"])


def propose_incident_closure(r):
    return _approval_block(r["approval"])


def verify_outcome(r):
    if not r["verified"]:
        return f"**{r['incident_id']}** ليس له تحقق ميداني بعد. {_tx(r['message'])}"
    v = r["latest_verification"]
    return (f"**التحقق من {r['incident_id']}** (حالة النظام: **{tv(r['incident_status'])}**، النتيجة: {tv(r['verification_outcome']) if r['verification_outcome'] else 'قيد الانتظار'})\n"
            f"- المحقق الميداني {v['Worker_ID']}{' (محاكى)' if v['Simulated_Worker'] == 'Yes' else ''} أبلغ بحالة **{tv(v['Verification_Status'])}** عند {v['GPS_Location']} (على بُعد {v['Distance_To_Detection_M']} م من نقطة الرصد).\n"
            f"- الملاحظة: {v['Observation']}\n- الدليل المصوّر: {v['Photo_URL'] or 'لا يوجد'}\n- **المقارنة:** {_tx(r['agent_assessment'])}\n_التالي:_ {_tx(r['next_step'])}")


def evaluate_outcomes(r):
    e = r["evaluation"]
    lines = [f"**التوقع مقابل النتيجة المؤكدة** - {e['total_verified']} مؤكدة من {e['total_detections']} رصدًا (معدل التحقق {_fmt(e['verification_rate'])})؛ الدقة الإجمالية {_fmt(e['overall_precision'])}."]
    for c, v in e["categories"].items():
        lines.append(f"- {tv(c)}: إيجابي صحيح {v['verified_true']} / إيجابي كاذب {v['verified_false']} / بانتظار التحقق {v['awaiting_verification']}؛ الدقة {_fmt(v['precision'])}؛ الاسترجاع {_fmt(v['recall'])}؛ المعايرة x{v['calibration']}")
    if r["calibration_update"]:
        lines.append("تم تحديث معايرة الخطورة من النتائج المؤكدة.")
    lines.append(f"_{_tx(r['disclaimer'])}_ {_tx(e['notes'])}")
    return "\n".join(lines)


def sensor_intelligence(r):
    lines = [f"قُيِّم {r['sensors_evaluated']} حسّاسًا، **{r['anomalous']} شاذًا**."]
    for s in r["sensors"][:5]:
        lines.append(f"- {s['sensor_id']} ({tv(s['area'])}، {s['pipeline_id']}): انخفاض الضغط {s['drop_pct']:+}٪، z={s['z']}، التدفق {s['flow_change_pct']:+}٪" + (" **شاذ**" if s["anomalous"] else ""))
    return "\n".join(lines)


def count_incidents(r):
    sc = r["scope"]
    scope = " ".join(x for x in ("مفتوحة" if r["open_only"] else "", f"({tv(sc.get('severity'))})" if sc.get("severity") else "", f"من نوع {NAMES.get(sc['category'], tv(sc['category']))}" if sc.get("category") else "",
                                 f"في {tv(sc['area'])}" if sc.get("area") else "") if x)
    if not r["count"]:
        return f"**لا توجد حوادث {scope}** حاليًا (سُجّل {r['total_all_time']} حادثة إجمالًا)."
    lines = [f"**{r['count']} حادثة {scope}** ({r['critical']} حرجة)."]
    if len(r["by_area"]) > 1 or not sc.get("area"):
        lines.append("- حسب المنطقة: " + _join(f"{tv(k)} {v}" for k, v in r["by_area"].items()))
    if len(r["by_category"]) > 1 or not sc.get("category"):
        lines.append("- حسب النوع: " + _join(f"{NAMES.get(k, tv(k))} {v}" for k, v in r["by_category"].items()))
    lines.append("- حسب الأولوية: " + _join(f"{k} {v}" for k, v in sorted(r["by_priority"].items())))
    lines.append("- حسب الحالة: " + _join(f"{tv(k)} {v}" for k, v in r["by_status"].items()))
    if r["awaiting_approval"]:
        lines.append(f"\n{r['awaiting_approval']} قرار بانتظار موافقتك.")
    return "\n".join(lines)


def feeds_summary(r):
    lines = [f"**{r['reports']} بلاغ مواطنين** ({tv(r['scope'])}): {r['waiting']} بانتظار التعزيز، {r['linked_to_incidents']} مرتبطة بحوادث."]
    if r["by_category"]:
        lines.append("- حسب النوع: " + _join(f"{tv(k)} {v}" for k, v in r["by_category"].items()))
    if r["by_area"]:
        lines.append("- حسب المنطقة: " + _join(f"{tv(k)} {v}" for k, v in list(r["by_area"].items())[:6]))
    lines.append(f"_{_tx(r['caveat'])}_")
    return "\n".join(lines)


def monitor_poles(r):
    if not r["flagged"]:
        return f"فحصتُ **{r['poles_evaluated']} عمودًا** ({tv(r['scope'])})؛ لا يتجاوز أي منها الحدود (الميلان {r['limits']['tilt_deg']}°، التآكل {tv(r['limits']['corrosion'])})."
    lines = [f"فحصتُ **{r['poles_evaluated']} عمودًا** ({tv(r['scope'])}) و**{r['flagged']}** منها يتجاوز حدود السلامة. هذه مخاطر إنشائية **متوقعة** وليست أعطالًا مؤكدة."]
    for d in r["detections"][:6]:
        lines.append(f"- **{d['asset_id']}** على {tv(d['corridor'])}: الميلان {d['tilt_deg']:.1f}°، تآكل {tv(d['corrosion'])}، الخطورة **{d['risk_score']}** ({tv(d['severity'])}).")
    lines.append("\n_التالي:_ قل «أنشئ حوادث» لتجميعها في حادثة فحص واحدة.")
    return "\n".join(lines)


def detect_visual_distortion(r):
    if not r["flagged"]:
        return f"قارنتُ **{r['previous_epoch']}** بـ **{r['current_epoch']}** في {tv(r['area'])} ({r['buildings_evaluated']} مبنى): لا تشوّه بصريًا فوق العتبة."
    lines = [f"قارنتُ تاريخَي التصوير في {tv(r['area'])} ({r['buildings_evaluated']} مبنى، صور **محاكاة**) ويظهر على **{r['flagged']}** منها تشوّه بصري."]
    for d in r["detections"][:6]:
        if d.get("visual_type"):
            lines.append(f"- **{tv(d['kind'])}** قرب {tv(d['name'])}: درجة التشوّه البصري {d['edge_warp_index']:.2f} (z={d['z_score']})، الخطورة **{d['risk_score']}** ({tv(d['severity'])})" + (f"، قرب {tv(d['near_facility'])}" if d["near_facility"] else "") + ".")
        else:
            lines.append(f"- **{tv(d['name'])}**: {tv(d['kind'])}، مؤشر التواء الحواف {d['edge_warp_index']:.2f} (z={d['z_score']})، الخطورة **{d['risk_score']}** ({tv(d['severity'])})" + (f"، قرب {tv(d['near_facility'])}" if d["near_facility"] else "") + ".")
    lines.append("\n_هذه مرشّحات لمعاينة ميدانية أو مسح إنشائي وليست أحكامًا نهائية._")
    return "\n".join(lines)


def analyze_land_use(r):
    lines = [f"**{tv(r['area'])}** مصنّفة *{tv(r['zone'])}* (الاستخدامات الجديدة المسموحة: {_join(tv(u) for u in r['permitted_uses']) or 'لا شيء'}). صنّفتُ **{r['significant_changes']}** تغيّرًا جوهريًا من الصور (محاكاة) ووجدت **{r['violations']}** مرشّح مخالفة تقسيم."]
    for d in r["detections"][:5]:
        lines.append(f"- **{d['change_id']}** {tv(d['land_use'])} ~{d['area_sqm']:,.0f} م²: {_tx(d['why'])}. الخطورة **{d['risk_score']}** ({tv(d['severity'])}).")
    lines.append("\n_مرشّحات لمعاينة موقعية وليست قرارات إنفاذ._")
    return "\n".join(lines)


COMPOSERS_AR = {k: v for k, v in globals().items() if callable(v) and k in (
    "detect_water_leaks", "predict_streetlight_failures", "detect_imagery_changes", "extract_geoai_features", "spatial_analysis", "executive_summary", "rank_incidents",
    "create_incidents_from_detections", "list_incidents", "get_incident", "propose_work_order", "propose_work_orders_bulk", "propose_field_assignment", "propose_incident_closure",
    "verify_outcome", "evaluate_outcomes", "sensor_intelligence", "count_incidents", "feeds_summary", "monitor_poles", "detect_visual_distortion", "analyze_land_use")}
COMPOSERS_AR["propose_asset_status_change"] = propose_incident_closure

# ---------------------------------------------------------------------------------------------------- fixed messages and suggestions
MSG = {
    "repair_reported": "أبلغ فريق محاكى عن إصلاح **{id}** ({wo}). اقتراح الإغلاق جاهز لموافقتك.",
    "empty": "اكتب طلبك، مثلًا: «اكشف التسرّبات المحتملة في الرياض».",
    "nothing_pending": "لا شيء بانتظار الموافقة.",
    "none_waiting": "لا يوجد ما ينتظر الموافقة.",
    "pending_head": "**الموافقات المعلّقة:**",
    "not_found": "لا أجد **{iid}**. اسأل «كم حادثة مفتوحة؟» أو «اعرض الحوادث المفتوحة» لمعرفة الحوادث الموجودة.",
    "could_not_run": "**تعذّر تشغيل {name}:** {err}",
    "executed": "**نُفِّذ** {id} - {summary}. تأكيد النظام: {conf}",
    "failed": "**فشل** {id}: {err}. لم يُجرَ أي تغيير.",
    "rejected": "تم رفض {id}: {summary}. لم يتغيّر أي شيء.",
    "sorry": "عذرًا، تعذّر ذلك: {err}",
    "compare_head": "مقارنة {n} رصدًا حاليًا حسب درجة الخطورة:",
    "most_critical": "\nالأكثر حرجًا: **{id}** - {ev}",
    "context": "السياق ضمن {r:.0f} م: {pipes} أنابيب، {lights} إنارة شوارع، {fac} مرافق؛ الممرات: {cor}.",
    "compare_next": "_التالي:_ قل «أنشئ حوادث» ثم «أنشئ أمر عمل لهذه الحادثة».",
    "intro": ("أنا وكيل عمليات الذكاء الاصطناعي المكاني. أستطيع الاستشعار (تسرّبات المياه، أعطال الإنارة)، والرؤية (تغيّر الصور)، والفهم (استخراج المعالم والتحليل المكاني)، "
              "والقرار (المؤشرات والترتيب)، والتنفيذ (الحوادث وأوامر العمل والتكليفات - دائمًا بموافقتك)، والتحقق (الأدلة الميدانية والنتائج). كما أعدّ الحوادث حسب المنطقة، "
              "وأقرأ بلاغات المواطنين، وأبحث عن أي سجل برقمه (مثل INC-0074). جرّب أحد الاقتراحات أدناه."),
}
SUGGESTIONS_AR = {
    "Approve": "موافقة", "Reject": "رفض", "Show pending approvals": "اعرض الموافقات المعلّقة",
    "Create a work order for that one": "أنشئ أمر عمل لهذه الحادثة", "Assign a field worker": "كلّف محققًا ميدانيًا", "Verify the outcome": "تحقق من النتيجة", "Close the incident": "أغلق الحادثة",
    "Which incidents require immediate intervention?": "أي الحوادث تتطلب تدخلًا فوريًا؟", "Show executive summary": "اعرض الموجز التنفيذي",
    "Create incidents from these detections": "أنشئ حوادث من هذه الرصودات", "Which one is the most critical?": "أيها الأكثر حرجًا؟", "Show spatial context for that one": "اعرض السياق المكاني لهذه",
    "How many incidents are open, and where?": "كم حادثة مفتوحة وأين؟", "Compare imagery epochs in Olaya District": "قارن فترات الصور في العليا", "What are residents reporting?": "ماذا يبلغ السكان؟",
}
