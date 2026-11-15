"""Stand-ins for ArcGIS Online, so no test contacts the account.

FakeGateway has the same methods as backend.gis.agol.ArcGISGateway and keeps the "hosted" rows in dictionaries.
"""
from __future__ import annotations

from backend.gis.schema import LAYERS
from backend.gis.store import StoreWriteError


class FakeGateway:
    def __init__(self, page_size: int = 2000, prefix: str = "CityView"):
        self.prefix, self.page_size = prefix, page_size
        self.layers: dict[str, dict[int, dict]] = {}          # layer -> OBJECTID -> {"id", "attrs", "geom", "oid", "edited_ms"}
        self.attachments: dict[tuple[str, str], dict[str, bytes]] = {}
        self.writes: list[tuple] = []                         # every edit the app made: (op, layer, id)
        self.requests: list[tuple] = []                       # every call, reads included: (method, layer)
        self.fail_next: Exception | None = None
        self._fail_in: int | None = None
        self._fail_exc: Exception | None = None
        self._oid = 0
        self.clock_ms = 1_000

    # ---- test controls ------------------------------------------------------------------------------------
    def fail_after(self, n: int | None, exc: Exception | None = None) -> None:
        """The n-th edit from now fails, and every edit after it, until fail_after(None)."""
        self._fail_in, self._fail_exc = n, exc

    def outside_edit(self, layer: str, attrs: dict, geom: dict | None = None) -> None:
        """Someone edits or adds a row in ArcGIS Online itself (Field Maps, Map Viewer). Not recorded as one of the app's writes."""
        fid = str(attrs[LAYERS[layer].id_field])
        self.clock_ms += 1_000
        cur = self._find(layer, fid)
        if cur:
            cur["attrs"] = {**cur["attrs"], **attrs}
            cur["geom"] = geom or cur["geom"]
            cur["edited_ms"] = self.clock_ms
        else:
            self._oid += 1
            self.layers.setdefault(layer, {})[self._oid] = {"id": fid, "attrs": dict(attrs), "geom": geom, "oid": self._oid, "edited_ms": self.clock_ms}

    def outside_delete(self, layer: str, fid: str) -> None:
        cur = self._find(layer, fid)
        if cur:
            del self.layers[layer][cur["oid"]]

    # ---- helpers ------------------------------------------------------------------------------------------
    def _find(self, layer: str, fid: str) -> dict | None:
        return next((r for r in self.layers.get(layer, {}).values() if r["id"] == str(fid)), None)

    def _edit(self, op: str, layer: str, fid: str) -> None:
        if self.fail_next is not None:
            exc, self.fail_next = self.fail_next, None
            raise exc
        if self._fail_in is not None:
            self._fail_in -= 1
            if self._fail_in <= 0:
                raise self._fail_exc or StoreWriteError("ArcGIS Online is unreachable", layer=layer, fid=fid)
        self.writes.append((op, layer, fid))

    def _check_lengths(self, layer: str, attrs: dict) -> None:
        for k, v in attrs.items():
            limit = 4000 if k in LONG_TEXT else 255
            if isinstance(v, str) and len(v) > limit:
                raise StoreWriteError(f"{layer}: the text in {k} has {len(v)} characters and the field holds {limit}", layer=layer)

    # ---- the gateway interface ------------------------------------------------------------------------------
    def title(self, layer: str) -> str:
        return f"{self.prefix}_{layer}"

    def rows(self, layer: str, since_ms: int | None = None, newer_than: tuple[str, str] | None = None) -> list[dict]:
        self.requests.append(("rows", layer))
        out = [dict(r, attrs=dict(r["attrs"])) for r in self.layers.get(layer, {}).values()
               if (since_ms is None or r["edited_ms"] > since_ms) and (newer_than is None or str(r["attrs"].get(newer_than[0], "")) >= newer_than[1])]
        pages = max(1, -(-len(out) // self.page_size))
        self.requests.extend(("rows-page", layer) for _ in range(pages - 1))
        return sorted(out, key=lambda r: r["oid"])

    def ids(self, layer: str) -> set[str]:
        self.requests.append(("ids", layer))
        return {r["id"] for r in self.layers.get(layer, {}).values()}

    def max_id(self, layer: str) -> str | None:
        self.requests.append(("max_id", layer))
        return max((r["id"] for r in self.layers.get(layer, {}).values()), default=None)

    def add(self, layer: str, attrs: dict, geom: dict | None) -> int:
        fid = str(attrs[LAYERS[layer].id_field])
        self._check_lengths(layer, attrs)
        self._edit("add", layer, fid)
        self._oid += 1
        self.clock_ms += 1_000
        self.layers.setdefault(layer, {})[self._oid] = {"id": fid, "attrs": dict(attrs), "geom": geom, "oid": self._oid, "edited_ms": self.clock_ms}
        return self._oid

    def update(self, layer: str, oid: int, attrs: dict, geom: dict | None) -> None:
        fid = str(attrs[LAYERS[layer].id_field])
        self._check_lengths(layer, attrs)
        self._edit("update", layer, fid)
        if oid not in self.layers.get(layer, {}):
            raise StoreWriteError(f"{layer}: row {fid} no longer exists in ArcGIS Online", layer=layer, fid=fid)
        self.clock_ms += 1_000
        self.layers[layer][oid].update(id=fid, attrs=dict(attrs), geom=geom, edited_ms=self.clock_ms)

    def delete(self, layer: str, oid: int) -> None:
        row = self.layers.get(layer, {}).get(oid)
        self._edit("delete", layer, row["id"] if row else "")
        self.layers.get(layer, {}).pop(oid, None)

    def apply_many(self, layer: str, adds: list[tuple[dict, dict | None]], updates: list[tuple[int, dict, dict | None]], deletes: list[int]) -> list[int]:
        """One request (in batches of 200) for a whole layer. Returns the OBJECTIDs of the adds, in order. All or nothing in this stand-in."""
        for attrs, _g in adds:
            self._check_lengths(layer, attrs)
        for _oid, attrs, _g in updates:
            self._check_lengths(layer, attrs)
        self._edit("many", layer, f"{len(adds)}+{len(updates)}-{len(deletes)}")
        oids = []
        self.clock_ms += 1_000
        for attrs, geom in adds:
            self._oid += 1
            self.layers.setdefault(layer, {})[self._oid] = {"id": str(attrs[LAYERS[layer].id_field]), "attrs": dict(attrs), "geom": geom, "oid": self._oid, "edited_ms": self.clock_ms}
            oids.append(self._oid)
        for oid, attrs, geom in updates:
            if oid in self.layers.get(layer, {}):
                self.layers[layer][oid].update(attrs=dict(attrs), geom=geom, edited_ms=self.clock_ms)
        for oid in deletes:
            self.layers.get(layer, {}).pop(oid, None)
        return oids

    def truncate(self, layer: str) -> None:
        self._edit("truncate", layer, "")
        self.layers.pop(layer, None)

    def add_attachment(self, layer: str, oid: int, name: str, data: bytes) -> None:
        row = self.layers.get(layer, {}).get(oid)
        self._edit("attach", layer, row["id"] if row else "")
        self.attachments.setdefault((layer, row["id"]), {})[name] = data

    def attachment(self, layer: str, oid: int, name: str) -> bytes | None:
        row = self.layers.get(layer, {}).get(oid)
        return self.attachments.get((layer, row["id"]), {}).get(name) if row else None

    def ensure_task_domains(self, layer: str, types: list[str], users: dict[str, str]) -> bool:
        self.task_domains = {"types": list(types), "users": dict(users)}
        return True


LONG_TEXT = {"Evidence", "Payload", "Result", "Instructions", "Observation", "Description", "Summary", "Input_Summary", "Output_Summary", "Notes", "Detection_IDs", "Value",
             "Field_Comment", "Trail", "Message", "esritask_description", "esritask_notes"}
