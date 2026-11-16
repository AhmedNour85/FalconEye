# Riyadh City View, Plan 4: Field Maps Tasks for the City and Mobility Crews

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Status:** written 2026-11-16, **waiting for the user's review**. Nothing in it is built yet.

**Goal:** An investigator opens ArcGIS Field Maps on a phone, sees the tasks the crew assigned (city services and mobility), taps Answer, writes a note, taps Finish, and the crew assesses the answer, in English and Arabic, on a new web map that points at the `CityView` layers.

**Architecture:** The server side already writes `esritask_*` values and reads Field Maps answers (`backend/services/tasks.py`, `platform.py`). This plan adds the three mobility task types and the two Traffic Response assignees to that mapping, then adds three scripts: one prepares the hosted Work Orders layer for Tasks, one creates the new web map with its task settings, and the two carried-over scripts (form, Answer button) are pointed at it. Every account change is a dry run the user approves. The phone itself is tested by the user.

**Tech Stack:** Python 3.10, ArcGIS API for Python 2.4.2, FastAPI (unchanged), pytest.

**Spec:** `docs/superpowers/specs/2026-11-15-riyadh-city-view-design.md`, sections "Field Maps tasks", "The Field Maps map" and build phase 7. Ends at **Checkpoint 4**: you approve each dry run, then test on a phone.

## What I found in your account (read-only check, 2026-11-16)

- `CityView_Riyadh_Work_Orders` has **no** `esritask_*` fields. It has `Field_Maps_Status`, `Field_Verdict`, `Field_Comment`, edit and attachment support.
- There is **no** `CityView` web map yet.
- `GEOAI_FIELD_USERS` is **empty** in `.env`, so no investigator has an ArcGIS login yet.
- So the new map is the whole job: Field Maps has never been switched on for this layer. In the City project, Field Maps Designer did that step by hand and added the task fields itself.

## Decisions for you

| # | Decision | Proposal | Alternative |
|---|---|---|---|
| 1 | **How the map is made.** | **By script first.** A script reads the working City Investigator Map and its task settings (read only) and creates a new `CityView` map. It also adds the `esritask_*` fields to the Work Orders layer. This is unproven: Field Maps may refuse task settings made this way. If the phone shows "Tasks couldn't be loaded", we switch to the manual way. | **By hand.** I write a checklist (Task 6); you enable Tasks in Field Maps Designer (about 15 minutes); my scripts then add everything else. |
| 2 | **Investigator logins.** | Until you give real logins, all nine investigators map to the one test account, as the City project did. Tasks then show for that account only, and each task's assignee name is not a real person. | You send the nine ArcGIS usernames; I put them in `.env` (you edit that file, I never print it). |
| 3 | **Task text language on the phone.** | `GEOAI_FIELD_LANG=both`: Arabic paragraph first, then English, as the City project supports. The form choices are bilingual too. | `en` or `ar` only. |
| 4 | **Map name.** | `CityView Field Maps - Investigator Map`. One map for everyone; Field Maps groups tasks by assignee. | A map per team (city, traffic response): two maps to keep in step. |
| 5 | **Answer choices for mobility tasks.** | The same five answers as the city tasks (Yes confirmed / Not found / Need to look again / Escalate / Repaired). "Repaired" is rarely right for a closure, and the crew ignores it there. | Hide "Repaired" for mobility types. Needs a form rule per task type, which is less proven in Field Maps. |
| 6 | **What the map shows besides tasks.** | Work Orders (tasks), Field Verification, Incidents, Traffic Incidents, Planned Closures, Event Notices, and the reference layers if they are hosted. Read-only except Work Orders and Field Verification. | Work Orders and Field Verification only: lighter on the phone, no road context. |

## Global Constraints

- The two source projects are read-only. Reading the City Investigator Map is allowed; nothing in it is changed.
- ArcGIS Online is the system of record. Every account change is a dry run first, applied only after the user's yes, then read back. Only items titled `CityView*` and owned by the signed-in account are created or changed. Nothing is ever deleted by title. The prefix `GeoAIOps` is refused.
- No script has a default web-map id. A script changes a web map only when its id is given.
- Existing task-type codes never change: new types are appended after the last one.
- The in-app investigator form stays enabled next to Field Maps.
- Every number and sentence on the phone comes from the Python tools; nothing is carried out without a person's approval.
- English and Arabic for every new label and task sentence.
- Tests never contact ArcGIS Online; they use the memory stand-in and sample JSON.
- The four city-service use cases and the mobility crew keep working; their tests stay green.
- ArcGIS Maps SDK for JavaScript stays at 4.30. Commits are local only.
- I cannot use a phone. The "verified" alert after Answer, Note and Finish was never confirmed on a phone in the City project either; Checkpoint 4 is where you confirm it.

## Review Focus

1. **Field Maps refuses the scripted map or its task settings.** Dry run states this risk; apply stops at the first read-back mismatch and prints how to undo (delete is never scripted: the printed item ids are for you to remove). Manual fallback checklist ready in Task 6. Tests in Task 3 (read-back mismatch is reported, not hidden).
2. **A task is approved for an investigator who has no ArcGIS login.** The task stays Unassigned in Field Maps and the work order keeps its worker; nothing is lost and the in-app page still shows it. Tests in Task 1.
3. **The script runs twice, or a map with that title already exists.** The second run refuses to create a duplicate, names the existing item, and offers `--update <id>` for that one id. Test in Task 3.
4. **A bilingual task text is too long for the hosted field.** Arabic then English can pass 4,000 characters. The text is cut at a sentence boundary with the cut shown, never rejected by the server, and the scan is not rolled back. Test in Task 1.
5. **A mobility task answered in Field Maps.** "Yes, confirmed" on a closure or event task closes the incident without a repair step; "Not found" on a road-clear task re-opens the review. Same results as the in-app form. Tests in Task 2.

## Deviations from the spec

- The spec says the script "adds the task fields to the new Work Orders layer"; the read-only check shows the layer has none, so Task 3 defines them (type, domain, length) from the City layer's definition, read-only. If Field Maps later adds its own, the script's run is safe to repeat.
- The scripts carried from the City project are used as they are for the form and the Answer button; only the mobility wording and a `--layer-title` check are added.

## File Structure

| File | Responsibility |
|---|---|
| `backend/services/tasks.py` (modify) | Three mobility task types appended; long-text cut |
| `backend/platform.py` (modify) | Assignee list covers all nine workers |
| `scripts/field_maps_plan.py` (create) | Pure functions: build the new web map and task settings from the City reference JSON |
| `scripts/setup_field_tasks_layer.py` (create) | Dry run and apply: `esritask_*` fields and domains on the Work Orders layer |
| `scripts/create_field_maps_map.py` (create) | Dry run and apply: create the new web map with its task settings |
| `scripts/setup_field_maps_form.py`, `scripts/add_task_answer_action.py` (modify) | Accept the new map; mobility wording |
| `docs/field_maps.md` (modify) | `CityView` names, manual fallback checklist, phone test script |
| `tests/test_field_maps.py`, `tests/test_field_maps_scripts.py` (modify, create) | All tests |

---

### Task 1: Mobility task types, nine assignees, safe text length

**Files:**
- Modify: `backend/services/tasks.py`, `backend/platform.py:240-262`
- Test: `tests/test_field_maps.py`

**Interfaces:**
- Consumes: `tasks.TASK_TYPES`, `tasks.task_fields(wo, finding)`, `Platform.setup_field_tasks()`, `Platform.apply_field_users()`.
- Produces: `tasks.TASK_TYPES` ending with `"Traffic Incident", "Planned Road Closure", "Major Event Traffic Plan"` (appended after the visual types); `tasks.DESCRIPTION_LIMIT = 4000`; `tasks.description()` never longer than the limit.

- [ ] **Step 1: Write the failing tests** in `tests/test_field_maps.py`:
  - `test_mobility_task_types_are_appended_and_existing_codes_are_unchanged`: `TASK_TYPES[:13]` equals the current 13 names; the last three are the mobility names; a work order with `Incident_Type="Planned Road Closure"` maps to that name, not "Other".
  - `test_a_mobility_task_for_an_investigator_without_a_login_stays_unassigned`: assigned work order for WRK-008 with no `Assigned_To_Username` gives `esritask_status == 0` and `esritask_assignee is None`; with a username it gives status 1 and that username.
  - `test_the_assignee_list_covers_all_nine_workers`: with `field_users` for WRK-001 to WRK-009, `setup_field_tasks` passes nine usernames to `ensure_task_domains` (use a recording gateway).
  - `test_a_bilingual_description_never_passes_the_hosted_limit`: instructions of 3,500 characters with `LANG="both"` give `len(description) <= 4000`, ending at a sentence boundary with the Arabic and English marker "…" so the cut is visible.
- [ ] **Step 2: Run** `.\.venv\Scripts\python.exe -m pytest tests/test_field_maps.py -q -p no:cacheprovider`. Expected: the four new tests FAIL.
- [ ] **Step 3: Implement.** Append the three names in `tasks.py`; add `DESCRIPTION_LIMIT` and a `_fit(text)` that cuts at the last sentence end before the limit; `description()` returns `_fit(...)`. In `platform.py` make `setup_field_tasks` build users from every worker that has `ArcGIS_Username` or a `field_users` entry (all nine), not only those named in `field_users`.
- [ ] **Step 4: Run** the same command plus `tests/test_visual_types.py`. Expected: PASS (the existing `TASK_TYPES[:13]` test is unchanged).
- [ ] **Step 5: Commit** `feat: mobility task types and nine Field Maps assignees`.

### Task 2: Answers on mobility tasks behave like the in-app form

**Files:**
- Test: `tests/test_field_maps.py`; Modify only if a test fails: `backend/platform.py:176-190, 326` and `backend/services/field.py`.

**Interfaces:**
- Consumes: the test helpers `_assigned_work_order(platform)`, the fake gateway classes in that file that return an `esritask_status == 3` edit with `Field_Verdict`, `Field_Comment`, `esritask_notes`.
- Produces: nothing new; proves the existing flow for the three mobility types.

- [ ] **Step 1: Write the tests** (one parametrized over `traffic_incident`, `road_closure`, `major_event`, built through the real event flow as in `tests/test_mobility_workflow.py`):
  - `test_finishing_a_mobility_task_in_field_maps_with_yes_confirmed_closes_it_without_a_repair_step` (closure and event close; the traffic incident goes to the "cleared" step).
  - `test_finishing_with_not_found_asks_for_a_further_look_and_does_not_close`.
  - `test_a_note_alone_still_works_on_a_mobility_task` (first word "Confirmed").
  - `test_the_task_text_of_a_mobility_task_is_bilingual` (`LANG="both"`: Arabic paragraph contains no Latin sentence from the English instructions except road names, ids and numbers).
- [ ] **Step 2: Run** `pytest tests/test_field_maps.py -q -p no:cacheprovider -k mobility`. Expected: PASS if the flow already holds; any FAIL is a real defect to fix in the files above under TDD.
- [ ] **Step 3: Fix** any failure; **Step 4: re-run** the file. Expected: PASS.
- [ ] **Step 5: Commit** `test: Field Maps answers on mobility tasks`.

### Task 3: The planner for the new map and the task fields

**Files:**
- Create: `scripts/field_maps_plan.py`
- Test: `tests/test_field_maps_scripts.py` (with small hand-written sample JSON: a reference web map, a `tasks-configuration.json`, layer urls)

**Interfaces:**
- Produces:
  - `plan_task_fields(existing_fields: list[dict], types: list[str], users: dict[str, str]) -> tuple[list[dict], list[str]]`: the `esritask_*` field definitions still missing (`esritask_type` coded integer, `esritask_assignee` coded text 128, `esritask_status` coded 0..3, `esritask_priority` coded 0..4, `esritask_duedate` date, `esritask_description` and `esritask_notes` text 4000) and the plain-language change list. Nothing existing is altered.
  - `plan_web_map(reference: dict, layer_urls: dict[str, str], title: str) -> tuple[dict, list[str]]`: a new web map definition: reference basemap and extent; operational layers for the layers named in decision 6 with `CityView` urls and titles; the Work Orders form copied from the reference; a change list. No City item id or url remains in the result.
  - `plan_tasks_config(reference_cfg: dict, work_orders_layer_id: str) -> tuple[dict, list[str]]`: the task settings with new ids, pointing at the new layer.
  - `find_existing(items, title) -> item | None`.
- Consumes: `scripts/_guard.own_item_or_exit`.

- [ ] **Step 1: Write the failing tests:**
  - `test_task_fields_are_planned_only_when_missing` (none present gives seven definitions; all present gives none; one present gives the other six).
  - `test_the_new_map_points_only_at_cityview_layers` (no City id, no `GeoAIOps` string anywhere in the dumped JSON).
  - `test_the_task_settings_point_at_the_new_work_orders_layer`.
  - `test_the_planner_does_not_change_its_input` (deep-compare the reference before and after).
  - `test_an_existing_map_with_the_title_is_found_so_nothing_is_created_twice`.
- [ ] **Step 2: Run** `pytest tests/test_field_maps_scripts.py -q -p no:cacheprovider`. Expected: FAIL (module missing).
- [ ] **Step 3: Implement** the four functions as pure code (no network). Field definitions copy type, length and domain shape from the City layer only through the `reference` argument, never from a live call here.
- [ ] **Step 4: Run** the file. Expected: PASS.
- [ ] **Step 5: Commit** `feat: planner for the Field Maps map and task fields`.

### Task 4: Dry-run and apply scripts for the layer and the map

**Files:**
- Create: `scripts/setup_field_tasks_layer.py`, `scripts/create_field_maps_map.py`
- Test: `tests/test_field_maps_scripts.py`

**Interfaces:**
- Consumes: Task 3 functions; `ArcGISGateway`; `own_item_or_exit`.
- Produces: both scripts take `--apply` (dry run without it) and print what they would change. `create_field_maps_map.py` also takes `--reference <City map id>` (required, read only), `--update <new map id>` (for a repeat run), and `--title`. Both refuse any title not starting with `CityView`. `main(argv, gateway=None) -> int` so tests pass a recording fake.

- [ ] **Step 1: Write the failing tests** with a recording fake gateway:
  - `test_dry_run_changes_nothing` (fake records zero writes for both scripts).
  - `test_apply_adds_fields_then_reads_them_back` and `test_a_read_back_mismatch_stops_and_says_so` (exit code 1, message names the field).
  - `test_the_map_script_refuses_a_second_map_with_the_same_title` (exit code 1, names the existing id, no write).
  - `test_the_scripts_refuse_a_geoaiops_title_and_a_missing_reference_id`.
  - `test_a_backup_of_the_layer_definition_is_saved_before_the_fields_are_added` (a file under a temp `data/backups`).
- [ ] **Step 2: Run** the file. Expected: the new tests FAIL.
- [ ] **Step 3: Implement** both scripts around the Task 3 planners; the layer script writes the definition JSON backup, calls `add_to_definition`, reads the fields back; the map script reads the reference map and its `tasks-configuration.json` (read only), creates the item (new item, never an overwrite), writes the task settings resource, and reads both back.
- [ ] **Step 4: Run** the file. Expected: PASS.
- [ ] **Step 5: Commit** `feat: scripts to prepare the layer and create the Field Maps map`.

### Task 5: Form and Answer button on the new map, mobility wording

**Files:**
- Modify: `scripts/setup_field_maps_form.py`, `scripts/add_task_answer_action.py`
- Test: `tests/test_field_maps_scripts.py`

- [ ] **Step 1: Write the failing tests:** `test_the_form_plan_is_bilingual_when_asked` (`--lang both` gives Arabic and English for the heading, hint and five choices; saved codes unchanged), `test_the_answer_action_is_added_once_after_finish` (run twice, one action), `test_both_scripts_refuse_a_map_without_the_prefix`. Sample JSON only.
- [ ] **Step 2: Run** the file. Expected: FAIL for any behaviour not already present (the scripts already hold most of it; the test pins it).
- [ ] **Step 3: Implement** the small gaps found (mobility hint sentence, the prefix check on the layer title).
- [ ] **Step 4: Run** the file and then the full suite. Expected: all green.
- [ ] **Step 5: Commit** `feat: Field Maps form and Answer button for the CityView map`.

### Task 6: Documents and the phone test script

**Files:**
- Modify: `docs/field_maps.md`, `docs/arcgis_checks.md`, `README.md`

- [ ] **Step 1:** Rewrite `docs/field_maps.md` for `CityView` layer names, the three mobility task types, the nine assignees, and `GEOAI_FIELD_LANG`.
- [ ] **Step 2:** Add **"If the scripted map does not load: the manual way"**: a numbered checklist for Field Maps Designer (add the `CityView_Riyadh_Work_Orders` layer, switch on Tasks, set the Unassigned/Assigned/In progress/Completed layouts, save), then which scripts to run.
- [ ] **Step 3:** Add **"Phone test script (Checkpoint 4)"**: sign in as the test account; sync the map; see the task grouped under Assigned; open a closure task; read the Arabic then English text; tap Start, then Answer (pick list shows both languages), type a note, attach a photo, tap Finish; then in the command center: the "verified" alert appears within 15 seconds, the incident closes without a repair step, the audit trail shows the answer. Record pass or fail for each line.
- [ ] **Step 4:** Add the Plan 4 status row to `README.md`.
- [ ] **Step 5: Commit** `docs: Field Maps for CityView, manual fallback and phone test script`.

### Task 7: Checkpoint 4 (live, only with your yes at each step)

No code. Each step shows its output to you and waits.

- [ ] **Step 1: Dry run: layer.** `python scripts/setup_field_tasks_layer.py`. You read the seven fields and the domains it would add. You say yes or no.
- [ ] **Step 2: Apply the layer change** (backup saved first), read the fields back, show you the result.
- [ ] **Step 3: Dry run: map.** `python scripts/create_field_maps_map.py --reference <City Investigator Map id you give me>`. You read the layer list and the task settings. You say yes or no.
- [ ] **Step 4: Apply the map.** Read it back: item id, layers, `tasks-configuration.json`.
- [ ] **Step 5: Dry run then apply the form** (`setup_field_maps_form.py --lang both --webmap <new id>`) and **the Answer button** (`add_task_answer_action.py --webmap <new id>`), each shown to you first.
- [ ] **Step 6: Task domains.** With your answer to decision 2, the app applies the task-type and assignee lists to the layer (`setup_field_tasks`, shown to you first).
- [ ] **Step 7: Server side live check (mine).** Approve one mobility assignment in the running app; read the work order back from ArcGIS Online and show the `esritask_*` values; edit the row as Field Maps would; show the crew's reaction. Re-time the 15-second refresh with 32 layers and report the number.
- [ ] **Step 8: Phone test (yours).** Run the phone test script from Task 6 and tell me each line's result. If the phone shows "Tasks couldn't be loaded", we take the manual way (decision 1) and I adjust the plan.

## Self-review

- **Spec coverage:** three mobility task types (Task 1), two new assignees and the assignee list (Task 1), new map pointing at `CityView` layers and task fields (Tasks 3 and 4), Answer button and bilingual form (Task 5), the Field Maps answers flow for mobility (Task 2), dry runs, phone test, Checkpoint 4 (Tasks 6 and 7). No gap found.
- **Open items this plan closes or reports:** 15-second refresh not re-timed with 32 layers (Task 7, step 7); photo attachment live check (Task 7, step 8). Open and not in this plan: API key versus password sign-in, store status text not translated, the Esri documentation server not connected.
- **Names checked:** `plan_task_fields`, `plan_web_map`, `plan_tasks_config`, `find_existing` are defined in Task 3 and used with the same names in Task 4.
