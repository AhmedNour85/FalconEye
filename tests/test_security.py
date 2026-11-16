"""Plan 5, Task 5: one guard in front of every /api route, local mode by default, token mode when API_TOKENS is set, security headers."""
import pytest
from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.security.guard import Guard, parse_tokens


def client(platform, agent=None, tokens=None, host="testclient"):
    object.__setattr__(platform.settings, "api_tokens", tokens or {})
    app = create_app(platform, agent)
    return TestClient(app, client=(host, 50000)), app


def test_local_mode_refuses_a_client_that_is_not_this_computer(platform):
    c, _ = client(platform, host="203.0.113.7")
    assert c.get("/api/config").status_code == 403
    assert c.get("/api/health").status_code == 200                     # the health check answers anyone: it carries no data


def test_local_mode_accepts_this_computer(platform):
    for host in ("127.0.0.1", "::1", "testclient"):
        c, _ = client(platform, host=host)
        assert c.get("/api/config").status_code == 200, host


def test_token_mode_refuses_a_missing_or_unknown_token(platform):
    c, _ = client(platform, tokens={"s3cret-view": "viewer"}, host="203.0.113.7")
    assert c.get("/api/config").status_code == 401
    assert c.get("/api/config", headers={"Authorization": "Bearer nope"}).status_code == 401
    assert c.get("/api/config", headers={"Authorization": "Bearer s3cret-view"}).status_code == 200      # a token works from any address


def test_a_viewer_token_cannot_approve(platform):
    c, _ = client(platform, tokens={"v": "viewer", "o": "operator"})
    assert c.post("/api/approvals/APR-9999/approve", headers={"Authorization": "Bearer v"}).status_code == 403
    assert c.post("/api/approvals/APR-9999/approve", headers={"Authorization": "Bearer o"}).status_code != 403


def test_the_role_header_is_ignored_in_token_mode(platform):
    c, _ = client(platform, tokens={"v": "viewer"})
    r = c.post("/api/approvals/APR-9999/approve", headers={"Authorization": "Bearer v", "X-Role": "operator"})
    assert r.status_code == 403
    r = c.post("/api/approvals/APR-9999/approve", headers={"X-Role": "operator"})
    assert r.status_code == 401


def test_the_role_header_still_works_in_local_mode(platform):
    c, _ = client(platform)
    assert c.post("/api/approvals/APR-9999/approve", headers={"X-Role": "viewer"}).status_code == 403
    assert c.post("/api/approvals/APR-9999/approve").status_code != 403          # no header: operator, as before


def test_every_api_route_goes_through_the_guard(platform):
    c, app = client(platform, tokens={"v": "viewer"})
    paths = {r.path for r in app.routes if getattr(r, "path", "").startswith("/api/")} - {"/api/health"}
    assert len(paths) > 40
    for path in sorted(paths):
        url = path.replace("{", "x").replace("}", "")
        for method in ("get", "post"):
            assert getattr(c, method)(url).status_code == 401, (method, path)


def test_headers_are_on_every_response_and_the_policy_is_report_only(platform):
    c, _ = client(platform)
    for url in ("/api/health", "/api/config", "/index.html"):
        r = c.get(url)
        assert r.headers["X-Content-Type-Options"] == "nosniff" and r.headers["X-Frame-Options"] == "SAMEORIGIN", url
        assert r.headers["Referrer-Policy"] == "same-origin"
        assert "Content-Security-Policy-Report-Only" in r.headers and "Content-Security-Policy" not in r.headers
        assert "js.arcgis.com" in r.headers["Content-Security-Policy-Report-Only"]


def test_tokens_are_read_from_the_setting_text():
    assert parse_tokens("abc=viewer, def=operator,bad=boss,=viewer,ghi") == {"abc": "viewer", "def": "operator"}
    assert parse_tokens("") == {}
    assert Guard({"a": "viewer"}).mode == "token" and Guard({}).mode == "local"
