"""ArcGIS Online gateway: the hosted feature layers that are the system of record (ArcGIS API for Python).

Every layer in the data model is one hosted feature service titled <prefix>_<layer>, owned by the signed-in account.
The gateway only ever looks for, creates and edits items with that prefix and that owner.

STATUS (2026-11-15): sign-in, search, service creation, queries, single and batched edits and task domains follow the
calls the Agentic_AI_City adapter used against a live organisation. Still to be confirmed against Esri documentation and
a live run (plan 1, task 10): editor tracking on new services, attachments, the field-length limit and query paging.
`import arcgis` is lazy, so the tests and a memory-only run do not need the package.
"""
from __future__ import annotations

import logging
import os
import tempfile
from datetime import datetime, timezone
from typing import Any

from config.settings import Settings, check_prefix

from .schema import LAYERS, LayerDef
from .store import StoreWriteError

log = logging.getLogger("geoai.agol")

NUMERIC = {
    "Diameter", "Length_M", "Pressure", "Flow", "Power_Consumption", "Confidence", "Risk_Score", "Base_Risk_Score",
    "Area_Sqm", "Mean_Magnitude", "Indicator_Value", "Distance_To_Detection_M", "Open_Tasks", "Rated_Power_W",
    "Avg_Power_W", "Power_Trend_Pct", "Flicker_30d", "Comm_Loss_Pct", "Faults_12m", "Days_Since_Maintenance", "Age_Years", "Lon", "Lat",
}
LONG_TEXT = {"Evidence", "Payload", "Result", "Instructions", "Observation", "Description", "Summary", "Input_Summary",
             "Output_Summary", "Notes", "Detection_IDs", "Value", "Field_Comment", "Trail", "Message"}
LONG_LENGTH, SHORT_LENGTH = 16000, 255      # ArcGIS Online allows far longer text; 4,000 is only the limit for an indexed field, and these are not indexed
TRACKING = {"enableEditorTracking": True, "enableOwnershipAccessControl": False, "allowOthersToUpdate": True, "allowOthersToDelete": True, "allowOthersToQuery": True,
            "allowAnonymousToUpdate": False, "allowAnonymousToDelete": False}
GEOM = {"Point": "esriGeometryPoint", "Polyline": "esriGeometryPolyline", "Polygon": "esriGeometryPolygon"}
BATCH = 200
TAGS = ["CityView-Riyadh", "SYNTHETIC-DEMO"]
SNIPPET = "Riyadh City View demo layer. Synthetic or modelled data, not real government data."


def _field_def(name: str) -> dict:
    if name in NUMERIC:
        return {"name": name, "type": "esriFieldTypeDouble", "alias": name, "nullable": True}
    return {"name": name, "type": "esriFieldTypeString", "alias": name, "length": LONG_LENGTH if name in LONG_TEXT else SHORT_LENGTH, "nullable": True}


def from_esri_geometry(g: dict | None) -> dict | None:
    if not g:
        return None
    if "x" in g:
        return {"type": "Point", "coordinates": [g["x"], g["y"]]}
    if "paths" in g:
        return {"type": "LineString", "coordinates": g["paths"][0]}
    if "rings" in g:
        return {"type": "Polygon", "coordinates": g["rings"]}
    return None


def to_esri_geometry(geom: dict | None) -> dict | None:
    if not geom:
        return None
    sr = {"wkid": 4326}
    t, c = geom["type"], geom["coordinates"]
    if t == "Point":
        return {"x": c[0], "y": c[1], "spatialReference": sr}
    if t == "LineString":
        return {"paths": [c], "spatialReference": sr}
    return {"rings": c, "spatialReference": sr}


def definition(d: LayerDef) -> dict:
    """The hosted layer (or table) definition for one layer of the data model. Editor tracking is a setting of the service, not of the
    layer: it is switched on with an update of the service definition after the layer exists (see ArcGISGateway._define)."""
    base = {
        "name": d.name, "objectIdField": "OBJECTID", "hasAttachments": d.geometry is not None,
        "fields": [{"name": "OBJECTID", "type": "esriFieldTypeOID", "alias": "OBJECTID", "nullable": False}]
        + [_field_def(f) for f in d.fields if not f.startswith("esritask_")],
        "capabilities": "Query,Create,Update,Delete,Editing,Uploads",
    }
    if d.geometry:
        base.update({"type": "Feature Layer", "geometryType": GEOM[d.geometry], "spatialReference": {"wkid": 4326}})
    else:
        base["type"] = "Table"
    return base


class ArcGISGateway:
    def __init__(self, settings: Settings, gis=None):
        """gis: an arcgis.gis.GIS connection (the tests pass a stand-in); by default the gateway signs in with the settings."""
        self.prefix = check_prefix(settings.arcgis_layer_prefix)
        self.s = settings
        if gis is None:
            from arcgis.gis import GIS  # lazy import

            gis = GIS(settings.arcgis_url, settings.arcgis_username, settings.arcgis_password)
        self.gis = gis
        self.owner = gis.properties.user.username
        self._layers: dict[str, Any] = {}
        self._fields: dict[str, dict] = {}
        log.info("Connected to ArcGIS Online as %s", self.owner)

    def title(self, layer: str) -> str:
        return f"{self.prefix}_{layer}"

    # -- items -------------------------------------------------------------------
    def _item(self, layer: str):
        """The hosted feature service of this layer: exact title, and owned by the signed-in account. Never anyone else's item."""
        title = self.title(layer)
        found = self.gis.content.search(f'title:"{title}" AND type:"Feature Service" AND owner:{self.owner}', max_items=10)
        return next((i for i in found if i.title == title and i.owner == self.owner), None)

    def _collection(self, item):
        from arcgis.features import FeatureLayerCollection

        return FeatureLayerCollection.fromitem(item)

    def create_layers(self, only: list[str] | None = None, dry_run: bool = True) -> list[dict]:
        """Create the hosted services that do not exist yet and add fields the data model gained. With dry_run nothing is changed:
        the returned plan lists what would happen. Existing rows are never touched and nothing is ever deleted."""
        plan = []
        for name, d in LAYERS.items():
            if only and name not in only:
                continue
            item = self._item(name)
            fields = [f for f in d.fields if not f.startswith("esritask_")]
            if item is None:
                step = {"layer": name, "title": self.title(name), "action": "create", "fields": fields}
                plan.append(step)
                if not dry_run:
                    item = self.gis.content.create_service(self.title(name), service_type="featureService", has_static_data=False, wkid=4326,
                                                           capabilities="Query,Create,Update,Delete,Editing,Uploads", tags=TAGS, snippet=SNIPPET)
                    step["item_id"] = item.id
                    self._define(item, d)
                continue
            if not (item.layers or item.tables):         # a service left empty by an interrupted earlier run
                plan.append({"layer": name, "title": self.title(name), "action": "define", "fields": fields, "item_id": item.id})
                if not dry_run:
                    self._define(item, d)
                continue
            missing = self._missing_fields(name)
            tracked = self.tracks_edits(name)
            step = {"layer": name, "title": self.title(name), "action": "add_fields" if missing else "exists", "fields": missing, "item_id": item.id, "tracking": tracked}
            plan.append(step)
            if missing and not dry_run:
                self.ensure_fields(name)
            if not tracked and not dry_run:
                step["tracking"] = self.enable_tracking(name)
        return plan

    def _define(self, item, d: LayerDef) -> None:
        flc = self._collection(item)
        if not (flc.properties.get("layers") or flc.properties.get("tables")):
            defn = definition(d)
            flc.manager.add_to_definition({"tables": [defn]} if d.geometry is None else {"layers": [defn]})
        # Esri documents editorTrackingInfo as a property of the SERVICE that is set with updateDefinition; it gives every row an EditDate,
        # which is how the app asks only for rows changed since its last look. Whether it took effect is read back by tracks_edits().
        flc.manager.update_definition({"editorTrackingInfo": dict(TRACKING)})
        self._forget(d.name)

    def enable_tracking(self, name: str) -> bool:
        """Switch editor tracking on for an existing service that lacks it. Returns whether the layer has an EditDate afterwards."""
        item = self._item(name)
        if item is None:
            return False
        self._collection(item).manager.update_definition({"editorTrackingInfo": dict(TRACKING)})
        self._forget(name)
        return self.tracks_edits(name)

    def layer(self, name: str):
        if name not in self._layers:
            item = self._item(name)
            if item is None:
                raise RuntimeError(f"hosted layer {self.title(name)} not found; run scripts/create_feature_layers.py")
            parts = item.layers or item.tables
            if not parts:
                raise RuntimeError(f"hosted service {self.title(name)} has no layer or table; rerun scripts/create_feature_layers.py")
            self._layers[name] = parts[0]
        return self._layers[name]

    def _field_info(self, layer: str) -> dict:
        """name -> (esri field type, length) of the hosted layer."""
        if layer not in self._fields:
            self._fields[layer] = {f["name"]: (f["type"], f.get("length")) for f in self.layer(layer).properties.fields}
        return self._fields[layer]

    def _forget(self, layer: str) -> None:
        self._layers.pop(layer, None)
        self._fields.pop(layer, None)

    def _missing_fields(self, name: str) -> list[str]:
        have = set(self._field_info(name))
        return [f for f in LAYERS[name].fields if f not in have and not f.startswith("esritask_")]

    def ensure_fields(self, name: str) -> list[str]:
        """Add fields that exist in the data model but not yet in the hosted layer. Returns the names added."""
        missing = self._missing_fields(name)
        if missing:
            self.layer(name).manager.add_to_definition({"fields": [_field_def(f) for f in missing]})
            self._forget(name)
        return missing

    def ensure_task_domains(self, layer: str, types: list[str], users: dict[str, str]) -> bool:
        """Field Maps Tasks: the coded values behind esritask_type (task titles) and esritask_assignee (who a task can be given to).
        Returns False when the hosted layer has no task fields (Tasks is not enabled on it)."""
        fl = self.layer(layer)
        by = {f["name"]: f for f in fl.properties.fields}
        if "esritask_type" not in by or "esritask_assignee" not in by:
            return False
        want = {"esritask_type": [{"name": n, "code": i} for i, n in enumerate(types)]}
        if users:
            want["esritask_assignee"] = [{"name": name, "code": user} for user, name in sorted(users.items())]
        changes = []
        for fname, codes in want.items():
            dom = by[fname].get("domain") or {}
            if [(c["name"], c["code"]) for c in dom.get("codedValues", [])] != [(c["name"], c["code"]) for c in codes]:
                changes.append({"name": fname, "domain": {"type": "codedValue", "name": dom.get("name") or f"CityView_{fname}", "codedValues": codes}})
        if changes:
            fl.manager.update_definition({"fields": changes})
            self._forget(layer)
        return True

    # -- reads -------------------------------------------------------------------
    def tracks_edits(self, layer: str) -> bool:
        return "EditDate" in self._field_info(layer)

    def rows(self, layer: str, since_ms: int | None = None, newer_than: tuple[str, str] | None = None) -> list[dict]:
        """Every row of the layer (the API follows the service's paging to the end), or only the rows edited after since_ms,
        or only the rows whose text field is >= a value: {"id", "attrs", "geom", "oid", "edited_ms"}."""
        d = LAYERS[layer]
        where = []
        if since_ms and self.tracks_edits(layer):
            where.append("EditDate > timestamp '" + datetime.fromtimestamp(since_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S") + "'")
        if newer_than:
            where.append(f"{newer_than[0]} >= '{newer_than[1]}'")
        clause = " AND ".join(where) or "1=1"
        fl = self.layer(layer)
        feats = fl.query(where=clause, out_fields="*", return_geometry=d.geometry is not None, out_sr=4326).features
        if not since_ms:                      # a full read must be complete: starting on part of a layer would look like data loss
            expected = fl.query(where=clause, return_count_only=True)
            if isinstance(expected, int) and expected != len(feats):
                raise RuntimeError(f"{self.title(layer)}: ArcGIS Online reports {expected} rows but {len(feats)} were returned; the layer was not read completely")
        fields = set(d.fields)
        out = []
        for f in feats:
            raw = f.attributes
            attrs = {k: ("" if v is None and k not in NUMERIC else v) for k, v in raw.items() if k in fields}
            out.append({"id": str(attrs.get(d.id_field) or ""), "attrs": attrs, "geom": from_esri_geometry(f.geometry), "oid": raw["OBJECTID"],
                        "edited_ms": int(raw.get("EditDate") or 0)})
        return out

    def ids(self, layer: str) -> set[str]:
        d = LAYERS[layer]
        feats = self.layer(layer).query(where="1=1", out_fields=d.id_field, return_geometry=False).features
        return {str(f.attributes.get(d.id_field) or "") for f in feats}

    def max_id(self, layer: str) -> str | None:
        d = LAYERS[layer]
        feats = self.layer(layer).query(where="1=1", out_fields=d.id_field, return_geometry=False, order_by_fields=f"{d.id_field} DESC", result_record_count=1,
                                        return_all_records=False).features
        return str(feats[0].attributes.get(d.id_field)) if feats else None

    # -- edits -------------------------------------------------------------------
    def _clean(self, layer: str, attrs: dict) -> dict:
        """Only the fields the hosted layer has; JSON for nested values; blanks become null for numeric and date fields.
        Text that does not fit its field is refused: it is never cut silently."""
        import json

        info = self._field_info(layer)
        out = {}
        for k, v in attrs.items():
            if k not in info:
                continue
            ftype, length = info[k]
            if isinstance(v, (dict, list)):
                v = json.dumps(v)
            if v == "" and ftype not in ("esriFieldTypeString", "esriFieldTypeGUID"):
                v = None
            if isinstance(v, str) and length and len(v) > length:
                raise StoreWriteError(f"{layer}: the text in {k} has {len(v)} characters and the hosted field holds {length}", layer=layer)
            out[k] = v
        return out

    def _feature(self, layer: str, attrs: dict, geom: dict | None, oid: int | None = None) -> dict:
        feat = {"attributes": self._clean(layer, attrs)}
        if oid is not None:
            feat["attributes"]["OBJECTID"] = oid
        g = to_esri_geometry(geom)
        if g:
            feat["geometry"] = g
        return feat

    def _edit(self, layer: str, **kw) -> dict:
        try:
            res = self.layer(layer).edit_features(**kw)
        except StoreWriteError:
            raise
        except Exception as exc:
            raise StoreWriteError(f"ArcGIS Online could not be reached or refused the edit to {layer}: {exc}", layer=layer) from exc
        bad = [r for key in ("addResults", "updateResults", "deleteResults") for r in (res.get(key) or []) if not r.get("success")]
        if bad:
            raise StoreWriteError(f"ArcGIS Online rejected {len(bad)} edit(s) to {layer}: {bad[0].get('error')}", layer=layer)
        return res

    def add(self, layer: str, attrs: dict, geom: dict | None) -> int:
        return self._edit(layer, adds=[self._feature(layer, attrs, geom)])["addResults"][0]["objectId"]

    def update(self, layer: str, oid: int, attrs: dict, geom: dict | None) -> None:
        self._edit(layer, updates=[self._feature(layer, attrs, geom, oid)])

    def delete(self, layer: str, oid: int) -> None:
        self._edit(layer, deletes=str(oid))

    def apply_many(self, layer: str, adds: list[tuple[dict, dict | None]], updates: list[tuple[int, dict, dict | None]], deletes: list[int]) -> list[int]:
        """Several changes to one layer, in requests of 200 rows. Returns the OBJECTIDs of the adds, in order.
        ArcGIS Online rolls back within one request, not across requests: a failure part-way is reported with how far it got."""
        add_feats = [self._feature(layer, a, g) for a, g in adds]                 # every row is checked before anything is sent
        upd_feats = [self._feature(layer, a, g, oid) for oid, a, g in updates]
        oids: list[int] = []
        done = 0
        try:
            for i in range(0, len(add_feats), BATCH):
                oids += [r["objectId"] for r in self._edit(layer, adds=add_feats[i:i + BATCH])["addResults"]]
                done += len(add_feats[i:i + BATCH])
            for i in range(0, len(upd_feats), BATCH):
                self._edit(layer, updates=upd_feats[i:i + BATCH])
                done += len(upd_feats[i:i + BATCH])
            for i in range(0, len(deletes), BATCH):
                self._edit(layer, deletes=",".join(str(o) for o in deletes[i:i + BATCH]))
                done += len(deletes[i:i + BATCH])
        except StoreWriteError as exc:
            total = len(add_feats) + len(upd_feats) + len(deletes)
            raise StoreWriteError(f"{exc} ({done} of {total} changes to this layer had already been written)", layer=layer) from exc
        return oids

    def truncate(self, layer: str) -> None:
        """Remove every row of the layer. The service itself, its fields and its item stay."""
        try:
            self.layer(layer).delete_features(where="1=1")
        except Exception as exc:
            raise StoreWriteError(f"ArcGIS Online could not empty {layer}: {exc}", layer=layer) from exc

    # -- attachments -------------------------------------------------------------
    def add_attachment(self, layer: str, oid: int, name: str, data: bytes) -> None:
        with tempfile.TemporaryDirectory() as tmp:          # the API uploads from a file; the copy is removed straight away
            path = os.path.join(tmp, os.path.basename(name))
            with open(path, "wb") as fh:
                fh.write(data)
            try:
                self.layer(layer).attachments.add(oid, path)
            except Exception as exc:
                raise StoreWriteError(f"ArcGIS Online did not accept the attachment {name} on {layer}: {exc}", layer=layer) from exc

    def attachment(self, layer: str, oid: int, name: str) -> bytes | None:
        att = self.layer(layer).attachments
        hit = next((a for a in att.get_list(oid) if a.get("name") == os.path.basename(name)), None)
        if not hit:
            return None
        with tempfile.TemporaryDirectory() as tmp:
            paths = att.download(oid=oid, attachment_id=hit["id"], save_path=tmp)
            with open(paths[0], "rb") as fh:
                return fh.read()
