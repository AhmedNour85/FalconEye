"""SQLite-backed feature store: the local system of record in demo mode.

Mirrors the ArcGIS Online hosted-layer model (one logical table per layer). When an
ArcGIS Online mirror is attached, every write is forwarded to it (write-through).
"""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Protocol

from .schema import LAYERS


class Mirror(Protocol):
    def apply(self, layer: str, op: str, fid: str, attrs: dict, geom: dict | None) -> None: ...


class ValidationError(ValueError):
    pass


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Store:
    def __init__(self, path: str = ":memory:"):
        self.path = path
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._lock = threading.RLock()
        self._mirrors: list[Mirror] = []
        self.mirror_errors: list[str] = []
        self._muted = False
        self.mirror_lock = threading.RLock()                 # one thread at a time talks to the mirror (background writer, pulls, bulk pushes)
        self._mq: dict | None = None                         # (layer, id) -> latest pending write; None = write-through (synchronous)
        self._mq_cv = threading.Condition()
        self.write_hooks: dict = {}                          # layer -> fn(attrs) -> attrs, applied to LOCAL writes only (not to rows pulled from ArcGIS)
        self._mq_busy = 0
        with self._lock:
            self._db.executescript(
                """
                CREATE TABLE IF NOT EXISTS features(layer TEXT, id TEXT, attrs TEXT, geom TEXT, PRIMARY KEY(layer,id));
                CREATE TABLE IF NOT EXISTS counters(prefix TEXT PRIMARY KEY, n INTEGER);
                CREATE INDEX IF NOT EXISTS ix_layer ON features(layer);
                """
            )
            cols = {r[1] for r in self._db.execute("PRAGMA table_info(features)")}
            for c in ("minx", "miny", "maxx", "maxy"):
                if c not in cols:
                    self._db.execute(f"ALTER TABLE features ADD COLUMN {c} REAL")
            self._db.execute("CREATE INDEX IF NOT EXISTS ix_bbox ON features(layer,minx,maxx,miny,maxy)")
            self._db.commit()
        self._defer = 0

    def batch(self):
        """Context manager: defer commits (one transaction) for bulk writes."""
        from contextlib import contextmanager

        @contextmanager
        def cm():
            self._defer += 1
            try:
                yield
            finally:
                self._defer -= 1
                if self._defer == 0:
                    with self._lock:
                        self._db.commit()
        return cm()

    def _commit(self):
        if not self._defer:
            self._db.commit()

    @staticmethod
    def _bbox(geom):
        if not geom:
            return (None, None, None, None)
        c = geom["coordinates"]
        pts = [c] if geom["type"] == "Point" else c if geom["type"] == "LineString" else c[0]
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        return (min(xs), min(ys), max(xs), max(ys))

    def bbox_query(self, layer: str, xmin: float, ymin: float, xmax: float, ymax: float, limit: int = 5000) -> list[dict]:
        with self._lock:
            rows = self._db.execute("SELECT id,attrs,geom FROM features WHERE layer=? AND maxx>=? AND minx<=? AND maxy>=? AND miny<=? LIMIT ?",
                                    (layer, xmin, xmax, ymin, ymax, limit)).fetchall()
        return [self._row(r) for r in rows]

    # -- mirrors -----------------------------------------------------------------
    def attach_mirror(self, m: Mirror, background: bool = False) -> None:
        """background=True sends writes to the mirror from a worker thread, so the caller never waits for ArcGIS Online.
        Repeated writes to the same feature collapse into the latest one; errors still land in mirror_errors."""
        self._mirrors.append(m)
        if background and self._mq is None:
            import atexit
            self._mq = {}
            threading.Thread(target=self._mirror_worker, daemon=True, name="mirror-writer").start()
            atexit.register(self.flush_mirror, 10.0)

    @property
    def has_mirror(self) -> bool:
        return bool(self._mirrors)

    @property
    def mirror_pending(self) -> int:
        return (len(self._mq) + self._mq_busy) if self._mq is not None else 0

    def flush_mirror(self, timeout: float = 30.0) -> bool:
        """Wait until every queued write has reached the mirror. True when the queue is empty."""
        if self._mq is None:
            return True
        import time
        end = time.monotonic() + timeout
        with self._mq_cv:
            while self._mq or self._mq_busy:
                left = end - time.monotonic()
                if left <= 0:
                    return False
                self._mq_cv.wait(left)
        return True

    def _mirror_worker(self) -> None:
        while True:
            with self._mq_cv:
                while not self._mq:
                    self._mq_cv.wait()
                key = next(iter(self._mq))
                op, attrs, geom = self._mq.pop(key)
                self._mq_busy = 1
            try:
                with self.mirror_lock:
                    self._apply_to_mirrors(key[0], op, key[1], attrs, geom)
            finally:
                with self._mq_cv:
                    self._mq_busy = 0
                    self._mq_cv.notify_all()

    def _apply_to_mirrors(self, layer, op, fid, attrs, geom) -> None:
        for m in self._mirrors:
            try:
                m.apply(layer, op, fid, attrs, geom)
            except Exception as exc:  # mirror failures must never corrupt local state
                import logging
                logging.getLogger("geoai.mirror").warning("mirror failed for %s/%s: %s", layer, fid, exc)
                self.mirror_errors.append(f"{layer}/{fid}: {exc}")

    # high-volume / internal layers are bulk-loaded by scripts/populate_feature_layers.py, not mirrored write-by-write
    MIRROR_SKIP = frozenset({"Riyadh_Reference_Buildings", "Riyadh_Sensor_Readings", "Riyadh_Streetlight_Telemetry", "Riyadh_Maintenance_History", "Riyadh_Learning_Config",
                             "Riyadh_Sim_Events", "Riyadh_Approvals", "Riyadh_Executive_Indicators", "Riyadh_Notifications", "Riyadh_Citizen_Reports", "Riyadh_Weather_Feed"})

    def muted(self):
        """Context manager: suspend mirror forwarding (used for bulk regeneration, followed by an explicit bulk push)."""
        from contextlib import contextmanager

        @contextmanager
        def cm():
            prev, self._muted = self._muted, True
            try:
                yield
            finally:
                self._muted = prev
        return cm()

    def _notify(self, layer, op, fid, attrs, geom):
        if self._muted or layer in self.MIRROR_SKIP:
            return
        if self._mq is not None:
            with self._mq_cv:
                self._mq.pop((layer, fid), None)                       # re-insert so the newest write for a feature is the one sent
                self._mq[(layer, fid)] = (op, dict(attrs) if attrs else attrs, geom)
                self._mq_cv.notify_all()
            return
        with self.mirror_lock:
            self._apply_to_mirrors(layer, op, fid, attrs, geom)

    # -- ids ---------------------------------------------------------------------
    def next_id(self, prefix: str, width: int = 4) -> str:
        with self._lock:
            row = self._db.execute("SELECT n FROM counters WHERE prefix=?", (prefix,)).fetchone()
            n = (row[0] if row else 0) + 1
            self._db.execute("INSERT OR REPLACE INTO counters VALUES(?,?)", (prefix, n))
            self._commit()
        return f"{prefix}-{n:0{width}d}"

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

    # -- CRUD --------------------------------------------------------------------
    def upsert(self, layer: str, attrs: dict, geom: dict | None = None, *, merge: bool = False, mirror: bool = True) -> dict:
        d = LAYERS.get(layer)
        if d is None:
            raise ValidationError(f"unknown layer {layer}")
        with self._lock:
            fid = attrs.get(d.id_field)
            existing = self.get(layer, fid) if fid else None
            if merge and existing:
                attrs = {**existing["attrs"], **attrs}
                geom = geom or existing["geom"]
            if mirror and layer in self.write_hooks:
                attrs = self.write_hooks[layer](dict(attrs))
            self._validate(layer, attrs, geom)
            bb = self._bbox(geom)
            self._db.execute(
                "INSERT OR REPLACE INTO features(layer,id,attrs,geom,minx,miny,maxx,maxy) VALUES(?,?,?,?,?,?,?,?)",
                (layer, str(fid), json.dumps(attrs, default=str), json.dumps(geom) if geom else None, *bb),
            )
            self._commit()
        if mirror:
            self._notify(layer, "update" if existing else "add", str(fid), attrs, geom)
        return {"id": str(fid), "attrs": attrs, "geom": geom}

    def update(self, layer: str, fid: str, **changes) -> dict:
        cur = self.get(layer, fid)
        if cur is None:
            raise KeyError(f"{layer}/{fid} not found")
        return self.upsert(layer, {**cur["attrs"], **changes}, cur["geom"])

    def upsert_many(self, layer: str, rows: Iterable[tuple[dict, dict | None]]) -> int:
        n = 0
        for attrs, geom in rows:
            self.upsert(layer, attrs, geom)
            n += 1
        return n

    @staticmethod
    def _row(r) -> dict:
        return {"id": r[0], "attrs": json.loads(r[1]), "geom": json.loads(r[2]) if r[2] else None}

    def get(self, layer: str, fid: str) -> dict | None:
        with self._lock:
            r = self._db.execute("SELECT id,attrs,geom FROM features WHERE layer=? AND id=?", (layer, str(fid))).fetchone()
        return self._row(r) if r else None

    def all(self, layer: str) -> list[dict]:
        with self._lock:
            rows = self._db.execute("SELECT id,attrs,geom FROM features WHERE layer=? ORDER BY id", (layer,)).fetchall()
        return [self._row(r) for r in rows]

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
            return self._db.execute("SELECT COUNT(*) FROM features WHERE layer=?", (layer,)).fetchone()[0]

    def delete(self, layer: str, fid: str) -> None:
        with self._lock:
            self._db.execute("DELETE FROM features WHERE layer=? AND id=?", (layer, str(fid)))
            self._commit()
        self._notify(layer, "delete", str(fid), {}, None)

    def clear(self, layers: Iterable[str] | None = None) -> None:
        with self._lock:
            if layers is None:
                self._db.execute("DELETE FROM features")
                self._db.execute("DELETE FROM counters")
            else:
                for l in layers:
                    self._db.execute("DELETE FROM features WHERE layer=?", (l,))
            self._db.commit()
        if self._mq is not None:                                          # pending writes belong to data that no longer exists
            with self._mq_cv:
                self._mq.clear()
            self.flush_mirror(15.0)
        for m in ([] if self._muted else self._mirrors):
            if hasattr(m, "clear"):
                try:
                    m.clear(list(layers) if layers else None)  # type: ignore[attr-defined]
                except Exception:
                    pass

    # -- GeoJSON -----------------------------------------------------------------
    def geojson(self, layer: str, where: Callable[[dict], bool] | None = None) -> dict:
        feats = []
        for f in self.all(layer):
            if where and not where(f["attrs"]):
                continue
            feats.append({"type": "Feature", "id": f["id"], "geometry": f["geom"], "properties": f["attrs"]})
        return {"type": "FeatureCollection", "features": feats}
