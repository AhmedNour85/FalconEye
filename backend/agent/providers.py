"""Planner choices for the Operation page: the offline rule planner, Claude, and any OpenAI-compatible chat API.

OpenAI, Google Gemini (through its OpenAI-compatible endpoint), local servers (LM Studio, Ollama, vLLM, llama.cpp ...), Hermes models served by any of those,
and any other OpenAI-compatible URL all use the same tool-calling adapter (`complete`). Claude keeps its own adapter in `agent.py`.
API keys live in memory only: they are never written to disk, logged, or returned by the API.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from urllib.parse import urlparse

import httpx

from backend.tools import registry

# id -> label, kind, default model, default base URL, needs an API key, suggested models, environment variable that supplies a key
PRESETS: list[dict] = [
    {"id": "rules", "label": "Offline rule planner", "kind": "offline", "model": "", "base_url": "", "needs_key": False, "models": [], "env": ""},
    {"id": "claude", "label": "Claude (Anthropic)", "kind": "cloud", "model": "claude-opus-5-5", "base_url": "", "needs_key": True,
     "models": ["claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"], "env": "ANTHROPIC_API_KEY"},
    {"id": "openai", "label": "OpenAI", "kind": "cloud", "model": "gpt-4.1", "base_url": "https://api.openai.com/v1", "needs_key": True,
     "models": ["gpt-4.1", "gpt-4.1-mini", "gpt-4o", "gpt-4o-mini"], "env": "OPENAI_API_KEY"},
    {"id": "google", "label": "Google Gemini", "kind": "cloud", "model": "gemini-3.5-flash-lite", "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
     "needs_key": True, "models": ["gemini-3.5-flash-lite", "gemini-3.5-flash", "gemini-2.5-pro"], "env": "GOOGLE_API_KEY"},
    {"id": "lmstudio", "label": "LM Studio (local)", "kind": "local", "model": "local-model", "base_url": "http://localhost:1234/v1", "needs_key": False, "models": ["local-model"], "env": ""},
    {"id": "ollama", "label": "Ollama (local)", "kind": "local", "model": "llama3.1", "base_url": "http://localhost:11434/v1", "needs_key": False,
     "models": ["llama3.1", "qwen2.5", "mistral-nemo"], "env": ""},
    {"id": "hermes", "label": "Hermes (local, via Ollama)", "kind": "local", "model": "hermes3", "base_url": "http://localhost:11434/v1", "needs_key": False,
     "models": ["hermes3", "hermes3:8b", "nous-hermes2"], "env": ""},
    {"id": "custom", "label": "Other OpenAI-compatible server", "kind": "custom", "model": "", "base_url": "", "needs_key": False, "models": [], "env": ""},
]
BY_ID = {p["id"]: p for p in PRESETS}
OPENAI_COMPATIBLE = {"openai", "google", "lmstudio", "ollama", "hermes", "custom"}


@dataclass
class PlannerConfig:
    provider: str = "rules"
    model: str = ""
    base_url: str = ""
    api_key: str = field(default="", repr=False)          # kept in memory only

    @property
    def label(self) -> str:
        p = BY_ID.get(self.provider, BY_ID["rules"])
        return p["label"] + (f" · {self.model}" if self.model and self.provider != "rules" else "")

    def public(self) -> dict:
        return {"provider": self.provider, "model": self.model, "base_url": self.base_url, "has_key": bool(self.api_key), "label": self.label}


class PlannerError(RuntimeError):
    """`summary` is ours (and translatable); `detail` is the provider's own words, shown as they are."""

    def __init__(self, summary: str, detail: str = ""):
        super().__init__(f"{summary}: {detail}" if detail else summary)
        self.summary, self.detail = summary, detail


def check_url(url: str) -> str:
    u = (url or "").strip().rstrip("/")
    p = urlparse(u)
    if p.scheme not in ("http", "https") or not p.netloc:
        raise PlannerError("the server address must start with http:// or https://")
    if p.path in ("", "/"):
        u += "/v1"                     # LM Studio, Ollama, vLLM and llama.cpp serve the OpenAI API under /v1; a bare host:port is a common slip
    return u


def openai_tools() -> list[dict]:
    """The agent's tools in the OpenAI function-calling format."""
    return [{"type": "function", "function": {"name": t["name"], "description": t["description"], "parameters": t["input_schema"]}} for t in registry.schemas()]


def complete(cfg: PlannerConfig, messages: list[dict], tools: list[dict] | None = None, max_tokens: int = 4000, timeout: float = 120.0) -> dict:
    """One chat-completions call; returns the assistant message ({"role", "content", "tool_calls"?}). Errors never include the API key."""
    base = check_url(cfg.base_url or BY_ID[cfg.provider]["base_url"])
    body: dict = {"model": cfg.model or BY_ID[cfg.provider]["model"], "messages": messages, "max_tokens": max_tokens}
    if tools:
        body["tools"], body["tool_choice"] = tools, "auto"
    headers = {"Content-Type": "application/json", **({"Authorization": f"Bearer {cfg.api_key}"} if cfg.api_key else {})}
    try:
        r = httpx.post(base + "/chat/completions", json=body, headers=headers, timeout=timeout)
    except httpx.ConnectError:
        raise PlannerError(f"cannot reach {base}; is the server running?") from None
    except httpx.TimeoutException:
        raise PlannerError(f"{base} did not answer in {timeout:.0f} s") from None
    except httpx.HTTPError as exc:
        raise PlannerError(f"network error: {type(exc).__name__}") from None
    if r.status_code >= 400:
        detail = ""
        try:
            e = r.json()
            e = e[0] if isinstance(e, list) and e else e
            detail = (e.get("error") or {}).get("message") if isinstance(e.get("error"), dict) else str(e.get("error") or e.get("message") or "")
        except Exception:  # not JSON
            detail = r.text[:200]
        hint = " (check the API key)" if r.status_code in (401, 403) else " (check the model name)" if r.status_code == 404 else ""
        raise PlannerError(f"HTTP {r.status_code}{hint}", (detail or "")[:400])
    try:
        return r.json()["choices"][0]["message"]
    except Exception:
        raise PlannerError("the server's answer was not an OpenAI-style chat completion") from None


def list_models(cfg: PlannerConfig, timeout: float = 8.0) -> tuple[list[str], bool]:
    """(model names, server reachable). The names come from GET /models, so the dialog can show what is really installed."""
    base = check_url(cfg.base_url or BY_ID[cfg.provider]["base_url"])
    headers = {"Authorization": f"Bearer {cfg.api_key}"} if cfg.api_key else {}
    try:
        r = httpx.get(base + "/models", headers=headers, timeout=timeout)
        if r.status_code >= 400:
            return [], True
        data = r.json()
        rows = data.get("data") if isinstance(data, dict) else data
        names = [str(m.get("id") or m.get("name") or "").removeprefix("models/") for m in (rows or []) if isinstance(m, dict)]
        return sorted({n for n in names if n})[:200], True
    except httpx.HTTPError:
        return [], False
    except ValueError:
        return [], True


def explain(exc: Exception, secret: str = "") -> tuple[str, str]:
    """(our summary, the provider's own words) for any planner failure, including the Anthropic SDK's, so the screen never shows a raw Python error."""
    if isinstance(exc, PlannerError):
        return exc.summary, exc.detail
    code = getattr(exc, "status_code", None)
    body = getattr(exc, "body", None)
    msg = ""
    if isinstance(body, dict):
        e = body.get("error") if isinstance(body.get("error"), dict) else body
        msg = str(e.get("message") or "")
    msg = msg or str(getattr(exc, "message", "") or "") or str(exc)
    low = msg.lower()
    if "credit balance" in low or "billing" in low and "upgrade" in low:
        summary = "The Anthropic account has no credit left (add credit under Plans & Billing)"
    elif code in (401, 403) or "api key" in low and "invalid" in low:
        summary = f"HTTP {code or 401} (check the API key)"
    elif code == 404:
        summary = "HTTP 404 (check the model name)"
    elif code == 429:
        summary = "HTTP 429 (rate limit reached; try again shortly)"
    elif code:
        summary = f"HTTP {code}"
    elif "connect" in type(exc).__name__.lower() or "timeout" in type(exc).__name__.lower():
        summary = "cannot reach the Anthropic API; check the internet connection"
    else:
        summary = type(exc).__name__
    detail = msg[:400]
    return summary, detail.replace(secret, "***") if secret else detail


def test(cfg: PlannerConfig, client=None, claude_model: str = "") -> dict:
    """A tiny call with no tools: proves the address, key and model work."""
    t0 = time.perf_counter()
    try:
        if cfg.provider == "claude":
            if client is None:
                raise PlannerError("no Claude API key is set")
            r = client.messages.create(model=cfg.model or claude_model, max_tokens=20, messages=[{"role": "user", "content": "Reply with the single word OK."}])
            text = "".join(getattr(b, "text", "") for b in r.content).strip()
        elif cfg.provider in OPENAI_COMPATIBLE:
            text = (complete(cfg, [{"role": "user", "content": "Reply with the single word OK."}], max_tokens=20, timeout=60.0).get("content") or "").strip()
        else:
            return {"ok": True, "ms": 0, "reply": "The offline rule planner needs no connection."}
        return {"ok": True, "ms": round((time.perf_counter() - t0) * 1000), "reply": text[:80]}
    except PlannerError as exc:
        return {"ok": False, "error": exc.summary, "detail": exc.detail}
    except Exception as exc:  # the Claude SDK raises its own errors
        summary, detail = explain(exc, cfg.api_key)
        return {"ok": False, "error": summary, "detail": detail}
