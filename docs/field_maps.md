# Field reports through ArcGIS Field Maps

The in-app investigator form is **off by default** in code (`/field.html` shows a notice, `POST /api/field/submit` and `/accept` return 410), but the project's `.env` sets
`GEOAI_FIELD_FORM=1`, so it runs alongside **ArcGIS Field Maps**, the main way field teams report.

## How a report travels

1. The command center creates and assigns a work order (after a person approves it). Both are written to the hosted layer `GeoAIOps_Riyadh_Work_Orders`.
2. The investigator opens the Field Maps map, taps the work order, and adds a record to **`GeoAIOps_Riyadh_Field_Verification`**.
3. The server polls ArcGIS Online every `GEOAI_FIELD_SYNC_SECONDS` (default 15) and pulls new or edited rows.
4. Each new report is completed and assessed exactly as the old form's reports were: the worker, incident and distance to the AI finding are filled in,
   the report is compared with the finding, and the incident, detection and work order are updated. The operator gets a "verified" alert straight away.

## What is sent when a work order is assigned

When an operator approves an assignment, the work order on `GeoAIOps_Riyadh_Work_Orders` is updated within a few seconds with:
`Assigned_Worker`, `Assigned_Worker_Name`, `Assigned_To_Username`, `Assigned_At`, `Status = Assigned`, `Incident_Type`, `Area_Name`, `Due_Date`, `Instructions` and
`Field_Maps_Status = Sent to ArcGIS Field Maps`. Set `GEOAI_FIELD_USERS=WRK-001=<username>,...` in `.env` so `Assigned_To_Username` holds each investigator's
ArcGIS Online login. In the Field Maps map, filter the work-order layer to `Assigned_To_Username = '<login>'` (one map or one filtered view per investigator) so each
worker sees only their own tasks. When a worker taps accept (sets `Accepted_At`) the operator gets an "accepted" alert.

This uses the work-order layer. It does not create ArcGIS Workforce assignments or push notifications to the phone; the worker sees the task after Field Maps syncs.

## Map and form setup in Field Maps (one time)

Add `GeoAIOps_Riyadh_Field_Verification` (point layer) to the field map and configure its form:

| Field | Setting |
|---|---|
| `Work_Order_ID` | optional; text (blank = matched to the nearest open work order within 300 m) |
| `Verification_Status` | required; radio buttons labelled **Yes, confirmed / Not found / Need to look again / Escalate / Repaired** (saved as `Confirmed`, `Rejected`, `Needs Further Inspection`, `Escalate`, `Repaired`) |
| `Observation` | required; labelled "What did you see?", multi-line, with an example hint |
| Photo | optional image attachment element |
| `Investigator_Name` | optional; leave it blank (or hide it) and the server fills in the assigned worker's name. A name typed here is kept |
| everything else | hidden (the server fills it in) |

Also add `GeoAIOps_Riyadh_Work_Orders` (read-only) so the worker can see the task, and turn on attachments for photos.

## Radio-button answer and comment on the task (recommended)

Instead of typing a verdict word in the Note, the task form can show the same choices as the in-app investigator form: **Yes, confirmed / Not found / Need to look again / Escalate / Repaired** (radio buttons, field `Field_Verdict`) and a required comment box **What did you see?** (field `Field_Comment`). When the investigator taps **Finish**, the server uses these two fields as the report; a typed Note still works as a fallback (an unknown or empty answer falls back to the Note's first word).

One-time setup (adds the two fields and the radio choices to the hosted Work Orders layer and the two form elements to the Field Maps web map(s); a JSON backup of each web map is saved first, existing form elements are kept):

```bash
.venv\Scripts\python.exe scripts\setup_field_maps_form.py            # dry run: shows what would change, changes nothing
.venv\Scripts\python.exe scripts\setup_field_maps_form.py --apply    # makes the changes
```

Choice labels follow `GEOAI_FIELD_LANG` (`en`, `ar`, or `both`, for example "Yes, confirmed / نعم، مؤكد"); pass `--lang` to override. After applying, re-sync the map on the phone. The same script also makes the Field verification report form bilingual (heading, questions, hint and radio choices) when the language is `ar` or `both`; the saved codes (`Confirmed`, `Rejected`, ...) never change, so reports and the server logic are unaffected.

### Radio buttons cannot be on a task: the "Answer" button

Field Maps tasks cannot show radio buttons on Finish or Note (Esri: edit actions cannot prompt for multiple-choice form elements), and the task page itself is a read-only details view. The task therefore gets an **Answer** button that opens a pick list of the choices, like the built-in Status button: **Finish | Answer | Note | Attach**. The investigator taps **Answer** (verdict in `Field_Verdict`), **Note** (what they saw), then **Finish**. The radio buttons stay on the **Field verification** report form (the **+** button).

```bash
.venv\Scripts\python.exe scriptsdd_task_answer_action.py             # dry run
.venv\Scripts\python.exe scriptsdd_task_answer_action.py --apply     # adds the button to the Investigator map (backups saved in data/backups)
```

Task actions live in the web map's hidden resource `tasks-configuration.json` (not in the web map JSON). Its `layerId` must be the id of the Work orders layer in that web map, otherwise Field Maps shows "Tasks couldn't be loaded". To undo, restore the backup files that the script prints.

## Finish on the task = the report

On the phone, an investigator can finish a task in one step: write the finding in **Note**, then tap **Finish**. The first word of the note is the verdict:
`Confirmed` (or "Yes"), `Rejected` (or "Not found"), `Repaired`, `Escalate`, or "Need to look again" (for example "Confirmed: cracks on the north wall"). The task text on the phone
lists these under "How to answer". No verdict word, or no note, becomes
"Needs Further Inspection". The server turns this into a verification and assesses it like any other report; the operator gets the "verified" alert.
Tasks does not record the phone's position, so the location is the task's own and there is no distance check. A separate report filed on the
Field verification layer (with GPS and photos) is stronger evidence, and if one already exists Finish does not create a second.

## Rules the server applies

- The GPS point of the report is compared with the finding; further than 150 m away is treated as weak evidence ("Requires Further Inspection").
- A report with no GPS point is never accepted as strong evidence.
- An invalid or empty status becomes "Needs Further Inspection".
- A report whose `Work_Order_ID` matches no work order is left untouched until the worker corrects it.
- Reports made in Field Maps get an id (`VER-xxxx`) assigned by the server, which is written back to the hosted layer.

## Not yet covered

- Photos taken in Field Maps stay in ArcGIS Online as attachments; the command center's report view does not show them yet.
- Without an ArcGIS Online connection there is no Field Maps channel. Use the "Simulated crew auto-responds" switch for demos.
