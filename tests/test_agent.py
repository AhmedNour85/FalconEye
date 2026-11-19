"""Agent tests: conversational continuity (rule brain), approval handling, and the Claude tool-calling loop with a fake client."""
from types import SimpleNamespace

import pytest

from backend.agent.agent import GeoAIAgent
from backend.gis import schema as S


def test_multi_turn_context_leak_to_verification(platform, agent):
    platform.sim.scenario("multi_incident")
    t = lambda m: agent.chat("s1", m)  # noqa: E731
    r = t("Check the water network for potential leaks.")
    assert "suspected leak" in r["reply"].lower() and r["trace"][0]["tool"] == "detect_water_leaks"
    r = t("Which one is the most critical?")
    assert "Most critical" in r["reply"]
    top = agent.session("s1").ctx.state["focus_detection"]
    n0 = platform.store.count(S.WORK_ORDERS)
    r = t("Create a work order for that one.")
    assert r["pending_approvals"] and platform.store.count(S.WORK_ORDERS) == n0, "no WO before approval"
    assert "Nothing has been created yet" in r["reply"]
    r = t("Approve.")
    assert platform.store.count(S.WORK_ORDERS) == n0 + 1 and "Executed" in r["reply"]
    inc = platform.store.get(S.DETECTIONS, top)["attrs"]["Incident_ID"]
    assert inc and platform.store.get(S.INCIDENTS, inc)["attrs"]["Status"] == "Work Order Created"
    r = t("Assign a field worker.")
    assert "Recommended worker" in r["reply"]
    t("approve")
    wo = agent.session("s1").ctx.state["focus_work_order"]
    platform.simulate_field_response(wo)
    r = t("Verify the outcome.")
    assert "Comparison" in r["reply"] and "Confirmed" in r["reply"]


def test_reject_in_chat(platform, agent):
    platform.sim.scenario("olaya_leak")
    agent.chat("s", "detect water leaks in Olaya")
    agent.chat("s", "create incidents")
    agent.chat("s", "create a work order for that incident")
    n0 = platform.store.count(S.WORK_ORDERS)
    r = agent.chat("s", "reject")
    assert "Rejected" in r["reply"] and platform.store.count(S.WORK_ORDERS) == n0
    assert agent.chat("s", "approve")["reply"].startswith("There is nothing")


def test_bulk_work_orders_top_n(platform, agent):
    platform.sim.scenario("multi_incident")
    agent.chat("a", "detect possible water leaks in Riyadh")
    agent.chat("a", "create incidents")
    r = agent.chat("a", "Create work orders for the top five priority incidents.")
    assert len(r["pending_approvals"]) >= 3
    r = agent.chat("a", "approve all")
    assert r["reply"].count("Executed") >= 3


def test_nothing_to_approve_and_help(agent):
    assert "nothing is waiting" in agent.chat("x", "pending approvals")["reply"].lower()
    assert "GeoAI Operations Agent" in agent.chat("x", "hello there")["reply"]


# ---------------- Claude loop with a fake client (verifies tool_result plumbing and approval boundary) ----------------
class FakeClient:
    def __init__(self, script):
        self.script, self.calls = list(script), []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kw):
        self.calls.append(kw)
        return self.script.pop(0)


def _resp(stop, *blocks):
    return SimpleNamespace(stop_reason=stop, content=list(blocks))


def test_claude_loop_executes_tools_and_cannot_approve(platform):
    platform.sim.scenario("olaya_leak")
    tu = lambda i, n, a: SimpleNamespace(type="tool_use", id=i, name=n, input=a)  # noqa: E731
    fc = FakeClient([
        _resp("tool_use", tu("t1", "detect_water_leaks", {"area": "Olaya"})),
        _resp("tool_use", tu("t2", "create_incidents_from_detections", {}), tu("t3", "propose_work_order", {})),
        _resp("end_turn", SimpleNamespace(type="text", text="Proposed a work order; awaiting your approval.")),
    ])
    ag = GeoAIAgent(platform, client=fc)
    assert ag.mode == "claude"
    n0 = platform.store.count(S.WORK_ORDERS)
    r = ag.chat("c", "Handle the Olaya leak")
    assert "awaiting your approval" in r["reply"] and [t["tool"] for t in r["trace"]] == ["detect_water_leaks", "create_incidents_from_detections", "propose_work_order"]
    assert platform.store.count(S.WORK_ORDERS) == n0 and r["pending_approvals"]
    # tool results were fed back in ONE user message and the schema list never contains an approval tool
    assert len(fc.calls[2]["messages"][-2]["content"]) == 2
    assert not any("approve" in t["name"] for t in fc.calls[0]["tools"])
    assert fc.calls[0]["model"] == platform.settings.anthropic_model
    r = ag.chat("c", "Approve.")  # human text handled by the gate, not by the model
    assert platform.store.count(S.WORK_ORDERS) == n0 + 1 and len(fc.calls) == 3


def test_claude_failure_falls_back_to_rules(platform):
    class Boom:
        messages = SimpleNamespace(create=lambda **k: (_ for _ in ()).throw(RuntimeError("api down")))
    ag = GeoAIAgent(platform, client=Boom())
    r = ag.chat("z", "show executive summary")
    assert "failed" in r["reply"].lower() and "Executive overview" in r["reply"]


def test_trace_items_carry_compact_structured_results(platform, ctx):
    import json
    from backend.agent.agent import GeoAIAgent, compact
    big = {"rows": list(range(50)), "text": "x" * 1000, "deep": {"a": {"b": {"c": {"d": {"e": 1}}}}}, "obj": object()}
    c = compact(big)
    assert len(c["rows"]) == 9 and c["rows"][-1].startswith("... +")      # lists are capped with a marker
    assert len(c["text"]) <= 300                                             # long strings are cut
    assert isinstance(c["deep"]["a"]["b"]["c"], str)                         # depth is bounded
    json.dumps(c)                                                            # always JSON-serialisable
    platform.sim.scenario("olaya_leak")
    ag = GeoAIAgent(platform)
    r = ag.run_tool("t", "detect_water_leaks", {"area": "Olaya"})
    item = ag._trace_item("detect_water_leaks", {"area": "Olaya"}, r)
    assert item["ok"] and isinstance(item["result"], dict) and "detections" in item["result"] and item["summary"]
    bad = ag._trace_item("spatial_analysis", {}, ag.run_tool("t", "spatial_analysis", {}))
    assert not bad["ok"] and "error" in bad["result"]


# ---------------- thinking-block binding: the system prompt must never change within a conversation ----------------
class SnapClient:
    """Records a deep copy of every request so later history appends cannot hide what was actually sent."""
    def __init__(self, script):
        import copy
        self._copy, self.script, self.calls = copy.deepcopy, list(script), []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kw):
        self.calls.append({k: self._copy(v) for k, v in kw.items()})
        r = self.script.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def test_system_prompt_constant_and_context_travels_in_user_message(platform):
    from backend.agent.prompts import SYSTEM_PROMPT
    platform.sim.scenario("olaya_leak")
    tu = SimpleNamespace(type="tool_use", id="t1", name="detect_water_leaks", input={"area": "Olaya"})
    think = SimpleNamespace(type="thinking", thinking="", signature="sig-abc")
    fc = SnapClient([_resp("tool_use", think, tu), _resp("end_turn", SimpleNamespace(type="text", text="done")), _resp("end_turn", SimpleNamespace(type="text", text="again"))])
    ag = GeoAIAgent(platform, client=fc)
    ag.chat("s", "check Olaya")        # state changes during this turn (focus_detection appears)
    ag.chat("s", "and now?")           # second model turn with a different state
    assert len(fc.calls) == 3
    assert {c["system"] for c in fc.calls} == {SYSTEM_PROMPT}, "system prompt must be identical on every call (thinking blocks are bound to it)"
    assert fc.calls[0]["tools"] == fc.calls[2]["tools"]
    first = fc.calls[0]["messages"][0]["content"]
    assert first.startswith("[CURRENT OPERATIONAL CONTEXT") and first.rstrip().endswith("check Olaya")
    last = fc.calls[2]["messages"][-1]["content"]
    assert "focus_detection" in last and last.rstrip().endswith("and now?")        # the newer context rides in the newer message
    assert fc.calls[2]["messages"][0]["content"] == first                          # earlier messages are never edited (append-only history)
    assert any(getattr(b, "type", "") == "thinking" for b in fc.calls[2]["messages"][1]["content"])   # thinking block replayed unchanged


def test_rejected_thinking_block_is_dropped_and_retried(platform):
    think = SimpleNamespace(type="thinking", thinking="", signature="sig-old")
    err = Exception("Error code: 400 - messages.1.content.0: Invalid `signature` in `thinking` block. The block is bound to a different conversation.")
    fc = SnapClient([_resp("end_turn", think, SimpleNamespace(type="text", text="first")), err, _resp("end_turn", SimpleNamespace(type="text", text="recovered"))])
    ag = GeoAIAgent(platform, client=fc)
    ag.chat("r", "hello")
    r = ag.chat("r", "again")
    assert r["reply"] == "recovered" and r["mode"] == "claude"     # no fallback to the offline planner, no error shown to the user
    assert len(fc.calls) == 3
    retry_assistant = fc.calls[2]["messages"][1]["content"]
    assert not any(getattr(b, "type", "") == "thinking" for b in retry_assistant) and any(getattr(b, "type", "") == "text" for b in retry_assistant)
    assert "[CURRENT OPERATIONAL CONTEXT" in fc.calls[2]["messages"][-1]["content"]


def test_unrelated_api_errors_still_fall_back(platform):
    fc = SnapClient([Exception("Error code: 500 - overloaded")])
    ag = GeoAIAgent(platform, client=fc)
    assert "failed" in ag.chat("e", "show executive summary")["reply"].lower() and len(fc.calls) == 1   # not retried


# ---------------- QA-01: only a message that is an approval approves anything ----------------
def _crew_proposals(platform, agent):
    """Proposals made by the crew (another session), as on the Operation page."""
    platform.sim.scenario("multi_incident")
    agent.chat("crew-side", "detect possible water leaks in Riyadh")
    agent.chat("crew-side", "create incidents")
    agent.chat("crew-side", "Create work orders for the top five priority incidents.")
    pend = platform.approvals.pending()
    assert len(pend) >= 3
    return pend


def test_a_sentence_that_starts_with_an_approval_word_approves_nothing(platform, agent):
    pend = _crew_proposals(platform, agent)
    for text in ("Proceed to list the open incidents", "Confirmed. What next?", "Execute the scan", "Go ahead and show the executive summary",
                 "approve the budget for next year", "Rejected items, how many are there?", "تابع حركة المرور", "موافقة على عرض الموجز التنفيذي"):
        r = agent.chat("ops", text)
        assert not [t for t in r["trace"] if t["tool"].startswith("approval_gate")], text
        assert len(platform.approvals.pending()) == len(pend), text


def test_a_bare_approve_without_context_names_the_waiting_items_and_approves_nothing(platform, agent):
    pend = _crew_proposals(platform, agent)
    r = agent.chat("ops", "approve")
    assert len(platform.approvals.pending()) == len(pend)
    assert pend[0]["Approval_ID"] in r["reply"] and "APR-" in r["reply"]


def test_approve_with_an_id_approves_exactly_that_one(platform, agent):
    pend = _crew_proposals(platform, agent)
    target = pend[1]["Approval_ID"]
    r = agent.chat("ops", f"approve {target}")
    left = {a["Approval_ID"] for a in platform.approvals.pending()}
    assert target not in left and len(left) == len(pend) - 1 and "Executed" in r["reply"]


def test_approve_with_an_id_that_is_not_waiting_says_so(platform, agent):
    _crew_proposals(platform, agent)
    r = agent.chat("ops", "approve APR-9999")
    assert "APR-9999" in r["reply"] and "not waiting" in r["reply"]


def test_approve_all_for_items_this_conversation_did_not_propose_asks_first(platform, agent):
    pend = _crew_proposals(platform, agent)
    n = len(pend)
    r = agent.chat("ops", "approve all")
    assert len(platform.approvals.pending()) == n and f"approve all {n}" in r["reply"]
    r = agent.chat("ops", f"approve all {n + 1}")                     # a count that does not match the list shown is refused
    assert len(platform.approvals.pending()) == n
    r = agent.chat("ops", f"approve all {n}")
    assert r["reply"].count("Executed") == n and not platform.approvals.pending()


def test_reject_all_also_asks_first(platform, agent):
    pend = _crew_proposals(platform, agent)
    agent.chat("ops", "reject all")
    assert len(platform.approvals.pending()) == len(pend)


# ---------------- chat buttons: Approve/Reject only for this conversation's own proposal ----------------
def test_no_approve_button_when_this_conversation_proposed_nothing(platform, agent):
    _crew_proposals(platform, agent)
    r = agent.chat("ops", "show executive summary")
    assert not [s for s in r["suggestions"] if s.lower().startswith(("approve", "reject"))], r["suggestions"]
    assert "Show pending approvals" in r["suggestions"]


def test_approve_button_names_this_conversations_proposal_and_works(platform, agent):
    platform.sim.scenario("olaya_leak")
    agent.chat("s", "detect water leaks in Olaya")
    agent.chat("s", "create incidents")
    r = agent.chat("s", "create a work order for that incident")
    own = agent.session("s").ctx.state["pending_approval"]
    assert f"Approve {own}" in r["suggestions"] and f"Reject {own}" in r["suggestions"]
    n0 = platform.store.count(S.WORK_ORDERS)
    r = agent.chat("s", f"Approve {own}")                          # pressing the button sends its text
    assert "Executed" in r["reply"] and platform.store.count(S.WORK_ORDERS) == n0 + 1


def test_arabic_approve_button_carries_the_id(platform, agent):
    from backend.agent.agent import AR_REPLY
    platform.sim.scenario("olaya_leak")
    agent.chat("s", "detect water leaks in Olaya")
    agent.chat("s", "create incidents")
    agent.chat("s", "create a work order for that incident")
    own = agent.session("s").ctx.state["pending_approval"]
    tok = AR_REPLY.set(True)
    try:
        sug = agent._suggestions(agent.session("s"))
    finally:
        AR_REPLY.reset(tok)
    assert f"موافقة {own}" in sug and f"رفض {own}" in sug


def test_instructions_tell_the_ai_to_ask_for_the_id_in_chat():
    from backend.agent.prompts import SYSTEM_PROMPT
    assert "approve APR-" in SYSTEM_PROMPT and "موافقة APR-" in SYSTEM_PROMPT


@pytest.mark.parametrize("text", ["موافقة ⁦{id}", "موافقة ⁦{id}⁩", "‏موافقة {id}", "«موافقة {id}»", '"approve {id}"'])
def test_an_approval_copied_from_an_arabic_reply_still_approves(platform, agent, text):
    """Ids in Arabic replies are wrapped in invisible direction marks (U+2066..U+2069); copying the text carries them along, sometimes with quotes."""
    target = _crew_proposals(platform, agent)[0]["Approval_ID"]
    r = agent.chat("ops", text.format(id=target))
    assert target not in {a["Approval_ID"] for a in platform.approvals.pending()}, r["reply"][:120]


# ---------------- review finding 1: the approval check must never hang the server ----------------
def test_a_long_run_of_digits_after_approve_returns_at_once():
    import time
    from backend.agent.agent import approval_words
    for text in ("approve " + "1" * 40 + "x", "approve " + "APR-1 " * 60 + "zz", "موافقة " + "٣" * 40 + "س"):
        t = time.perf_counter()
        assert approval_words(text) is None
        assert time.perf_counter() - t < 0.2, text[:20]
    assert approval_words("approve APR-0012") == (True, " APR-0012")          # a normal approval still works
