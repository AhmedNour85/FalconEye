# ArcGIS checks

What was checked against Esri documentation before the code relied on it, and what still needs a live run.

Checked on 2026-11-15 by web search of Esri's own sites. The Esri documentation server (MCP) was not connected in the session, so this is the fallback the plan allows. The live results are further down.

## Checked against documentation

| Question | Finding | What the code does | Source |
|---|---|---|---|
| How long may a hosted text field be? | The maximum is 2,147,483,647 characters. 4,000 is only the limit for a field that has an index or a unique constraint. The default is 256. | Long text fields (alert trail, approval payload, descriptions) are created with a length of 16,000. They are not indexed. Text that does not fit is refused with an error; it is never cut. | [Add or delete a field](https://doc.arcgis.com/en/arcgis-online/manage-data/add-or-delete-fields.htm), [Add and manage indexes](https://doc.arcgis.com/en/arcgis-online/manage-data/add-manage-indexes.htm) |
| How is editor tracking switched on? | `editorTrackingInfo` is a property of the service, set with Update Definition. It is not a layer property of Add to Definition. Community threads report cases where the call answers "success" and nothing changes. | The service is created, the layer is added, then the service definition is updated with `editorTrackingInfo`. Whether it worked is read back from the layer's fields (`tracks_edits`). If a layer has no `EditDate`, the app reads it in full: the two field layers every 15 s, the others every 60 s. | [Update Definition (Feature Service)](https://developers.arcgis.com/rest/services-reference/online/update-definition-feature-service/), [Hosted Feature Service](https://developers.arcgis.com/rest/services-reference/online/hosted-feature-service/) |
| Does a query return every row of a layer larger than one page? | `FeatureLayer.query` has `return_all_records`, which defaults to true and pages to the end. An old release (1.7.0) had a report of an incomplete result. | The default is used. A full read is also compared with the row count ArcGIS Online reports; if they differ the app stops and says so. | [arcgis.features module](https://developers.arcgis.com/python/latest/api-reference/arcgis.features.toc.html) |
| Which Python versions does the ArcGIS API for Python support? | Releases 2.4.2 and later list Python 3.10 to 3.13. | The project's environment is Python 3.10.11. | [System requirements](https://developers.arcgis.com/python/latest/guide/system-requirements/) |

## Checked against the installed package

ArcGIS API for Python 2.4.2 is installed in `.venv` (Python 3.10.11). Without signing in, the gateway's calls were compared with the package's own function signatures on 2026-11-15. All of these exist with the argument names the gateway uses:

- `FeatureLayer.query`: `where`, `out_fields`, `return_geometry`, `out_sr`, `return_count_only`, `order_by_fields`, `result_record_count`, `return_all_records`.
- `FeatureLayer.edit_features`: `adds`, `updates`, `deletes`. `FeatureLayer.delete_features`: `where`.
- `AttachmentManager.add(oid, file_path)`, `.get_list(oid)`, `.download(oid, attachment_id, save_path)`.
- `FeatureLayerManager.add_to_definition` and `.update_definition`; the service-level manager has both too.
- `ContentManager.create_service`: `name`, `service_type`, `has_static_data`, `wkid`, `capabilities`, `tags`, `snippet`.
- `GIS(url, username, password)` and `FeatureLayerCollection.fromitem`.

This shows the calls are spelled correctly. It does not show what ArcGIS Online answers; that needs the live run.

## Confirmed by a live run

2026-11-15, account `story_viewer`, organisation "Esri Saudi Arabia GeoAI Portal" (role publisher, user type Creator).

| Item | Result |
|---|---|
| Creating the hosted layers | 22 services created by `scripts/create_feature_layers.py --apply` in 646 s (about 30 s each). All are private. |
| Fields | Read back: every data-model field is present on every layer. ArcGIS Online added `OBJECTID`, `GlobalID`, `CreationDate`, `Creator`, `EditDate`, `Editor`. |
| Editor tracking set on the service with Update Definition | Took effect on 22 of 22 layers: each has an `EditDate`. The silent failure the community threads describe did not happen here. |
| Long text length | `Notifications.Trail` and `Approvals.Payload` are 16,000 characters; ordinary text fields are 255. |
| Attachments | Switched on for the 13 feature layers; off for the 9 tables, as defined. |

## Measured timings

Measured on 2026-11-15 from this computer against the live `CityView` layers (5,442 demo rows). One run each unless a range is given, so treat them as indications, not benchmarks.

| Operation | First version | After the fixes below |
|---|---|---|
| Sign in | 8 to 10 s | same |
| Load all 22 layers at start-up | 77 s | 12 s |
| Server answering after a restart | not measured | about 17 to 20 s |
| One add, update or delete | 0.25 s (first one 0.45 s) | same |
| Refresh with nothing changed | 11 to 16 s | 2.7 to 2.9 s (first one 6 s) |
| Refresh with the deletion check (every fourth) | 24 s | 5 s |
| Crew scan that opens 4 incidents | 25 s, 88 requests | not re-measured; a scan now sends one request per layer |
| Crew scan with nothing new | 7.7 s, 28 requests | 0.9 to 3.2 s, 1 to 2 requests |
| Load the demo data (5,442 rows) | 135 s | not re-measured |
| An edit made outside the app shows in the app | | 6 s and 14 s in two tries |

The first version was too slow to use: a refresh meant to run every 15 s took 11 to 24 s. Four changes fixed it:

1. One search finds all the project's hosted layers; before, each layer was searched for separately.
2. Reads of different layers are sent side by side (8 at a time) at start-up and on every refresh.
3. A crew scan is one batch: one request per layer at the end. If ArcGIS Online refuses it, the whole scan is undone in the working copy.
4. A write that changes nothing is not sent.

A batch holds the store until it ends, so a write from another thread waits and is never swept into someone else's batch. A side effect: the page's requests wait while a scan's batch is being sent (about 1 to 3 s), and for about two minutes during Reset demo.

## Live checks passed

- An approval in the page (`APR-0004`) created work order `WO-0023`; read directly from ArcGIS Online, the work order, the approval (`Executed`) and the incident (`Work Order Created`) were all there.
- A facility name changed directly in ArcGIS Online appeared in the app after 6 s; changed back, after 14 s.
- The server was killed and started again: the same 4 open incidents, 4 pending approvals and 6 alerts came back, and the lock left by the killed server was taken over at once.

Not checked live: cutting the network during a write (covered by tests on the stand-in only), and a photo attachment.

## Mobility layers on the map (2026-11-16)

Checked in the browser on the development server without ArcGIS Online (`GEOAI_STORE=memory`), with the full road network read from `data/mobility/network.json.gz` (10,986 road sections, 7,939 junctions). One run each.

| Item | Result |
|---|---|
| Traffic model built after start-up (24 hours, in the background) | 24.8 s. Until it is ready the page says "Building the traffic model… n of 24 hours ready" and tries again every 3 s. |
| Traffic layer on the map after the box is ticked | About 1.1 s the first time (roads and one hour are fetched); a new hour redraws in under a second. |
| What is drawn | One drawing for all roads in the "free" colour, plus at most three more (slow, heavy, stop-and-go) per hour. 4 drawings, not 10,986. |
| Hour slider | 03:00: 2 road sections slow or worse, average speed 79.8 km/h. 12:00: 428. 08:00 and 17:00: 597, average speed 48.2 km/h (both peaks use the same demand factor, 1.0, so they are equal by design). |
| Metro, Bus, Hospitals | 6 lines and 94 stations; 117 routes in one drawing and 3,010 stops in one drawing (shown when zoomed in); 8 hospitals. Each loads when first ticked. |
| Pages and languages | Operation page and Executive Hub, English and Arabic (right-to-left), at 1440 px wide; Operation page also at 375 px wide. |
| Console errors | None in six page loads with every layer switched on and off and the slider moved. |

### Reference layers in ArcGIS Online (2026-11-16)

Created and filled after the account owner's yes, each step shown as a dry run first. One run each.

| Item | Result |
|---|---|
| Creating the six layers (`create_feature_layers.py --apply`) | 229 s. `CityView_Riyadh_Roads`, `_Metro_Lines`, `_Metro_Stations`, `_Bus_Routes`, `_Bus_Stops`, `_Emergency_Facilities`. All private. The 22 existing layers were reported "exists, no change". |
| Filling them (`publish_reference_layers.py --apply`) | 113 s in all; 14,226 rows added, none deleted. Roads 10,986 rows in 56 s; bus stops 3,010 in 19 s; the other four 2 to 4 s each. |
| Read back | A second dry run reads the counts from ArcGIS Online: 10,986 / 6 / 94 / 117 / 3,010 / 13, every layer "up to date, no change". |
| Start-up with 28 layers (about 19,700 rows) | 17 s from sign-in to the server answering (it was 12 s for 22 layers and 5,442 rows). With sign-in, roughly 27 s; the moment the process started was not logged, so that figure is an estimate. |
| Traffic model after start-up | Ready 22.8 s later, built from the hosted roads layer (`source: arcgis`, 10,986 road sections, 7,939 junctions). |
| Same result as from the files | 03:00: 2 road sections slow or worse, 79.8 km/h. 08:00: 597, 48.2 km/h. Identical to the run on the files. |
| Map layers | Each answer reports `read_from: arcgis`: 6 metro lines, 94 stations, 117 bus routes, 3,010 stops, 8 hospitals. Both pages draw them; no page errors. |
| Operational record | Unchanged: the same 4 open incidents and 4 pending approvals as before. |

Seen in the log during start-up: two `urllib3` warnings "Connection pool is full, discarding connection". The reads still completed; the side-by-side reads briefly open more connections than the pool keeps.

Not re-measured: the 15-second refresh. Reference layers are left out of it by design, so it should be unchanged, but that was not timed again.

## Mobility crew, events and road impact (Plan 3, 2026-11-16)

Layers: `scripts/create_feature_layers.py --apply` created `CityView_Riyadh_Traffic_Incidents`, `_Planned_Closures`, `_Event_Notices` and `_Mobility_Scenarios` (32 layers in all; a second dry run shows 32 unchanged). `scripts/add_mobility_demo_rows.py --apply` added WRK-008 and WRK-009 (9 workers). Both ran as a dry run first, were shown, and were applied after a yes.

Live run against ArcGIS Online (full network, 10,986 road sections; one event of each kind, then a traffic incident taken to Resolved):

| Measurement | Result |
|---|---|
| Traffic incident simulation (background job) | 18 s |
| Closure simulation with the strategy comparison (background job) | 25.7 s |
| Major event simulation (background job) | 7.6 s |
| Road-impact run (day and night, two scenario runs) on the full network | 44 s |
| Crew scan with no simulation running | 0.7 to 1.8 s |
| Event injected (scan only; the simulation continues in the background) | 2.8 to 7.9 s |

The 60-second crew scan never waited for a simulation. A traffic incident went through approval, assignment, the simulated field check, closing, and ended Resolved with its road report Cleared; an approved closure plan appeared on the planned-closures map as Approved, and "View impact on map" drew the closed section, the worse sections and the detours with the "Modelled" note. Arabic: the Simulate menu groups, eleven crew names, layer names and alert text read in Arabic.

Found and fixed during the live run: the hosted `Agent_Assessment` field holds 255 characters and a mobility field result made a longer one, so the scan was refused (nothing was changed, as designed). The stored text now shortens the quoted observation to fit; the full observation stays in its own field. The two longest simulated observations were also shortened so the alert never cuts them.

Not seen live: the water-leak road-impact line. The demo leak sits 87 m from the nearest modelled road, outside the 60 m rule, so no closure was proposed; the rule was checked on the skeleton network in the tests (tests never contact ArcGIS Online).

## ArcGIS Maps SDK for JavaScript version (checked 2026-11-16)

The pages load version **4.30** from Esri's CDN with `require([...])`. No upgrade was made. Esri's release notes say:

| Fact | Source |
|---|---|
| The current release is 5.2 (November 2026). 5.0 came out on 24 February 2026 and is the first release with semantic versioning. | [Release notes for 5.2](https://developers.arcgis.com/javascript/latest/release-notes/), [Release notes for 5.0](https://developers.arcgis.com/javascript/latest/v5-0/) |
| From 5.0 the CDN address is one module script; the script tag needs `type="module"`. `require()` (AMD) is deprecated in 5.0 and is to be removed in 6.0; `$arcgis.import` replaces it. | [Release notes for 5.0](https://developers.arcgis.com/javascript/latest/v5-0/), [5.0 release announcement](https://community.esri.com/t5/arcgis-javascript-maps-sdk-blog/arcgis-maps-sdk-for-javascript-version-5-0-release/ba-p/1686211) |
| 5.2 is the last release with widgets and with the view's own popup and UI. 6.0 (planned for Q1 2027) removes them; Esri recommends the `arcgis-map` and `arcgis-scene` components instead of `MapView` and `SceneView`. | [Release notes for 5.2](https://developers.arcgis.com/javascript/latest/release-notes/), [Widget deprecation](https://support.esri.com/en-us/knowledge-base/deprecation-widgets-in-arcgis-maps-sdk-for-javascript-000040437) |

What moving this project from 4.30 would need:

1. Both pages (`frontend/index.html`, `frontend/strategic_dashboard.html`): the 5.x script tag with `type="module"`, and the dark theme stylesheet address for 5.x.
2. `frontend/nccc.js` and `frontend/strategic_dashboard.js`: `require([...], callback)` replaced by `$arcgis.import`. They use `esri/Map`, `esri/views/MapView`, `esri/views/SceneView`, `esri/layers/GraphicsLayer`, `esri/Graphic`, and the Operation page also `esri/widgets/Search`.
3. The Search widget replaced by the search component.
4. To be ready for 6.0: `MapView`/`SceneView` (and the 2D/3D switch built on them) moved to the `arcgis-map` and `arcgis-scene` components, and the popups of incidents, metro stations and hospitals moved to the popup component.
5. `frontend/mobility.js` uses only `GraphicsLayer` and `Graphic`, which it receives from the page, so it needs no change of its own.

Steps 1 to 3 are enough for 5.x. Step 4 is the larger piece of work and is only forced by 6.0. Version 4.30 keeps working from the CDN in the meantime. This is a major change and will not be made without a review.

## Not confirmed yet

| Item | Why it matters | When it is settled |
|---|---|---|
| Attachments accepted and read back by ArcGIS Online | Investigator photos | Task 10, step 9: one photo sent and read back |
| An API key in place of the stored password | The toolkit's sign-in guidance prefers it | Task 10, step 2, before the running server is switched |
| Reset demo from the page, timed | It holds the store while it runs | Next session |
## Known limits

- ArcGIS Online rolls back inside one edit request, not across requests. A batch that fails part-way leaves the earlier requests applied. The error says how many changes had been written, and the app then reloads the affected layers from ArcGIS Online so its working copy matches the record.
- A row deleted outside the app is noticed within 60 seconds, not 15.
- Only one server may run against the `CityView` layers at a time. A second one refuses to start.
