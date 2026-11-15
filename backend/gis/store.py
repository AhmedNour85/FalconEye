"""The feature store: a working copy in memory, with every write sent to the system of record first.

There is no local database. `Store` on its own keeps nothing beyond the life of the process: it is what the tests and
development use. `ArcGISStore` (below, added with the ArcGIS Online gateway) overrides the three persist hooks, so a
change is made in ArcGIS Online first and reaches the working copy only when ArcGIS Online has confirmed it.

Geometry objects are shared between the working copy and the rows handed out: treat them as read-only.
"""
from __future__ import annotations

import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Callable, Iterable

from .schema import LAYERS


class ValidationError(ValueError):
    pass


class StoreWriteError(RuntimeError):
    """The system of record did not accept a change. The working copy is left as it was."""

    def __init__(self, message: str, layer: str = "", fid: str = ""):
        super().__init__(message)
        self.layer, self.fid = layer, fid


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Store:
    is_hosted = False            # True when the rows live in ArcGIS Online (ArcGISStore)

    def __init__(self):
        self._rows: dict[str, dict[str, dict]] = {}          # layer -> id -> {"attrs", "geom", "bbox", "oid"}
        self._counters: dict[str, int] = {}
        self._files: dict[tuple[str, str], dict[str, bytes]] = {}
        self._lock = threading.RLock()
        self.write_hooks: dict[str, Callable[[dict], dict]] = {}   # layer -> fn(attrs) -> attrs, applied to the app's own writes (not to rows read from the record)
        self._batch_depth = 0
        self._journal: list[tuple] = []                      # (layer, fid, row before or None, persist) for every write made inside a batch

    # -- hooks a subclass overrides ----------------------------------------------
    def _persist(self, layer: str, op: str, fid: str, attrs: dict, geom: dict | None) -> int | None:
        """Make one change in the system of record. op is "add", "update" or "delete". Raise StoreWriteError to refuse it.
        May return the record's own row number (OBJECTID), which is kept with the row."""
        return None

    def _persist_many(self, layer: str, rows: list[tuple[str, str, dict, dict | None]]) -> dict[str, int] | None:
        """Make several changes to one layer at once: rows are (op, id, attrs, geom). May return {id: row number} for the adds."""
        return None

    def _persist_clear(self, layers: list[str] | None) -> None:
        """Remove every row of these layers (None = all layers) from the system of record."""

    def _after_failed_batch(self, layers: list[str]) -> None:
        """Called after a batch was refused and the working copy was rolled back."""

    # -- validation --------------------------------------------------------------
    @staticmethod
    def _validate(layer: str, attrs: dict, geom: dict | None) -> None:
        d = LAYERS.get(layer)
        if d is None:
            raise ValidationError(f"unknown layer {layer}")
        if not attrs.get(d.id_field):
            raise ValidationError(f"{layer}: missing id field {d.id_field}")
        unknown = set(attrs) - set(d.fields)
        if unknown:
            raise ValidationError(f"{layer}: unknown fields {sorted(unknown)}")
        want = {"Point": "Point", "Polyline": "LineString", "Polygon": "Polygon"}.get(d.geometry or "")
        if want is None and geom is not None:
            raise ValidationError(f"{layer} is a table; geometry not allowed")
        if want is not None and geom is not None and geom.get("type") != want:
            raise ValidationError(f"{layer}: geometry must be {want}, got {geom.get('type')}")

    @staticmethod
    def _bbox(geom):
        if not geom:
            return None
        c = geom["coordinates"]
        pts = [c] if geom["type"] == "Point" else c if geom["type"] == "LineString" else c[0]
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        return (min(xs), min(ys), max(xs), max(ys))

    @staticmethod
    def _out(fid: str, r: dict) -> dict:
        return {"id": fid, "attrs": dict(r["attrs"]), "geom": r["geom"]}

    # -- ids ---------------------------------------------------------------------
    def next_id(self, prefix: str, width: int = 4) -> str:
        with self._lock:
            n = self._counters.get(prefix, 0) + 1
            self._counters[prefix] = n
        return f"{prefix}-{n:0{width}d}"

    # -- batches -----------------------------------------------------------------
    @contextmanager
    def batch(self):
        """Group writes: the working copy changes straight away (so the code inside can read what it wrote), and the system of
        record gets one request per layer when the outermost batch ends. If it refuses, the working copy is rolled back."""
        with self._lock:
            self._batch_depth += 1
        try:
            yield
        except BaseException:
            with self._lock:
                self._batch_depth -= 1
                if self._batch_depth == 0:
                    self._rollback()
            raise
        else:
            with self._lock:
                self._batch_depth -= 1
                if self._batch_depth == 0:
                    self._flush()

    def _rollback(self) -> list[str]:
        layers = []
        for layer, fid, before, _persist in reversed(self._journal):
            if before is None:
                self._rows.get(layer, {}).pop(fid, None)
            else:
                self._rows.setdefault(layer, {})[fid] = before
            if layer not in layers:
                layers.append(layer)
        self._journal = []
        return layers

    def _flush(self) -> None:
        first: dict[tuple[str, str], dict | None] = {}        # (layer, id) -> the row before the batch touched it
        order: list[tuple[str, str]] = []
        for layer, fid, before, persist in self._journal:
            if persist and (layer, fid) not in first:
                first[(layer, fid)] = before
                order.append((layer, fid))
        per_layer: dict[str, list] = {}
        for layer, fid in order:
            before, now = first[(layer, fid)], self._rows.get(layer, {}).get(fid)
            if before is None and now is None:
                continue                                       # added and removed again inside the batch
            op = "add" if before is None else "delete" if now is None else "update"
            per_layer.setdefault(layer, []).append((op, fid, dict(now["attrs"]) if now else {}, now["geom"] if now else None))
        try:
            for layer, rows in per_layer.items():
                oids = self._persist_many(layer, rows) or {}
                for fid, oid in oids.items():
                    if fid in self._rows.get(layer, {}):
                        self._rows[layer][fid]["oid"] = oid
        except Exception:
            self._after_failed_batch(self._rollback())
            raise
        self._journal = []

    # -- writes ------------------------------------------------------------------
    def upsert(self, layer: str, attrs: dict, geom: dict | None = None, *, merge: bool = False, persist: bool = True) -> dict:
        """persist=False stores a row that came from the system of record: it is not sent back and the write hooks do not run."""
        if LAYERS.get(layer) is None:
            raise ValidationError(f"unknown layer {layer}")
        with self._lock:
            fid = attrs.get(LAYERS[layer].id_field)
            existing = self._rows.get(layer, {}).get(str(fid)) if fid else None
            if merge and existing:
                attrs = {**existing["attrs"], **attrs}
                geom = geom or existing["geom"]
            if persist and layer in self.write_hooks:
                attrs = self.write_hooks[layer](dict(attrs))
            self._validate(layer, attrs, geom)
            fid = str(fid)
            row = {"attrs": dict(attrs), "geom": geom, "bbox": self._bbox(geom), "oid": existing["oid"] if existing else None}
            if self._batch_depth:
                self._journal.append((layer, fid, existing, persist))
            elif persist:
                oid = self._persist(layer, "update" if existing else "add", fid, dict(attrs), geom)   # may raise: nothing has changed yet
                if oid is not None:
                    row["oid"] = oid
            self._rows.setdefault(layer, {})[fid] = row
        return {"id": fid, "attrs": attrs, "geom": geom}

    def update(self, layer: str, fid: str, **changes) -> dict:
        cur = self.get(layer, fid)
        if cur is None:
            raise KeyError(f"{layer}/{fid} not found")
        return self.upsert(layer, {**cur["attrs"], **changes}, cur["geom"])

    def upsert_many(self, layer: str, rows: Iterable[tuple[dict, dict | None]]) -> int:
        n = 0
        with self.batch():
            for attrs, geom in rows:
                self.upsert(layer, attrs, geom)
                n += 1
        return n

    def delete(self, layer: str, fid: str, *, persist: bool = True) -> None:
        with self._lock:
            fid = str(fid)
            existing = self._rows.get(layer, {}).get(fid)
            if existing is None:
                return
            if self._batch_depth:
                self._journal.append((layer, fid, existing, persist))
            elif persist:
                self._persist(layer, "delete", fid, dict(existing["attrs"]), existing["geom"])
            del self._rows[layer][fid]
            self._files.pop((layer, fid), None)

    def clear(self, layers: Iterable[str] | None = None) -> None:
        """Remove every row of these layers (None = everything, and the id counters). Not undone by a batch rollback."""
        names = list(layers) if layers is not None else None
        with self._lock:
            self._persist_clear(names)
            if names is None:
                self._rows.clear()
                self._counters.clear()
                self._files.clear()
                self._journal = []
            else:
                for name in names:
                    self._rows.pop(name, None)
                self._journal = [j for j in self._journal if j[0] not in names]
                self._files = {k: v for k, v in self._files.items() if k[0] not in names}

    # -- reads -------------------------------------------------------------------
    def get(self, layer: str, fid: str) -> dict | None:
        with self._lock:
            r = self._rows.get(layer, {}).get(str(fid))
            return self._out(str(fid), r) if r else None

    def all(self, layer: str) -> list[dict]:
        with self._lock:
            rows = self._rows.get(layer, {})
            return [self._out(fid, rows[fid]) for fid in sorted(rows)]

    def query(self, layer: str, where: Callable[[dict], bool] | None = None, **eq: Any) -> list[dict]:
        out = []
        for f in self.all(layer):
            a = f["attrs"]
            if any(a.get(k) != v for k, v in eq.items()):
                continue
            if where and not where(a):
                continue
            out.append(f)
        return out

    def count(self, layer: str) -> int:
        with self._lock:
            return len(self._rows.get(layer, {}))

    def bbox_query(self, layer: str, xmin: float, ymin: float, xmax: float, ymax: float, limit: int = 5000) -> list[dict]:
        out = []
        with self._lock:
            rows = self._rows.get(layer, {})
            for fid in sorted(rows):
                b = rows[fid]["bbox"]
                if b and b[2] >= xmin and b[0] <= xmax and b[3] >= ymin and b[1] <= ymax:
                    out.append(self._out(fid, rows[fid]))
                    if len(out) >= limit:
                        break
        return out

    def geojson(self, layer: str, where: Callable[[dict], bool] | None = None) -> dict:
        feats = []
        for f in self.all(layer):
            if where and not where(f["attrs"]):
                continue
            feats.append({"type": "Feature", "id": f["id"], "geometry": f["geom"], "properties": f["attrs"]})
        return {"type": "FeatureCollection", "features": feats}

    # -- files attached to a row (investigator photos) ---------------------------
    def add_attachment(self, layer: str, fid: str, name: str, data: bytes) -> None:
        with self._lock:
            if self.get(layer, fid) is None:
                raise KeyError(f"{layer}/{fid} not found")
            self._files.setdefault((layer, str(fid)), {})[name] = data

    def attachment(self, layer: str, fid: str, name: str) -> bytes | None:
        with self._lock:
            return self._files.get((layer, str(fid)), {}).get(name)
