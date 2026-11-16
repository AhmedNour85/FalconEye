"""Who may call the API. One guard in front of every /api route (the health check excepted), applied as a middleware so no route can be left out.

Local mode (no API_TOKENS): the API answers only to this computer. The role comes from the X-Role header, default "operator", as before.
Token mode (API_TOKENS=token=role,token=role): every request needs `Authorization: Bearer <token>` (or `X-API-Token`); the role is the token's role and the X-Role header is ignored.
The pages themselves are static files and carry no data. In token mode a browser needs a proxy that adds the header; the guard never reads a token from a URL.
"""
from __future__ import annotations

import hmac

from fastapi import HTTPException

ROLES = {"viewer": 0, "worker": 1, "operator": 2}
LOCAL_HOSTS = ("127.0.0.1", "::1", "localhost", "testclient")      # "testclient" is the in-process test client, not a network address
OPEN_PATHS = ("/api/health",)

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


class Guard:
    def __init__(self, tokens: dict | None = None):
        self.tokens = dict(tokens or {})

    @property
    def mode(self) -> str:
        return "token" if self.tokens else "local"

    def _token_role(self, request) -> str | None:
        got = request.headers.get("x-api-token") or ""
        auth = request.headers.get("authorization") or ""
        if auth.lower().startswith("bearer "):
            got = auth[7:].strip()
        for tok, role in self.tokens.items():
            if got and hmac.compare_digest(tok.encode(), got.encode()):
                return role
        return None

    def check(self, request) -> str:
        """The caller's role, or HTTPException 401 (token mode, no or unknown token) / 403 (local mode, not this computer)."""
        if self.mode == "token":
            role = self._token_role(request)
            if role is None:
                raise HTTPException(401, "A valid API token is required (Authorization: Bearer <token>).")
            return role
        host = request.client.host if request.client else ""
        if host not in LOCAL_HOSTS:
            raise HTTPException(403, "This server answers only to the computer it runs on. Set API_TOKENS to allow other callers.")
        return request.headers.get("x-role") or "operator"


def apply_headers(response) -> None:
    for k, v in HEADERS.items():
        response.headers[k] = v
