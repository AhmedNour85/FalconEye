"""The daily brief: one A4 page, English or Arabic. Every figure comes from the records or the traffic model at the moment of the request; nothing is stored."""
from __future__ import annotations

import datetime as dt
import io
import json

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from backend.gis import schema as S
from backend.services import i18n, mobility_numbers, pdf_arabic
from backend.tools import executive, ops
from backend.tools.common import ToolContext

TEXT = {   # label: (English, Arabic)
    "title": ("Falcon Eye - Daily brief", "منظور مدينة الرياض - الملخص اليومي"),
    "label": ("Synthetic and modelled data. Not measured. Nothing here is carried out without a person's approval.",
              "بيانات اصطناعية ومحسوبة وليست قياسات فعلية. لا يُنفَّذ شيء هنا دون موافقة شخص."),
    "city": ("City services", "خدمات المدينة"), "mobility": ("Mobility (modelled)", "التنقل (محسوب)"),
    "urgent": ("Most urgent open items", "أكثر البنود المفتوحة إلحاحًا"), "latest": ("Latest simulation", "آخر محاكاة"),
    "open": ("Open incidents", "الحوادث المفتوحة"), "critical": ("Critical incidents", "الحوادث الحرجة"),
    "wo": ("Open work orders", "أوامر العمل المفتوحة"), "resolved": ("Resolved incidents", "الحوادث المغلقة"),
    "peak": ("Busiest hour", "ساعة الذروة"), "slow": ("Slowing at the peak (quiet-hour speed / peak speed)", "التباطؤ وقت الذروة (سرعة الهدوء / سرعة الذروة)"),
    "severe": ("Road sections heavy or stopped at the peak", "مقاطع طرق مزدحمة أو متوقفة وقت الذروة"),
    "hosp": ("Worst hospital access at the peak (minutes)", "أسوأ زمن وصول إلى مستشفى وقت الذروة (دقائق)"),
    "closures": ("Planned closures in place", "الإغلاقات المخططة القائمة"),
    "notready": ("The traffic model is not ready yet, so the mobility numbers are left out.", "نموذج المرور غير جاهز بعد، لذلك لم تُدرج أرقام التنقل."),
    "none_open": ("No open items.", "لا بنود مفتوحة."), "no_sim": ("No simulation has been run yet.", "لم تُجرَ أي محاكاة بعد."),
    "pending": ("Pending approvals", "موافقات بانتظار القرار"), "rec": ("recommended", "الموصى به"),
}
KINDS = {"closure": ("closure", "إغلاق"), "closure_run": ("closure", "إغلاق"), "event": ("event", "فعالية"), "demand": ("demand growth", "نمو الطلب"),
         "incident": ("traffic incident", "حادث مروري"), "road_impact": ("repair closure", "إغلاق للإصلاح")}


def riyadh_now() -> dt.datetime:
    return dt.datetime.utcnow() + dt.timedelta(hours=3)


def content(platform, lang: str = "en") -> list[tuple[str, str]]:
    """The page as (kind, text) lines: title, sub, label, section, row, note."""
    i = 1 if lang == "ar" else 0
    t = lambda k: TEXT[k][i]  # noqa: E731
    tr = (lambda s: i18n.to_ar(s)) if lang == "ar" else (lambda s: s)
    ctx = ToolContext(platform, "brief")
    k = executive.compute_kpis(platform.store)
    s = mobility_numbers.summary(platform)
    out: list[tuple[str, str]] = [("title", t("title")), ("sub", riyadh_now().strftime("%Y-%m-%d %H:%M")), ("label", t("label")),
                                  ("section", t("city")),
                                  ("row", f"{t('open')}: {k['open_incidents']}"), ("row", f"{t('critical')}: {k['critical_incidents']}"),
                                  ("row", f"{t('wo')}: {k['open_work_orders']}"), ("row", f"{t('resolved')}: {k['resolved_incidents']}"),
                                  ("section", t("mobility"))]
    if s["peak_hour"] is None:
        out.append(("note", t("notready")))
    else:
        out += [("row", f"{t('peak')}: {s['peak_hour']:02d}:00"), ("row", f"{t('slow')}: {s['peak_delay_ratio']}"), ("row", f"{t('severe')}: {s['severe_segments']}"),
                ("row", f"{t('hosp')}: {s['worst_hospital_minutes']}")]
    out.append(("row", f"{t('closures')}: {s['planned_closures']}"))
    out.append(("section", t("urgent")))
    ranked = ops.rank_incidents(ctx, 3)["ranked"]
    for r in ranked:
        out.append(("row", f"{r['incident_id']} - {r['priority']} - {tr(str(r['area']))} - {tr(str(r['status']))}"))
    if not ranked:
        out.append(("note", t("none_open")))
    out.append(("section", t("latest")))
    done = sorted((f for f in platform.store.all(S.SCENARIOS) if f["attrs"].get("Status") == "Completed"), key=lambda f: f["attrs"].get("Completed") or "", reverse=True)
    if done:
        a = done[0]["attrs"]
        try:
            summ = json.loads(a.get("Summary") or "{}")
        except ValueError:
            summ = {}
        name = next((x["name"] for x in summ.get("strategies", []) if x["id"] == a.get("Recommended")), "")
        kind = KINDS.get(a.get("Scenario_Type"), (a.get("Scenario_Type") or "", a.get("Scenario_Type") or ""))[i]
        place = summ.get("road") or summ.get("venue") or summ.get("place") or ""
        line = f"{a.get('Scenario_ID') or done[0]['id']} - {kind}" + (f" - {tr(place)}" if place else "")
        if name:
            line += f" - {t('rec')}: {tr(name)}"
        out.append(("row", line))
    else:
        out.append(("note", t("no_sim")))
    out.append(("section", t("pending")))
    out.append(("row", f"{t('pending')}: {len(platform.approvals.pending())}"))
    return out


def build(platform, lang: str = "en") -> bytes:
    """The brief as PDF bytes. Arabic needs the shaping libraries and an Arabic font (pdf_arabic.ArabicUnavailable otherwise)."""
    rtl = lang == "ar"
    if rtl:
        pdf_arabic.register()
    lines = content(platform, lang)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=14 * mm, pageCompression=0,
                            title=TEXT["title"][1 if rtl else 0], author="Falcon Eye")
    ink, mute, accent = colors.HexColor("#0b1f3a"), colors.HexColor("#5b6b80"), colors.HexColor("#0b6bcb")
    spec = {"title": (18, True, ink, 8), "sub": (10, False, mute, 6), "label": (9, True, colors.HexColor("#a15c00"), 12), "section": (12, True, accent, 4),
            "row": (10.5, False, ink, 3), "note": (10, False, mute, 3)}
    flow = []
    for kind, text in lines:
        size, bold, color, gap = spec[kind]
        if kind == "section":
            flow.append(Spacer(1, 6))
        if rtl:
            flow.append(pdf_arabic.RTLParagraph(text, size, bold=bold, color=color))
        else:
            flow.append(Paragraph(text.replace("&", "&amp;").replace("<", "&lt;"), ParagraphStyle(kind, fontName="Helvetica-Bold" if bold else "Helvetica", fontSize=size,
                                                                                               leading=size * 1.4, textColor=color)))
        flow.append(Spacer(1, gap))
    doc.build(flow)
    return buf.getvalue()
