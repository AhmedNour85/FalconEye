# Riyadh City View, Plan 5: Interface, Ask the Crew, Daily Brief, Access and Finish

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Status:** built and approved (Checkpoint 5, 2026-11-17).

**Goal:** The command center and the Executive Hub show the mobility story clearly (lifecycle strip, strategy table, four mobility numbers, trend and hotspots); operators can ask the crew mobility questions in English and Arabic; a one-page daily brief downloads as a PDF; every API route is protected; and the whole project is checked, documented and ready for your final review.

**Architecture:** Everything shown is computed by Python and sent to the pages as data: a lifecycle position per alert, a strategy comparison per scenario, mobility numbers beside the city numbers. Ask-the-crew maps a question to the mobility tools already in the registry (Plan 3). The brief reuses the Transportation PDF and Arabic shaping approach. The access guard is one middleware in front of every route. No new hosted layers and no ArcGIS Online change are planned, except the optional demo-leak move in decision 3.

**Tech Stack:** Python 3.10, FastAPI, vanilla JavaScript, ArcGIS Maps SDK for JavaScript 4.30, reportlab, arabic-reshaper, python-bidi (decision 1).

**Spec:** `docs/superpowers/specs/2026-11-15-riyadh-city-view-design.md`, sections 4 (Operation page, Executive Hub), 7 (Ask the crew, Daily brief, Roles and access, Languages) and build phases 8 to 11. Ends at **Checkpoint 5**: final review.

## Decisions for you

| # | Decision | Proposal | Alternative |
|---|---|---|---|
| 1 | **Three new Python packages** for the PDF: `reportlab`, `arabic-reshaper`, `python-bidi` (the Transportation project uses the same three). | Install them into `.venv` and add them to `requirements.txt`. If they are missing, the English brief still works and the Arabic brief says why it cannot be made. | No PDF: the brief becomes an HTML page you print. Nothing to install, no Arabic shaping. |
| 2 | **Access protection.** The design ports Transportation's guard. | **Local mode by default**: the API answers only to this computer. **Token mode** when `API_TOKENS` is set: every route needs a token that maps to a role (viewer, investigator, operator). The role header used today is ignored in token mode. | Keep only the role header (demo-grade, anyone who can reach the port can claim "operator"). |
| 3 | **The demo water leak sits 87 m from the nearest road**, outside the 60 m road-impact rule, so the headline story cannot be shown without picking another incident by hand. | Move the demo leak onto a modelled arterial in the generator. The live record needs **Reset demo**, which I show as a dry run first (it empties and refills the `CityView` demo layers, with your yes). | Keep the demo data; use INC-0010 (0.1 m from a road) with "Request inspection" for the headline story. No account change. |
| 4 | **Closures after their window.** Today an "In Place" closure stays on the map after its end time. | Hide a closure from the map and the Executive Hub numbers once its end time has passed; the record stays, with status "Ended". | Leave as is. |
| 5 | **Daily brief contents.** | One A4 page: the date, "Synthetic and modelled data" label, the four city numbers, the four mobility numbers, the three most urgent open items, the latest closure or event with its recommended strategy, and a pending-approvals count. English or Arabic. | Your list. |
| 6 | **Demo script.** The design asks for one at the finish. | A two-minute walk-through in `docs/demo_script.md`: the headline story, then one city-service story, then Arabic. | Skip it. |

## Global Constraints

- The two source projects are read-only.
- ArcGIS Online is the system of record. No local database. Every account change is a dry run first, applied only after the user's yes, then read back. Only `CityView*` items owned by the signed-in account are touched. Nothing is deleted by title. `GeoAIOps` is refused.
- Every number on screen and in the PDF comes from a Python tool, never from a language model.
- Nothing is carried out without a person's approval.
- Simulation results are labelled "Modelled"; road reports, accident history and asset condition "Synthetic".
- The 60-second crew scan never waits for a simulation.
- The four city-service use cases and the mobility crew keep working; their tests stay green without edits to what they assert.
- English and Arabic for every new label, sentence and answer; a test parses every `T("...")` literal against the Arabic dictionary.
- ArcGIS Maps SDK for JavaScript stays at 4.30.
- Tests never contact ArcGIS Online.
- Commits are local only.

## Review Focus

1. **Arabic PDF cannot be built** (packages missing or font not found). The English brief is unaffected; the Arabic request returns a clear message naming what is missing, never a broken file. Test in Task 6.
2. **Token mode with a missing, wrong or viewer-level token.** Every route answers 401 or 403, including routes that were open before; the health route answers without data. Tests in Task 5.
3. **Mobility numbers before any model, trend or closure exists.** Cards show "not available yet" instead of zero or an error; the trend line draws without mobility points. Tests in Task 3.
4. **A question names a road or place the model does not know, or has no time window.** The crew says what it could not find and lists the roads it knows; it never invents numbers. Tests in Task 4.
5. **An alert for a rejected or expired proposal, or for an incident closed without a repair step.** The lifecycle strip shows the real position (stopped at Proposed; Resolved without a Verified-repair step), not a full or empty strip. Tests in Task 1.

## Deviations from the spec

- The spec lists the lifecycle strip as seven steps without naming them; Task 1 names them: Detected, Analysed, Proposed, Approved, Dispatched, Verified, Resolved.
- Mobility in the trend series and the closed-closure hiding (decision 4) come from the Plan 3 deferred minors.

## File Structure

| File | Responsibility |
|---|---|
| `backend/services/lifecycle.py` (create) | Position of an incident on the seven steps |
| `backend/services/mobility_numbers.py` (create) | The four mobility numbers, the trend series and the congestion hotspots |
| `backend/agent/mobility_questions.py` (create) | Turns an English or Arabic question into a mobility tool call; builds the answer sentence |
| `backend/security/guard.py` (create) | Local mode, token mode, headers |
| `backend/services/brief.py`, `backend/services/pdf_arabic.py` (create, ported) | One-page PDF in English or Arabic |
| `backend/api/app.py` (modify) | New routes, guard, closure hiding |
| `frontend/nccc.js`, `mobility.js`, `strategic_dashboard.js`, `index.html`, `strategic_dashboard.html`, `i18n.js`, `mobility.css` (modify) | Strip, table, cards, toggles, brief button, Arabic |
| `docs/demo_script.md`, `docs/arcgis_checks.md`, `README.md` (create, modify) | Finish |

---

### Task 1: Lifecycle strip

**Files:** Create `backend/services/lifecycle.py`; modify `backend/orchestration/crew.py` (`notifications()`), `frontend/nccc.js`, `frontend/mobility.css`, `frontend/i18n.js`; tests `tests/test_lifecycle.py`.

**Interfaces:**
- Produces: `lifecycle.STEPS: list[str]` (the seven keys above); `lifecycle.position(store, incident_id: str) -> dict` returning `{"steps": [{"key": str, "state": "done"|"current"|"todo"|"stopped"}], "current": str, "outcome": "open"|"rejected"|"resolved"}`. Each notification dict gains `lifecycle` (None when it has no incident).

- [ ] **Step 1: Write failing tests:** `test_a_new_incident_is_at_detected`; `test_a_traffic_plan_awaiting_approval_is_at_proposed`; `test_a_rejected_proposal_stops_at_proposed_and_says_rejected`; `test_a_dispatched_closure_is_at_dispatched`; `test_a_closure_resolved_without_a_repair_visit_is_resolved_with_verified_done`; `test_every_alert_carries_a_lifecycle` (city and mobility; ordered, exactly one `current` unless resolved or rejected).
- [ ] **Step 2: Run** `pytest tests/test_lifecycle.py -q -p no:cacheprovider`. Expected: FAIL (module missing).
- [ ] **Step 3: Implement** `position` from the incident status, its approvals and work orders (read-only; no new stored field).
- [ ] **Step 4: Front end:** `nccc.js` draws the strip under each alert; step names go through `T()`; Arabic entries added to `i18n.js` (RTL: the strip reverses).
- [ ] **Step 5: Run** `pytest tests/test_lifecycle.py tests/test_i18n.py -q -p no:cacheprovider`. Expected: PASS. **Commit** `feat: lifecycle strip on every alert`.

### Task 2: Compare strategies

**Files:** Modify `backend/api/app.py`, `frontend/nccc.js`, `frontend/mobility.js`, `frontend/mobility.css`, `frontend/i18n.js`; tests `tests/test_mobility_api.py`.

**Interfaces:**
- Consumes: scenario rows (Plan 3) and `Jobs.request_preview`.
- Produces: `GET /api/mobility/scenarios/{id}/strategies` returning `{"scenario_id", "label": "Modelled", "recommended": str, "strategies": [{"key","name","verdict","trip_hours","delay_min","affected_segments","cost_note"}], "assumptions": [str]}`; 404 unknown id; 409 when the scenario was not a closure; 503 with `Retry-After: 3` while the comparison is being recalculated.

- [ ] **Step 1: Read** one live scenario row and list what it stores (note the result in the ledger). Decide from it whether the table is read from the row or recalculated through the job worker; recalculation reuses the Plan 3 preview path.
- [ ] **Step 2: Write failing tests:** the route returns five strategies, exactly one `recommended`, the "Modelled" label and a non-empty assumptions list; the three error codes above.
- [ ] **Step 3: Implement** the route; **Step 4:** a "Compare strategies" button on closure alerts opens a table (recommended row highlighted, "Modelled" badge, assumptions under the table), English and Arabic.
- [ ] **Step 5: Run** `pytest tests/test_mobility_api.py tests/test_i18n.py -q -p no:cacheprovider`. Expected: PASS. **Commit** `feat: strategy comparison table`.

### Task 3: Executive Hub mobility numbers, trend, hotspots, toggles

**Files:** Create `backend/services/mobility_numbers.py`; modify `backend/api/app.py` (executive summary route), `frontend/strategic_dashboard.js`, `strategic_dashboard.html`, `frontend/i18n.js`; tests `tests/test_mobility_numbers.py`.

**Interfaces:**
- Produces: `mobility_numbers.summary(platform) -> dict` with `peak_delay_ratio: float|None`, `severe_segments: int|None`, `worst_hospital_minutes: float|None`, `planned_closures: int`, `label: "Modelled"`; `trend(platform) -> list[{"day": str, "incidents": int, "mobility_incidents": int}]`; `hotspots(platform, top_n=3) -> list[{"road","kind":"congestion","score"}]`. Fields are `None` before the model is ready; closures count only those whose window has not ended (decision 4).

- [ ] **Step 1: Write failing tests:** numbers equal what the tools return for the skeleton network; `None` and a "not available yet" card when the model is not ready; an ended closure is not counted or drawn; the trend contains mobility incidents; hotspots rank by score and mix with city hotspots.
- [ ] **Step 2: Run** `pytest tests/test_mobility_numbers.py -q -p no:cacheprovider`. Expected: FAIL.
- [ ] **Step 3: Implement**; closure hiding uses the existing `Ended` status path from Plan 3 (set it when the end time passes, during the scan).
- [ ] **Step 4: Front end:** four cards with a "Modelled" badge; Traffic and Metro layer toggles on the Hub map; the hotspots strip includes congestion.
- [ ] **Step 5: Run** the test file plus `tests/test_mobility_api.py`. Expected: PASS. **Commit** `feat: mobility numbers on the Executive Hub`.

### Task 4: Ask the crew, mobility questions in English and Arabic

**Files:** Create `backend/agent/mobility_questions.py`; modify `backend/agent/agent.py` (`_rule_turn`), `backend/agent/ar.py`, `frontend/i18n.js`; tests `tests/test_mobility_questions.py`.

**Interfaces:**
- Produces: `mobility_questions.parse(text: str) -> dict | None` returning `{"intent": one of "closure_impact"|"best_response"|"demand_growth"|"event_impact"|"hospital_access"|"maintenance_priority"|"traffic_now", "args": dict}` or `None`; `answer(intent, result: dict, lang: str) -> str` (sentences built from the tool's numbers only).
- Consumes: registry tools `simulate_closure`, `compare_closure_strategies`, `simulate_event`, `hospital_access`, `road_safety_context`, `traffic_state`.

- [ ] **Step 1: Write failing tests**, one per intent in English and Arabic, with the questions from the design: "What if King Fahd Road is closed tomorrow from 8 to 4?", "Best response to a closure on King Fahd Road", "What happens to traffic if 40,000 people attend an event at King Fahd Stadium?", "How long to reach hospitals now?", "Which road segments need maintenance first?", "Traffic now". Assert the tool called, its arguments (corridor, hours, attendance) and that every number in the answer appears in the tool result.
- [ ] **Step 2: Run** `pytest tests/test_mobility_questions.py -q -p no:cacheprovider`. Expected: FAIL.
- [ ] **Step 3: Implement** `parse` with ordered patterns (reusing the Transportation planner's time-window parsing as an idea, rewritten here, not copied wholesale) and wire it into `_rule_turn` before the city-service rules; unknown road or place gives the "I could not find" sentence listing known roads. Language-model planners need no change: the tools are already in the registry.
- [ ] **Step 4: Test** `test_an_unknown_road_is_reported_not_guessed` and `test_a_closure_question_needs_a_proposal_to_be_acted_on` (the answer is information; it creates no approval).
- [ ] **Step 5: Run** the file and `tests/test_agent*.py`. Expected: PASS. **Commit** `feat: ask the crew mobility questions`.

### Task 5: Roles and protection

**Files:** Create `backend/security/guard.py`; modify `backend/api/app.py`, `config/settings.py`, `.env.example`; tests `tests/test_security.py`.

**Interfaces:**
- Produces: `Guard(mode: "local"|"token", tokens: dict[str, str])`; `guard.check(request) -> role | raises HTTPException(401|403)`; `apply_headers(response)` adding `X-Content-Type-Options`, `Referrer-Policy`, `X-Frame-Options` and `Content-Security-Policy-Report-Only` (allowing the ArcGIS hosts the pages use). Settings: `api_tokens: dict[str, str]` from `API_TOKENS=token=role,...`.

- [ ] **Step 1: Write failing tests:** local mode refuses a non-loopback client with 403 and accepts loopback; token mode refuses a missing token (401), an unknown token (401) and a viewer-level token on an approval route (403); the role header is ignored in token mode; every route under `/api` goes through the guard (iterate `app.routes` and assert none is unguarded except health and static pages); headers are present; the policy is report-only.
- [ ] **Step 2: Run** `pytest tests/test_security.py -q -p no:cacheprovider`. Expected: FAIL.
- [ ] **Step 3: Implement** the guard as one dependency applied to the router, replacing the per-route `role(...)` checks by role lookups from the guard; the existing role names (viewer, worker, operator) stay.
- [ ] **Step 4: Run** the whole suite. Expected: PASS (existing tests run in local mode as before).
- [ ] **Step 5: Commit** `feat: guard on every route, token mode, security headers`.

### Task 6: Daily brief PDF

**Files:** Create `backend/services/brief.py`, `backend/services/pdf_arabic.py` (ported idea, own code); modify `backend/api/app.py`, `requirements.txt`, `frontend/strategic_dashboard.html`, `frontend/strategic_dashboard.js`, `frontend/i18n.js`; tests `tests/test_brief.py`.

**Interfaces:**
- Consumes: `mobility_numbers.summary`, the executive summary, pending approvals (Tasks 3 and the existing code).
- Produces: `brief.build(platform, lang: "en"|"ar") -> bytes`; `GET /api/brief.pdf?lang=en|ar` (`application/pdf`, guarded as a viewer route); `pdf_arabic.ArabicUnavailable`.

- [ ] **Step 1: Write failing tests:** the English brief starts with `%PDF`, is one page, and its text contains the "synthetic and modelled" label and the numbers from `summary`; the Arabic brief contains shaped Arabic text and the same numbers; with the Arabic libraries made unavailable the route answers 503 with a message naming them while English still answers 200; the file is built from data only (no stored copy).
- [ ] **Step 2: Run** `pytest tests/test_brief.py -q -p no:cacheprovider`. Expected: FAIL.
- [ ] **Step 3: Install** the packages with your yes (decision 1), then implement.
- [ ] **Step 4:** a "Download daily brief" button in Executive Briefs, with an English and an Arabic link.
- [ ] **Step 5: Run** the test file. Expected: PASS. **Commit** `feat: daily brief PDF in English and Arabic`.

### Task 7: Demo leak, Arabic pass, documents, full check

**Files:** Modify `backend/services/synthetic.py` (only if decision 3 is yes), `docs/arcgis_checks.md`, `README.md`; create `docs/demo_script.md` (decision 6); tests `tests/test_synthetic*.py`.

- [ ] **Step 1 (decision 3 yes):** write `test_the_demo_leak_is_within_the_road_impact_rule_of_a_modelled_arterial`; move the leak in the generator until it passes; the existing demo tests stay green.
- [ ] **Step 2: Arabic pass.** Add a test that renders every alert kind, strategy name, lifecycle step, brief label and mobility answer in Arabic and fails on any English sentence left (road names, ids and numbers excepted).
- [ ] **Step 3: Documents.** Update the README status table and `docs/arcgis_checks.md`; write `docs/demo_script.md`.
- [ ] **Step 4: Full check.** Run the whole suite (about 9 minutes); open the pages in the browser at desktop and phone width, in English and Arabic, and report anything that is wrong with a screenshot or text.
- [ ] **Step 5 (decision 3 yes, with your yes):** show the **Reset demo** dry run (what is emptied and refilled), apply it, run the headline story live (leak repair with the road-impact line, then approval), and read the result back from ArcGIS Online.
- [ ] **Step 6: Commit** `docs: demo script, status and final checks`; give you the final list: rulings I made, deferred minors, open items.

## Self-review

- **Spec coverage:** lifecycle strip (Task 1), strategy table (2), Hub mobility numbers, map toggles, hotspots and the trend (3), Ask-the-crew questions (4), roles and protection (5), daily brief (6), Arabic pass, documentation, demo script and full check (7). The feed cards and the Simulate menu were built in Plan 3. No gap found.
- **Names:** `lifecycle.position`, `mobility_numbers.summary/trend/hotspots`, `mobility_questions.parse/answer`, `Guard`, `brief.build` are defined in their tasks and used with the same names in Tasks 6 and 7.
- **Open items this plan closes:** mobility missing in the trend series, In Place closures staying on the map, the demo leak outside the 60 m rule. Left open: API key versus password sign-in, store status text not translated, the Esri documentation server not connected, road names English in popups.
