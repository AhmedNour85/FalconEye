"""Choosing the planner on the Operation page: offline rules, Claude, OpenAI, Gemini and local OpenAI-compatible servers."""
import json

import httpx
from fastapi.testclient import TestClient

from backend.agent import providers
from backend.agent.agent import GeoAIAgent
from backend.api.app import create_app


class FakeResp:
    def __init__(self, status=200, body=None):
        self.status_code, self._b, self.text = status, body or {}, json.dumps(body or {})

    def json(self):
        return self._b


def completion(content=None, calls=None):
    msg = {"role": "assistant", "content": content}
    if calls:
        msg["tool_calls"] = [{"id": f"c{i}", "type": "function", "function": {"name": n, "arguments": json.dumps(a)}} for i, (n, a) in enumerate(calls)]
    return FakeResp(200, {"choices": [{"message": msg}]})


def client(platform):
    return TestClient(create_app(platform, GeoAIAgent(platform)))


def test_planner_list_and_default(platform):
    c = client(platform)
    info = c.get("/api/planner").json()
    ids = [p["id"] for p in info["presets"]]
    assert info["active"]["provider"] == "rules" and {"rules", "claude", "openai", "google", "lmstudio", "ollama", "hermes", "custom"} <= set(ids)
    assert c.get("/api/health").json()["planner"] == "Offline rule planner"


def test_switching_needs_what_the_provider_needs(platform):
    c = client(platform)
    assert c.post("/api/planner", json={"provider": "openai"}).status_code == 400                         # needs a key
    assert c.post("/api/planner", json={"provider": "nope"}).status_code == 400
    assert c.post("/api/planner", json={"provider": "custom", "model": "m", "base_url": "ftp://x"}).status_code == 400
    assert c.post("/api/planner", json={"provider": "custom", "base_url": "http://localhost:9/v1"}).status_code == 400   # no model
    r = c.post("/api/planner", json={"provider": "lmstudio"})                                              # local: no key
    assert r.status_code == 200 and r.json()["active"]["provider"] == "lmstudio" and r.json()["active"]["base_url"] == "http://localhost:1234/v1"
    assert c.post("/api/planner", json={"provider": "hermes"}).json()["active"]["model"] == "hermes3"
    assert c.post("/api/planner", json={"provider": "rules"}).json()["active"]["provider"] == "rules"
    assert c.post("/api/planner", json={"provider": "lmstudio"}, headers={"X-Role": "viewer"}).status_code == 403


def test_api_key_is_never_returned(platform):
    c = client(platform)
    r = c.post("/api/planner", json={"provider": "openai", "api_key": "sk-secret-123"})
    assert r.status_code == 200 and r.json()["active"]["has_key"] is True
    assert "sk-secret-123" not in r.text and "sk-secret-123" not in c.get("/api/planner").text and "sk-secret-123" not in c.get("/api/health").text
    # switching to another model keeps the key without sending it again
    assert c.post("/api/planner", json={"provider": "openai", "model": "gpt-4o"}).json()["active"]["has_key"] is True


def test_openai_compatible_tool_loop(platform, monkeypatch):
    c = client(platform)
    c.post("/api/planner", json={"provider": "ollama", "model": "hermes3"})
    seen = []
    replies = iter([completion(calls=[("count_incidents", {})]), completion("There are incidents; see the counts.")])

    def fake_post(url, json=None, headers=None, timeout=None):
        seen.append((url, json, headers))
        return next(replies)

    monkeypatch.setattr(providers.httpx, "post", fake_post)
    r = c.post("/api/nccc/ask", json={"message": "How many incidents?", "session_id": "t"}).json()
    assert r["reply"] == "There are incidents; see the counts." and r["mode"] == "ollama"
    assert [t["tool"] for t in r["trace"]] == ["count_incidents"] and r["trace"][0]["ok"]
    url, body, headers = seen[0]
    assert url == "http://localhost:11434/v1/chat/completions" and body["model"] == "hermes3" and "Authorization" not in headers
    assert body["messages"][0]["role"] == "system" and any(t["function"]["name"] == "propose_work_order" for t in body["tools"])
    second = seen[1][1]["messages"]
    assert second[-1]["role"] == "tool" and second[-2]["tool_calls"][0]["function"]["name"] == "count_incidents"      # the tool result went back to the model


def test_models_can_only_propose_never_execute(platform, monkeypatch):
    c = client(platform)
    c.post("/api/nccc/events/olaya_leak")
    c.post("/api/planner", json={"provider": "openai", "api_key": "k"})
    iid = next(f["id"] for f in platform.store.all("Riyadh_Operational_Incidents") if f["attrs"]["Status"] == "Open")
    for a in c.get("/api/approvals?pending=true").json():
        c.post(f"/api/approvals/{a['Approval_ID']}/reject")
    before = len(platform.store.all("Riyadh_Work_Orders"))
    replies = iter([completion(calls=[("propose_work_order", {"incident_id": iid})]), completion("Prepared; waiting for your approval.")])
    monkeypatch.setattr(providers.httpx, "post", lambda *a, **k: next(replies))
    r = c.post("/api/nccc/ask", json={"message": f"create a work order for {iid}", "session_id": "g"}).json()
    assert r["pending_approvals"] and r["trace"][0]["tool"] == "propose_work_order"
    assert len(platform.store.all("Riyadh_Work_Orders")) == before                      # an approval exists, but no work order was created


def test_failure_falls_back_to_the_offline_planner(platform, monkeypatch):
    c = client(platform)
    c.post("/api/planner", json={"provider": "lmstudio"})

    def boom(*a, **k):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(providers.httpx, "post", boom)
    r = c.post("/api/nccc/ask", json={"message": "How many incidents are open?", "session_id": "f"}).json()
    assert "cannot reach" in r["reply"] and "Falling back to the offline planner" in r["reply"] and "incident" in r["reply"].lower()
    ar = c.post("/api/nccc/ask?lang=ar", json={"message": "كم حادثة مفتوحة؟", "session_id": "f2"}).json()["reply"]
    assert "المخطِّط" in ar


def test_connection_test_endpoint(platform, monkeypatch):
    c = client(platform)
    assert c.post("/api/planner/test").json()["ok"] is True                                              # offline needs nothing
    c.post("/api/planner", json={"provider": "google", "api_key": "AIza-secret"})
    monkeypatch.setattr(providers.httpx, "post", lambda *a, **k: FakeResp(401, {"error": {"message": "bad key"}}))
    r = c.post("/api/planner/test").json()
    assert r["ok"] is False and "401" in r["error"] and "API key" in r["error"] and "AIza-secret" not in json.dumps(r)
    monkeypatch.setattr(providers.httpx, "post", lambda *a, **k: completion("OK"))
    assert c.post("/api/planner/test").json()["ok"] is True


def test_history_is_cleared_when_the_planner_changes(platform, monkeypatch):
    c = client(platform)
    c.post("/api/planner", json={"provider": "lmstudio"})
    monkeypatch.setattr(providers.httpx, "post", lambda *a, **k: completion("hi"))
    c.post("/api/nccc/ask", json={"message": "hello", "session_id": "h"})
    ag = c.app.state.agent
    assert ag.session("h").oa
    c.post("/api/planner", json={"provider": "ollama"})
    assert not ag.session("h").oa


def test_bare_host_gets_the_v1_path(platform):
    assert providers.check_url("http://localhost:11434") == "http://localhost:11434/v1"
    assert providers.check_url("http://localhost:11434/") == "http://localhost:11434/v1"
    assert providers.check_url("http://localhost:1234/v1/") == "http://localhost:1234/v1"
    assert providers.check_url("https://generativelanguage.googleapis.com/v1beta/openai") == "https://generativelanguage.googleapis.com/v1beta/openai"
    c = client(platform)
    assert c.post("/api/planner", json={"provider": "ollama", "base_url": "http://localhost:11434"}).json()["active"]["base_url"] == "http://localhost:11434/v1"


def test_installed_models_are_listed_and_errors_translate(platform, monkeypatch):
    from backend.services import i18n
    c = client(platform)
    seen = []

    def fake_get(url, headers=None, timeout=None):
        seen.append(url)
        return FakeResp(200, {"data": [{"id": "gemma3:12b"}, {"id": "hermes3:8b"}, {"id": "models/x"}]})

    monkeypatch.setattr(providers.httpx, "get", fake_get)
    r = c.post("/api/planner/models", json={"provider": "ollama", "base_url": "http://localhost:11434"}).json()
    assert r["models"] == ["gemma3:12b", "hermes3:8b", "x"] and r["reachable"] is True and seen == ["http://localhost:11434/v1/models"]
    assert c.post("/api/planner/models", json={"provider": "claude"}).json()["models"] == []             # only OpenAI-compatible servers list models
    monkeypatch.setattr(providers.httpx, "get", lambda *a, **k: (_ for _ in ()).throw(httpx.ConnectError("x")))
    assert c.post("/api/planner/models", json={"provider": "lmstudio"}).json() == {"models": [], "reachable": False}
    ar = i18n.to_ar("HTTP 404 (check the model name): model 'gemma4:31b' not found")
    assert "gemma4:31b" in ar and "غير موجود" in ar and "HTTP 404" in ar
    assert "تعذّر الوصول" in i18n.to_ar("cannot reach http://localhost:1234/v1; is the server running?")


def test_provider_message_is_kept_apart_from_our_summary(platform, monkeypatch):
    c = client(platform)
    c.post("/api/planner", json={"provider": "google", "api_key": "k"})
    msg = "This model models/gemini-2.5-flash-lite is no longer available to new users."
    monkeypatch.setattr(providers.httpx, "post", lambda *a, **k: FakeResp(404, {"error": {"message": msg}}))
    r = c.post("/api/planner/test").json()
    assert r["error"] == "HTTP 404 (check the model name)" and r["detail"] == msg
    ar = c.post("/api/planner/test?lang=ar").json()
    assert "خطأ HTTP 404" in ar["error"] and ar["detail"] == msg                    # our words are Arabic, the provider's stay exactly as sent


def test_claude_errors_are_explained_not_dumped(platform):
    """A Claude/Anthropic failure (for example an empty credit balance) shows a short summary plus the provider's own message, never a Python class name."""
    from backend.services import i18n

    class BadRequestError(Exception):
        status_code = 400
        body = {"type": "error", "error": {"type": "invalid_request_error", "message": "Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing."}}

    class Client:
        class messages:                                   # noqa: N801
            @staticmethod
            def create(**kw):
                raise BadRequestError("Error code: 400")

    ag = GeoAIAgent(platform, client=Client())
    r = ag.test_planner()
    assert r["ok"] is False and "BadRequestError" not in r["error"] and "credit" in r["error"].lower()
    assert r["detail"].startswith("Your credit balance is too low")
    assert "رصيدًا" in i18n.to_ar(r["error"])
    out = ag.chat("t", "How many incidents are open?")["reply"]                # the chat falls back to the offline planner with the same plain explanation
    assert "BadRequestError" not in out and "no credit left" in out and "Falling back to the offline planner" in out
