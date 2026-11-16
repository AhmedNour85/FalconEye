"""Arabic support for text that the backend writes in English.

The system of record keeps one language (English), so ids, ArcGIS Online layers and tests never change. When a client asks for Arabic
(`?lang=ar` or an `X-Lang: ar` header) the API runs the free-text fields of its JSON through `to_ar()`:

1. RULES  - ordered regular expressions for the sentences the crew, the tools and the approval gate write (numbers and ids are kept as they are);
2. TERMS  - fixed vocabulary (areas, incident types, teams, investigators, agents ...), replaced longest first.

Text that nothing matches is returned unchanged, so a missing translation shows English instead of breaking the screen.
Machine-translated wording here should be reviewed by an Arabic speaker before a real deployment.
"""
from __future__ import annotations

import re
from contextvars import ContextVar

LANGS = ("en", "ar")
DEFAULT_LANG = "en"
CURRENT: ContextVar[str] = ContextVar("geoai_lang", default=DEFAULT_LANG)   # language of the request being served (set by the API middleware)


def pick(value: str | None) -> str:
    """Normalise a requested language ('ar', 'ar-SA', 'EN' ...) to a supported one."""
    v = (value or "").strip().lower()[:2]
    return v if v in LANGS else DEFAULT_LANG


# ---------------------------------------------------------------------------------------------------- vocabulary
TERMS: dict[str, str] = {
    # areas
    "Diplomatic Quarter": "الحي الدبلوماسي", "King Salman Park": "حديقة الملك سلمان", "Al Malaz": "الملز", "Olaya": "العليا", "KAFD": "المركز المالي (كافد)",
    "Diriyah": "الدرعية", "Riyadh": "الرياض", "building": "مبنى", "Street": "شارع", "Road": "طريق", "King Fahd": "الملك فهد",
    # investigators and agents
    "Nawaf Al-Harbi": "نواف الحربي", "Khalid Al-Otaibi": "خالد العتيبي", "Saad Al-Qahtani": "سعد القحطاني", "Hamad Al-Ghamdi": "حمد الغامدي",
    "Yousef Al-Dosari": "يوسف الدوسري", "Ibrahim Al-Shehri": "إبراهيم الشهري", "Majed Al-Mutairi": "ماجد المطيري",
    "Faisal": "فيصل", "Mansour": "منصور", "Sarah": "سارة", "Abdullah": "عبدالله", "Zayed": "زايد", "Reem": "ريم", "Turki": "تركي", "Maha": "مها",
    # agent roles and focus
    "Executive GeoCoworker": "زميل جيومكاني تنفيذي", "Operations GeoCoworker": "زميل جيومكاني للعمليات", "Fault & Leak GeoCoworker": "زميل جيومكاني للأعطال والتسرّبات",
    "Asset Health GeoCoworker": "زميل جيومكاني لصحة الأصول", "Change & Planning GeoCoworker": "زميل جيومكاني للتغيّر والتخطيط",
    "Service Impact GeoCoworker": "زميل جيومكاني لأثر الخدمات", "Field Operations GeoCoworker": "زميل جيومكاني للعمليات الميدانية",
    "Performance GeoCoworker": "زميل جيومكاني للأداء",
    "Escalates critical risk and briefs leadership": "يصعّد المخاطر الحرجة ويُطلع القيادة",
    "Triages findings into incidents and coordinates the crew": "يحوّل الرصودات إلى حوادث وينسّق عمل الفريق",
    "Watches pressure and flow sensors for water faults": "يراقب حسّاسات الضغط والتدفق لاكتشاف أعطال المياه",
    "Predicts streetlight failures and monitors pole health": "يتنبأ بأعطال إنارة الشوارع ويراقب سلامة الأعمدة",
    "Urban change and visual distortion from imagery epochs": "التغيّر العمراني والتشوّه البصري من صور الأقمار الصناعية",
    "Finds the facilities and services around each finding": "يحدد المرافق والخدمات المحيطة بكل رصد",
    "Prepares work orders, dispatch and closure": "يُعدّ أوامر العمل والتكليف والإغلاق",
    "Compares field results with predictions and learns": "يقارن نتائج الميدان بالتوقعات ويتعلّم منها",
    # teams
    "Water Rapid Response": "الاستجابة السريعة للمياه", "Electrical Maintenance": "الصيانة الكهربائية", "Survey & Inspection": "المسح والتفتيش",
    # incident / detection / task types
    "Water Leak (Suspected)": "تسرّب مياه (مشتبه به)", "Streetlight Failure (Predicted)": "عطل إنارة شارع (متوقع)", "Streetlight Cluster Maintenance": "صيانة مجموعة إنارة شوارع",
    "Streetlight Pole Inspection": "فحص أعمدة إنارة الشوارع", "Streetlight Pole Risk (Predicted)": "خطر عمود إنارة (متوقع)", "Urban Change Review": "مراجعة تغيّر عمراني",
    "Visual Distortion Review": "مراجعة تشوّه بصري", "Visual Distortion (Candidate)": "تشوّه بصري (مرشّح)", "Land-Use Violation Review": "مراجعة مخالفة استخدام أراضٍ",
    "Land-Use Violation (Candidate)": "مخالفة استخدام أراضٍ (مرشّحة)", "Water Issue (Citizen-reported)": "مشكلة مياه (بلاغ مواطنين)",
    "Streetlight Failure (Citizen-reported)": "عطل إنارة (بلاغ مواطنين)", "Urban Case": "حالة عمرانية", "Water Leak": "تسرّب مياه", "Streetlight Failure": "عطل إنارة شارع",
    "Visual Distortion": "تشوّه بصري", "Urban Change": "تغيّر عمراني", "Inspect & Verify": "فحص وتحقق", "Inspect & Repair": "فحص وإصلاح", "Candidate": "مرشّح",
    # imagery change types and land-use categories
    "New construction (candidate)": "إنشاءات جديدة (مرشّح)", "Vegetation loss (possible seasonal - unconfirmed)": "فقدان غطاء نباتي (قد يكون موسميًا - غير مؤكد)",
    "Clearing / demolition (candidate)": "إزالة / هدم (مرشّح)", "Spectral change (unclassified)": "تغيّر طيفي (غير مصنّف)",
    "Large-scale development": "مشروع تطوير واسع النطاق", "Residential": "سكني", "Commercial": "تجاري", "Cleared land": "أرض مُزالة", "Vegetation change": "تغيّر في الغطاء النباتي",
    "Commercial & mixed-use": "تجاري ومتعدد الاستخدامات", "Financial district": "حي مالي", "Institutional / diplomatic": "مؤسسي / دبلوماسي", "Open space / park": "مساحة مفتوحة / حديقة",
    "Heritage & tourism": "تراثي وسياحي", "Unzoned (demo)": "غير مصنّفة (تجريبي)",
    "Facade bulging / wall deformation": "انتفاخ الواجهة / تشوّه الجدران", "Footprint skew (possible settlement)": "انحراف البصمة (هبوط محتمل)", "Roof-line sagging": "تدلّي خط السقف",
    "structural deformation": "تشوّه إنشائي",
    "Pressure/Flow Sensor": "حسّاس ضغط/تدفق", "Streetlight": "إنارة شارع",
    # facility types
    "Hospital": "مستشفى", "School": "مدرسة", "Mosque": "مسجد", "Clinic": "عيادة", "University": "جامعة",
    # multi-word statuses
    "Work Order Created": "تم إنشاء أمر العمل", "Closed - False Positive": "أُغلق - إنذار كاذب", "Needs Further Inspection": "يحتاج إلى فحص إضافي",
    "Requires Further Inspection": "يتطلب فحصًا إضافيًا", "Repair Reported": "أُبلغ عن الإصلاح", "In Progress": "قيد التنفيذ",
    # feeds
    "Water sensors": "حسّاسات المياه", "Streetlights & poles": "إنارة الشوارع والأعمدة", "Satellite imagery": "صور الأقمار الصناعية", "Visual distortion (imagery)": "التشوّه البصري (صور)", "street-level problems and building shape between satellite dates": "مشكلات بصرية في الشوارع وشكل المباني بين تاريخَي التصوير",
    "Land use / zoning": "استخدام الأراضي / التقسيم", "Citizen reports": "بلاغات المواطنين",
    "change scan on each new pass": "فحص التغيّر عند كل مرور جديد للقمر", "edge-warp between satellite dates": "التواء الحواف بين تاريخَي التصوير",
    "construction vs. zoning rules": "الإنشاءات مقابل أنظمة التقسيم",
    # lowercase forms the tools write inside sentences
    "hospital": "مستشفى", "school": "مدرسة", "mosque": "مسجد", "clinic": "عيادة", "university": "جامعة", "residential": "سكني", "commercial": "تجاري",
    "large-scale development": "مشروع تطوير واسع النطاق", "cleared land": "أرض مُزالة", "vegetation change": "تغيّر في الغطاء النباتي",
    "new construction": "إنشاءات جديدة", "clearing / demolition": "إزالة / هدم", "vegetation loss (possible seasonal - unconfirmed)": "فقدان غطاء نباتي (قد يكون موسميًا - غير مؤكد)",
    "spectral change (unclassified)": "تغيّر طيفي (غير مصنّف)", "all areas": "كل المناطق", "all corridors": "كل الممرات",
    # misc nouns used inside sentences
    "Critical": "حرج", "High": "عالٍ", "Medium": "متوسط", "Low": "منخفض",
}
from backend.services import visual_types as _vt  # noqa: E402  (pure data)

for _v in _vt.VISUAL_TYPES.values():             # the eight visual-distortion types: names and the short description used in the evidence sentence
    TERMS[_v["name"]] = _v["ar"]
    TERMS[_v["what"]] = _v["what_ar"]
from backend.services import i18n_mobility as _mob  # noqa: E402  (pure data)

TERMS.update(_mob.TERMS)
_TERM_RE = re.compile("|".join(r"(?<![\w])" + re.escape(k) + r"(?![\w])" for k in sorted(TERMS, key=len, reverse=True)))
_CAT_AR = {"water": "مياه", "lighting": "إنارة", "change": "تغيّر عمراني", "distortion": "تشوّه بصري", "land_use": "استخدام أراضٍ", "mobility": _mob.CAT_AR}
_STATUS_AR = {"Open": "مفتوحة", "Assigned": "مُكلَّفة", "In Progress": "قيد التنفيذ", "Resolved": "تم الحل", "Confirmed": "مؤكدة", "Rejected": "مرفوضة", "Escalated": "مصعَّدة"}
_ID_RE = re.compile(r"\b[A-Z][A-Z0-9]*(?:-[A-Za-z0-9]+)+\b")
_ARABIC_RE = re.compile(r"[؀-ۿ]")
_SEV_ONLY = {"Critical", "High", "Medium", "Low"}        # translated only as whole values or after a priority, never inside a sentence ("High" may be a verb phrase)

N = r"([\d,]+(?:\.\d+)?)"           # a number
SN = r"([+-]?[\d,]+(?:\.\d+)?)"     # a signed number
X = r"(.+?)"                        # any text, shortest

# ---------------------------------------------------------------------------------------------------- sentence rules
# (pattern, replacement). Applied in order to the same string; ids, numbers and free text written by a person are left alone.
RULES: list[tuple[str, str]] = [
    # ---- crew steps (action | detail)
    (r"^Scanned water sensors$", "فحص حسّاسات المياه"),
    (rf"^{N} sensors, {N} suspected leak\(s\)$", r"\1 حسّاس، \2 تسرّب(ات) مشتبه بها"),
    (rf"^{N} sensors, all normal$", r"\1 حسّاس، كلها طبيعية"),
    (r"^Checked streetlights and poles$", "فحص إنارة الشوارع والأعمدة"),
    (rf"{N} lamps, {N} at risk of failing", r"\1 مصباح، \2 معرّض للعطل"),
    (rf"{N} lamps, none at risk", r"\1 مصباح، لا خطر على أي منها"),
    (r"lamps not checked", "لم تُفحص المصابيح"),
    (rf"{N} of {N} poles beyond tilt/corrosion limits", r"\1 من \2 عمودًا تجاوزت حدود الميلان/التآكل"),
    (r"poles sound", "الأعمدة سليمة"),
    (r"^Compared building shapes between satellite dates$", "قارن أشكال المباني بين تاريخَي التصوير"),
    (rf"^{X}: {N} building\(s\) with visual distortion$", r"\1: \2 مبنى بتشوّه بصري"),
    (r"^Checked land use against zoning$", "راجع استخدام الأراضي مقابل أنظمة التقسيم"),
    (rf"^{X}: {N} possible zoning violation\(s\)$", r"\1: \2 مخالفة تقسيم محتملة"),
    (r"^Compared satellite imagery$", "قارن صور الأقمار الصناعية"),
    (rf"^{X}: {N} significant change\(s\)$", r"\1: \2 تغيّر(ات) جوهرية"),
    (rf"^{X}: no significant change$", r"\1: لا تغيّر جوهري"),
    (r"^Opened incidents$", "فتح حوادث"),
    (rf"^{N} new incident\(s\) from {N} finding\(s\)$", r"\1 حادثة جديدة من \2 رصد"),
    (r"^Assessed impact$", "قيّم الأثر"),
    (r"^Prepared work order$", "أعدّ أمر عمل"),
    (r"^Escalated$", "صعّد"),
    (r"^(\S+) is Critical$", r"\1 حرجة"),
    (r"^Recommended a crew$", "رشّح فريقًا"),
    (r"^Briefed leadership$", "أطلع القيادة"),
    (r"^Verified outcome$", "تحقق من النتيجة"),
    (r"^Prepared closure$", "أعدّ الإغلاق"),
    (r"^Assignment accepted$", "تم قبول التكليف"),
    (r"^Task finished in Field Maps$", "أُنهيت المهمة في Field Maps"),
    (r"^Prepared inspection work order$", "أعدّ أمر عمل للفحص"),
    (r"\(operator request\)", "(بطلب المشغّل)"),
    (r"^Crew repaired the fault \(simulated\)$", "أصلح الفريق العطل (محاكاة)"),
    (r"^Crew visited the site \(simulated\)$", "زار الفريق الموقع (محاكاة)"),
    (rf"^Read citizen reports$", "قرأ بلاغات المواطنين"),
    (rf"^{N} new report\(s\) from residents$", r"\1 بلاغ جديد من السكان"),
    # ---- impact line (also inside trails)
    (rf"{N} facilities, {N} pipes, {N} streetlights within {N} m", r"\1 مرافق، \2 أنابيب، \3 إنارة شوارع ضمن \4 م"),
    (r"\(e\.g\. ", "(مثلًا: "),
    (r"^Impact: ", "الأثر: "),
    # ---- errors shown to the operator
    (r"^fault confirmed but repair not yet reported by the field team; to continue in a demo, report the repair as a simulated crew \(the 'Simulate repair' button on the verified alert, or say 'simulate repair for (\S+)'\)$",
     r"تأكد العطل لكن لم يُبلَّغ عن الإصلاح من الفريق الميداني؛ لمتابعة العرض أبلغ عن الإصلاح كفريق محاكى (زر «محاكاة الإصلاح» في تنبيه التحقق، أو قل «حاكِ إصلاح \1»)"),
    (r"^incident (\S+) has not been confirmed in the field yet; a repair can only be reported after that$", r"لم تُؤكَّد الحادثة \1 ميدانيًا بعد؛ لا يمكن الإبلاغ عن إصلاح قبل ذلك"),
    (r"^the repair of (\S+) has already been reported$", r"سبق الإبلاغ عن إصلاح \1"),
    (r"^incident (\S+) is already closed$", r"الحادثة \1 مغلقة بالفعل"),
    (r"^incident (\S+) has no active work order with an assigned worker$", r"لا يوجد للحادثة \1 أمر عمل نشط بمحقق مكلَّف"),
    (r"^I could not report that repair: (.+)\.$", r"تعذّر الإبلاغ عن ذلك الإصلاح: \1"),
    (r"^The Anthropic account has no credit left \(add credit under Plans & Billing\)$", "حساب Anthropic لا يملك رصيدًا كافيًا (أضف رصيدًا من «الخطط والفواتير» Plans & Billing)"),
    (r"^HTTP 429 \(rate limit reached; try again shortly\)$", "خطأ HTTP 429: تم بلوغ حد الطلبات؛ أعد المحاولة بعد قليل"),
    (r"^cannot reach the Anthropic API; check the internet connection$", "تعذّر الوصول إلى واجهة Anthropic؛ تحقق من اتصال الإنترنت"),
    (r"^HTTP (\d+) \(check the model name\)$", r"خطأ HTTP \1: اسم النموذج غير صحيح أو لم يعد متاحًا. اختر نموذجًا من القائمة أدناه."),
    (r"^HTTP (\d+) \(check the API key\)$", r"خطأ HTTP \1: مفتاح الواجهة البرمجية غير صحيح أو لا يملك الصلاحية."),
    (r"^HTTP (\d+)$", r"خطأ HTTP \1"),
    (r"^HTTP (\d+) \(check the model name\): model '(.+)' not found.*$", r"خطأ HTTP \1: النموذج '\2' غير موجود على الخادم. اختر اسمًا من قائمة النماذج المثبّتة."),
    (r"^HTTP (\d+) \(check the API key\): (.*)$", r"خطأ HTTP \1 (تحقق من مفتاح الواجهة البرمجية): \2"),
    (r"^HTTP (\d+) \(check the model name\): (.*)$", r"خطأ HTTP \1 (تحقق من اسم النموذج): \2"),
    (r"^HTTP (\d+): (.*)$", r"خطأ HTTP \1: \2"),
    (r"^cannot reach (\S+); is the server running\?$", r"تعذّر الوصول إلى \1؛ هل الخادم يعمل؟"),
    (r"^(\S+) did not answer in (\d+) s$", r"لم يرد \1 خلال \2 ثانية"),
    (r"^the server address must start with http:// or https://$", "يجب أن يبدأ عنوان الخادم بـ http:// أو https://"),
    (r"^enter the model name$", "أدخل اسم النموذج"),
    (r"^no incident specified and none in context; list or create incidents first$", "لم تُحدَّد حادثة ولا توجد حادثة في السياق؛ اعرض الحوادث أو أنشئها أولًا"),
    (r"^no incident specified or in context$", "لم تُحدَّد حادثة ولا توجد حادثة في السياق"),
    # ---- ranking evidence
    (r"^risk ([\d.]+) \((\w+)\)$", lambda m: f"الخطورة {m.group(1)} ({TERMS.get(m.group(2), m.group(2))})"),
    (r"^status (.+)$", lambda m: f"الحالة {_STATUS_AR.get(m.group(1)) or TERMS.get(m.group(1), m.group(1))}"),
    (r"urgency = risk score \(calibrated by verified outcomes\) \+ ageing \(max \+(\d+)\)", r"الاستعجال = درجة الخطورة (معايرة بالنتائج المؤكدة) + عامل التقادم (حتى +\1)"),
    # street names: Arabic puts the type first
    (r"\b((?:[A-Z][A-Za-z']+ )+)Street\b(?!\s+[A-Za-z])", r"شارع \1"), (r"\b((?:[A-Z][A-Za-z']+ )+)Road\b(?!\s+[A-Za-z])", r"طريق \1"),
    (r"^([\d]+) linked detection\(s\); confidence ([\d.]+)$", r"\1 رصد(ات) مرتبطة؛ الثقة \2"),
    (r"^incident (\S+) already has active work order (\S+)$", r"الحادثة \1 لديها أمر عمل نشط بالفعل \2"),
    (r"^incident (\S+) is (.+)$", r"الحادثة \1 حالتها: \2"),
    # ---- notes and caveats written by the tools
    (r"Index-differencing candidate on SIMULATED imagery\. Not a confirmed construction event; requires field/analyst verification\.", "مرشّح من مقارنة المؤشرات على صور محاكاة. ليس حدث إنشاء مؤكدًا؛ يتطلب تحققًا ميدانيًا أو تحليليًا."),
    (r"Vegetation-only change may be seasonal or irrigation-related\.", "قد يكون التغيّر النباتي فقط موسميًا أو ناتجًا عن الري."),
    (r"^All items are SUSPECTED leaks derived from simulated sensor data; none are confirmed until field verification\.$", "جميع العناصر تسرّبات مشتبه بها مستمدة من بيانات حسّاسات محاكاة؛ ولا يُؤكَّد أي منها قبل التحقق الميداني."),
    (r"^These are PREDICTED failures from simulated telemetry, not confirmed faults\.$", "هذه أعطال متوقعة من قياسات محاكاة، وليست أعطالًا مؤكدة."),
    (r"^SIMULATED pole telemetry\. Detections are PREDICTIONS for field inspection, not confirmed failures\.$", "قياسات أعمدة محاكاة. الرصودات توقعات للفحص الميداني وليست أعطالًا مؤكدة."),
    (r"^SIMULATED imagery and processing\. Distortion is a CANDIDATE finding that needs a structural survey; it is not a structural verdict\.$", "صور ومعالجة محاكاة. التشوّه نتيجة مرشّحة تحتاج إلى مسح إنشائي، وليست حكمًا إنشائيًا."),
    (r"^SIMULATED imagery and zoning reference\. Violations are CANDIDATES for site inspection, not enforcement decisions\.$", "صور ومرجع تقسيم محاكاة. المخالفات مرشّحات للمعاينة الموقعية وليست قرارات إنفاذ."),
    (r"^Buildings are REAL OpenStreetMap footprints \(ODbL\)\. Facility positions marked REFERENCE are approximate; SYNTHETIC facilities and all operational assets are demo data\.$", "المباني بصمات حقيقية من OpenStreetMap (رخصة ODbL). مواقع المرافق المعلَّمة «مرجعية» تقريبية؛ والمرافق الاصطناعية وجميع الأصول التشغيلية بيانات عرض."),
    (r"^Incidents are created in status Open; no external action has been taken\.$", "تُنشأ الحوادث بحالة «مفتوحة»؛ ولم يُتخذ أي إجراء خارجي."),
    (r"^Citizen reports are a SIMULATED feed in this demo\.$", "بلاغات المواطنين مصدر محاكى في هذا العرض."),
    (r"^Learning = feedback records, metrics and configurable calibration\. No ML model was retrained\.$", "التعلّم = سجلات التغذية الراجعة والمقاييس ومعايرة قابلة للضبط. لم يُعاد تدريب أي نموذج تعلّم آلي."),
    (r"^False negatives are computed from simulator ground truth \(not available in production\)\.$", "تُحسب السلبيات الكاذبة من الحقيقة المرجعية للمحاكي (غير متاحة في التشغيل الفعلي)."),
    (r"^Simulator-only check against injected changes; not available on real imagery\.$", "فحص للمحاكي فقط مقابل تغيّرات مُدخلة؛ غير متاح على صور حقيقية."),
    # ---- historical records
    (r"^Historical (water|lighting|change|distortion|land_use) incident at (.+)$", lambda m: f"حادثة {_CAT_AR[m.group(1)]} سابقة في {m.group(2)}"),
    (r"^Historical (water|lighting|change|distortion|land_use) case$", lambda m: f"حالة {_CAT_AR[m.group(1)]} سابقة"),
    (r"^Historical work order\.$", "أمر عمل سابق."), (r"^Historical seeded verification\.$", "تحقق سابق مُدرج مسبقًا."),
    (r"^Historical \(seeded\)$", "سجل تاريخي (مُدرج مسبقًا)"),
    # ---- trail
    (r"^Detected: (.+) in (.+)$", r"رصد: \1 في \2"),
    (rf"^Compared the two satellite dates and found (.+?) of about {N} m² in (.+)$", r"قارن بين تاريخَي التصوير ووجد \1 بمساحة نحو \2 م² في \3"),
    (rf"^Opened (\S+) - (P\d) / (\w+), team (.+)$", lambda m: f"فتح {m.group(1)} - {m.group(2)} / {TERMS.get(m.group(3), m.group(3))}، الفريق: {m.group(4)}"),
    (rf"^{N} citizen report\(s\) nearby back this up$", r"\1 بلاغ(ات) من المواطنين قريبة تدعم ذلك"),
    (rf"^{N} citizen reports clustered in (.+) with no sensor alarm$", r"\1 بلاغات مواطنين مجمّعة في \2 دون إنذار من الحسّاسات"),
    (r"^Prepared a work order \((\S+)\) and is waiting for your approval$", r"أعدّ أمر عمل (\1) وينتظر موافقتك"),
    (r"^No dispatch needed yet - kept on watch$", "لا حاجة لتكليف الآن - تحت المراقبة"),
    (r"^Escalated to executive level$", "صُعّد إلى المستوى التنفيذي"),
    (rf"^Ranked field crews by skill, distance and workload - (.+) wins \({N}\)$", r"رتّب الفرق الميدانية حسب المهارة والمسافة وحجم العمل - فاز \1 (\2)"),
    (r"^(.+) reported from site: ", r"أبلغ \1 من الموقع: "),
    (r"^Compared the field report with the AI prediction and updated the model calibration$", "قارن التقرير الميداني بتوقع الذكاء الاصطناعي وحدّث معايرة النموذج"),
    (r"^Field evidence is in - closure prepared for your approval$", "وصلت الأدلة الميدانية - الإغلاق جاهز لموافقتك"),
    (r"^(.+) confirmed the assignment for (\S+)$", r"أكّد \1 التكليف لأمر العمل \2"),
    (r"^(.+) marked (\S+) completed in ArcGIS Field Maps$", r"وضع \1 علامة الإكمال على \2 في ArcGIS Field Maps"),
    (r"^Inspection requested by the operator - work order (\S+) prepared for approval$", r"طلب المشغّل فحصًا - أمر العمل \1 جاهز للموافقة"),
    # ---- alert titles and messages
    (r"^Dispatch (.+) to (\S+)$", r"تكليف \1 إلى \2"),
    (r"^(.+) \((.+)\) is the best fit: ", r"\1 (\2) هو الأنسب: "),
    (r"skill match=(yes|partial|no)", lambda m: "تطابق المهارة=" + {"yes": "نعم", "partial": "جزئي", "no": "لا"}[m.group(1)]),
    (rf"([\d.]+) km away, {N} open task\(s\)", r"يبعد \1 كم، \2 مهمة مفتوحة"),
    (r"^Executive brief$", "موجز تنفيذي"),
    (rf"^{N} new incident\(s\); {N} open, {N} critical; {N} decision\(s\) waiting for you\.$", r"\1 حادثة جديدة؛ \2 مفتوحة، \3 حرجة؛ \4 قرار ينتظرك."),
    (r"^Urban change: (.+) - (.+)$", r"تغيّر عمراني: \1 - \2"),
    (r"^Fault confirmed on site - ", "تأكد العطل في الموقع - "), (r"^Repair completed - ", "اكتمل الإصلاح - "), (r"^False alarm - nothing found - ", "إنذار كاذب - لم يُعثر على شيء - "),
    (r"^Investigator needs a further inspection - ", "المحقق يحتاج إلى فحص إضافي - "), (r"^Investigator escalated the incident - ", "المحقق صعّد الحادثة - "), (r"^Field update - ", "تحديث ميداني - "),
    (r"^(.+) on (INC-\d+): ", r"\1 بشأن \2: "),
    (r"^Ready to close (\S+)$", r"\1 جاهزة للإغلاق"),
    (r"^(.+) accepted (\S+)$", r"قبِل \1 المهمة \2"),
    (r"^(.+) \((.+)\) confirmed the assignment and is heading to (.+)\. The report will appear here when it is sent\.$", r"أكّد \1 (\2) التكليف وهو في طريقه إلى \3. سيظهر التقرير هنا عند إرساله."),
    (r"^(.+) finished (\S+) in Field Maps$", r"أنهى \1 المهمة \2 في Field Maps"),
    (r"^(.+) marked work order (\S+) \((.+), (.+)\) as completed\. ", r"وضع \1 علامة الإكمال على أمر العمل \2 (\3، \4). "),
    (r"Their report is being assessed\.", "يجري تقييم تقريره."),
    (r"No report has been filed yet; ask them to submit one so it can be verified\.", "لم يُقدَّم تقرير بعد؛ اطلب منه تقديم تقرير ليتم التحقق."),
    (r"^More residents report (\S+)$", r"مزيد من السكان يبلغون عن \1"),
    (rf"^(.+) in (.+): {N} residents are now reporting the same problem, which raises confidence in the finding\.$", r"\1 في \2: \3 من السكان يبلغون الآن عن المشكلة نفسها، مما يرفع الثقة بالرصد."),
    # ---- approvals
    (rf"^Create (P\d) work order for (\S+) \((.+), (.+)\)$", r"إنشاء أمر عمل \1 للحادثة \2 (\3، \4)"),
    (rf"^Work order created in the system of record; incident moves to '(.+)'; due in {N} h\.(?= |$)", r"يُنشأ أمر العمل في السجل المرجعي؛ تنتقل الحادثة إلى '\1'؛ الاستحقاق خلال \2 ساعة."),
    (r"^Assign (.+) \((.+)\) to (\S+) for (\S+)$", r"تكليف \1 (\2) بأمر العمل \3 للحادثة \4"),
    (r"^Field task appears in (.+)'s portal; incident status becomes Assigned\.$", r"تظهر المهمة الميدانية في بوابة \1؛ وتصبح حالة الحادثة 'مُكلَّفة'."),
    (r"^Close incident (\S+) as '(.+)'$", r"إغلاق الحادثة \1 بحالة '\2'"),
    (r"^Incident status becomes '(.+)'\.$", r"تصبح حالة الحادثة '\1'."),
    (r"^Set (\S+) to '(.+)'$", r"ضبط \1 على '\2'"),
    (r"^Operational asset status changes in the system of record\.$", "تتغيّر حالة الأصل التشغيلي في السجل المرجعي."),
    (r"'Resolved'", "'تم الحل'"), (r"'Assigned'", "'مُكلَّفة'"),
    # ---- incident descriptions (evidence of the four use cases)
    (r"SUSPECTED leak \(not confirmed\)\.", "تسرّب مشتبه به (غير مؤكد)."),
    (rf"Pressure on (\S+) fell {N}% vs the same hours yesterday", r"انخفض الضغط عند \1 بنسبة \2٪ مقارنة بنفس الساعات أمس"),
    (rf"\({N}->{N} kPa, z=([-\d.]+)\)", r"(\1←\2 كيلوباسكال، z=\3)"),
    (rf"flow changed {SN}%", r"تغيّر التدفق بنسبة \1٪"),
    (rf"{N} adjacent sensor\(s\) show a milder drop\.", r"\1 حسّاس(ات) مجاورة تُظهر انخفاضًا أخفّ."),
    (r"Pattern is consistent with a leak but also with valve operation or a pump transient; field verification is required before treating it as a confirmed leak\.",
     "النمط يتوافق مع تسرّب لكنه يتوافق أيضًا مع تشغيل صمام أو اضطراب مؤقت في المضخة؛ يلزم التحقق الميداني قبل اعتباره تسرّبًا مؤكدًا."),
    (rf"PREDICTED failure \(not a confirmed fault\): estimated probability {N}%\.", r"عطل متوقع (وليس عطلًا مؤكدًا): الاحتمال المقدّر \1٪."),
    (rf"Drivers: power drift {SN}%, {N} flicker events/30d, {N}% comms loss, {N} fault\(s\) in 12 months, {N} days since maintenance\.",
     r"العوامل: انحراف الطاقة \1٪، \2 وميض/30 يومًا، \3٪ فقدان اتصال، \4 عطل(أعطال) في 12 شهرًا، \5 يومًا منذ آخر صيانة."),
    (r"Preventive inspection recommended\.", "يُوصى بفحص وقائي."),
    (rf"POLE: (.+?), age {N} y\.", r"عمود: \1، العمر \2 سنة."),
    (rf"tilt {N}° \(limit {N}°\)", r"ميلان \1° (الحد \2°)"),
    (r"(none|low|moderate|severe) base corrosion", lambda m: {"none": "لا تآكل", "low": "تآكل خفيف", "moderate": "تآكل متوسط", "severe": "تآكل شديد"}[m.group(1)] + " في القاعدة"),
    (r"PREDICTED structural risk \(not a confirmed failure\); the pole could fall onto the carriageway if not inspected\.",
     "خطر إنشائي متوقع (وليس عطلًا مؤكدًا)؛ قد يسقط العمود على الطريق إن لم يُفحص."),
    (rf"^{N} streetlight poles on (.+?) exceed the tilt/corrosion limits \(cluster (\S+?)\)\. PREDICTED structural risk, not confirmed\.$",
     r"\1 عمود إنارة على \2 تتجاوز حدود الميلان/التآكل (المجموعة \3). خطر إنشائي متوقع وغير مؤكد."),
    (rf"^{N} streetlights on (.+?) with elevated predicted failure probability \(cluster (\S+?)\)\. PREDICTED, not confirmed\.$",
     r"\1 مصباح إنارة على \2 باحتمال عطل متوقع مرتفع (المجموعة \3). متوقع وغير مؤكد."),
    (rf"CANDIDATE \(SIMULATED imagery, (.+?) -> (.+?)\): (.+?); edge-warp index ([\d.]+) vs area norm ([\d.]+)±([\d.]+) \(z=([-\d.]+)\)\.",
     r"مرشّح (صور محاكاة، \1 ← \2): \3؛ مؤشر التواء الحواف \4 مقابل معيار المنطقة \5±\6 (z=\7)."),
    (rf"It stands {N} m from a (.+?) \((.+?)\)\.", r"يبعد \1 م عن \2 (\3)."),
    (r"Needs a structural survey\.", "يحتاج إلى مسح إنشائي."),
    (rf"CANDIDATE: (.+?) covering about {N} m² between (.+?) and (.+?) \(simulated imagery\)\. Not confirmed; needs field verification\.",
     r"مرشّح: \1 بمساحة نحو \2 م² بين \3 و\4 (صور محاكاة). غير مؤكد؛ يحتاج إلى تحقق ميداني."),
    (r"CRITICAL because ", "حرج لأن "),
    (rf"CANDIDATE: (.+?) of about {N} m² appeared between the two satellite dates\.", r"مرشّح: \1 بمساحة نحو \2 م² ظهرت بين تاريخَي التصوير."),
    (r"Needs a site inspection before enforcement\.", "يحتاج إلى معاينة موقعية قبل الإنفاذ."),
    (r"(.+?) is NOT permitted in the (.+?) zone", r"\1 غير مسموح به في نطاق \2"),
    (r"\(permitted: none\)", "(المسموح: لا شيء)"), (r"\(permitted: (.+?)\)", lambda m: "(المسموح: " + m.group(1).replace(", ", "، ") + ")"),
    (r"(.+?) is permitted in the (.+?) zone", r"\1 مسموح به في نطاق \2"),

    (r"(.+?) is not a permanent use; kept on watch", r"\1 ليس استخدامًا دائمًا؛ تحت المراقبة"),
    # ---- field assessment (AI vs investigator)
    (r"AI predicted: ", "توقّع الذكاء الاصطناعي: "), (r"; Field observed: ", ". ما رصده المحقق: "), (r"Field observed: ", "ما رصده المحقق: "),
    (rf"\(risk {N}, confidence {N}\)", r"(الخطورة \1، الثقة \2)"),
    (rf"Distance to detection {N} m\.", r"المسافة إلى نقطة الرصد \1 م."),
    (r"Agent assessment: ", "تقييم الوكيل: "),
    (rf"GPS fix was {N} m from the detection \(tolerance {N} m\): evidence is weak, further inspection required\.", r"كان تحديد الموقع على بعد \1 م من نقطة الرصد (التسامح \2 م): الدليل ضعيف ويلزم فحص إضافي."),
    (r"Worker reports the fault repaired; incident closure requires operator approval\.", "أفاد العامل بإصلاح العطل؛ يتطلب إغلاق الحادثة موافقة المشغّل."),
    (r"\bConfirmed\b(?= \.| ?$)", "مؤكد"), (r"\bRejected\b(?= \.| ?$)", "مرفوض"), (r"\bEscalated\b(?= \.| ?$)", "مصعَّد"),
    # ---- work-order instructions
    (r"^Locate the suspected leak near the marked point, check for surface water / valve transients, photograph evidence, record GPS and confirm or reject\.$",
     "حدّد موقع التسرّب المشتبه به قرب النقطة المعلَّمة، وافحص وجود مياه سطحية أو اضطرابات صمامات، وصوّر الأدلة، وسجّل الموقع، ثم أكّد الرصد أو ارفضه."),
    (r"^Inspect the listed lamps for flicker, driver or cable damage, photograph evidence, record GPS and confirm or reject the predicted failure\.$",
     "افحص المصابيح المدرجة بحثًا عن الوميض أو تلف المشغّل أو الكابلات، وصوّر الأدلة، وسجّل الموقع، ثم أكّد العطل المتوقع أو ارفضه."),
    (r"^Visit the polygon, determine whether construction/clearing is present or only seasonal change, photograph evidence and confirm or reject\.$",
     "زر المنطقة المحددة، وتحقق هل توجد إنشاءات/إزالة أم مجرد تغيّر موسمي، وصوّر الأدلة، ثم أكّد الرصد أو ارفضه."),
    (r"^Inspect the flagged building from street level, photograph cracks, bulging or leaning, record GPS and confirm or reject the structural distortion\.$",
     "افحص المبنى المحدد من مستوى الشارع، وصوّر الشقوق أو الانتفاخ أو الميلان، وسجّل الموقع، ثم أكّد التشوّه الإنشائي أو ارفضه."),
    (r"^Inspect the listed poles: measure tilt with an inclinometer, check base corrosion and anchor bolts, photograph evidence and confirm or reject the structural risk\.$",
     "افحص الأعمدة المدرجة: قِس الميلان بمقياس الميل، وتحقق من تآكل القاعدة وبراغي التثبيت، وصوّر الأدلة، ثم أكّد الخطر الإنشائي أو ارفضه."),
    (r"^Visit the polygon, confirm what is being built, check the permit against the zoning, photograph evidence and confirm or reject the violation\.$",
     "زر المنطقة المحددة، وتأكد مما يُبنى، وقارن التصريح بأنظمة التقسيم، وصوّر الأدلة، ثم أكّد المخالفة أو ارفضها."),
    (r"^Inspect the location and confirm or reject the AI finding\.$", "افحص الموقع ثم أكّد رصد الذكاء الاصطناعي أو ارفضه."),
    # ---- executive recommendations
    (r"^Approve a work order and dispatch the nearest qualified team$", "وافق على أمر عمل وكلّف أقرب فريق مؤهل"),
    (r"^Assign a field worker$", "كلّف مُحققًا ميدانيًا"), (r"^Field inspection is pending - monitor$", "الفحص الميداني قيد الانتظار - تابع"),
    (r"^Fault confirmed - track repair, then close$", "تأكد العطل - تابع الإصلاح ثم أغلق"), (r"^Approve closure after repair report$", "وافق على الإغلاق بعد تقرير الإصلاح"),
    (r"^Close as false positive$", "أغلق كإنذار كاذب"), (r"^Schedule a follow-up inspection$", "حدّد موعد فحص متابعة"), (r"^Escalate to duty manager$", "صعّد إلى مدير المناوبة"), (r"^Review$", "مراجعة"),
    # ---- feeds
    (rf"^{N} sensors · hourly$", r"\1 حسّاس · كل ساعة"), (rf"^{N} lamps · telemetry, tilt & corrosion$", r"\1 مصباح · قياسات عن بُعد وميلان وتآكل"),
    # ---- field maps task text headings (when a whole task text is translated)
    (r"^Work order: ", "أمر العمل: "), (r"^Incident: ", "الحادثة: "), (r"WHAT THE AI FOUND \(not confirmed\): ", "ما وجده الذكاء الاصطناعي (غير مؤكد): "),
    (r"YOUR TASK: ", "مهمتك: "), (r"HOW TO ANSWER: ", "كيف تجيب: "),
]
RULES += [(rf"^{re.escape(_v['instr'])}$", _v["instr_ar"]) for _v in _vt.VISUAL_TYPES.values()]
RULES += [
    (rf"CANDIDATE \(SIMULATED imagery, (.+?) -> (.+?)\): (.+?) - (.+?); visual-distortion score ([\d.]+) vs area norm ([\d.]+)±([\d.]+) \(z=([-\d.]+)\)\.",
     r"مرشّح (صور محاكاة، \1 ← \2): \3 - \4؛ درجة التشوّه البصري \5 مقابل معيار المنطقة \6±\7 (z=\8)."),
    (r"Needs a field inspection and, if confirmed, a notice to the owner\.", "يحتاج إلى معاينة ميدانية، وإن تأكد الرصد فيُوجَّه إشعار إلى المالك."),
    (r"scenario: temporary hoarding, scaffolding or shadow mistaken for a visual problem \(false positive\)", "سيناريو: سياج مؤقت أو سقالات أو ظل التُبس بمشكلة بصرية (إنذار كاذب)"),
]
# what the SIMULATED field crew writes after a visit (so an Arabic page does not show these English sentences)
_SIM_OBS = {
    "[SIMULATED WORKER] ": "[عامل محاكى] ",
    "Fault repaired and tested; area made safe.": "تم إصلاح العطل واختباره؛ والمنطقة آمنة.",
    "Visible water seepage and wet asphalt at the indicated location; pipe fitting corroded. Leak confirmed.": "تسرّب مياه ظاهر وأسفلت مبتل في الموقع المحدد؛ وصلة الأنبوب متآكلة. تأكد التسرّب.",
    "Lamp driver failing: intermittent flicker and heat damage observed. Fault confirmed on site.": "مشغّل المصباح يتعطل: وميض متقطع وتلف حراري. تأكد العطل في الموقع.",
    "New construction site with fencing and early foundations observed.": "موقع إنشاءات جديد بسياج وأساسات أولية.",
    "Visible diagonal cracks and a bulging wall section confirmed from street level; structural engineer requested.": "شقوق قطرية ظاهرة وانتفاخ في جزء من الجدار من مستوى الشارع؛ طُلب مهندس إنشائي.",
    "Pole base heavily corroded and leaning toward the carriageway; anchor bolts loose. Structural risk confirmed.": "قاعدة العمود متآكلة بشدة ويميل نحو الطريق؛ وبراغي التثبيت مرتخية. تأكد الخطر الإنشائي.",
    "Active construction with site hoarding and no permit displayed; building is not allowed in this zone. Violation confirmed.": "أعمال بناء جارية بسياج موقع ودون تصريح ظاهر؛ والبناء غير مسموح في هذا النطاق. تأكدت المخالفة.",
    "No visible leak, dry surface; pressure transient from nearby valve operation likely. Finding not reproduced.": "لا تسرّب ظاهر والسطح جاف؛ وغالبًا اضطراب ضغط من تشغيل صمام قريب. لم يتكرر الرصد.",
    "Lamps operate normally; no flicker or heat damage found.": "المصابيح تعمل بشكل طبيعي؛ لا وميض ولا تلف حراري.",
    "Seasonal vegetation change only; no construction present.": "تغيّر نباتي موسمي فقط؛ لا توجد إنشاءات.",
    "Building is sound: the apparent distortion was scaffolding and shadow in the imagery. No cracks or deformation.": "المبنى سليم: التشوّه الظاهر كان سقالات وظلًّا في الصورة. لا شقوق ولا تشوّه.",
    "Pole is plumb and the base is sound; the inclinometer reading was drift. No action needed.": "العمود مستقيم وقاعدته سليمة؛ وقراءة مقياس الميل كانت انحرافًا. لا إجراء مطلوب.",
    "Structure is a permitted temporary works area; no violation found.": "الموقع منطقة أعمال مؤقتة مسموحة؛ لا مخالفة.",
}
RULES += [(re.escape(k), v) for k, v in _SIM_OBS.items()]
RULES += [
    (r"(.+?) confirmed from street level: (.+?)\. Photographed and noted for the notice to the owner\.", r"تأكد وجود \1 من مستوى الشارع: \2. تم التصوير والتسجيل لإشعار المالك."),
    (r"Nothing found on site: the apparent (.+?) was temporary hoarding or a shadow in the imagery\.", r"لم يُعثر على شيء في الموقع: كان \1 الظاهر سياجًا مؤقتًا أو ظلًّا في الصورة."),
]
RULES += _mob.RULES
_COMPILED = [(re.compile(p, re.S), r) for p, r in RULES]
# a road that is not in the vocabulary keeps its name; the word "Road" or "Street" goes before it, as it is written in Arabic
_ROAD_RE = re.compile(r"(?<![\w-])((?:[A-Z][\w'’.-]*)(?: [A-Z][\w'’.-]*){0,2}) (Road|Street)(?![\w])(?! [A-Z])")
_ROAD_WORD = {"Road": "طريق", "Street": "شارع"}


def _road(m):
    return m.group(0) if m.group(0) in TERMS else f"{_ROAD_WORD[m.group(2)]} {m.group(1)}"

HOW_TO_ANSWER_AR = ("اختر إجابتك (نعم، مؤكد / لم يتم العثور / أحتاج إلى معاينة أخرى / تصعيد)، واكتب ما رأيته في التعليق، ثم اضغط إنهاء. "
                    "وإن لم يظهر سوى حقل الملاحظات فابدأ الملاحظة بإحدى العبارات: تم التأكيد، لم يتم العثور، أحتاج إلى معاينة أخرى، تصعيد.")

# the choices on the Field Maps task form: code -> (English label, Arabic label, hint). Same wording as the in-app investigator form.
VERDICT_CHOICES = [
    ("Confirmed", "Yes, confirmed", "نعم، مؤكد", "The fault or change is there"),
    ("Rejected", "Not found", "لم يتم العثور", "Nothing wrong at this location"),
    ("Needs Further Inspection", "Need to look again", "أحتاج إلى معاينة أخرى", "Could not decide on this visit"),
    ("Escalate", "Escalate", "تصعيد", "Dangerous or too large for me"),
    ("Repaired", "Repaired", "تم الإصلاح", "The fault is fixed and the area is safe"),
]


def verdict_label(code: str, lang: str = "en") -> str:
    for c, en, ar, _ in VERDICT_CHOICES:
        if c == code:
            return ar if lang == "ar" else f"{en} / {ar}" if lang == "both" else en
    return code

# Arabic verdict openers accepted in a Field Maps note (the first words decide the verdict; see Platform._report_from_finished_task)
AR_VERDICTS = {"تم التأكيد": "Confirmed", "تأكيد": "Confirmed", "تأكد": "Confirmed", "نعم": "Confirmed", "مؤكد": "Confirmed", "أكدت": "Confirmed",
               "لم يتم العثور": "Rejected", "لم أجد": "Rejected", "لا يوجد خلل": "Rejected", "لا شيء": "Rejected", "مرفوض": "Rejected",
               "أحتاج إلى معاينة أخرى": "Needs Further Inspection", "أحتاج معاينة أخرى": "Needs Further Inspection", "يحتاج معاينة": "Needs Further Inspection",
               "تم الإصلاح": "Repaired", "إصلاح": "Repaired", "تصعيد": "Escalate", "صعّد": "Escalate", "أصعّد": "Escalate"}


def verdict_from_note(notes: str) -> str | None:
    """Verdict for an Arabic opener in a note, or None. Longest opener wins."""
    t = (notes or "").strip()
    for k in sorted(AR_VERDICTS, key=len, reverse=True):
        if t.startswith(k):
            return AR_VERDICTS[k]
    return None


def _terms(text: str) -> str:
    return _TERM_RE.sub(lambda m: TERMS[m.group(0)], text)


def to_ar(text: str, terms_only: bool = False) -> str:
    """Arabic for a backend-written string. `terms_only` translates a whole value that is a known term (names, types) and nothing else."""
    if not isinstance(text, str) or not text:
        return text
    if terms_only:
        return TERMS.get(text, text) if text not in _SEV_ONLY else text
    out = text
    for rx, rep in _COMPILED:
        out = rx.sub(rep, out)
    out = _ROAD_RE.sub(_road, out)
    # keep "High/Low ..." words out of sentences; translate the rest of the vocabulary
    out = _TERM_RE.sub(lambda m: m.group(0) if m.group(0) in _SEV_ONLY else TERMS[m.group(0)], out)
    # ids such as SEN-W-001 or INC-0042 are isolated so the hyphens do not reorder them inside right-to-left text
    return _ID_RE.sub(lambda m: "⁦" + m.group(0) + "⁩", out) if _ARABIC_RE.search(out) else out


# keys whose string values are sentences written by the backend, and keys that hold names or types
FREE_KEYS = {"detail", "error", "Title", "Message", "did", "action", "detail", "last_action", "summary", "Summary", "expected", "Expected_Result", "Description", "Evidence", "evidence",
             "assessment", "Agent_Assessment", "instructions", "Instructions", "recommended_action", "rationale", "why", "why_suspicious", "message", "Notes", "reply", "finding",
             "rule_text", "note", "explanation"}
TERM_KEYS = {"name", "Name", "role", "focus", "team", "Team", "Assigned_Team", "Incident_Type", "Detection_Type", "type", "Change_Type", "Task_Type", "Facility_Type", "Worker_Name",
             "Assigned_Worker_Name", "Investigator_Name", "worker", "Location", "land_use", "Land_Use_Category", "zone", "kind"}


def localize(obj, lang: str = "ar"):
    """Deep copy of a JSON value with its backend-written text translated. English (or unknown) returns the value untouched."""
    if pick(lang) != "ar":
        return obj

    def walk(v, key=None):
        if isinstance(v, dict):
            return {k: walk(x, k) for k, x in v.items()}
        if isinstance(v, list):
            return [walk(x, key) for x in v]
        if isinstance(v, str):
            if key in FREE_KEYS:
                return to_ar(v)
            if key in TERM_KEYS:
                return to_ar(v, terms_only=True)
        return v

    return walk(obj)


# ---------------------------------------------------------------------------------------------------- Field Maps text
def field_lang(setting: str | None) -> str:
    """GEOAI_FIELD_LANG: 'en' (default), 'ar' or 'both' (Arabic first, then English) for the task text on investigators' phones."""
    v = (setting or "en").strip().lower()
    return v if v in ("en", "ar", "both") else "en"
