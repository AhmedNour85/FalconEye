"""Plan 5, Task 6: the one-page daily brief as a PDF, English and Arabic. Built from data at request time; nothing is stored."""
import re

import pytest
from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.mobility import traffic
from backend.services import brief, pdf_arabic
from backend.services import mobility_numbers as MN


@pytest.fixture()
def ready(platform):
    traffic.warm(wait=True)
    return platform


def pages(pdf: bytes) -> int:
    return len(re.findall(rb"/Type\s*/Page\b", pdf))


def test_the_english_brief_is_one_a4_page_with_the_label_and_the_numbers(ready):
    pdf = brief.build(ready, "en")
    assert pdf.startswith(b"%PDF") and pages(pdf) == 1
    text = brief.content(ready, "en")
    flat = " ".join(t for _k, t in text)
    s = MN.summary(ready)
    assert "Synthetic and modelled data" in flat
    for v in (s["peak_hour"], s["severe_segments"]):
        assert str(v) in flat
    assert f"{s['peak_delay_ratio']}" in flat and f"{s['worst_hospital_minutes']}" in flat
    assert b"Synthetic and modelled data" in pdf                      # standard font, uncompressed: the label is in the file itself


def test_the_brief_lists_the_city_numbers_and_the_pending_approvals(ready):
    flat = " ".join(t for _k, t in brief.content(ready, "en"))
    assert "Open incidents" in flat and "Pending approvals" in flat


def test_the_arabic_brief_is_arabic_with_the_same_numbers(ready):
    pdf = brief.build(ready, "ar")
    assert pdf.startswith(b"%PDF") and pages(pdf) == 1
    flat = " ".join(t for _k, t in brief.content(ready, "ar"))
    assert re.search(r"[؀-ۿ]", flat) and "بيانات اصطناعية ومحسوبة" in flat
    s = MN.summary(ready)
    assert str(s["severe_segments"]) in flat and str(s["worst_hospital_minutes"]) in flat
    assert not re.search(r"\b(Open incidents|Pending approvals|Synthetic and modelled)\b", flat)        # no English label left


def test_before_the_model_is_ready_the_brief_says_so_instead_of_printing_zero(platform, monkeypatch):
    monkeypatch.setattr(traffic, "status", lambda: {"ready": False})
    flat = " ".join(t for _k, t in brief.content(platform, "en"))
    assert "not ready" in flat.lower() and brief.build(platform, "en").startswith(b"%PDF")


def test_the_route_serves_a_pdf_and_names_the_missing_arabic_libraries(ready, monkeypatch):
    c = TestClient(create_app(ready))
    r = c.get("/api/brief.pdf?lang=en")
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf" and r.content.startswith(b"%PDF")
    assert c.get("/api/brief.pdf?lang=ar").status_code == 200

    def boom():
        raise pdf_arabic.ArabicUnavailable("Arabic PDF needs the 'arabic-reshaper' and 'python-bidi' packages")
    monkeypatch.setattr(pdf_arabic, "register", boom)
    r = c.get("/api/brief.pdf?lang=ar")
    assert r.status_code == 503 and "arabic-reshaper" in r.json()["detail"]
    assert c.get("/api/brief.pdf?lang=en").status_code == 200


def test_a_viewer_token_may_download_the_brief(ready):
    object.__setattr__(ready.settings, "api_tokens", {"v": "viewer"})
    c = TestClient(create_app(ready))
    assert c.get("/api/brief.pdf").status_code == 401
    assert c.get("/api/brief.pdf", headers={"Authorization": "Bearer v"}).status_code == 200
