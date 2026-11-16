# Field reports through ArcGIS Field Maps (Riyadh City View)

ArcGIS Field Maps is the main way investigators receive tasks and report. The in-app investigator page (`/field.html`) stays enabled next to it
(`GEOAI_FIELD_FORM=1`). Both write to the same hosted layers, so a report from either is assessed the same way.
All layers are titled `CityView_<name>`. Nothing here touches the Agentic_AI_City layers (`GeoAIOps_*`), which the app refuses.

## The task types

A task's title in Field Maps is the work order's incident type. Existing codes never change; new types are appended.

| Crew | Task titles |
|---|---|
| City services | Water Leak (Suspected), Water Leak, Streetlight Failure (Predicted), Streetlight Failure, Streetlight Cluster Maintenance, Streetlight Pole Inspection, Visual Distortion Review, Visual Distortion, Urban Change Review, Urban Change, Land-Use Violation Review, Urban Case, Other, and the visual types |
| Mobility (Plan 4) | **Traffic Incident** ("Confirm the road is clear"), **Planned Road Closure** ("Confirm the closure is in place"), **Major Event Traffic Plan** ("Confirm the traffic plan is in place") |

## The nine investigators

Seven city-service investigators (WRK-001 to WRK-007) and two Traffic Response investigators: Bandar Al-Shehri (WRK-008) and Rayan Al-Anazi (WRK-009).
Set each one's ArcGIS login in `.env`, comma separated, worker id = login:

```
GEOAI_FIELD_USERS=WRK-001=nawaf.harbi,WRK-002=khalid.otaibi,...,WRK-009=rayan.anazi
```

Until real logins are given, map all nine to the one test account. A task approved for an investigator who has no login stays in the **Unassigned** list in Field Maps; the in-app page still shows it, nothing is lost.
`GEOAI_FIELD_LANG` sets the task text on the phone: `en`, `ar`, or `both` (Arabic paragraph first, then English). The text never passes 4,000 characters; a longer text is cut at a sentence end and marked with "…".

## How a task and an answer travel

1. A person approves an assignment in the command center. The work order on `CityView_Riyadh_Work_Orders` is updated with the worker, the login, the due date, `Field_Maps_Status = Sent to ArcGIS Field Maps` and the task fields (`esritask_type`, `esritask_assignee`, `esritask_status`, `esritask_priority`, `esritask_duedate`, `esritask_description`).
2. The investigator syncs the map, taps the task, taps **Start**, then **Answer** (pick list), **Note** (what they saw), optionally **Attach**, and **Finish**.
3. The server reads the hosted layers every `GEOAI_FIELD_SYNC_SECONDS` (default 15). Finish becomes the report, which is assessed like any other: the operator gets a "verified" alert, and the incident moves on.
4. For a closure or event plan, "Yes, confirmed" is enough: there is nothing to repair, so the incident can be closed once a person approves. A traffic incident needs a second, "road cleared" step.

## One-time setup (every step is a dry run first)

Run each command without `--apply` first, read the output, then run it again with `--apply`.

```bash
.venv\Scripts\python.exe scripts\setup_field_tasks_layer.py                          # 1. the task fields on the Work Orders layer
.venv\Scripts\python.exe scripts\create_field_maps_map.py --reference <City map id>  # 2. the new web map and its task settings
.venv\Scripts\python.exe scripts\setup_field_maps_form.py --webmap <new map id>      # 3. the answer form (--lang en|ar|both)
.venv\Scripts\python.exe scripts\add_task_answer_action.py --webmap <new map id>     # 4. the Answer button
```

- Step 1 adds only missing fields and saves the layer definition in `data/backups/` first.
- Step 2 reads the City project's working Investigator Map (never changes it) and creates a **new** private web map, `CityView Field Maps - Investigator Map`. A second run refuses to create a duplicate and names the existing map; `--update <id>` repeats the change on that one map after saving a backup.
- Steps 3 and 4 only change the map id you give them, and only maps titled `CityView*` owned by the signed-in account.
- No script deletes anything. To undo, restore the backup files the scripts print.
- The map's layers are Work orders (tasks), Field verification, Incidents, Traffic incidents, Planned closures and Event notices. Who can edit a layer is set by the hosted layer, not by the map.

Task actions live in the map's hidden resource `tasks-configuration.json`. Its `layerId` must be the id of the Work orders layer in that map (`WorkOrders_tasks` here), otherwise Field Maps shows "Tasks couldn't be loaded".

### Radio buttons cannot be on a task: the Answer button

Field Maps tasks cannot show radio buttons on Finish or Note, so the task has **Finish | Answer | Note | Attach**. Answer opens a pick list: **Yes, confirmed / Not found / Need to look again / Escalate / Repaired** (field `Field_Verdict`). The radio buttons stay on the **Field verification** report form (the **+** button). The saved codes (`Confirmed`, `Rejected`, `Needs Further Inspection`, `Escalate`, `Repaired`) never change, whatever language the labels use.
"Repaired" is rarely right for a closure or an event plan; the crew does not use it there.

## If the scripted map does not load: the manual way

Field Maps may refuse task settings made by a script ("Tasks couldn't be loaded"). Then make the map by hand; this is how the City map was made (about 15 minutes):

1. Run step 1 above, or let Field Maps add the task fields itself in step 4 below (either way, do not add them twice).
2. In **Field Maps Designer**, create a new map named `CityView Field Maps - Investigator Map`. Add `CityView_Riyadh_Work_Orders` and `CityView_Riyadh_Field_Verification`; add the other layers from the list above for context.
3. Open the Work orders layer, choose **Tasks**, and switch Tasks on. Accept the three lists (types, assignees, status) Designer proposes. Keep the layouts Unassigned, Assigned, In progress, Completed.
4. Save the map. Note its item id (in the address bar).
5. Run steps 3 and 4 of the setup with `--webmap <that id>`, each as a dry run first.
6. Re-run the app's task setup (restart the server): it fills the task-type and assignee lists on the layer.

## Phone test script (Checkpoint 4)

Do these on a phone with the Field Maps app, signed in as the account that owns the tasks. Write pass or fail for each line.

1. Open `CityView Field Maps - Investigator Map` and sync. The map opens; the Tasks tab loads.
2. In the command center, simulate a road closure, approve the closure plan, then approve the assignment to a Traffic Response investigator.
3. Sync. The task **Planned Road Closure** appears under Assigned, with the Arabic paragraph first and the English one after it (when the language is `both`).
4. Tap the task, then **Start**. Within 15 seconds the command center shows the assignment as accepted.
5. Tap **Answer**: the pick list shows five choices in both languages. Choose **Yes, confirmed**.
6. Tap **Note** and type a sentence; tap **Attach** and add a photo.
7. Tap **Finish**. Within 15 seconds the command center shows a "verified" alert, the incident is Confirmed, and the closure can be closed without a repair step. The audit trail shows the answer.
8. Repeat once with a city-service task (a water leak) and answer **Not found**: the incident goes to "Requires Further Inspection".
9. Repeat with a Traffic Incident task: after **Yes, confirmed** the incident still needs a "road cleared" step.
10. Open the Field verification layer (the **+** button) and file one report with GPS and a photo; the server assesses it the same way.

The "verified" alert after Answer, Note and Finish was never confirmed on a phone in the City project either; this is the first real test.

## Rules the server applies

- The GPS point of a report is compared with the finding; further than 150 m away is weak evidence ("Requires Further Inspection").
- A report with no GPS point is never strong evidence.
- An invalid or empty answer falls back to the Note's first word (`Confirmed`, "Yes", `Rejected`, "Not found", `Repaired`, `Escalate`, "Need to look again"); no verdict word becomes "Needs Further Inspection".
- Tasks does not record the phone's position, so a Finish has no distance check. A separate report on the Field verification layer is stronger evidence; if one exists, Finish does not create a second.
- A report whose `Work_Order_ID` matches no work order is left alone until the worker corrects it.
- Reports made in Field Maps get an id (`VER-xxxx`) assigned by the server and written back to the hosted layer.

## Not yet covered

- Photos taken in Field Maps stay in ArcGIS Online as attachments; the command center's report view does not show them yet.
- Without an ArcGIS Online connection there is no Field Maps channel. Use the "Simulated crew auto-responds" switch for demos.
- The map's layers cannot be made read-only from the web map; edit rights come from the hosted layers.
