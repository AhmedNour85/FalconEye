"""GeoAI Operations Agent: ONE conversational agent coordinating all tools.

Two interchangeable reasoning backends share the same tools, state and approval gate:
  * ClaudeBrain  - Claude API tool-calling loop (used when ANTHROPIC_API_KEY is set)
  * RuleBrain    - offline intent planner (no LLM; deterministic replies composed from tool results)
Approval/rejection phrases typed by the human are handled deterministically BEFORE any brain runs, so the model can
never approve its own proposals.
"""
from __future__ import annotations

import json
import logging
from contextvars import ContextVar
import re
import uuid
from dataclasses import dataclass, field

from backend.agent import ar, compose, mobility_questions, providers
from backend.agent.prompts import SYSTEM_PROMPT
from backend.services import i18n
from backend.gis import schema as S
from backend.platform import Platform
from backend.services.synthetic import AREAS
from backend.tools import registry
from backend.tools.common import ToolContext

log = logging.getLogger("geoai.agent")
AR_REPLY: ContextVar[bool] = ContextVar("geoai_reply_ar", default=False)   # the current chat turn answers in Arabic


def _M(key: str, **kw) -> str:
    """A fixed chat message in the language of the current turn."""
    return ar.MSG[key].format(**kw)

APPROVE_RE = re.compile(r"^\s*(yes[,.!\s]*)?(please\s+)?(approve[ds]?|i approve|go ahead|confirm(ed)?|execute|proceed)\b(?P<rest>.*)$", re.I)
REJECT_RE = re.compile(r"^\s*(no[,.!\s]*)?(please\s+)?(reject(ed)?|deny|denied|decline|cancel that|do not (do|proceed))\b(?P<rest>.*)$", re.I)


def compact(o, depth: int = 0):
    """JSON-safe, size-bounded copy of a tool result for display (lists capped at 8, strings at 300 chars, depth at 4)."""
    if isinstance(o, dict):
        return {str(k): compact(v, depth + 1) for k, v in list(o.items())[:40]} if depth < 4 else f"{{{len(o)} fields}}"
    if isinstance(o, (list, tuple)):
        if depth >= 4:
            return f"[{len(o)} items]"
        out = [compact(x, depth + 1) for x in list(o)[:8]]
        return out + [f"... +{len(o) - 8} more"] if len(o) > 8 else out
    if isinstance(o, str):
        return o if len(o) <= 300 else o[:297] + "..."
    if o is None or isinstance(o, (bool, int, float)):
        return o
    return str(o)


@dataclass
class Session:
    id: str
    ctx: ToolContext
    messages: list = field(default_factory=list)  # Claude message history (kept append-only)
    oa: list = field(default_factory=list)        # OpenAI-style history for the other online and local planners


class GeoAIAgent:
    def __init__(self, platform: Platform, client=None):
        self.p = platform
        self.sessions: dict[str, Session] = {}
        self.client = client
        if client is None and platform.settings.claude_enabled:
            try:
                import anthropic

                self.client = anthropic.Anthropic(api_key=platform.settings.anthropic_api_key, timeout=120.0, max_retries=2)
            except Exception as exc:  # pragma: no cover
                log.warning("anthropic client unavailable: %s", exc)
        self.cfg = (providers.PlannerConfig("claude", platform.settings.anthropic_model, "", platform.settings.anthropic_api_key) if self.client
                    else providers.PlannerConfig())
        self._start_planner_from_env()

    # -- planner choice (offline rules, Claude, OpenAI, Gemini, local servers) -------------------
    @property
    def mode(self) -> str:
        return self.cfg.provider

    def _env_key(self, provider: str) -> str:
        st = self.p.settings
        return {"claude": st.anthropic_api_key, "openai": getattr(st, "openai_api_key", ""), "google": getattr(st, "google_api_key", "")}.get(provider, "")

    def _start_planner_from_env(self) -> None:
        want = (getattr(self.p.settings, "planner", "") or "").strip().lower()
        if want and want in providers.BY_ID and want != self.cfg.provider:
            try:
                self.set_planner(want, "", "", "")
            except providers.PlannerError as exc:
                log.warning("GEOAI_PLANNER=%s ignored: %s", want, exc)

    def planner_info(self) -> dict:
        presets = [{**x, "key_in_env": bool(self._env_key(x["id"]))} for x in providers.PRESETS]
        return {"active": self.cfg.public(), "presets": presets}

    def set_planner(self, provider: str, model: str = "", base_url: str = "", api_key: str = "") -> dict:
        """Switch the planner. An empty key keeps the one already set (or the one from .env). Conversation history is cleared because formats differ."""
        if provider not in providers.BY_ID:
            raise providers.PlannerError(f"unknown planner '{provider}'")
        preset = providers.BY_ID[provider]
        model = (model or "").strip() or preset["model"]
        base = (base_url or "").strip() or preset["base_url"]
        key = (api_key or "").strip() or (self.cfg.api_key if self.cfg.provider == provider else "") or self._env_key(provider)
        if provider in providers.OPENAI_COMPATIBLE:
            base = providers.check_url(base)
            if not model:
                raise providers.PlannerError("enter the model name")
        if provider == "claude":
            if not key:
                raise providers.PlannerError("enter a Claude API key (or set ANTHROPIC_API_KEY)")
            if (api_key or "").strip() or self.client is None or self.cfg.provider != "claude":
                try:
                    import anthropic

                    self.client = anthropic.Anthropic(api_key=key, timeout=120.0, max_retries=2)
                except Exception as exc:
                    raise providers.PlannerError(f"the Anthropic library is not available: {type(exc).__name__}") from None
        if preset["needs_key"] and not key and provider != "claude":
            raise providers.PlannerError(f"enter the {preset['label']} API key")
        self.cfg = providers.PlannerConfig(provider, model, base if provider in providers.OPENAI_COMPATIBLE else "", key)
        for sess in self.sessions.values():
            sess.messages.clear()
            sess.oa.clear()
        return self.cfg.public()

    def list_models(self, provider: str, base_url: str = "", api_key: str = "") -> tuple[list[str], bool]:
        if provider not in providers.OPENAI_COMPATIBLE:
            return [], False
        preset = providers.BY_ID[provider]
        key = (api_key or "").strip() or (self.cfg.api_key if self.cfg.provider == provider else "") or self._env_key(provider)
        return providers.list_models(providers.PlannerConfig(provider, "", (base_url or "").strip() or preset["base_url"], key))

    def test_planner(self) -> dict:
        return providers.test(self.cfg, self.client, self.p.settings.anthropic_model)

    @property
    def uses_llm(self) -> bool:
        return self.cfg.provider != "rules"

    # -- sessions -------------------------------------------------------------------------
    def session(self, sid: str | None = None) -> Session:
        sid = sid or uuid.uuid4().hex[:8]
        if sid not in self.sessions:
            self.sessions[sid] = Session(sid, ToolContext(self.p, sid))
        return self.sessions[sid]

    def run_tool(self, sid: str, name: str, args: dict | None = None) -> dict:
        """Execute a tool inside a session (used by the guided demo so it shares the same context as the chat)."""
        return registry.execute(self.session(sid).ctx, name, args or {})

    # -- main entry -----------------------------------------------------------------------
    def chat(self, sid: str | None, text: str) -> dict:
        s = self.session(sid)
        text = (text or "").strip()
        token = AR_REPLY.set(i18n.CURRENT.get() == "ar" or bool(re.search(r"[\u0600-\u06FF]", text)))
        try:
            return self._chat(s, text)
        finally:
            AR_REPLY.reset(token)

    def _chat(self, s: Session, text: str) -> dict:
        if not text:
            return self._pack(s, ar.MSG["empty"] if AR_REPLY.get() else "Please type a request, e.g. 'Detect possible water leaks in Riyadh.'", [], "system")
        m_ap, m_rj = APPROVE_RE.match(text) or ar.APPROVE_AR.match(text), REJECT_RE.match(text) or ar.REJECT_AR.match(text)
        if m_ap or m_rj:
            return self._approval_turn(s, text, bool(m_ap), (m_ap or m_rj).group("rest"))
        n_oa = len(s.oa)
        try:
            if self.mode == "claude":
                reply, trace = self._claude_turn(s, text)
            elif self.mode in providers.OPENAI_COMPATIBLE:
                reply, trace = self._openai_turn(s, text)
            else:
                reply, trace = self._rule_turn(s, text)
        except Exception as exc:
            log.exception("agent turn failed")
            if self.uses_llm:
                del s.oa[n_oa:]                                           # a half-finished tool exchange must not poison the next turn
                who = self.cfg.label
                head_s, head_d = providers.explain(exc, self.cfg.api_key)
                why = f"{head_s}: {head_d}" if head_d else head_s
                head = (f"تعذّر الاتصال بالمخطِّط ({who}): {why}. أعود إلى المخطِّط دون اتصال في هذه المرة.\n\n" if AR_REPLY.get()
                        else f"The {who} planner failed ({why}). Falling back to the offline planner for this turn.\n\n")
                r2, t2 = self._rule_turn(s, text)
                reply, trace = head + r2, t2
            else:
                reply, trace = (_M("sorry", err=exc) if AR_REPLY.get() else f"Sorry, that failed: {exc}"), []
        return self._pack(s, reply, trace, self.mode)

    def _pack(self, s: Session, reply: str, trace: list, mode: str) -> dict:
        st = s.ctx.state
        return {"session_id": s.id, "reply": reply, "trace": trace, "mode": mode, "pending_approvals": self.p.approvals.pending(),
                "context": {k: v for k, v in st.items() if k.startswith("focus_") or k == "pending_approval"}, "suggestions": self._suggestions(s)}

    # -- approvals (human-typed only) -------------------------------------------------------
    def _approval_turn(self, s: Session, text: str, approve: bool, rest: str) -> dict:
        pend = self.p.approvals.pending()
        if not pend:
            return self._pack(s, ar.MSG["none_waiting"] if AR_REPLY.get() else "There is nothing waiting for approval.", [], "system")
        m = re.search(r"APR-\d+", rest, re.I)
        if m:
            targets = [a for a in pend if a["Approval_ID"].upper() == m.group(0).upper()]
        elif re.search(r"\ball\b", rest, re.I) or ar.ALL_AR.search(rest):
            targets = pend
        else:
            cur = s.ctx.state.get("pending_approval")
            targets = [a for a in pend if a["Approval_ID"] == cur] or [pend[-1]]
        lines, trace = [], []
        for a in targets:
            if approve:
                res = self.p.approvals.approve(a["Approval_ID"], actor="operator (chat)")
                self._after_action(s, a, res)
                trace.append({"tool": "approval_gate.approve", "stage": "ACT", "ok": bool(res.get("ok")), "input": {"approval_id": a["Approval_ID"]}, "summary": json.dumps(res, default=str)[:300], "result": compact(res)})
                if res.get("ok"):
                    if AR_REPLY.get():
                        lines.append(_M("executed", id=a["Approval_ID"], summary=i18n.to_ar(a["Summary"]), conf=self._confirmation(res)) + (f"\n> {i18n.to_ar(res['warning'])}" if res.get("warning") else ""))
                    else:
                        lines.append(f"**Executed** {a['Approval_ID']} - {a['Summary']}. System confirmation: {self._confirmation(res)}" + (f"\n> {res['warning']}" if res.get("warning") else ""))
                elif AR_REPLY.get():
                    lines.append(_M("failed", id=a["Approval_ID"], err=i18n.to_ar(str(res.get("error")))))
                else:
                    lines.append(f"**Failed** {a['Approval_ID']}: {res.get('error')}. No change was made.")
            else:
                res = self.p.approvals.reject(a["Approval_ID"], actor="operator (chat)", reason=rest.strip() or "rejected in chat")
                trace.append({"tool": "approval_gate.reject", "stage": "ACT", "ok": True, "input": {"approval_id": a["Approval_ID"]}, "summary": "rejected"})
                lines.append(_M("rejected", id=a["Approval_ID"], summary=i18n.to_ar(a["Summary"])) if AR_REPLY.get() else f"Rejected {a['Approval_ID']}: {a['Summary']}. Nothing was changed.")
        reply = "\n".join(lines)
        if self.mode == "claude":  # keep the model's history coherent without letting it act
            s.messages += [{"role": "user", "content": text}, {"role": "assistant", "content": reply}]
        elif self.mode in providers.OPENAI_COMPATIBLE:
            s.oa += [{"role": "user", "content": text}, {"role": "assistant", "content": reply}]
        return self._pack(s, reply, trace, "approval-gate")

    @staticmethod
    def _confirmation(res: dict) -> str:
        keys = ("work_order_id", "incident_id", "worker", "status", "asset_id")
        return ", ".join(f"{k}={res[k]}" for k in keys if k in res)

    def _after_action(self, s: Session, a: dict, res: dict) -> None:
        """Update conversational focus after an approved action so follow-ups ('assign a worker') resolve."""
        if not res.get("ok"):
            return
        st = s.ctx.state
        if a["Action_Type"] == "create_work_order":
            st["focus_work_order"] = res["work_order_id"]
            st["focus_incident"] = res["incident_id"]
        elif a["Action_Type"] == "assign_worker":
            st["focus_work_order"] = res["work_order_id"]
        st.pop("pending_approval", None)

    def approve_via_ui(self, approval_id: str, actor: str = "operator (UI)") -> dict:
        """Called by the REST approval panel; updates every session's focus the same way chat approval does."""
        a = self.p.store.get(S.APPROVALS, approval_id)
        res = self.p.approvals.approve(approval_id, actor=actor)
        if a:
            for s in self.sessions.values():
                if s.ctx.state.get("pending_approval") == approval_id or a["attrs"]["Session_ID"] == s.id:
                    self._after_action(s, a["attrs"], res)
        return res

    # -- suggestions ----------------------------------------------------------------------
    def _suggestions(self, s: Session) -> list[str]:
        out = self._suggestions_en(s)
        return [ar.SUGGESTIONS_AR.get(x, x) for x in out] if AR_REPLY.get() else out

    def _suggestions_en(self, s: Session) -> list[str]:
        st = s.ctx.state
        if self.p.approvals.pending():
            return ["Approve", "Reject", "Show pending approvals"]
        inc = st.get("focus_incident") and self.p.store.get(S.INCIDENTS, st["focus_incident"])
        if inc:
            status = inc["attrs"]["Status"]
            nxt = {"Open": "Create a work order for that one", "Work Order Created": "Assign a field worker", "Assigned": "Verify the outcome", "In Progress": "Verify the outcome",
                   "Confirmed": "Verify the outcome", "Repair Reported": "Close the incident", "Rejected": "Close the incident"}.get(status)
            if nxt:
                return [nxt, "Which incidents require immediate intervention?", "Show executive summary"]
        if st.get("last_detections"):
            return ["Create incidents from these detections", "Which one is the most critical?", "Show spatial context for that one"]
        return ["How many incidents are open, and where?", "Compare imagery epochs in Olaya District", "What are residents reporting?"]

    # -- Claude brain ---------------------------------------------------------------------
    def _context_block(self, s: Session) -> str:
        """Live operational context. It travels INSIDE each user message, never in the system prompt: Claude binds its thinking
        blocks to the exact system prompt, so the system prompt (and the tool list) must stay byte-identical for the whole conversation."""
        st = s.ctx.state
        pend = [{"id": a["Approval_ID"], "summary": a["Summary"]} for a in self.p.approvals.pending()]
        ctx = {"focus": {k: v for k, v in st.items() if k.startswith("focus_")}, "last_detections": st.get("last_detections", [])[:10], "pending_approvals": pend, "areas": list(AREAS)}
        if i18n.CURRENT.get() == "ar":
            ctx["reply_language"] = "Arabic (العربية): write the whole reply in Arabic; keep ids, numbers and tool names as they are"
        return "[CURRENT OPERATIONAL CONTEXT - from system state, not typed by the user]\n" + json.dumps(ctx, default=str) + "\n[END CONTEXT]"

    @staticmethod
    def _strip_thinking(messages: list) -> list:
        """Copy of the history without thinking blocks (recovery path when the API reports a stale/foreign thinking signature)."""
        out = []
        for m in messages:
            c = m["content"]
            if m["role"] == "assistant" and isinstance(c, list):
                kept = [b for b in c if (b.get("type") if isinstance(b, dict) else getattr(b, "type", "")) not in ("thinking", "redacted_thinking")]
                out.append({"role": "assistant", "content": kept or [{"type": "text", "text": "(continuing)"}]})
            else:
                out.append(m)
        return out

    def _create(self, s: Session):
        """One Claude call with a constant system prompt; if the API rejects a thinking block (bound to a different prompt/conversation),
        drop the thinking blocks from the history once and retry instead of failing the turn."""
        kw = dict(model=self.p.settings.anthropic_model, max_tokens=8000, system=SYSTEM_PROMPT, tools=registry.schemas())
        try:
            return self.client.messages.create(messages=s.messages, **kw)
        except Exception as exc:
            msg = str(exc).lower()
            if "thinking" in msg and ("signature" in msg or "block" in msg):
                log.warning("stale thinking block rejected by the API; retrying without thinking blocks: %s", exc)
                s.messages[:] = self._strip_thinking(s.messages)
                return self.client.messages.create(messages=s.messages, **kw)
            raise

    def _claude_turn(self, s: Session, text: str) -> tuple[str, list]:
        s.messages.append({"role": "user", "content": self._context_block(s) + "\n\n" + text})   # appended once, never edited later
        trace: list = []
        for _ in range(10):
            resp = self._create(s)
            s.messages.append({"role": "assistant", "content": resp.content})  # unchanged, so thinking blocks stay valid
            if resp.stop_reason == "refusal":
                return "The model declined this request.", trace
            if resp.stop_reason != "tool_use":
                out = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip()
                if resp.stop_reason == "max_tokens":
                    out += "\n\n(Response was cut off at the token limit.)"
                return out or "(no text returned)", trace
            results = []
            for b in resp.content:
                if getattr(b, "type", "") != "tool_use":
                    continue
                r = registry.execute(s.ctx, b.name, b.input if isinstance(b.input, dict) else {})
                trace.append(self._trace_item(b.name, b.input, r))
                payload = json.dumps(r.get("result") if r["ok"] else {"error": r["error"]}, default=str)
                if len(payload) > 14000:
                    payload = payload[:14000] + '..."truncated"'
                results.append({"type": "tool_result", "tool_use_id": b.id, "content": payload, **({} if r["ok"] else {"is_error": True})})
            s.messages.append({"role": "user", "content": results})
        return "I reached the tool-call limit for this turn; please narrow the request.", trace

    def _openai_turn(self, s: Session, text: str) -> tuple[str, list]:
        """Tool-calling loop for OpenAI, Gemini and local servers (LM Studio, Ollama, Hermes ...). Same tools, same approval gate as the Claude path."""
        s.oa.append({"role": "user", "content": self._context_block(s) + "\n\n" + text})
        tools, trace = providers.openai_tools(), []
        for _ in range(10):
            msg = providers.complete(self.cfg, [{"role": "system", "content": SYSTEM_PROMPT}] + s.oa, tools)
            calls = msg.get("tool_calls") or []
            s.oa.append({"role": "assistant", "content": msg.get("content") or "", **({"tool_calls": calls} if calls else {})})
            if not calls:
                return (msg.get("content") or "").strip() or "(no text returned)", trace
            for c in calls:
                fn = c.get("function") or {}
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except ValueError:
                    args = {}
                r = registry.execute(s.ctx, fn.get("name", ""), args if isinstance(args, dict) else {})
                trace.append(self._trace_item(fn.get("name", ""), args, r))
                payload = json.dumps(r.get("result") if r["ok"] else {"error": r["error"]}, default=str)
                if len(payload) > 14000:
                    payload = payload[:14000] + '..."truncated"'
                s.oa.append({"role": "tool", "tool_call_id": c.get("id", ""), "content": payload})
        return "I reached the tool-call limit for this turn; please narrow the request.", trace

    # -- rule brain -----------------------------------------------------------------------
    @staticmethod
    def _area(text: str) -> str | None:
        t = text.lower()
        for k in AREAS:
            if k.lower() in t:
                return k
        if "diplomatic" in t:
            return "Diplomatic Quarter"
        if "malaz" in t:
            return "Al Malaz"
        return None

    @staticmethod
    def _trace_item(name, args, r) -> dict:
        summ = json.dumps(r.get("result") if r["ok"] else r["error"], default=str)
        return {"tool": name, "stage": r.get("stage"), "input": args, "ok": r["ok"], "duration_ms": r.get("duration_ms"), "summary": summ[:240],
                "result": compact(r.get("result") if r["ok"] else {"error": r["error"]})}

    def _call(self, s: Session, trace: list, name: str, **args) -> dict:
        r = registry.execute(s.ctx, name, {k: v for k, v in args.items() if v is not None})
        trace.append(self._trace_item(name, args, r))
        return r

    def _say(self, name: str, r: dict) -> str:
        if AR_REPLY.get():
            if not r["ok"]:
                return _M("could_not_run", name=name, err=i18n.to_ar(str(r["error"])))
            if name in ar.COMPOSERS_AR:
                return ar.COMPOSERS_AR[name](r["result"])
        if not r["ok"]:
            return f"**{name} could not run:** {r['error']}"
        return compose.COMPOSERS[name](r["result"])

    def _mobility_turn(self, s: Session, text: str) -> tuple[str, list] | None:
        """A mobility question (closure, event, demand, hospital access, road maintenance, traffic now). One tool call; the reply is written from its numbers."""
        q = mobility_questions.parse(text)
        if not q:
            return None
        lang = "ar" if AR_REPLY.get() else "en"
        trace: list = []
        if q["intent"] in ("unknown_road", "unknown_place"):
            return mobility_questions.known_list(q["intent"].split("_")[1], lang), trace
        r = self._call(s, trace, mobility_questions.TOOL[q["intent"]], **q["args"])
        if not r["ok"]:
            err = str(r["error"])
            return (i18n.to_ar(err) if lang == "ar" else err), trace
        return mobility_questions.answer(q["intent"], r["result"], lang, q["args"]), trace

    def _rule_turn(self, s: Session, text: str) -> tuple[str, list]:
        asked = self._mobility_turn(s, text)
        if asked:
            return asked
        text = ar.augment(text)              # Arabic words add the English keywords the rules below look for
        t = text.lower()
        trace: list = []
        area = self._area(text)
        st = s.ctx.state
        has = lambda *w: any(x in t for x in w)  # noqa: E731
        n = re.search(r"\b(?:top|first)\s+(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\b", t)
        words = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
        top_n = int(words.get(n.group(1), n.group(1))) if n else None

        # a record id in the message is the subject: "INC-0074", "tell me about INC-0074", "create a work order for INC-0074", "WO-0012", "DET-0040"
        mi, mw, md = re.search(r"INC-\d+", text, re.I), re.search(r"WO-\d+", text, re.I), re.search(r"DET-\d+", text, re.I)
        iid = mi.group(0).upper() if mi else None
        if not iid and mw:
            wo = self.p.store.get(S.WORK_ORDERS, mw.group(0).upper())
            iid = wo["attrs"]["Incident_ID"] if wo else None
        if not iid and md:
            det = self.p.store.get(S.DETECTIONS, md.group(0).upper())
            iid = det["attrs"]["Incident_ID"] if det and det["attrs"]["Incident_ID"] else None
            if det and not iid:
                return self._say("spatial_analysis", self._call(s, trace, "spatial_analysis", target_type="detection", target_id=det["id"])), trace
        if iid:
            if not self.p.store.get(S.INCIDENTS, iid):
                return (_M("not_found", iid=iid) if AR_REPLY.get() else f"I can't find **{iid}**. Ask 'how many incidents are open?' or 'list open incidents' to see the ones that exist."), trace
            if has("repair") and has("simulat"):
                try:
                    res = self.p.simulate_repair(iid)
                except ValueError as exc:
                    return (i18n.to_ar(str(exc)) if AR_REPLY.get() else f"I could not report that repair: {exc}."), trace
                return (_M("repair_reported", id=iid, wo=res["work_order_id"]) if AR_REPLY.get()
                        else f"A simulated crew reported the repair of **{iid}** ({res['work_order_id']}). The closure proposal is ready for your approval."), trace
            if has("work order") and has("create", "prepare", "generate", "raise", "make", "propose"):
                return self._say("propose_work_order", self._call(s, trace, "propose_work_order", incident_id=iid)), trace
            if has("close"):
                return self._say("propose_incident_closure", self._call(s, trace, "propose_incident_closure", incident_id=iid)), trace
            if has("verify", "verification", "field evidence", "outcome"):
                return self._say("verify_outcome", self._call(s, trace, "verify_outcome", incident_id=iid)), trace
            if has("nearby", "spatial", "around", "proximity", "surround", "context", "affected", "impact"):
                return self._say("spatial_analysis", self._call(s, trace, "spatial_analysis", target_type="incident", target_id=iid)), trace
            return self._say("get_incident", self._call(s, trace, "get_incident", incident_id=iid)), trace
        if has("pending approval", "show approvals", "waiting for approval"):
            p = self.p.approvals.pending()
            if AR_REPLY.get():
                return (ar.MSG["pending_head"] + "\n" + "\n".join(f"- {a['Approval_ID']}: {i18n.to_ar(a['Summary'])}" for a in p)) if p else ar.MSG["nothing_pending"], trace
            return ("**Pending approvals:**\n" + "\n".join(f"- {a['Approval_ID']}: {a['Summary']}" for a in p)) if p else "Nothing is waiting for approval.", trace
        if has("how many", "number of", "count of", "how much") or (has("where") and has("incident", "problem", "fault")) or has("which area", "by area", "most incidents", "breakdown", "per area"):
            if has("citizen", "resident", "report"):
                return self._say("feeds_summary", self._call(s, trace, "feeds_summary", area=area)), trace
            if has("work order", "approval") and not has("incident"):
                return self._say("executive_summary", self._call(s, trace, "executive_summary", area=area)), trace
            cat = "water" if has("water", "leak", "pipe") else "lighting" if has("light", "lamp") else "change" if has("change", "construction", "imagery") else None
            sev = "Critical" if has("critical") else "High" if has("high") else None
            return self._say("count_incidents", self._call(s, trace, "count_incidents", area=area, category=cat, severity=sev, open_only=None if not has("all time", "ever", "total") else False)), trace
        if has("citizen", "resident", "social media", "balady", "complaint"):
            return self._say("feeds_summary", self._call(s, trace, "feeds_summary", area=area)), trace
        if has("work order") and has("create", "prepare", "generate", "raise", "make"):
            if top_n or has("top five", "priority incidents", "all incidents"):
                return self._say("propose_work_orders_bulk", self._call(s, trace, "propose_work_orders_bulk", top_n=top_n or 5)), trace
            if not st.get("focus_incident") and st.get("focus_detection") and not self.p.store.get(S.DETECTIONS, st["focus_detection"])["attrs"]["Incident_ID"]:
                self._call(s, trace, "create_incidents_from_detections")
            return self._say("propose_work_order", self._call(s, trace, "propose_work_order")), trace
        if has("assign", "field worker", "dispatch") and not has("verify"):
            return self._say("propose_field_assignment", self._call(s, trace, "propose_field_assignment")), trace
        if has("close") and has("incident"):
            return self._say("propose_incident_closure", self._call(s, trace, "propose_incident_closure")), trace
        if has("compare") and has("prediction", "predictions") and has("field", "actual", "observ", "verified"):
            return self._say("evaluate_outcomes", self._call(s, trace, "evaluate_outcomes")), trace
        if has("verified", "been verified") and has("which", "show", "list"):
            r = self._call(s, trace, "list_incidents", limit=50)
            if r["ok"]:
                r["result"]["incidents"] = [i for i in r["result"]["incidents"] if i["verification"]]
                r["result"]["count"] = len(r["result"]["incidents"])
            return self._say("list_incidents", r), trace
        if has("verify", "verification", "field evidence", "outcome"):
            return self._say("verify_outcome", self._call(s, trace, "verify_outcome")), trace
        if has("evaluate", "model performance", "false positive", "precision", "recalibrate", "learn"):
            return self._say("evaluate_outcomes", self._call(s, trace, "evaluate_outcomes", recalibrate=has("recalibrate", "update", "learn"))), trace
        if has("water") and has("leak") or has("leak", "pressure", "burst"):
            if has("sensor") and not has("detect", "check", "find"):
                return self._say("sensor_intelligence", self._call(s, trace, "sensor_intelligence", area=area, anomalies_only=True)), trace
            return self._say("detect_water_leaks", self._call(s, trace, "detect_water_leaks", area=area)), trace
        if has("pole", "tilt", "corrosion", "structural health"):
            corridor = "King Fahd Road" if has("king fahd") else "Olaya Street" if has("olaya street") else None
            return self._say("monitor_poles", self._call(s, trace, "monitor_poles", area=None if corridor else area, corridor=corridor)), trace
        if has("distortion", "deform", "warp", "facade", "settlement", "cracked building"):
            return self._say("detect_visual_distortion", self._call(s, trace, "detect_visual_distortion", area=area)), trace
        if has("land use", "land-use", "landuse", "zoning", "zone", "violation", "encroach"):
            return self._say("analyze_land_use", self._call(s, trace, "analyze_land_use", area=area)), trace
        if has("streetlight", "street light", "lighting", "lamp"):
            corridor = "King Fahd Road" if has("king fahd") else "Olaya Street" if has("olaya street") else None
            return self._say("predict_streetlight_failures", self._call(s, trace, "predict_streetlight_failures", area=None if corridor else area, corridor=corridor)), trace
        if has("extract") or (has("building", "road") and has("around", "detected")):
            return self._say("extract_geoai_features", self._call(s, trace, "extract_geoai_features")), trace
        if has("imagery", "epoch", "urban change", "change detection", "significant") and has("compare", "change", "epoch", "show"):
            return self._say("detect_imagery_changes", self._call(s, trace, "detect_imagery_changes", area=area)), trace
        if has("spatial", "nearby", "around", "proximity", "context", "surround"):
            tt, tid = ("incident", st.get("focus_incident")) if st.get("focus_incident") else ("detection", st.get("focus_detection")) if st.get("focus_detection") else ("change", st.get("focus_change"))
            return self._say("spatial_analysis", self._call(s, trace, "spatial_analysis", target_type=tt, target_id=tid)), trace
        if has("create incident", "create the incident", "open incident", "convert") or (has("incident") and has("create")):
            return self._say("create_incidents_from_detections", self._call(s, trace, "create_incidents_from_detections")), trace
        if has("highest-risk", "highest risk", "hotspot", "kpi", "executive", "summary", "overview", "dashboard", "risk area"):
            return self._say("executive_summary", self._call(s, trace, "executive_summary", area=area)), trace
        if has("critical", "immediate", "priorit", "urgent", "rank", "most important", "which one", "which incident"):
            if has("which one", "most critical", "this one", "that one") and st.get("last_detections") and not self._has_incidents(st["last_detections"]):
                return self._compare_detections(s, trace), trace
            return self._say("rank_incidents", self._call(s, trace, "rank_incidents", top_n=top_n or 5)), trace
        if has("incident") and has("list", "open", "show", "all"):
            return self._say("list_incidents", self._call(s, trace, "list_incidents", open_only=True, area=area)), trace
        if has("incident") and (has("detail", "tell me", "status") or re.search(r"inc-\d+", t)):
            m = re.search(r"INC-\d+", text, re.I)
            return self._say("get_incident", self._call(s, trace, "get_incident", incident_id=m.group(0).upper() if m else None)), trace
        if AR_REPLY.get():
            return ar.MSG["intro"], trace
        return ("I'm the GeoAI Operations Agent. I can sense (water leaks, streetlight failures), see (imagery change), understand (feature extraction, spatial analysis), decide (KPIs, ranking), "
                "act (incidents, work orders, assignments - always with your approval) and verify (field evidence, outcomes). I can also count incidents by area, read the citizen-report feed, and look up any record by id (for example INC-0074). Try one of the suggestions below."), trace

    def _has_incidents(self, det_ids: list[str]) -> bool:
        return any((f := self.p.store.get(S.DETECTIONS, d)) and f["attrs"]["Incident_ID"] for d in det_ids)

    def _compare_detections(self, s: Session, trace: list) -> str:
        rows = [self.p.store.get(S.DETECTIONS, d) for d in s.ctx.state["last_detections"]]
        rows = sorted([r for r in rows if r], key=lambda r: -r["attrs"]["Risk_Score"])
        top = rows[0]
        s.ctx.state["focus_detection"] = top["id"]
        sp = self._call(s, trace, "spatial_analysis", target_type="detection", target_id=top["id"])
        if AR_REPLY.get():
            lines = [_M("compare_head", n=len(rows))]
            for r in rows[:5]:
                a = r["attrs"]
                lines.append(f"- **{r['id']}** {ar.tv(a['Detection_Type'])} - الخطورة {a['Risk_Score']} ({ar.tv(a['Severity'])})، الثقة {a['Confidence']}، {ar.tv(a['Area_Name'])}")
            a = top["attrs"]
            lines.append(_M("most_critical", id=top["id"], ev=i18n.to_ar(a["Evidence"][:260])))
            if sp["ok"]:
                pa = sp["result"]["potentially_affected"]
                lines.append(_M("context", r=sp["result"]["radius_m"], pipes=pa["pipes"], lights=pa["lights"], fac=pa["facilities"], cor="، ".join(sp["result"]["road_corridors"]) or "لا يوجد"))
            lines.append(ar.MSG["compare_next"])
            return "\n".join(lines)
        lines = [f"Comparing {len(rows)} current detection(s) by risk score:"]
        for r in rows[:5]:
            a = r["attrs"]
            lines.append(f"- **{r['id']}** {a['Detection_Type']} - risk {a['Risk_Score']} ({a['Severity']}), confidence {a['Confidence']}, {a['Area_Name']}")
        a = top["attrs"]
        lines.append(f"\nMost critical: **{top['id']}** - {a['Evidence'][:260]}")
        if sp["ok"]:
            pa = sp["result"]["potentially_affected"]
            lines.append(f"Context within {sp['result']['radius_m']:.0f} m: {pa['pipes']} pipes, {pa['lights']} streetlights, {pa['facilities']} facilities; corridors: {', '.join(sp['result']['road_corridors']) or 'none'}.")
        lines.append("_Next:_ 'create incidents' then 'create a work order for that one'.")
        return "\n".join(lines)
