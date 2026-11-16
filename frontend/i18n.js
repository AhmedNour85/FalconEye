/* English / Arabic for every page. English text is its own key: T("Approve") returns "Approve" in English and "موافقة" in Arabic.
   Pages load this file first (it must run before the ArcGIS script so the map widgets get the same language).
   - static HTML: text nodes and the title / placeholder / aria-label / alt attributes are translated automatically when their exact text is a key below;
   - scripts: use T("text {n}", { n: 3 }) and TV(value) for stored values such as severities and statuses;
   - the language is kept in localStorage and sent to the API as ?lang=, which also translates the sentences the backend writes. */
"use strict";
(function () {
  const KEY = "geoai.lang";
  let lang = "en";
  try { lang = localStorage.getItem(KEY) || ((navigator.language || "").toLowerCase().startsWith("ar") ? "ar" : "en"); } catch (e) { /* storage blocked: stay English */ }
  if (lang !== "ar") lang = "en";
  const rtl = lang === "ar";
  const root = document.documentElement;
  root.lang = lang; root.dir = rtl ? "rtl" : "ltr"; root.classList.add(rtl ? "rtl" : "ltr");
  window.dojoConfig = Object.assign(window.dojoConfig || {}, { locale: lang });       // ArcGIS widgets (search, zoom, popups) follow the page language

  const AR = {
    /* ---- shared / navigation */
    "Riyadh City View": "منظور مدينة الرياض",
    "Records: {s}": "السجلات: {s}",
    "Your report was saved, but the photo was not. You can send the photo again later.": "تم حفظ تقريرك، لكن الصورة لم تُحفظ. يمكنك إرسال الصورة مرة أخرى لاحقًا.",
    "ArcGIS Online did not accept a change: {m}": "لم يقبل ArcGIS Online التغيير: {m}",
    "The layers in ArcGIS Online hold no demo data yet. Run scripts/initialize_demo.py.": "طبقات ArcGIS Online لا تحتوي على بيانات العرض بعد. شغّل scripts/initialize_demo.py.",
    "City services and mobility in one command center. Select your role to enter.": "خدمات المدينة والتنقل في مركز قيادة واحد. اختر دورك للدخول.",
    "GeoAI Operations Center": "مركز عمليات الذكاء الاصطناعي المكاني",
    "GeoAI Operations Center | Riyadh": "مركز عمليات الذكاء الاصطناعي المكاني | الرياض",
    "Select your operational role to enter the Riyadh geospatial intelligence suite.": "اختر دورك التشغيلي للدخول إلى منظومة الذكاء الجيومكاني لمدينة الرياض.",
    "Executive Hub": "المركز التنفيذي",
    "Strategic oversight, City Health KPIs, and high-level risk management.": "إشراف استراتيجي ومؤشرات صحة المدينة وإدارة المخاطر على المستوى الأعلى.",
    "Operational Center": "مركز العمليات",
    "Real-time triage, agent coordination, imagery comparison and field dispatch control.": "فرز فوري للحالات، وتنسيق الوكلاء، ومقارنة الصور، والتحكم في التكليف الميداني.",
    "Portal": "البوابة", "Strategic": "الاستراتيجي", "Operation": "العمليات", "Language": "اللغة", "Switch language": "تغيير اللغة",
    "Executive Hub | GeoAI Riyadh": "المركز التنفيذي | الذكاء الاصطناعي المكاني الرياض",
    "NCCC | National Command & Control Center": "NCCC | المركز الوطني للقيادة والتحكم",
    "NCCC | Field investigator": "NCCC | المحقق الميداني",
    "National Command & Control Center · Riyadh": "المركز الوطني للقيادة والتحكم · الرياض",
    "Field investigator": "المحقق الميداني",
    /* ---- operation page: header and KPIs */
    "Skip to alerts": "تخطَّ إلى التنبيهات",
    "AI Agents": "وكلاء الذكاء الاصطناعي",
    "When on, the AI agents keep watching and raise alerts by itself": "عند التشغيل يواصل الوكلاء المراقبة ويرفعون التنبيهات تلقائيًا",
    "Switch between 2D and 3D view": "التبديل بين العرض ثنائي وثلاثي الأبعاد",
    "Map: 2D": "الخريطة: ثنائية الأبعاد", "Map: 3D": "الخريطة: ثلاثية الأبعاد",
    "Scan now": "افحص الآن", "Compare imagery": "قارن الصور",
    "Compare satellite images from two dates to spot urban change": "قارن صور الأقمار الصناعية من تاريخين لاكتشاف التغيّر العمراني",
    "Simulate an event": "محاكاة حدث", "Simulate an event…": "محاكاة حدث…",
    "Water leak": "تسرّب مياه", "Streetlight & pole monitoring": "مراقبة إنارة الشوارع والأعمدة", "Visual distortion detection": "كشف التشوّه البصري", "Land-use management": "إدارة استخدام الأراضي",
    "Alerts": "التنبيهات", "Key numbers": "الأرقام الرئيسية",
    "Waiting for your decision": "بانتظار قرارك", "Open incidents": "حوادث مفتوحة", "Critical": "حرج", "Resolved": "تم الحل",
    "Needs action": "يتطلب إجراء", "All": "الكل", "Mark all read": "تعليم الكل كمقروء",
    "Ask the crew… e.g. “Which incident needs attention first?”": "اسأل الفريق… مثلًا: «ما الحادثة التي تحتاج إلى اهتمام أولًا؟»",
    "Ask the crew": "اسأل الفريق", "Ask": "اسأل",
    "Digital crew": "الفريق الرقمي", "Idle": "خامل", "Latest hand-offs": "آخر عمليات التسليم",
    "Map of open incidents in Riyadh": "خريطة الحوادث المفتوحة في الرياض",
    "High": "عالٍ", "Medium": "متوسط", "Low": "منخفض", "Info": "معلومة", "Citizen report": "بلاغ مواطن",
    "Live data feeds": "مصادر البيانات الحيّة",
    "Demo data is synthetic or simulated": "بيانات العرض اصطناعية أو محاكاة", "Every action is approved by a person and logged": "كل إجراء يوافق عليه شخص ويُسجَّل",
    "Simulated crew auto-responds": "الفريق المحاكى يستجيب تلقائيًا",
    "Answer assigned work orders automatically as a simulated crew (demo without an investigator device)": "الرد تلقائيًا على أوامر العمل المكلَّف بها كفريق محاكى (عرض بدون جهاز محقق)",
    "Investigator view": "واجهة المحقق", "Classic view": "العرض الكلاسيكي", "Reset demo": "إعادة ضبط العرض",
    "Reasoning: Claude": "الاستدلال: Claude", "Reasoning: offline rule planner": "الاستدلال: مخطِّط القواعد دون اتصال",
    /* ---- planner choice */
    "Planner": "المخطِّط", "Planner: {p}": "المخطِّط: {p}", "AI planner": "مخطِّط الذكاء الاصطناعي", "Who plans and answers in the crew chat": "من يخطّط ويجيب في محادثة الفريق",
    "Choose which AI plans and answers: the offline rules, an online API or a local model": "اختر أي ذكاء اصطناعي يخطّط ويجيب: القواعد دون اتصال أو واجهة برمجية عبر الإنترنت أو نموذج محلي",
    "Offline": "دون اتصال", "Online (API)": "عبر الإنترنت (واجهة برمجية)", "Local or your own server": "محلي أو خادمك الخاص", "Other": "أخرى",
    "Offline rule planner": "مخطِّط القواعد دون اتصال", "Claude (Anthropic)": "Claude (أنثروبيك)", "OpenAI": "OpenAI", "Google Gemini": "Google Gemini",
    "LM Studio (local)": "LM Studio (محلي)", "Ollama (local)": "Ollama (محلي)", "Hermes (local, via Ollama)": "Hermes (محلي، عبر Ollama)", "Other OpenAI-compatible server": "خادم آخر متوافق مع OpenAI",
    "The offline planner answers from fixed rules. It needs no internet and no key, and sends nothing anywhere.": "يجيب المخطِّط دون اتصال بقواعد ثابتة. لا يحتاج إلى إنترنت ولا إلى مفتاح، ولا يرسل أي شيء إلى أي جهة.",
    "Model": "النموذج", "Server address": "عنوان الخادم", "OpenAI-compatible address, usually ending in": "عنوان متوافق مع OpenAI وينتهي عادةً بـ",
    "API key": "مفتاح الواجهة البرمجية", "API key (optional)": "مفتاح الواجهة البرمجية (اختياري)", "Only if the server asks for one": "فقط إذا طلبه الخادم",
    "A key is set. Leave empty to keep it.": "المفتاح محفوظ. اتركه فارغًا للإبقاء عليه.", "Using the key from the server settings. Leave empty to keep it.": "يُستخدم المفتاح من إعدادات الخادم. اتركه فارغًا للإبقاء عليه.",
    "Paste the key": "الصق المفتاح", "Kept in the server's memory only. It is never saved to disk or shown again.": "يُحفظ في ذاكرة الخادم فقط. لا يُكتب على القرص ولا يُعرض مرة أخرى.",
    "A local model keeps your data on this machine. Pick a model that supports tool calling (Hermes, Llama 3.1, Qwen 2.5 ...).": "النموذج المحلي يبقي بياناتك على هذا الجهاز. اختر نموذجًا يدعم استدعاء الأدوات، مثل Hermes أو Llama 3.1 أو Qwen 2.5.",
    "Questions and the incident data the tools return are sent to this provider. Demo data is synthetic. The AI can only propose actions; a person still approves them.": "تُرسل الأسئلة وبيانات الحوادث التي تعيدها الأدوات إلى هذا المزوّد. بيانات العرض اصطناعية. يستطيع الذكاء الاصطناعي اقتراح الإجراءات فقط، ويظل الشخص هو من يوافق عليها.",
    "Installed on the server (click to use):": "المثبّتة على الخادم (انقر للاستخدام):",
    "The server is running but has no models installed. For Ollama, run: ollama pull llama3.1": "الخادم يعمل لكن لا توجد نماذج مثبّتة عليه. في Ollama نفّذ: ollama pull llama3.1",
    "Simulate repair": "محاكاة الإصلاح", "Report the repair as a simulated crew so the incident can be closed": "الإبلاغ عن الإصلاح كفريق محاكى ليتم إغلاق الحادثة",
    "Repair reported by a simulated crew. The closure is ready for your approval.": "أبلغ فريق محاكى عن الإصلاح. الإغلاق جاهز لموافقتك.",
    "Use this planner": "استخدم هذا المخطِّط", "Save and test": "حفظ واختبار", "The offline planner is active.": "المخطِّط دون اتصال هو المفعّل الآن.", "Testing the connection…": "جارٍ اختبار الاتصال…",
    "Connected ({ms} ms). This planner now answers in the crew chat.": "تم الاتصال ({ms} م.ث). هذا المخطِّط يجيب الآن في محادثة الفريق.",
    "Saved, but the test failed: {e}. Questions fall back to the offline planner until it works.": "تم الحفظ لكن الاختبار فشل: {e}. تعود الأسئلة إلى المخطِّط دون اتصال حتى يعمل الاتصال.",
    /* ---- operation page: dialogs */
    "Compare imagery epochs": "مقارنة فترات الصور", "Spot urban change between two dates": "اكتشف التغيّر العمراني بين تاريخين", "Close": "إغلاق", "Investigator report": "تقرير المحقق",
    /* ---- operation page: scripts */
    "Offline - retrying…": "غير متصل - إعادة المحاولة…",
    "AI Agents on · every {s}s · {n} scans": "وكلاء الذكاء الاصطناعي يعملون · كل {s} ثانية · {n} عمليات فحص", "AI Agents off": "وكلاء الذكاء الاصطناعي متوقفون",
    "{n} more alerts": "{n} تنبيهات أخرى",
    "just now": "الآن", "{n} min ago": "منذ {n} دقيقة", "{n} h ago": "منذ {n} ساعة", "{n} d ago": "منذ {n} يوم",
    "All clear": "لا شيء يستدعي القلق", "No alerts yet": "لا توجد تنبيهات بعد", "Nothing needs your action right now.": "لا شيء يتطلب إجراءً منك الآن.",
    "The crew is idle. Start the AI Agents and they will watch the network and alert you.": "الفريق خامل. شغّل وكلاء الذكاء الاصطناعي ليراقبوا الشبكة وينبهوك.",
    "The crew is watching. New faults and changes will appear here.": "الفريق يراقب. ستظهر هنا الأعطال والتغيّرات الجديدة.",
    "Start AI Agents": "تشغيل وكلاء الذكاء الاصطناعي",
    "Approve": "موافقة", "Reject": "رفض", "✓ Approved and done": "✓ تمت الموافقة والتنفيذ", "Got it": "علم", "Request inspection": "طلب فحص",
    "Prepare a work order to send a team to check this": "إعداد أمر عمل لإرسال فريق للتحقق من ذلك", "View report": "عرض التقرير", "Open investigator view": "فتح واجهة المحقق",
    "Open the page the assigned investigator sees (new tab)": "افتح الصفحة التي يراها المحقق المكلَّف (تبويب جديد)", "Compare epochs": "قارن الفترات", "Show on map": "اعرض على الخريطة",
    "If approved: ": "في حال الموافقة: ", "How the crew handled this": "كيف تعامل الفريق مع ذلك",
    "Work order prepared. Approve it to send a team.": "تم إعداد أمر العمل. وافق عليه لإرسال فريق.",
    "Approved. Work order {id} created.": "تمت الموافقة. أُنشئ أمر العمل {id}.",
    "Approved. The assignment for {who} was sent to ArcGIS Field Maps.": "تمت الموافقة. أُرسل تكليف {who} إلى ArcGIS Field Maps.",
    "Approved. {who} gets a pop-up to confirm the assignment.": "تمت الموافقة. ستظهر لـ {who} نافذة لتأكيد التكليف.",
    "Approved and done.": "تمت الموافقة والتنفيذ.", "Rejected. Nothing was changed.": "تم الرفض. لم يتغيّر أي شيء.",
    "updated {t}": "حُدّث {t}", "waiting for data": "بانتظار البيانات", "read by {n}": "قراءة: {n}",
    "Loading imagery…": "جارٍ تحميل الصور…", "Area": "المنطقة", "Show changes": "إظهار التغييرات", "Match brightness": "مطابقة السطوع",
    "Matches the brightness of the two dates, as the detector does": "يطابق سطوع التاريخين كما يفعل الكاشف",
    "Satellite image, after: {d}": "صورة القمر الصناعي، بعد: {d}", "Satellite image, before: {d}": "صورة القمر الصناعي، قبل: {d}", "Detected changes": "التغيّرات المرصودة",
    "Before · {d}": "قبل · {d}", "After · {d}": "بعد · {d}",
    "Drag to swipe between the before and after images": "اسحب للتنقل بين صورتي قبل وبعد",
    "confidence": "الثقة", "significant": "جوهري", "minor or possibly seasonal": "طفيف أو موسمي محتمل", "Open alert": "افتح التنبيه",
    "False-colour composite (SWIR, NIR, red). Red outlines are significant candidate changes; grey dashed outlines are minor or possibly seasonal. Imagery and processing are SIMULATED; candidates are not confirmed until a field crew verifies them.":
      "صورة مركّبة بألوان زائفة (SWIR وNIR والأحمر). الخطوط الحمراء تمثل تغيّرات مرشّحة جوهرية، والخطوط الرمادية المتقطعة تمثل تغيّرات طفيفة أو موسمية محتملة. الصور والمعالجة محاكاة؛ ولا تُعتبر المرشّحات مؤكدة حتى يتحقق منها فريق ميداني.",
    "changes found": "تغيّرات مرصودة", "Rescan this area": "أعد فحص هذه المنطقة", "Scan this area": "افحص هذه المنطقة",
    "Zayed compares the two dates and opens incidents for significant change.": "يقارن زايد بين التاريخين ويفتح حوادث عند التغيّر الجوهري.",
    "No comparison has been run for this area yet. Press Scan to compare the two dates.": "لم تُجرَ مقارنة لهذه المنطقة بعد. اضغط «افحص» لمقارنة التاريخين.",
    "Comparing…": "جارٍ المقارنة…", "Zayed found change events: {n} new alert(s).": "رصد زايد أحداث تغيّر: {n} تنبيه(ات) جديدة.", "Comparison complete. No new alerts.": "اكتملت المقارنة. لا توجد تنبيهات جديدة.",
    "Loading the report…": "جارٍ تحميل التقرير…", "Incident confirmed": "تم تأكيد الحادثة", "Repair completed": "اكتمل الإصلاح", "Not found (false alarm)": "لم يُعثر عليه (إنذار كاذب)",
    "Needs a further inspection": "يحتاج إلى فحص إضافي", "Escalated": "مصعَّد", "SIMULATED crew": "فريق محاكى",
    "Incident": "الحادثة", "Work order": "أمر العمل", "Reported from": "أُبلغ من", "{n} m from the detected point": "على بُعد {n} م من النقطة المرصودة",
    "What the investigator saw": "ما رآه المحقق", "Photo evidence": "دليل مصوّر", "Photo taken by the investigator": "صورة التقطها المحقق", "No photo was attached.": "لم تُرفق صورة.",
    "AI assessment": "تقييم الذكاء الاصطناعي", "Not available.": "غير متاح.", "Open the incident alert": "افتح تنبيه الحادثة",
    "Simulated crew will answer assigned work orders.": "سيرد الفريق المحاكى على أوامر العمل المكلَّف بها.", "Assigned work orders now wait for the investigator.": "أوامر العمل المكلَّف بها تنتظر المحقق الآن.",
    "{n} unread alerts": "{n} تنبيهات غير مقروءة", "Alerts, none unread": "التنبيهات، لا توجد غير مقروءة", "{n} unread": "{n} غير مقروءة", "You are all caught up.": "لا يوجد جديد.",
    "Working…": "يعمل…", "Active {t}": "نشط {t}", "Tools:": "الأدوات:",
    "Crew is scanning…": "الفريق يفحص…", "Event received - crew is reacting…": "تم استلام الحدث - الفريق يستجيب…",
    "Crew raised {n} new alert(s).": "رفع الفريق {n} تنبيه(ات) جديدة.", "Scan complete. Nothing new.": "اكتمل الفحص. لا جديد.",
    "AI Agents on. They are watching the network.": "وكلاء الذكاء الاصطناعي يعملون. إنهم يراقبون الشبكة.", "AI Agents paused.": "تم إيقاف وكلاء الذكاء الاصطناعي مؤقتًا.",
    "Map unavailable": "الخريطة غير متاحة", "The ArcGIS map needs internet access. Alerts still work.": "تحتاج خريطة ArcGIS إلى اتصال بالإنترنت. ما زالت التنبيهات تعمل.",
    "Citizen report · {t}": "بلاغ مواطن · {t}", "status: {s}": "الحالة: {s}", "supports {id}": "يدعم {id}", "Open {id}": "افتح {id}",
    "team: {t}": "الفريق: {t}", "not assigned": "غير مكلَّف", "no work order yet": "لا يوجد أمر عمل بعد", "{n} citizen report(s)": "{n} بلاغ(ات) مواطنين",
    "Show alert": "اعرض التنبيه", "Tell me about incident {id}": "أخبرني عن الحادثة {id}",
    "The crew is working on it…": "الفريق يعمل على ذلك…", "Handled by": "تولّى الأمر", "Close answer": "إغلاق الإجابة",
    "Reset the demo to a clean state? All alerts, open incidents and approvals will be cleared; only the closed history stays.": "إعادة ضبط العرض إلى حالة نظيفة؟ سيتم مسح كل التنبيهات والحوادث المفتوحة والموافقات، ويبقى السجل المغلق فقط.", "Demo reset.": "تمت إعادة ضبط العرض.",
    /* ---- executive hub */
    "Show the urban-change polygons found in the satellite comparison": "إظهار مضلّعات التغيّر العمراني المرصودة من مقارنة الصور",
    "Collapse Executive Briefs": "طيّ الموجزات التنفيذية", "Expand Executive Briefs": "توسيع الموجزات التنفيذية",
    "Loading…": "جارٍ التحميل…", "City Overview": "نظرة عامة على المدينة", "Incident Trend · 45 days": "اتجاه الحوادث · 45 يومًا", "Hotspots": "النقاط الساخنة",
    "Strategic view · urban change & incidents": "العرض الاستراتيجي · التغيّر العمراني والحوادث", "Map layers": "طبقات الخريطة",
    "Urban change": "التغيّر العمراني", "Incidents": "الحوادث", "Critical only": "الحرجة فقط",
    "Urban change candidate": "مرشّح تغيّر عمراني", "P1 / Critical incident": "حادثة P1 / حرجة", "Other open incident": "حادثة مفتوحة أخرى",
    "Executive Briefs": "الموجزات التنفيذية", "Generate daily report": "إنشاء التقرير اليومي", "Refresh": "تحديث", "All crew alerts": "كل تنبيهات الفريق",
    "Updated {t}": "حُدّث {t}", "Update failed": "فشل التحديث", "Refresh failed": "فشل التحديث", "Refreshed": "تم التحديث",
    "Stable": "مستقرة", "Needs attention": "تحتاج إلى اهتمام", "Degraded": "متدهورة", "Overall city overview": "نظرة عامة على المدينة",
    "{n} critical incident(s) are pulling the score down.": "{n} حادثة حرجة تخفض النتيجة.", "{n} open incident(s), none critical.": "{n} حادثة مفتوحة، لا شيء منها حرج.", "No open incidents.": "لا توجد حوادث مفتوحة.",
    "City health {n} percent": "صحة المدينة {n} بالمئة", "Not enough history yet.": "لا يوجد سجل كافٍ بعد.", "Detections per day by category": "الرصودات اليومية حسب الفئة",
    "water": "المياه", "lighting": "الإنارة", "change": "التغيّر", "distortion": "التشوّه البصري", "square-root scale": "مقياس الجذر التربيعي", "land_use": "استخدام الأراضي",
    "Nothing here. The crew escalates P1 events to this panel.": "لا شيء هنا. يصعّد الفريق أحداث P1 إلى هذه اللوحة.",
    "Critical incidents": "الحوادث الحرجة", "{n} open in total": "{n} مفتوحة إجمالًا", "Urban changes": "التغيّرات العمرانية", "{n} candidates scanned": "{n} مرشّحًا تم فحصه",
    "Avg response": "متوسط الاستجابة", "{n} critical": "{n} حرجة", "Per resolved incident": "لكل حادثة محلولة", "{n}% resolved": "{n}٪ تم حلها", "Awaiting approval": "بانتظار الموافقة", "Decisions pending": "قرارات معلّقة", "Nothing pending": "لا شيء معلّق",
    "{o} open · {c} critical": "{o} مفتوحة · {c} حرجة", "No hotspots.": "لا توجد نقاط ساخنة.", "Not ready": "غير جاهز", "Data is still loading.": "ما زالت البيانات قيد التحميل.", "Report failed": "فشل إنشاء التقرير",
    "Daily City Health Report": "تقرير صحة المدينة اليومي", "SYNTHETIC DEMO DATA": "بيانات عرض اصطناعية", "City health": "صحة المدينة", "health score": "درجة الصحة", "critical": "حرجة",
    "open incidents": "حوادث مفتوحة", "urban changes": "تغيّرات عمرانية", "avg response (h)": "متوسط الاستجابة (ساعة)", "Highest-priority incidents": "الحوادث الأعلى أولوية",
    "ID": "المعرّف", "Priority": "الأولوية", "Risk": "الخطورة", "Evidence": "الدليل", "Recommended actions": "الإجراءات الموصى بها", "Crew escalations": "تصعيدات الفريق", "None": "لا شيء",
    "Figures computed from stored records at generation time. Use Print → Save as PDF.": "الأرقام محسوبة من السجلات المخزّنة وقت الإنشاء. استخدم طباعة ← حفظ بصيغة PDF.",
    "Report generated": "تم إنشاء التقرير", "Use Save as PDF in the print dialog.": "استخدم «حفظ بصيغة PDF» في نافذة الطباعة.", "risk": "الخطورة", "{n} m²": "{n} م²", "Confidence": "الثقة",
    /* ---- field investigator page */
    "I am": "أنا", "Investigator": "المحقق", "My assignments": "مهامي", "Checking…": "جارٍ التحقق…", "Offline, retrying…": "غير متصل، إعادة المحاولة…",
    "{n} open": "{n} مفتوحة", "Nothing assigned": "لا توجد مهام مكلَّف بها",
    "Demo page: in production the investigator signs in on a phone and receives a push notification. Locations and imagery are simulated.": "صفحة تجريبية: في التشغيل الفعلي يسجّل المحقق الدخول من هاتفه ويتلقى إشعارًا فوريًا. المواقع والصور محاكاة.",
    "New assignment": "تكليف جديد", "New NCCC assignment": "تكليف جديد من NCCC", "No assignments yet": "لا توجد مهام بعد", "You will get a pop-up here the moment the operator assigns you an incident.": "ستظهر لك نافذة هنا لحظة تكليف المشغّل لك بحادثة.",
    "Waiting for you": "بانتظارك", "Confirmed · repair report due": "تم التأكيد · تقرير الإصلاح مطلوب", "Accepted · report due": "تم القبول · التقرير مطلوب", "due {t}": "الاستحقاق {t}",
    "Open report form": "افتح نموذج التقرير", "Review assignment": "راجع التكليف", "overdue": "متأخر", "in {n} min": "خلال {n} دقيقة", "in {n} h": "خلال {n} ساعة",
    "Due": "الاستحقاق", "Your task:": "مهمتك:", "What the AI found": "ما وجده الذكاء الاصطناعي", "(not confirmed):": "(غير مؤكد):", "no detail": "لا تفاصيل",
    "Accept assignment": "قبول التكليف", "Later": "لاحقًا", "Assignment accepted. The operator has been told.": "تم قبول التكليف. تم إبلاغ المشغّل.",
    "Report the repair": "أبلغ عن الإصلاح", "Confirm the incident": "أكّد الحادثة", "Outcome": "النتيجة",
    "Repaired": "تم الإصلاح", "The fault is fixed and the area is safe": "تم إصلاح العطل والمنطقة آمنة", "Needs more work": "يحتاج إلى مزيد من العمل", "Not finished yet": "لم يكتمل بعد",
    "Escalate": "تصعيد", "Needs a specialist team": "يحتاج إلى فريق متخصص", "Yes, confirmed": "نعم، مؤكد", "The fault or change is there": "العطل أو التغيّر موجود",
    "Not found": "لم يُعثر عليه", "Nothing wrong at this location": "لا خلل في هذا الموقع", "Need to look again": "أحتاج إلى معاينة أخرى", "Could not decide on this visit": "تعذّر الحسم في هذه الزيارة",
    "Dangerous or too large for me": "خطر أو أكبر من قدرتي", "What did you see? (required)": "ماذا رأيت؟ (مطلوب)", "For example: water seeping through the asphalt near the valve chamber": "مثلًا: مياه تتسرب عبر الأسفلت قرب غرفة الصمامات",
    "Latitude": "خط العرض", "Longitude": "خط الطول", "Use my device location": "استخدم موقع جهازي", "Prefilled with the incident location for the demo.": "معبأ مسبقًا بموقع الحادثة لأغراض العرض.",
    "This device has no location service.": "لا تتوفر خدمة الموقع على هذا الجهاز.", "Locating…": "جارٍ تحديد الموقع…", "Using your device location.": "يتم استخدام موقع جهازك.",
    "Could not read your location; keep the prefilled one.": "تعذّرت قراءة موقعك؛ أبقِ الموقع المعبأ مسبقًا.", "Photo (optional)": "صورة (اختياري)", "Photo preview": "معاينة الصورة",
    "Send report": "إرسال التقرير", "Sending…": "جارٍ الإرسال…", "Report sent. The operator can see it now ({o}).": "تم إرسال التقرير. يستطيع المشغّل رؤيته الآن ({o}).",
    /* ---- field maps / statuses and values shown in the UI */
    "Open": "مفتوحة", "Assigned": "مُكلَّفة", "In Progress": "قيد التنفيذ", "Work Order Created": "تم إنشاء أمر العمل", "Closed - False Positive": "أُغلقت - إنذار كاذب", "Confirmed": "مؤكدة",
    "Rejected": "مرفوضة", "Requires Further Inspection": "تتطلب فحصًا إضافيًا", "Needs Further Inspection": "تحتاج إلى فحص إضافي", "Repair Reported": "أُبلغ عن الإصلاح",
    "Proposed": "مقترحة", "Executed": "نُفّذت", "Failed": "فشلت", "New": "جديدة", "Acknowledged": "تم الاطلاع", "Completed": "مكتملة", "Created": "منشأة", "Cancelled": "ملغاة", "Linked": "مرتبطة",
    "Construction Waste": "مخلفات البناء", "Abandoned Vehicles": "السيارات التالفة والمهملة", "Illegal Graffiti": "الكتابات الجدارية العشوائية", "Non-compliant Billboards": "اللوحات الإعلانية المخالفة", "Unlicensed Canopies and Hangars": "المظلات والهناجر المخالفة", "Unregulated Street Vendors": "الباعة الجائلون غير المنظمين", "Neglected Vacant Land": "إهمال الأراضي الفضاء", "Exposed Wiring and Neglected Utilities": "الأسلاك المكشوفة وإهمال المرافق",
    "Water Leak (Suspected)": "تسرّب مياه (مشتبه به)", "Streetlight Failure (Predicted)": "عطل إنارة شارع (متوقع)", "Streetlight Cluster Maintenance": "صيانة مجموعة إنارة شوارع",
    "Streetlight Pole Inspection": "فحص أعمدة إنارة الشوارع", "Urban Change Review": "مراجعة تغيّر عمراني", "Visual Distortion Review": "مراجعة تشوّه بصري",
    "Land-Use Violation Review": "مراجعة مخالفة استخدام أراضٍ", "Urban Case": "حالة عمرانية",
    "Olaya": "العليا", "KAFD": "المركز المالي (كافد)", "Al Malaz": "الملز", "Diplomatic Quarter": "الحي الدبلوماسي", "King Salman Park": "حديقة الملك سلمان", "Diriyah": "الدرعية",
    "Water sensors": "حسّاسات المياه", "Streetlights & poles": "إنارة الشوارع والأعمدة", "Satellite imagery": "صور الأقمار الصناعية", "Visual distortion (imagery)": "التشوّه البصري (صور)",
    "Land use / zoning": "استخدام الأراضي / التقسيم", "Citizen reports": "بلاغات المواطنين",
    "Water": "مياه", "Streetlight": "إنارة", "Distortion": "تشوّه", "Land use": "استخدام الأراضي",
    "fault": "عطل", "change": "تغيّر", "dispatch": "تكليف", "digest": "موجز", "verified": "تحقق", "closure": "إغلاق", "accepted": "قبول", "field_done": "إنجاز ميداني", "corroboration": "تعزيز",
    // mobility map layers (mobility.js)
    "Mobility layers": "طبقات التنقل", "Traffic": "حركة المرور", "Metro": "المترو", "Bus": "الحافلات", "Hospitals": "المستشفيات", "Hour": "الساعة",
    "Traffic at {h}": "حركة المرور عند {h}", "Free": "انسيابي", "Slow": "بطيء", "Heavy": "مزدحم", "Stop-and-go": "شبه متوقف",
    "Modelled": "نموذج محاكاة", "calculated from the road network and synthetic demand, not measured": "محسوبة من شبكة الطرق وطلب افتراضي، وليست قياسات فعلية",
    "{n} road sections slow or worse": "{n} مقطع طريق بطيء أو أسوأ", "average speed {v} km/h": "متوسط السرعة {v} كم/س",
    "Roads": "الطرق", "Metro and bus": "المترو والحافلات",
    "Royal Commission for Riyadh City (RCRC) open data, KSA Open Data License": "البيانات المفتوحة للهيئة الملكية لمدينة الرياض، رخصة البيانات المفتوحة في المملكة العربية السعودية",
    "Bus stops appear when you zoom in": "تظهر مواقف الحافلات عند تقريب الخريطة", "approximate positions": "مواقع تقريبية", "Map sources": "مصادر الخريطة","approximate position": "موقع تقريبي",
    "Building the traffic model… {n} of 24 hours ready": "جارٍ بناء نموذج المرور… {n} من 24 ساعة جاهزة", "Could not load this layer: {m}": "تعذّر تحميل هذه الطبقة: {m}",
    "Metro station": "محطة مترو", "Hospital": "مستشفى",
    /* ---- mobility crew, closures and the impact drawing (Plan 3) */
    "City services": "خدمات المدينة", "Mobility": "التنقل", "Traffic incident": "حادثة مرورية", "Road closure": "إغلاق طريق", "Major event": "فعالية كبرى",
    "Planned closures": "الإغلاقات المخططة", "Planned closure": "إغلاق مخطط", "Requested": "مطلوب", "Approved": "معتمد", "In Place": "قيد التنفيذ", "Ended": "انتهى",
    "whole road closed": "الطريق مغلق بالكامل", "{n} lane(s) closed": "{n} حارة مغلقة",
    "Impact of {id}": "أثر {id}", "Closed section": "المقطع المغلق", "Worse after the closure": "أسوأ بعد الإغلاق", "Detour": "مسار التحويل", "Usual route": "المسار المعتاد",
    "Clear the impact drawing": "إزالة رسم الأثر", "Calculating the map drawing…": "جارٍ حساب رسم الخريطة…", "The impact drawing is not available: {m}": "رسم الأثر غير متاح: {m}",
    "View impact on map": "عرض الأثر على الخريطة", "Show the closed road, the worse road sections and the detours (modelled)": "إظهار الطريق المغلق ومقاطع الطرق الأسوأ ومسارات التحويل (نمذجة)",
    "The impact drawing needs the map, which needs internet access.": "رسم الأثر يحتاج إلى الخريطة، والخريطة تحتاج إلى اتصال بالإنترنت.",
    "Traffic Incident": "حادثة مرورية", "Planned Road Closure": "إغلاق طريق مخطط", "Major Event Traffic Plan": "خطة مرورية لفعالية كبرى", "Road Closure Request": "طلب إغلاق طريق",
    "Major Event": "فعالية كبرى", "Traffic Response": "الاستجابة المرورية", "Confirm the road is clear": "تأكيد خلو الطريق", "Confirm the closure is in place": "تأكيد تنفيذ الإغلاق",
    "Confirm the traffic plan is in place": "تأكيد تنفيذ الخطة المرورية", "Bandar Al-Shehri": "بندر الشهري", "Rayan Al-Anazi": "ريان العنزي", "Cleared": "تمت إزالة الانسداد",
    "Water leak repair": "إصلاح تسرّب مياه", "Resurfacing works": "أعمال إعادة السفلتة", "Bridge joint replacement": "استبدال فواصل الجسر",
    "Utility crossing under the carriageway": "عبور خدمات تحت الطريق", "Drainage repair": "إصلاح تصريف المياه",
    "Traffic & road reports": "المرور وبلاغات الطرق", "Closures & events": "الإغلاقات والفعاليات"
  };
  AR["change"] = "التغيّر";

  const fmt = (s, v) => v ? String(s).replace(/\{(\w+)\}/g, (m, k) => (k in v ? v[k] : m)) : s;
  const T = (s, v) => fmt(rtl && AR[s] !== undefined ? AR[s] : s, v);
  const TV = s => (rtl && AR[s] !== undefined ? AR[s] : s);               // a stored value (status, severity, area, incident type)
  const locale = rtl ? "ar-SA-u-nu-latn" : undefined;                       // Arabic with Western digits so ids and numbers read the same in both languages
  const apiUrl = u => { if (!rtl) return u; return u + (u.includes("?") ? "&" : "?") + "lang=ar"; };

  /* translate what is already in the page (static HTML) */
  const ATTRS = ["title", "placeholder", "aria-label", "alt", "label"];
  function translateNode(el) {
    if (!rtl) return;
    const w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT, { acceptNode: n => /^(SCRIPT|STYLE)$/.test(n.parentNode.nodeName) ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT });
    const nodes = []; while (w.nextNode()) nodes.push(w.currentNode);
    for (const n of nodes) {
      const raw = n.nodeValue, k = raw.trim(); if (!k) continue;
      if (AR[k] !== undefined) n.nodeValue = raw.replace(k, AR[k]);
    }
    el.querySelectorAll("*").forEach(e => ATTRS.forEach(a => { const v = e.getAttribute(a); if (v && AR[v] !== undefined) e.setAttribute(a, AR[v]); }));
  }

  function toggle() {
    const b = document.createElement("button");
    b.type = "button"; b.className = "lang-toggle"; b.id = "lang-toggle";
    b.textContent = rtl ? "English" : "العربية"; b.setAttribute("lang", rtl ? "en" : "ar");
    b.title = rtl ? "Switch to English" : "التبديل إلى العربية"; b.setAttribute("aria-label", b.title);
    b.onclick = () => { try { localStorage.setItem(KEY, rtl ? "en" : "ar"); } catch (e) { /* ignore */ } location.reload(); };
    const host = document.querySelector(".tools") || document.querySelector(".topright") || document.querySelector("header.top");
    if (host) host.appendChild(b); else { b.classList.add("floating"); document.body.appendChild(b); }
  }

  const start = () => { if (rtl) { translateNode(document.body); document.title = T(document.title); } toggle(); };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start); else start();

  const AGENT_AR = { faisal: "فيصل", mansour: "منصور", sarah: "سارة", abdullah: "عبدالله", zayed: "زايد", reem: "ريم", turki: "تركي", maha: "مها", nasser: "ناصر", noura: "نورة", fahad: "فهد" };
  const agentName = id => (rtl && AGENT_AR[id]) || id;

  window.I18N = { lang, rtl, T, TV, locale, apiUrl, agentName, translateNode, dict: AR };
})();
