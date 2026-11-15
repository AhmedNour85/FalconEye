# ArcGIS checks

What was checked against Esri documentation before the code relied on it, and what still needs a live run.

Checked on 2026-11-15 by web search of Esri's own sites. The Esri documentation server (MCP) was not connected in the session, so this is the fallback the plan allows. Nothing here has been run against ArcGIS Online yet.

## Checked against documentation

| Question | Finding | What the code does | Source |
|---|---|---|---|
| How long may a hosted text field be? | The maximum is 2,147,483,647 characters. 4,000 is only the limit for a field that has an index or a unique constraint. The default is 256. | Long text fields (alert trail, approval payload, descriptions) are created with a length of 16,000. They are not indexed. Text that does not fit is refused with an error; it is never cut. | [Add or delete a field](https://doc.arcgis.com/en/arcgis-online/manage-data/add-or-delete-fields.htm), [Add and manage indexes](https://doc.arcgis.com/en/arcgis-online/manage-data/add-manage-indexes.htm) |
| How is editor tracking switched on? | `editorTrackingInfo` is a property of the service, set with Update Definition. It is not a layer property of Add to Definition. Community threads report cases where the call answers "success" and nothing changes. | The service is created, the layer is added, then the service definition is updated with `editorTrackingInfo`. Whether it worked is read back from the layer's fields (`tracks_edits`). If a layer has no `EditDate`, the app reads it in full: the two field layers every 15 s, the others every 60 s. | [Update Definition (Feature Service)](https://developers.arcgis.com/rest/services-reference/online/update-definition-feature-service/), [Hosted Feature Service](https://developers.arcgis.com/rest/services-reference/online/hosted-feature-service/) |
| Does a query return every row of a layer larger than one page? | `FeatureLayer.query` has `return_all_records`, which defaults to true and pages to the end. An old release (1.7.0) had a report of an incomplete result. | The default is used. A full read is also compared with the row count ArcGIS Online reports; if they differ the app stops and says so. | [arcgis.features module](https://developers.arcgis.com/python/latest/api-reference/arcgis.features.toc.html) |
| Which Python versions does the ArcGIS API for Python support? | Releases 2.4.2 and later list Python 3.10 to 3.13. | The project's environment is Python 3.10.11. | [System requirements](https://developers.arcgis.com/python/latest/guide/system-requirements/) |

## Not confirmed yet

| Item | Why it matters | When it is settled |
|---|---|---|
| Editor tracking actually taking effect on a service created by script | Without it every refresh reads whole layers | Plan 1, task 10, step 6: read back after the layers are created |
| `AttachmentManager.add` and `.download` call shapes | Investigator photos | Task 10, step 9: one photo sent and read back |
| An API key in place of the stored password | The toolkit's sign-in guidance prefers it | Task 10, step 2, before the running server is switched |
| Real timings: start-up load, one write, one crew scan, Reset demo | The plan's figures are estimates | Task 10, step 8 |
| Batched edits of 200 rows being accepted for the largest layers | Reset demo | Task 10, step 7 |

## Known limits

- ArcGIS Online rolls back inside one edit request, not across requests. A batch that fails part-way leaves the earlier requests applied. The error says how many changes had been written, and the app then reloads the affected layers from ArcGIS Online so its working copy matches the record.
- A row deleted outside the app is noticed within 60 seconds, not 15.
- Only one server may run against the `CityView` layers at a time. A second one refuses to start.
