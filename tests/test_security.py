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


# ---------------- QA-02: a request that changes something must come from the app's own pages ----------------
CROSS = {"Origin": "https://evil.example", "Sec-Fetch-Site": "cross-site"}


@pytest.mark.parametrize("path", ["/api/approvals/APR-9999/approve", "/api/approvals/APR-9999/reject", "/api/demo/reset", "/api/sim/reset",
                                  "/api/nccc/scan", "/api/nccc/notifications/ack-all", "/api/nccc/events/olaya_leak"])
def test_a_change_sent_from_another_website_is_refused(platform, path):
    c, _ = client(platform)
    r = c.post(path, headers=CROSS)
    assert r.status_code == 403 and "another website" in r.json()["detail"]


def test_a_cross_site_request_is_refused_by_origin_alone_or_by_fetch_metadata_alone(platform):
    c, _ = client(platform)
    approvals0 = c.get("/api/approvals").json()
    assert c.post("/api/approvals/APR-9999/approve", headers={"Origin": "https://evil.example"}).status_code == 403
    assert c.post("/api/approvals/APR-9999/approve", headers={"Origin": "null"}).status_code == 403
    assert c.post("/api/approvals/APR-9999/approve", headers={"Origin": "http://localhost:3000"}).status_code == 403      # another site on this computer
    assert c.post("/api/approvals/APR-9999/approve", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert c.post("/api/approvals/APR-9999/approve", headers={"Sec-Fetch-Site": "same-site"}).status_code == 403
    assert c.get("/api/approvals").json() == approvals0


def test_the_apps_own_pages_and_scripts_can_still_make_changes(platform):
    c, _ = client(platform)
    own = {"Origin": "http://testserver", "Sec-Fetch-Site": "same-origin"}
    assert c.post("/api/nccc/notifications/ack-all", headers=own).status_code == 200
    assert c.post("/api/nccc/notifications/ack-all", headers={"Sec-Fetch-Site": "none"}).status_code == 200     # typed by the person
    assert c.post("/api/nccc/notifications/ack-all").status_code == 200                                         # a script or curl: no browser headers
    assert c.get("/api/config", headers=CROSS).status_code == 200                                               # reading is not a change


def test_token_mode_also_refuses_a_change_from_another_website(platform):
    c, _ = client(platform, tokens={"o": "operator"})
    assert c.post("/api/nccc/notifications/ack-all", headers={**CROSS, "Authorization": "Bearer o"}).status_code == 403
    assert c.post("/api/nccc/notifications/ack-all", headers={"Authorization": "Bearer o"}).status_code == 200


# ---------------- review finding 2: DNS rebinding (a hostile site pointed at 127.0.0.1) ----------------
def test_local_mode_refuses_a_page_reached_through_another_host_name(platform):
    c, _ = client(platform, host="127.0.0.1")
    assert c.get("/api/config", headers={"Host": "evil.test:8020"}).status_code == 403
    assert c.post("/api/approvals/APR-1/approve", headers={"Host": "evil.test:8020", "Origin": "http://evil.test:8020", "Sec-Fetch-Site": "same-origin"}).status_code == 403
    for host in ("127.0.0.1:8020", "localhost:8020", "[::1]:8020", "localhost"):
        assert c.get("/api/config", headers={"Host": host}).status_code == 200, host


# ---------------- sign-in for a public copy (token mode): the token is typed once and kept in a cookie ----------------
def test_sign_in_sets_a_cookie_that_the_api_then_accepts(platform):
    c, _ = client(platform, tokens={"op-token": "operator", "view-token": "viewer"}, host="203.0.113.7")
    assert c.get("/api/config").status_code == 401
    r = c.post("/api/session", json={"token": "wrong"})
    assert r.status_code == 401 and "fe_session" not in r.cookies
    r = c.post("/api/session", json={"token": "view-token"})
    assert r.status_code == 200 and r.json()["role"] == "viewer"
    sc = r.headers["set-cookie"].lower()
    assert "httponly" in sc and "samesite=strict" in sc
    assert c.get("/api/config").status_code == 200                                         # the cookie now carries the token
    assert c.post("/api/approvals/APR-1/approve").status_code == 403                       # a viewer still cannot approve
    assert c.get("/api/session").json()["role"] == "viewer"
    assert c.delete("/api/session").status_code == 200
    assert c.get("/api/config").status_code == 401                                         # signed out


def test_pages_send_a_visitor_without_a_session_to_the_sign_in_page(platform):
    c, _ = client(platform, tokens={"op-token": "operator"}, host="203.0.113.7")
    r = c.get("/index.html", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"].startswith("/signin.html")
    assert c.get("/signin.html").status_code == 200                                        # the sign-in page and its files are open
    assert c.get("/nccc.css").status_code == 200
    c.post("/api/session", json={"token": "op-token"})
    assert c.get("/index.html", follow_redirects=False).status_code == 200


def test_sign_in_attempts_are_limited(platform):
    c, _ = client(platform, tokens={"op-token": "operator"}, host="203.0.113.7")
    codes = [c.post("/api/session", json={"token": f"guess-{i}"}).status_code for i in range(12)]
    assert codes[:10] == [401] * 10 and codes[10:] == [429, 429]
    assert c.post("/api/session", json={"token": "op-token"}).status_code == 429          # even the right token waits out the pause


def test_local_mode_pages_need_no_sign_in(platform):
    c, _ = client(platform, host="127.0.0.1")
    assert c.get("/index.html", follow_redirects=False).status_code == 200


# ---------------- behind a host's proxy the public address is configured, not guessed ----------------
def test_a_configured_public_origin_is_accepted_for_changes(platform, monkeypatch):
    monkeypatch.setenv("PUBLIC_ORIGINS", "https://falcon.example.org")
    c, _ = client(platform, tokens={"op-token": "operator"}, host="203.0.113.7")
    h = {"Authorization": "Bearer op-token", "Host": "internal-host:10000", "Origin": "https://falcon.example.org", "Sec-Fetch-Site": "same-origin"}
    assert c.post("/api/approvals/APR-9999/approve", headers=h).status_code != 403
    h["Origin"] = "https://evil.example.org"
    assert c.post("/api/approvals/APR-9999/approve", headers=h).status_code == 403
