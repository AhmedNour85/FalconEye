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
