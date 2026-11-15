"""The eight kinds of visual distortion (urban visual pollution, "التشوه البصري") that the visual-distortion use case raises as incidents.

Pure data, shared by the detector, the simulator, the work-order instructions, the Field Maps task types and the Arabic translation.
`key` is what the simulator stores; `name` is the incident type shown to people; `what` completes the sentence "<name> - <what>".
All detections of these kinds are SIMULATED candidates until an investigator confirms them in the field.
"""
from __future__ import annotations

VISUAL_TYPES: dict[str, dict] = {
    "construction_waste": {
        "name": "Construction Waste", "ar": "مخلفات البناء",
        "what": "building and finishing material left in the street", "what_ar": "بقايا وأنقاض مواد الترميم والبناء المتروكة في الشوارع",
        "instr": "Visit the location, confirm the construction waste, photograph it (wide shot and close-up), note the street and the nearest site or owner, and confirm or reject.",
        "instr_ar": "زر الموقع وتأكد من وجود مخلفات البناء، وصوّرها (لقطة عامة ولقطة قريبة)، وسجّل اسم الشارع وأقرب موقع أو مالك، ثم أكّد الرصد أو ارفضه."},
    "abandoned_vehicles": {
        "name": "Abandoned Vehicles", "ar": "السيارات التالفة والمهملة",
        "what": "damaged or abandoned vehicles left on pavements or public roads", "what_ar": "مركبات تالفة أو مهملة متروكة في الأرصفة أو الطرق العامة",
        "instr": "Visit the location, confirm the vehicle is damaged or abandoned, photograph it with the plate and the surroundings, note how long it appears to have been there, and confirm or reject.",
        "instr_ar": "زر الموقع وتأكد أن المركبة تالفة أو مهملة، وصوّرها مع اللوحة والمحيط، وسجّل المدة التقريبية لبقائها، ثم أكّد الرصد أو ارفضه."},
    "graffiti": {
        "name": "Illegal Graffiti", "ar": "الكتابات الجدارية العشوائية",
        "what": "unlicensed drawings or writing on walls", "what_ar": "رسوم أو كتابات غير مرخصة على الجدران",
        "instr": "Visit the location, confirm the graffiti is unlicensed, photograph the wall and the writing, note the surface and its owner, and confirm or reject.",
        "instr_ar": "زر الموقع وتأكد أن الكتابات غير مرخصة، وصوّر الجدار والكتابات، وسجّل نوع السطح ومالكه، ثم أكّد الرصد أو ارفضه."},
    "billboards": {
        "name": "Non-compliant Billboards", "ar": "اللوحات الإعلانية المخالفة",
        "what": "old signs or signs that do not follow the regulations", "what_ar": "لوحات قديمة أو غير ملتزمة بالأنظمة والاشتراطات",
        "instr": "Visit the location, compare the sign with its permit and the signage rules (size, condition, position), photograph it, and confirm or reject the violation.",
        "instr_ar": "زر الموقع وقارن اللوحة بتصريحها وأنظمة اللوحات (الحجم والحالة والموقع)، وصوّرها، ثم أكّد المخالفة أو ارفضها."},
    "unlicensed_structures": {
        "name": "Unlicensed Canopies and Hangars", "ar": "المظلات والهناجر المخالفة",
        "what": "structures outside the property line or without approval", "what_ar": "إنشاءات خارجة عن حدود الملكية أو غير معتمدة",
        "instr": "Visit the location, check the structure against the property line and its approval, photograph it from the street, and confirm or reject the violation.",
        "instr_ar": "زر الموقع وقارن الإنشاء بحدود الملكية واعتماده، وصوّره من الشارع، ثم أكّد المخالفة أو ارفضها."},
    "street_vendors": {
        "name": "Unregulated Street Vendors", "ar": "الباعة الجائلون غير المنظمين",
        "what": "random trading on roads and pavements", "what_ar": "الإشغالات العشوائية للطرق والأرصفة",
        "instr": "Visit the location, confirm the unregulated trading, photograph the stalls and the blocked area, note the time of day, and confirm or reject.",
        "instr_ar": "زر الموقع وتأكد من وجود البيع العشوائي، وصوّر البسطات والمساحة المشغولة، وسجّل وقت اليوم، ثم أكّد الرصد أو ارفضه."},
    "vacant_land": {
        "name": "Neglected Vacant Land", "ar": "إهمال الأراضي الفضاء",
        "what": "left without fencing, paving or cleaning", "what_ar": "تُركت دون تسوير أو رصف أو نظافة",
        "instr": "Visit the plot, confirm it is neglected (no fence, paving or cleaning), photograph it and any waste on it, note the visible boundary, and confirm or reject.",
        "instr_ar": "زر القطعة وتأكد من إهمالها (دون تسوير أو رصف أو نظافة)، وصوّرها وأي مخلفات عليها، وسجّل حدودها الظاهرة، ثم أكّد الرصد أو ارفضه."},
    "exposed_utilities": {
        "name": "Exposed Wiring and Neglected Utilities", "ar": "الأسلاك المكشوفة وإهمال المرافق",
        "what": "electricity extensions or untidy connections on building fronts", "what_ar": "تمديدات الكهرباء أو الاتصالات غير المرتبة على واجهات المباني",
        "instr": "Visit the location, confirm the exposed wiring or neglected utility, keep a safe distance, photograph it from the street, note the building, and confirm or reject.",
        "instr_ar": "زر الموقع وتأكد من وجود أسلاك مكشوفة أو مرفق مهمل، وحافظ على مسافة آمنة، وصوّره من الشارع، وسجّل المبنى، ثم أكّد الرصد أو ارفضه."},
}

KEYS = tuple(VISUAL_TYPES)
NAMES = {v["name"]: k for k, v in VISUAL_TYPES.items()}


def by_key(kind: str | None) -> dict | None:
    return VISUAL_TYPES.get(kind or "")


def by_name(name: str | None) -> dict | None:
    k = NAMES.get((name or "").replace(" (Candidate)", "").strip())
    return VISUAL_TYPES[k] if k else None
