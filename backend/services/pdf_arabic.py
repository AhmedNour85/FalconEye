"""Arabic text for ReportLab PDFs. ReportLab has no letter shaping, so Arabic is reshaped to joined forms and reordered to visual order here.
Wrapping happens on the logical text and each line is reordered on its own. Needs `arabic-reshaper`, `python-bidi` and a TrueType font with Arabic glyphs
(set PDF_ARABIC_FONT to use another)."""
from __future__ import annotations

import os
import re
from functools import lru_cache
from typing import List, Optional

from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Flowable

REGULAR, BOLD = "ArReport", "ArReport-Bold"
_CANDIDATES = [("C:/Windows/Fonts/tahoma.ttf", "C:/Windows/Fonts/tahomabd.ttf"), ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf"),
               ("C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/segoeuib.ttf"),
               ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
               ("/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf", "/usr/share/fonts/truetype/noto/NotoSansArabic-Bold.ttf"),
               ("/System/Library/Fonts/Supplemental/Arial.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf")]
_font: Optional[str] = None
_ARABIC = re.compile(r"[\u0600-\u06FF]")


class ArabicUnavailable(RuntimeError):
    pass


def has_arabic(text: str) -> bool:
    return bool(_ARABIC.search(text or ""))


def _libs():
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        return arabic_reshaper, get_display
    except ImportError as e:  # pragma: no cover
        raise ArabicUnavailable("The Arabic brief needs the 'arabic-reshaper' and 'python-bidi' packages (pip install -r requirements.txt).") from e


def register() -> str:
    """Register the Arabic font once; returns the file used."""
    global _font
    if _font:
        return _font
    _libs()
    env = os.environ.get("PDF_ARABIC_FONT")
    for reg, bold in ([(env, None)] if env else []) + _CANDIDATES:
        if reg and os.path.exists(reg):
            pdfmetrics.registerFont(TTFont(REGULAR, reg))
            pdfmetrics.registerFont(TTFont(BOLD, bold if bold and os.path.exists(bold) else reg))
            _font = reg
            return reg
    raise ArabicUnavailable("No Arabic-capable TrueType font was found. Set PDF_ARABIC_FONT to a .ttf file with Arabic letters (for example Tahoma or DejaVu Sans).")


@lru_cache(maxsize=4096)
def visual(text: str) -> str:
    reshaper, get_display = _libs()
    return get_display(reshaper.reshape(text), base_dir="R")


class RTLParagraph(Flowable):
    """A right-aligned, word-wrapped paragraph of plain text."""

    def __init__(self, text: str, size: float = 9, leading: Optional[float] = None, bold: bool = False, color=colors.black, align: str = "right"):
        super().__init__()
        self.text, self.size, self.leading = str(text), size, leading or size * 1.45
        self.ltr = not has_arabic(self.text)
        self.font, self.color = (BOLD if bold else REGULAR), color
        self.align = "left" if self.ltr and align == "right" else align
        self._lines: List[str] = []

    def _break(self, width: float) -> List[str]:
        space = pdfmetrics.stringWidth(" ", self.font, self.size)
        lines, cur, cur_w = [], [], 0.0
        for word in self.text.split():
            w = pdfmetrics.stringWidth(word if self.ltr else visual(word), self.font, self.size)
            add = w + (space if cur else 0)
            if cur and cur_w + add > width:
                lines.append(" ".join(cur)); cur, cur_w = [word], w
            else:
                cur.append(word); cur_w += add
        if cur:
            lines.append(" ".join(cur))
        return lines or [""]

    def wrap(self, availWidth, availHeight):
        self.width = availWidth
        self._lines = self._break(availWidth)
        self.height = len(self._lines) * self.leading
        return self.width, self.height

    def draw(self):
        c = self.canv
        c.setFont(self.font, self.size)
        c.setFillColor(self.color)
        for i, line in enumerate(self._lines):
            y = self.height - (i + 1) * self.leading + (self.leading - self.size) * 0.55
            v = line if self.ltr else visual(line)
            if self.align == "center":
                c.drawCentredString(self.width / 2, y, v)
            elif self.align == "left":
                c.drawString(0, y, v)
            else:
                c.drawRightString(self.width, y, v)
