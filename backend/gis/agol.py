"""ArcGIS Online adapter (hosted feature layers) using the ArcGIS API for Python.

STATUS: written against the documented arcgis API; it can only be exercised with real
ArcGIS Online credentials (ARCGIS_USERNAME / ARCGIS_PASSWORD in .env). Without them the
application runs entirely on the local store (demo mode) and this module is never loaded.
`import arcgis` is lazy so the rest of the app has no dependency on the (large) package.
"""
from __future__ import annotations

import logging
from typing import Any

from config.settings import Settings

from .schema import LAYERS, LayerDef

log = logging.getLogger("geoai.agol")

NUMERIC = {
    "Diameter", "Length_M", "Pressure", "Flow", "Power_Consumption", "Confidence", "Risk_Score", "Base_Risk_Score",
    "Area_Sqm", "Mean_Magnitude", "Indicator_Value", "Distance_To_Detection_M", "Open_Tasks", "Rated_Power_W",
    "Avg_Power_W", "Power_Trend_Pct", "Flicker_30d", "Comm_Loss_Pct", "Faults_12m", "Days_Since_Maintenance", "Age_Years",
}
LONG_TEXT = {"Evidence", "Payload", "Result", "Instructions", "Observation", "Description", "Summary", "Input_Summary",
             "Output_Summary", "Notes", "Detection_IDs", "Value", "Field_Comment"}
GEOM = {"Point": "esriGeometryPoint", "Polyline": "esriGeometryPolyline", "Polygon": "esriGeometryPolygon"}


def _field_def(name: str, id_field: str) -> dict:
    if name in NUMERIC:
        return {"name": name, "type": "esriFieldTypeDouble", "alias": name, "nullable": True}
    return {"name": name, "type": "esriFieldTypeString", "alias": name, "length": 4000 if name in LONG_TEXT else 255, "nullable": True}



def from_esri_geometry(g: dict | None) -> dict | None:
    if not g:
        return None
    t = g.get("type") or g.get("esriGeometryType")
    c = g.get("x") # Point
    if t == "esriGeometryPoint" or "x" in g:
        return {"type": "Point", "coordinates": [g["x"], g["y"]]}
    if t == "esriGeometryPolyline" or "paths" in g:
        return {"type": "LineString", "coordinates": g["paths"][0]}
    if t == "esriGeometryPolygon" or "rings" in g:
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


class ArcGISOnlineMirror:
    def __init__(self, settings: Settings):
        from arcgis.gis import GIS  # lazy import

        self.s = settings
        self.gis = GIS(settings.arcgis_url, settings.arcgis_username, settings.arcgis_password)
        self._layers: dict[str, Any] = {}
        self._ftypes: dict[str, dict] = {}
        log.info("Connected to ArcGIS Online as %s", self.gis.properties.user.username)

    def title(self, layer: str) -> str:
        return f"{self.s.arcgis_layer_prefix}_{layer}"

    # -- creation ----------------------------------------------------------------
    def create_layers(self, only: list[str] | None = None) -> dict[str, str]:
        """Create one hosted feature service per layer (idempotent: reuses by title)."""
        from arcgis.features import FeatureLayerCollection

        out = {}
        for name, d in LAYERS.items():
            if d.internal or (only and name not in only):
                continue
            found = self.gis.content.search(f'title:"{self.title(name)}" AND type:"Feature Service"', max_items=5)
            item = next((i for i in found if i.title == self.title(name)), None)
            if item is None:
                item = self.gis.content.create_service(
                    self.title(name), service_type="featureService", has_static_data=False, wkid=4326,
                    capabilities="Query,Create,Update,Delete,Editing,Uploads",
                    tags=["GeoAI-Operations-Riyadh", "SYNTHETIC-DEMO"],
                    snippet="Synthetic demo layer for the GeoAI Operations Center | Riyadh. Not real government data.",
                )
            # repair services left empty by an interrupted earlier run: add the definition whenever the service has no layer/table
            flc = FeatureLayerCollection.fromitem(item)
            if not (flc.properties.get("layers") or flc.properties.get("tables")):
                defn = self._definition(d)
                flc.manager.add_to_definition({"tables": [defn]} if d.geometry is None else {"layers": [defn]})
            out[name] = item.id
            self.ensure_fields(name)
        return out

    def ensure_fields(self, name: str) -> list[str]:
        """Add fields that exist in the data model but not yet in the hosted layer (idempotent). Returns the names added."""
        d = LAYERS[name]
        fl = self.layer(name)
        have = {f["name"] for f in fl.properties.fields}
        missing = [_field_def(f, d.id_field) for f in d.fields if f not in have and not f.startswith("esritask_")]
        if missing:
            fl.manager.add_to_definition({"fields": missing})
            self._layers.pop(name, None)
        return [m["name"] for m in missing]

    @staticmethod
    def _definition(d: LayerDef) -> dict:
        base = {
            "name": d.name, "objectIdField": "OBJECTID", "hasAttachments": d.geometry is not None,
            "fields": [{"name": "OBJECTID", "type": "esriFieldTypeOID", "alias": "OBJECTID", "nullable": False}]
            + [_field_def(f, d.id_field) for f in d.fields if not f.startswith("esritask_")],
            "capabilities": "Query,Create,Update,Delete,Editing,Uploads",
        }
        if d.geometry:
            base.update({"type": "Feature Layer", "geometryType": GEOM[d.geometry], "spatialReference": {"wkid": 4326}})
        else:
            base["type"] = "Table"
        return base

    def layer(self, name: str):
        if name not in self._layers:
            found = self.gis.content.search(f'title:"{self.title(name)}" AND type:"Feature Service"', max_items=5)
            item = next((i for i in found if i.title == self.title(name)), None)
            if item is None:
                raise RuntimeError(f"hosted layer {self.title(name)} not found; run scripts/create_feature_layers.py")
            parts = item.layers or item.tables
            if not parts:
                raise RuntimeError(f"hosted service {self.title(name)} has no layer/table; rerun scripts/create_feature_layers.py")
            self._layers[name] = parts[0]
        return self._layers[name]

    # -- edits -------------------------------------------------------------------
    def _hosted_fields(self, layer: str) -> dict:
        """name -> esri field type of the hosted layer (cached with the layer object)."""
        if layer not in self._ftypes:
            self._ftypes[layer] = {f["name"]: f["type"] for f in self.layer(layer).properties.fields}
        return self._ftypes[layer]

    def _clean(self, layer: str, attrs: dict) -> dict:
        """Only fields the hosted layer actually has; JSON for nested values; blanks become null for numeric and date fields."""
        import json
        types = self._hosted_fields(layer)
        out = {}
        for k, v in attrs.items():
            if k not in types:
                continue
            if isinstance(v, (dict, list)):
                v = json.dumps(v)
            if v == "" and types[k] not in ("esriFieldTypeString", "esriFieldTypeGUID"):
                v = None
            out[k] = v
        return out

    def ensure_task_domains(self, layer: str, types: list[str], users: dict[str, str]) -> bool:
        """Field Maps Tasks: set the coded values behind esritask_type (task titles) and esritask_assignee (who a task can be given to).
        Returns False when the hosted layer has no task fields (Tasks not enabled on it), True when they are in place."""
        fl = self.layer(layer)
        by = {f["name"]: f for f in fl.properties.fields}
        if "esritask_type" not in by or "esritask_assignee" not in by:
            return False
        want = {
            "esritask_type": [{"name": n, "code": i} for i, n in enumerate(types)],
        }
        if users:
            want["esritask_assignee"] = [{"name": name, "code": user} for user, name in sorted(users.items())]
        changes = []
        for fname, codes in want.items():
            dom = by[fname].get("domain") or {}
            if [(c["name"], c["code"]) for c in dom.get("codedValues", [])] != [(c["name"], c["code"]) for c in codes]:
                changes.append({"name": fname, "domain": {"type": "codedValue", "name": dom.get("name") or f"GeoAI_{fname}", "codedValues": codes}})
        if changes:
            fl.manager.update_definition({"fields": changes})
            self._layers.pop(layer, None)
            self._ftypes.pop(layer, None)
        return True

    def apply(self, layer: str, op: str, fid: str, attrs: dict, geom: dict | None) -> None:
        d = LAYERS[layer]
        if d.internal:
            return
        fl = self.layer(layer)
        where = f"{d.id_field}='{fid}'"
        if op == "delete":
            fl.delete_features(where=where)
            return
        feat = {"attributes": self._clean(layer, attrs)}
        g = to_esri_geometry(geom)
        if g:
            feat["geometry"] = g
        existing = fl.query(where=where, out_fields="OBJECTID", return_geometry=False).features
        if existing:
            feat["attributes"]["OBJECTID"] = existing[0].attributes["OBJECTID"]
            res = fl.edit_features(updates=[feat])["updateResults"]
        else:
            res = fl.edit_features(adds=[feat])["addResults"]
        if not all(r.get("success") for r in res):
            raise RuntimeError(f"ArcGIS Online rejected edit for {layer}/{fid}: {res}")

    def bulk_push(self, layer: str, rows: list[dict], batch: int = 200) -> int:
        d = LAYERS[layer]
        fl = self.layer(layer)
        fl.delete_features(where="1=1")
        n = 0
        for i in range(0, len(rows), batch):
            adds = []
            for r in rows[i:i + batch]:
                f = {"attributes": self._clean(layer, r["attrs"])}
                g = to_esri_geometry(r["geom"])
                if g:
                    f["geometry"] = g
                adds.append(f)
            res = fl.edit_features(adds=adds)["addResults"]
            n += sum(1 for x in res if x.get("success"))
        return n


    ID_PREFIX = {"Verification_ID": "VER"}

    SERVER_OWNED = {"Riyadh_Field_Verification": ("Agent_Assessment",)}

    def pull_updates(self, layer: str, since: str, store: Any) -> int:
        """Pull features created or edited in ArcGIS (for example by workers in Field Maps) into the local store.
        Returns how many rows actually changed. Rows created in Field Maps have no id yet: one is assigned here and written back.
        Pulled rows are stored with mirror=False so they are not echoed back to ArcGIS Online."""
        d = LAYERS[layer]
        if d.internal:
            return 0
        fl = self.layer(layer)
        where = f"EditDate > '{since}'" if since and "EditDate" in {f["name"] for f in fl.properties.fields} else "1=1"
        features = fl.query(where=where, out_fields="*", return_geometry=True).features
        fields = set(d.fields) | {d.id_field}
        count = 0
        for f in features:
            raw = f.attributes
            attrs = {k: ("" if v is None and k not in NUMERIC else v) for k, v in raw.items() if k in fields}
            geom = from_esri_geometry(f.geometry)
            fid = attrs.get(d.id_field)
            if not fid:
                prefix = self.ID_PREFIX.get(d.id_field)
                if not prefix:
                    continue
                fid = store.next_id(prefix)
                attrs[d.id_field] = fid
                try:
                    fl.edit_features(updates=[{"attributes": {"OBJECTID": raw["OBJECTID"], d.id_field: fid}}])
                except Exception as exc:  # the row is still processed locally; the id will be pushed again with the next local edit
                    log.warning("could not write id %s back to ArcGIS Online: %s", fid, exc)
            local = store.get(layer, str(fid))
            if local:
                # fields that only the server fills in: ArcGIS Online may still hold the blank value from before the server's own write reached it
                for k in self.SERVER_OWNED.get(layer, ()):
                    if attrs.get(k) in ("", None) and local["attrs"].get(k) not in ("", None):
                        attrs.pop(k, None)
            if local and all(local["attrs"].get(k, "") == v or (v in ("", None) and not local["attrs"].get(k)) for k, v in attrs.items()):
                continue                                   # unchanged since the last pull
            store.upsert(layer, {**(local["attrs"] if local else {}), **attrs}, geom or (local["geom"] if local else None), mirror=False)
            count += 1
        return count

    def clear(self, layers: list[str] | None) -> None:
        for name in layers or [n for n, d in LAYERS.items() if not d.internal]:
            if not LAYERS[name].internal:
                self.layer(name).delete_features(where="1=1")
