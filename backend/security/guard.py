"""Who may call the API. One guard in front of every /api route (the health check excepted), applied as a middleware so no route can be left out.

Local mode (no API_TOKENS): the API answers only to this computer. The role comes from the X-Role header, default "operator", as before.
Token mode (API_TOKENS=token=role,token=role): every request needs `Authorization: Bearer <token>` (or `X-API-Token`); the role is the token's role and the X-Role header is ignored.
The pages themselves are static files and carry no data. A browser in token mode signs in once on /signin.html: the access code (a token) is checked and
exchanged for a random session id kept in an HttpOnly, SameSite=Strict cookie; the code itself is never stored in the browser. The guard never reads a token from a URL.
"""
from __future__ import annotations

import hmac
import os
import secrets
import time

from fastapi import HTTPException

ROLES = {"viewer": 0, "worker": 1, "operator": 2}
LOCAL_HOSTS = ("127.0.0.1", "::1", "localhost", "testclient")      # "testclient" is the in-process test client, not a network address
LOCAL_NAMES = ("127.0.0.1", "localhost", "[::1]", "::1", "testserver")   # the names this computer answers to; "testserver" is the in-process test client
OPEN_PATHS = ("/api/health", "/api/session")       # /api/session checks the code itself (POST) and only ends a session (DELETE)
SESSION_COOKIE = "fe_session"
SESSION_HOURS = 12
SIGNIN_TRIES, SIGNIN_WINDOW_S = 10, 300          # wrong codes allowed per address in the window, then a pause

CSP_REPORT_ONLY = ("default-src 'self'; script-src 'self' 'unsafe-inline' https://js.arcgis.com https://*.arcgis.com; "
                   "style-src 'self' 'unsafe-inline' https://js.arcgis.com https://*.arcgis.com https://fonts.googleapis.com; "
                   "img-src 'self' data: blob: https:; font-src 'self' data: https://js.arcgis.com https://fonts.gstatic.com; "
                   "connect-src 'self' https:; worker-src 'self' blob: https://js.arcgis.com; frame-ancestors 'self'")
HEADERS = {"X-Content-Type-Options": "nosniff", "X-Frame-Options": "SAMEORIGIN", "Referrer-Policy": "same-origin",
           "Content-Security-Policy-Report-Only": CSP_REPORT_ONLY}


def parse_tokens(text: str) -> dict:
    """"abc=viewer,def=operator" -> {"abc": "viewer", "def": "operator"}. An entry with an empty token or an unknown role is dropped."""
    out = {}
    for part in (text or "").split(","):
        tok, _, role = part.partition("=")
        tok, role = tok.strip(), role.strip().lower()
        if tok and role in ROLES:
            out[tok] = role
    return out


def host_name(host_header: str) -> str:
    """'localhost:8020' -> 'localhost', '[::1]:8020' -> '[::1]'."""
    h = (host_header or "").strip().lower()
    if h.startswith("["):
        return h.split("]", 1)[0] + "]"
    return h.rsplit(":", 1)[0] if h.count(":") == 1 else h


class Guard:
    def __init__(self, tokens: dict | None = None):
        self.tokens = dict(tokens or {})
        self.sessions: dict[str, tuple[str, float]] = {}      # session id -> (role, expires at)
        self.failures: dict[str, list[float]] = {}             # client address -> times of wrong codes

    # -- sign-in (token mode) ----------------------------------------------------------
    def role_of(self, token: str) -> str | None:
        for tok, role in self.tokens.items():
            if token and hmac.compare_digest(tok.encode(), token.encode()):
                return role
        return None

    def sign_in(self, token: str, address: str) -> tuple[str, str]:
        """(session id, role) for a valid code; 401 for a wrong one; 429 after too many wrong ones from one address."""
        now = time.time()
        recent = [t for t in self.failures.get(address, []) if now - t < SIGNIN_WINDOW_S]
        if len(recent) >= SIGNIN_TRIES:
            self.failures[address] = recent
            raise HTTPException(429, "Too many wrong access codes. Wait a few minutes and try again.")
        role = self.role_of(token or "")
        if role is None:
            self.failures[address] = recent + [now]
            raise HTTPException(401, "That access code is not valid.")
        self.failures.pop(address, None)
        sid = secrets.token_urlsafe(32)
        self.sessions = {k: v for k, v in self.sessions.items() if v[1] > now}     # forget expired sessions
        self.sessions[sid] = (role, now + SESSION_HOURS * 3600)
        return sid, role

    def sign_out(self, sid: str | None) -> None:
        self.sessions.pop(sid or "", None)

    def session_role(self, request) -> str | None:
        hit = self.sessions.get(request.cookies.get(SESSION_COOKIE) or "")
        if hit and hit[1] > time.time():
            return hit[0]
        return None

    def page_allowed(self, request) -> bool:
        """In token mode a page needs a session (or a token header); in local mode the API's own checks apply."""
        return self.mode == "local" or self.session_role(request) is not None or self._token_role(request) is not None

    @property
    def mode(self) -> str:
        return "token" if self.tokens else "local"

    def _token_role(self, request) -> str | None:
        got = request.headers.get("x-api-token") or ""
        auth = request.headers.get("authorization") or ""
        if auth.lower().startswith("bearer "):
            got = auth[7:].strip()
        return self.role_of(got)

    def check(self, request) -> str:
        """The caller's role, or HTTPException 401 (token mode, no or unknown token) / 403 (local mode, not this computer; or a change sent from another website)."""
        refuse_cross_site(request)
        if self.mode == "token":
            role = self._token_role(request) or self.session_role(request)
            if role is None:
                raise HTTPException(401, "A valid API token is required (Authorization: Bearer <token>), or sign in on /signin.html.")
            return role
        host = request.client.host if request.client else ""
        if host not in LOCAL_HOSTS:
            raise HTTPException(403, "This server answers only to the computer it runs on. Set API_TOKENS to allow other callers.")
        # DNS rebinding: a hostile site can make its own name point at 127.0.0.1; the browser then still sends that name as Host
        if host_name(request.headers.get("host", "")) not in LOCAL_NAMES:
            raise HTTPException(403, "This server answers only to its own address (localhost or 127.0.0.1).")
        return request.headers.get("x-role") or "operator"


SAFE_METHODS = ("GET", "HEAD", "OPTIONS")
CROSS_SITE = ("Refused: this change was sent from another website, not from the app's own pages. "
              "Open the app itself to approve, reject or reset.")


def refuse_cross_site(request) -> None:
    """A browser sends a plain form POST from any website to this server without asking first, and in local mode it would count as the operator.
    So a request that changes something must come from the app's own pages: the browser's Sec-Fetch-Site must be same-origin (or none, typed by the
    person), and an Origin, when sent, must be this server's own. A request with neither header is not from a browser page (a script, curl) and passes."""
    if request.method.upper() in SAFE_METHODS:
        return
    site = (request.headers.get("sec-fetch-site") or "").lower()
    if site and site not in ("same-origin", "none"):
        raise HTTPException(403, CROSS_SITE)
    origin = request.headers.get("origin")
    if origin is not None:
        own = (request.headers.get("host") or "").lower()
        o = origin.lower().rstrip("/")
        scheme, _, rest = o.partition("://")
        if o in public_origins():                         # behind a host's proxy the Host header is the proxy's; the public address is configured
            return
        if o == "null" or not rest or rest != own or scheme not in ("http", "https"):
            raise HTTPException(403, CROSS_SITE)


def public_origins() -> set[str]:
    """PUBLIC_ORIGINS=https://falcon.example.org,https://other.example.org : the addresses the app is published under."""
    return {x.strip().lower().rstrip("/") for x in (os.environ.get("PUBLIC_ORIGINS") or "").split(",") if x.strip()}


def apply_headers(response) -> None:
    for k, v in HEADERS.items():
        response.headers[k] = v
