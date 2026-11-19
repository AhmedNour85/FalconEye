"""Arabic for the mobility crew (Plan 3): names, roles, types, and one rule for every sentence the crew writes about roads, closures and events.

Pure data, read by backend/services/i18n.py. The English sentences live in backend/mobility/wording.py, backend/mobility/road_impact.py,
backend/mobility/strategies.py, backend/tools/mobility.py and backend/orchestration/crew.py: a sentence changed there needs its rule changed here
(tests/test_i18n.py walks all three mobility events and fails on any English that is left).
Road names that are not listed stay in English (they are proper names from OpenStreetMap); the word "Road" or "Street" is put before the name.
"""
from __future__ import annotations

N = r"([\d,]+(?:\.\d+)?)"
SN = r"([+-]?[\d,]+(?:\.\d+)?)"
X = r"(.+?)"
PFX = r"Road impact \(modelled\): "
PFX_AR = "أثر الطريق (نمذجة): "
WINDOW = {"day": "النهار", "night": "الليل"}

TERMS = {
    "King Fahad Medical City": "مدينة الملك فهد الطبية", "DQ": "الحي الدبلوماسي",
    "King Khalid University Hospital": "مستشفى الملك خالد الجامعي", "King Faisal Specialist Hospital": "مستشفى الملك فيصل التخصصي", "Security Forces Hospital": "مستشفى قوى الأمن",
    "Dr. Sulaiman Al Habib Hospital (Olaya)": "مستشفى الدكتور سليمان الحبيب (العليا)", "King Abdulaziz Medical City": "مدينة الملك عبدالعزيز الطبية",
    "Imam Abdulrahman Al Faisal Hospital (East)": "مستشفى الإمام عبدالرحمن الفيصل (الشرق)", "Northern Riyadh Hospital (sample)": "مستشفى شمال الرياض (نموذج)",
    "Civil Defense HQ (sample)": "مقر الدفاع المدني (نموذج)", "Civil Defense Station North (sample)": "محطة الدفاع المدني الشمالية (نموذج)",
    "Civil Defense Station East (sample)": "محطة الدفاع المدني الشرقية (نموذج)", "Red Crescent Dispatch Centre (sample)": "مركز إسعاف الهلال الأحمر (نموذج)",
    "Red Crescent Station South (sample)": "محطة الهلال الأحمر الجنوبية (نموذج)",

    "Al Nakheel": "النخيل", "Nakheel": "النخيل", "Al Narjis": "النرجس", "Narjis": "النرجس", "Al Wurud": "الورود", "Wurud": "الورود", "Al Yasmin": "الياسمين", "Yasmin": "الياسمين",
    "Malaz": "الملز", "KAHC": "المدينة الطبية بالملك عبدالله", "KAPark": "حديقة الملك عبدالله", "KKIA": "مطار الملك خالد الدولي", "KSU": "جامعة الملك سعود",
    "King Khalid International Airport": "مطار الملك خالد الدولي", "RiyadhFront": "واجهة الرياض", "King Abdullah Financial District (KAFD)": "المركز المالي (كافد)",

    # the three agents, their roles and what they do
    "Nasser": "ناصر", "Noura": "نورة", "Fahad": "فهد",
    "Traffic GeoCoworker": "زميل جيومكاني للمرور", "Mobility Simulation GeoCoworker": "زميل جيومكاني لمحاكاة التنقل",
    "Road Safety & Assets GeoCoworker": "زميل جيومكاني لسلامة الطرق والأصول",
    "Watches the traffic state and road incidents": "يراقب حالة المرور وحوادث الطرق",
    "Simulates closures and events, compares response strategies, checks hospital access": "يحاكي الإغلاقات والفعاليات، ويقارن استراتيجيات الاستجابة، ويفحص الوصول إلى المستشفيات",
    "Adds accident history and road-asset condition, ranks maintenance priority": "يضيف سجل الحوادث وحالة أصول الطرق، ويرتّب أولوية الصيانة",
    # team and investigators
    "Traffic Response": "الاستجابة المرورية", "Bandar Al-Shehri": "بندر الشهري", "Rayan Al-Anazi": "ريان العنزي",
    # incident, detection and task types
    "Traffic Incident": "حادثة مرورية", "Planned Road Closure": "إغلاق طريق مخطط", "Major Event Traffic Plan": "خطة مرورية لفعالية كبرى",
    "Road Closure Request": "طلب إغلاق طريق", "Major Event": "فعالية كبرى",
    "Confirm the road is clear": "تأكيد خلو الطريق", "Confirm the closure is in place": "تأكيد تنفيذ الإغلاق", "Confirm the traffic plan is in place": "تأكيد تنفيذ الخطة المرورية",
    "Crash": "حادث تصادم",
    # feeds
    "Traffic & road reports": "المرور وبلاغات الطرق", "Closures & events": "الإغلاقات والفعاليات",
    # closure reasons (as written in a closure request, and as stored)
    "Resurfacing works": "أعمال إعادة السفلتة", "resurfacing works": "أعمال إعادة السفلتة",
    "Bridge joint replacement": "استبدال فواصل الجسر", "bridge joint replacement": "استبدال فواصل الجسر",
    "Utility crossing under the carriageway": "عبور خدمات تحت الطريق", "utility crossing under the carriageway": "عبور خدمات تحت الطريق",
    "Drainage repair": "إصلاح تصريف المياه", "drainage repair": "إصلاح تصريف المياه", "road works": "أعمال طرق", "Water leak repair": "إصلاح تسرّب مياه",
    # events and venues
    "Riyadh Season concert": "حفل موسم الرياض", "National festival evening": "أمسية المهرجان الوطني", "Football final screening": "عرض نهائي كرة القدم",
    "Heritage night": "ليلة التراث", "Graduation ceremony": "حفل التخرج", "An event": "فعالية",
    "King Fahd International Stadium": "استاد الملك فهد الدولي",
    "King Abdullah Park": "حديقة الملك عبدالله", "Riyadh Front": "واجهة الرياض", "King Abdulaziz Historical Center": "مركز الملك عبدالعزيز التاريخي",
    "King Saud University": "جامعة الملك سعود",
    # roads the demo uses
    "King Fahd Road": "طريق الملك فهد", "Olaya Street": "شارع العليا", "Airport Road": "طريق المطار", "Makkah Road": "طريق مكة المكرمة",
    "Northern Ring Road": "الطريق الدائري الشمالي", "Eastern Ring Road": "الطريق الدائري الشرقي", "Southern Ring Road": "الطريق الدائري الجنوبي",
    "Western Ring Road": "الطريق الدائري الغربي", "Takhassusi Street": "شارع التخصصي", "Al Malaz main roads": "الطرق الرئيسية في الملز", "KAFD main roads": "الطرق الرئيسية في كافد",
    # response strategies
    "Do nothing": "عدم اتخاذ إجراء",
    "Combined: diversion plan + demand shift": "مزيج: خطة تحويل المسار وخفض الطلب",
}

CAT_AR = "مرور وتنقّل"


ACTION = {"reconstruction": "إعادة إنشاء", "rehabilitation": "تأهيل", "preventive": "صيانة وقائية", "monitor": "مراقبة", "unknown": "غير معروف"}


RULES: list = [
    # ---- alert and trail sentences about a simulation's result (backend/mobility/wording.py, road_impact.py)
    (rf"{PFX}{N} lane\(s\) blocked on {X} for about {N} hours adds {N} trip-hours and {N} min to the worst hospital access; {N} road sections become severe\.",
     PFX_AR + r"إغلاق \1 حارة في \2 لمدة نحو \3 ساعة يضيف \4 ساعة-رحلة و\5 دقيقة إلى أسوأ وصول للمستشفيات؛ ويصبح \6 مقطع طريق شديد الازدحام."),
    (rf"{PFX}{X} blocked for about {N} hours adds {N} trip-hours and {N} min to the worst hospital access; {N} road sections become severe\.",
     PFX_AR + r"\1 مغلق لمدة نحو \2 ساعة يضيف \3 ساعة-رحلة و\4 دقيقة إلى أسوأ وصول للمستشفيات؛ ويصبح \5 مقطع طريق شديد الازدحام."),
    (rf"{PFX}{N} people at {X} add {N} vehicles per hour at the peak and {N} trip-hours; parking is short by {N} vehicles\.",
     PFX_AR + r"\1 شخص في \2 يضيفون \3 مركبة في الساعة عند الذروة و\4 ساعة-رحلة؛ والعجز في المواقف \5 مركبة."),
    (rf"{PFX}closing {X} (\d\d:\d\d) to (\d\d:\d\d) adds {N} trip-hours\. Recommended response: no extra measures\.",
     PFX_AR + r"إغلاق \1 من \2 إلى \3 يضيف \4 ساعة-رحلة. الاستجابة الموصى بها: لا إجراءات إضافية."),
    (rf"{PFX}closing {X} (\d\d:\d\d) to (\d\d:\d\d) adds {N} trip-hours\. Recommended response: {X} \({N}% less delay\)\.",
     PFX_AR + r"إغلاق \1 من \2 إلى \3 يضيف \4 ساعة-رحلة. الاستجابة الموصى بها: \5 (تأخير أقل بنسبة \6%)."),
    (rf"{PFX}closing {X} (\d\d:\d\d) to (\d\d:\d\d) adds {N} trip-hours and {N} min to the worst hospital access; at night {N} trip-hours and {N} min\. Recommended: (day|night)\.",
     lambda m: f"{PFX_AR}إغلاق {m.group(1)} من {m.group(2)} إلى {m.group(3)} يضيف {m.group(4)} ساعة-رحلة و{m.group(5)} دقيقة إلى أسوأ وصول للمستشفيات؛ "
               f"وفي الليل {m.group(6)} ساعة-رحلة و{m.group(7)} دقيقة. الموصى به: {WINDOW[m.group(8)]}."),
    (rf"{PFX}small in both windows \(day {N}, night {N} trip-hours\)\. Recommended: (day|night)\.",
     lambda m: f"{PFX_AR}صغير في الفترتين (النهار {m.group(1)}، الليل {m.group(2)} ساعة-رحلة). الموصى به: {WINDOW[m.group(3)]}."),
    (r"Road impact could not be calculated: ", "تعذّر حساب أثر الطريق: "),
    (r" A field check is proposed instead\.", " اقتُرح فحص ميداني بدلًا من ذلك."),
    (r"The server stopped while this simulation was running\.", "توقف الخادم أثناء تشغيل هذه المحاكاة."),
    (r"Noura is calculating the road impact of the repair", "نورة تحسب أثر الطريق للإصلاح"),
    (r"Noura is calculating the road impact\.", "نورة تحسب أثر الطريق."),
    (r"^Calculating the road impact \(modelled\); the proposed plan follows$", "حساب أثر الطريق (نمذجة)؛ وتأتي الخطة المقترحة بعد ذلك"),
    (r"^The server stopped while the road impact was being calculated; the simulation has been started again$", "توقف الخادم أثناء حساب أثر الطريق؛ وأُعيد تشغيل المحاكاة"),
    # ---- the strategy comparison (backend/mobility/strategies.py)
    (r"Reschedule to off-peak \((\d+):00 start\)", r"إعادة الجدولة إلى خارج أوقات الذروة (البدء الساعة \1:00)"),
    (rf"Diversion plan \+ signal retiming \(\+{N}% capacity on alternatives\)", r"خطة تحويل المسار وإعادة ضبط الإشارات (زيادة السعة بنسبة \1% على المسارات البديلة)"),
    (rf"Demand shift \({SN}% of trips near the closure\)", r"خفض الطلب (\1% من الرحلات قرب الإغلاق)"),
    (rf"Diversion: \+{N}% capacity on up to {N} segments that gained the most traffic in the do-nothing run \(signal retiming/VMS/temporary lanes\)\.",
     r"التحويل: زيادة السعة بنسبة \1% على ما يصل إلى \2 مقطعًا ازدادت حركته أكثر من غيره في سيناريو عدم اتخاذ إجراء (إعادة ضبط الإشارات واللوحات المتغيرة والمسارات المؤقتة)."),
    (rf"Demand shift: {SN}% of trips with an origin or destination within {N} km of the closure\.",
     r"خفض الطلب: \1% من الرحلات التي تبدأ أو تنتهي ضمن \2 كم من الإغلاق."),
    (rf"Reschedule: same duration starting {X}; night demand follows the synthetic hourly profile\.",
     r"إعادة الجدولة: المدة نفسها بدءًا من \1؛ ويتبع الطلب الليلي التوزيع الساعي الافتراضي."),
    (r"The closure's modelled impact is small, so no response strategy changes outcomes materially\. Proceed as planned and monitor\.",
     "أثر الإغلاق المنمذج صغير، فلا تغيّر أي استراتيجية استجابة النتائج جوهريًا. تابع التنفيذ كما هو مخطط وراقب."),
    (rf"Recommended: {X}\. It lowers the weighted impact score from 100 to {N} \({N}% less trip-time lost over the window; worst hospital-access increase {N} -> {N} min\)\.",
     r"الموصى به: \1. يخفض درجة الأثر المرجّحة من 100 إلى \2 (\3% وقت رحلات ضائع أقل خلال الفترة؛ أسوأ زيادة في الوصول للمستشفيات \4 ← \5 دقيقة)."),
    (rf" Note: this strategy assumes {N}% fewer trips network-wide at the peak hour; its benefit depends entirely on that behavioural assumption\.",
     r" ملاحظة: تفترض هذه الاستراتيجية انخفاضًا قدره \1% في الرحلات على مستوى الشبكة عند ساعة الذروة؛ ويعتمد نفعها كليًا على هذا الافتراض السلوكي."),
    (r"No strategy improves the weighted score by at least 2%; the differences are within the model's noise\.",
     "لا تحسّن أي استراتيجية الدرجة المرجّحة بنسبة 2% على الأقل؛ والفروق ضمن هامش خطأ النموذج."),
    # ---- what a road report, a closure request and an event notice say (backend/tools/mobility.py, crew.py)
    (rf"REPORTED: {X} blocking {N} of {N} lane\(s\) on {X} \(road report, SYNTHETIC\)\.", r"مُبلَّغ: \1 يعيق \2 من \3 حارة في \4 (بلاغ طريق، بيانات اصطناعية)."),
    (rf"Modelled load on this section at (\d\d:\d\d) is {N} of capacity; with the lanes blocked about {N} \(abnormal: heavy or worse\)\.",
     r"الحمل المنمذج على هذا المقطع عند \1 هو \2 من الطاقة الاستيعابية؛ ومع إغلاق الحارات نحو \3 (غير طبيعي: شديد الازدحام أو أسوأ)."),
    (rf"Modelled load on this section at (\d\d:\d\d) is {N} of capacity; with the lanes blocked about {N} \(within the normal range\)\.",
     r"الحمل المنمذج على هذا المقطع عند \1 هو \2 من الطاقة الاستيعابية؛ ومع إغلاق الحارات نحو \3 (ضمن النطاق الطبيعي)."),
    (rf"Modelled load on this section at (\d\d:\d\d) is {N} of capacity; every lane is blocked, so the section is closed\.",
     r"الحمل المنمذج على هذا المقطع عند \1 هو \2 من الطاقة الاستيعابية؛ وجميع الحارات مغلقة، فالمقطع مغلق."),
    (r"The modelled load on this section is not known yet \(the traffic model is still being built\)\.", "الحمل المنمذج على هذا المقطع غير معروف بعد (نموذج المرور قيد الإنشاء)."),
    (r" Needs confirmation on site\.", " يحتاج إلى تأكيد في الموقع."),
    (rf"REQUESTED: full closure of {X} \({X}\), (\d{{4}}-\d\d-\d\d \d\d:\d\d) to (\d\d:\d\d), for {X} \(closure request, SYNTHETIC\)\. Needs a traffic plan before it goes ahead\.",
     r"مطلوب: إغلاق كامل لـ\1 (\2)، من \3 إلى \4، بسبب \5 (طلب إغلاق، بيانات اصطناعية). يحتاج إلى خطة مرورية قبل التنفيذ."),
    (rf"REQUESTED: closure of {N} lane\(s\) of {X} \({X}\), (\d{{4}}-\d\d-\d\d \d\d:\d\d) to (\d\d:\d\d), for {X} \(closure request, SYNTHETIC\)\. Needs a traffic plan before it goes ahead\.",
     r"مطلوب: إغلاق \1 حارة من \2 (\3)، من \4 إلى \5، بسبب \6 (طلب إغلاق، بيانات اصطناعية). يحتاج إلى خطة مرورية قبل التنفيذ."),
    (rf"NOTIFIED: {X} at {X}, about {N} people, (\d{{4}}-\d\d-\d\d \d\d:\d\d) to (\d\d:\d\d) \(event notice, SYNTHETIC\)\. Needs a traffic plan\.",
     r"إشعار: \1 في \2، نحو \3 شخص، من \4 إلى \5 (إشعار فعالية، بيانات اصطناعية). يحتاج إلى خطة مرورية."),
    # ---- the trail
    (r"^Road report received: blocked lanes on (.+)$", r"استُلم بلاغ طريق: حارات مغلقة في \1"),
    (r"^Closure request received for (.+)$", r"استُلم طلب إغلاق لـ\1"),
    (r"^Event notice received for (.+)$", r"استُلم إشعار فعالية لـ\1"),
    (rf"Road safety \(SYNTHETIC\): {N} recorded accident\(s\) on this section in the last 12 months, {N} severe; road-asset condition {N} of 100 \({X}\)$",
     lambda m: f"سلامة الطرق (بيانات اصطناعية): {m.group(1)} حادث مسجّل على هذا المقطع خلال آخر 12 شهرًا، منها {m.group(2)} خطير؛ "
               f"حالة أصل الطريق {m.group(3)} من 100 ({ACTION.get(m.group(4), m.group(4))})"),
    (rf"Road safety \(SYNTHETIC\): {N} recorded accident\(s\) on this section in the last 12 months, {N} severe$",
     r"سلامة الطرق (بيانات اصطناعية): \1 حادث مسجّل على هذا المقطع خلال آخر 12 شهرًا، منها \2 خطير"),
    (r"^Prepared the traffic plan \((\S+)\) and is waiting for your approval$", r"أعدّ الخطة المرورية (\1) وهي بانتظار موافقتك"),
    (r"^Prepared a plain field check \((\S+)\) instead and is waiting for your approval$", r"أعدّ فحصًا ميدانيًا بسيطًا (\1) بدلًا من ذلك وهو بانتظار موافقتك"),
    (rf"^Added the planned closure \({X}\) to work order proposal (\S+); one approval covers both$", r"أضاف الإغلاق المخطط (\1) إلى مقترح أمر العمل \2؛ وموافقة واحدة تشمل الاثنين"),
    (r"^For information: the work order was decided before this result arrived, so no planned closure is recorded$",
     "للعلم: صدر القرار في أمر العمل قبل وصول هذه النتيجة، لذا لم يُسجَّل إغلاق مخطط"),
    # ---- crew steps (action | detail)
    (r"^Checked road reports and traffic$", "فحص بلاغات الطرق والمرور"),
    (rf"^{N} new road report\(s\)", r"\1 بلاغ طريق جديد"),
    (r"^no new road reports", "لا بلاغات طرق جديدة"),
    (rf"; {N} road section\(s\) heavy or stopped at (\d\d:\d\d) \(modelled\)$", r"؛ \1 مقطع طريق مزدحم أو متوقف عند \2 (نمذجة)"),
    (r"; no abnormal congestion at (\d\d:\d\d) \(modelled\)$", r"؛ لا ازدحام غير طبيعي عند \1 (نمذجة)"),
    (r"^Read closure requests and event notices$", "قرأ طلبات الإغلاق وإشعارات الفعاليات"),
    (rf"^{N} closure request\(s\), {N} event notice\(s\)$", r"\1 طلب إغلاق، \2 إشعار فعالية"),
    (r"^Added road-safety context$", "أضاف سياق سلامة الطرق"),
    (r"^Simulated the road impact of the repair$", "حاكى أثر الإصلاح على الطريق"),
    (r"^Could not simulate the road impact of the repair$", "تعذّرت محاكاة أثر الإصلاح على الطريق"),
    (r"^Simulated the road impact$", "حاكى أثر الطريق"),
    (r"^Could not simulate the road impact$", "تعذّرت محاكاة أثر الطريق"),
    (r"^Prepared traffic plan$", "أعدّ الخطة المرورية"),
    (r"^Added planned closure to the proposal$", "أضاف الإغلاق المخطط إلى المقترح"),
    (r"^Recorded rejected closure$", "سجّل إغلاقًا مرفوضًا"),
    (rf"^{X}: the plan was rejected, so the closure is not approved$", r"\1: رُفضت الخطة، فلم يُعتمد الإغلاق"),
    # ---- feeds
    (rf"^{N} road report\(s\) · traffic state modelled, not measured$", r"\1 بلاغ طريق · حالة المرور منمذجة وليست مقاسة"),
    (rf"^{N} closure request\(s\) · {N} event notice\(s\)$", r"\1 طلب إغلاق · \2 إشعار فعالية"),
    # ---- proposals (backend/tools/mobility.py propose_traffic_plan, workflows/actions.py)
    (rf"Traffic response for (\S+): send Traffic Response to {X} to confirm and clear the blockage", r"استجابة مرورية لـ\1: إرسال الاستجابة المرورية إلى \2 لتأكيد الانسداد وإزالته"),
    (rf"Closure plan for {X} \((\S+)\): ", r"خطة الإغلاق لـ\1 (\2): "),
    (rf"Event traffic plan for {X} \((\S+)\): approach routes, parking guidance and marshals", r"الخطة المرورية للفعالية في \1 (\2): مسارات الوصول وإرشاد المواقف والمنظّمون"),
    (r"A field-check work order is created and the incident moves to 'Work Order Created'\.", "يُنشأ أمر عمل للفحص الميداني وتنتقل الحادثة إلى «تم إنشاء أمر العمل»."),
    (r"The closure is recorded as Approved with this response, and a field-check work order is created\.", "يُسجَّل الإغلاق «معتمدًا» بهذه الاستجابة ويُنشأ أمر عمل للفحص الميداني."),
    (r"The event notice is recorded as Planned, and a field-check work order is created\.", "يُسجَّل إشعار الفعالية «مخططًا» ويُنشأ أمر عمل للفحص الميداني."),
    (r" The plan is a record: nothing controls signals, signs or dispatch systems\.", " الخطة سجلّ فقط: لا شيء يتحكم بالإشارات أو اللوحات أو أنظمة التكليف."),
    (rf" A planned closure \({X}\) is recorded with it\.", r" يُسجَّل معه إغلاق مخطط (\1)."),
    (rf"Planned closure: {X} \(modelled recommendation: (day|night) window\)\.", lambda m: f"الإغلاق المخطط: {m.group(1)} (توصية النموذج: فترة {WINDOW[m.group(2)]})."),
    (r"Inspect the location and confirm or reject the AI finding\.(?= Planned closure| الإغلاق المخطط)", "افحص الموقع ثم أكّد رصد الذكاء الاصطناعي أو ارفضه."),
    (rf"Go to {X}\. Confirm the reported blockage \({X}\), make the scene safe, direct traffic and report when the road is clear\. Modelled impact if it lasts {N} hours: {N} extra trip-hours\.",
     r"توجّه إلى \1. أكّد الانسداد المبلَّغ عنه (\2)، وأمّن الموقع ووجّه حركة المرور وأبلغ عند خلو الطريق. الأثر المنمذج إن استمر \3 ساعة: \4 ساعة-رحلة إضافية."),
    (rf"Confirm the closure of {X} is set up as approved \({X} to {X}; response: {X}\): signs, barriers and the diversion route in place\. Photograph and report\.",
     r"أكّد أن إغلاق \1 منفَّذ كما اعتُمد (\2 إلى \3؛ الاستجابة: \4): اللوحات والحواجز ومسار التحويل في أماكنها. صوّر وأبلغ."),
    (rf"Confirm the traffic plan for the event at {X} is in place: approach routes signed, parking guidance and marshals\. Modelled peak: {N} added vehicles per hour\. Photograph and report\.",
     r"أكّد تنفيذ الخطة المرورية للفعالية في \1: لوحات مسارات الوصول وإرشاد المواقف والمنظّمون. الذروة المنمذجة: \2 مركبة إضافية في الساعة. صوّر وأبلغ."),
    (rf"(\d+) lane\(s\) blocked", r"\1 حارة مغلقة"),
    (r"road blocked", "الطريق مغلق"),
    # ---- what the simulated crew finds on the road (backend/services/simulation.py MOBILITY_OBS)
    (r"Crashed vehicles blocking the reported lanes; traffic queuing\. Scene made safe\. Blockage confirmed\.",
     "مركبات متصادمة تسدّ الحارات المبلَّغ عنها وحركة المرور تتكدّس خلفها. أُمّن الموقع ووُجّهت حركة المرور. تأكد الانسداد."),
    (r"All lanes are open and traffic is flowing normally; no crash or debris found at the reported point\.", "جميع الحارات مفتوحة وحركة المرور طبيعية؛ لا حادث ولا حطام عند النقطة المبلَّغ عنها."),
    (r"Signs, barriers and the diversion route are in place as approved; the section is closed to traffic\. Closure confirmed\.",
     "اللوحات والحواجز ومسار التحويل في أماكنها كما اعتُمد؛ والمقطع مغلق أمام المرور. تأكد الإغلاق."),
    (r"No closure found on site: no signs or barriers are set up and traffic is using the section\.", "لا إغلاق في الموقع: لا لوحات ولا حواجز والمرور يستخدم المقطع."),
    (r"Approach routes signed, parking guidance up, marshals in position at the venue\. Traffic plan confirmed in place\.",
     "مسارات الوصول موسومة وإرشاد المواقف قائم والمنظّمون في أماكنهم في الموقع. تأكد تنفيذ الخطة المرورية."),
    (r"No traffic plan found on site: no signs, parking guidance or marshals at the venue\.", "لا خطة مرورية في الموقع: لا لوحات ولا إرشاد مواقف ولا منظّمين."),
    (r"Vehicles removed and debris cleared; all lanes are open again and traffic is back to normal\.", "أُزيلت المركبات والحطام؛ وجميع الحارات مفتوحة من جديد وحركة المرور عادت طبيعية."),
    # ---- shared: lanes, windows and unknown road names (applied last)
    (r"\b(\d+) lanes of ", r"\1 حارات من "),
    (r"(\d{4}-\d\d-\d\d) (\d\d:\d\d)(?::\d\d)? to (\d\d:\d\d)", r"\1 \2 إلى \3"),
]
