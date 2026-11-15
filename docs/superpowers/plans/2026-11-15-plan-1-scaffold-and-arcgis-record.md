# Riyadh City View, Plan 1: Scaffold and ArcGIS Online as the System of Record

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A copy of `Agentic_AI_City` named Riyadh City View that keeps every record in ArcGIS Online hosted layers titled `CityView_*`, with no local database, and runs the four City use cases on them.

**Architecture:** `backend/gis/store.py` is the only file in the City code that touches SQLite. It becomes a working copy in memory (`Store`) whose writes call a persist hook first. `ArcGISStore` implements that hook against an `ArcGISGateway` (ArcGIS API for Python), loads the layers at start-up and refreshes them every 15 seconds. Tests use the plain `Store` and a `FakeGateway`.

**Tech Stack:** Python 3.10+, FastAPI, ArcGIS API for Python (`arcgis`, `six`), pytest, vanilla JavaScript, ArcGIS Maps SDK for JavaScript 4.30.

**Spec:** `docs/superpowers/specs/2026-11-15-riyadh-city-view-design.md` (revision 4, approved 2026-11-15). This plan covers its phases 0, 1 and 2 and ends at Checkpoint 1.

**Later plans**, each written when its turn comes, because they depend on what phase 2 measures:

| Plan | Spec phases | Ends at |
|---|---|---|
| 2 | 3 Mobility engine, 4 Map layers | Checkpoint 2 |
| 3 | 5 Crew and events, 6 Cross-domain link | Checkpoint 3 |
| 4 | 7 Field Maps | Checkpoint 4 |
| 5 | 8 Interface, 9 Ask the crew, 10 Brief and access, 11 Finish | Checkpoint 5 |

## Global Constraints

- Project folder: `C:\AI\Agentic_City_View\Riyadh_City_View`. `Agentic_AI_City` and `Agentic_AI_Transportation` are read-only.
- Hosted layer prefix default is `CityView`. The app refuses the prefix `GeoAIOps` (any letter case).
- The app creates and changes only ArcGIS Online items whose title starts with `CityView`. Scripts never delete items.
- Every script that changes the account is a dry run by default and changes something only with `--apply`. `--apply` is run only after the user says yes to the dry-run output.
- No SQLite, no SQLAlchemy, no file that holds records. No background write queue.
- A write counts as done only when ArcGIS Online confirms it. A failed write raises, leaves the working copy unchanged and reaches the operator as an error.
- The app never deletes data by itself. Only Reset demo and `scripts/initialize_demo.py --apply` delete rows.
- Tests never contact ArcGIS Online.
- Secrets are never printed, never asked for in chat, never committed. `.env` is in `.gitignore`.
- Port 8020. Environment variables keep the `GEOAI_` prefix. `GEOAI_OFFLINE` and `GEOAI_DB_PATH` are removed.
- Every ArcGIS-specific choice is checked against Esri documentation before it is relied on (Task 10 lists them).
- Commit after each task. Commits are local; nothing is pushed.

## Review Focus

1. **ArcGIS Online drops mid-scan.** A crew scan in progress stops with an error alert, the working copy holds only confirmed writes, and the next scan runs normally. Test in Task 6.
2. **Text longer than the hosted field.** A trail or payload over the field length is rejected with an error that names the layer and field. It is never cut silently. Test in Task 5.
3. **A row deleted outside the app** (Map Viewer). It leaves the working copy within 60 seconds and the app does not crash on references to it. Test in Task 6.
4. **A second server started on the same layers.** It refuses to start and says which host holds the lock. Test in Task 6.
5. **A layer with more than one page of rows** (sensor readings, about 2,800; the audit log grows without limit). Every row loads; the audit log loads the last 7 days only and its id counter still continues from the highest id. Test in Task 5 and Task 6.

---

## File Structure

| File | Responsibility |
|---|---|
| `backend/gis/store.py` | `Store` (working copy in memory, persist hooks), `ArcGISStore`, `StoreWriteError`, `StoreLockedError` |
| `backend/gis/agol.py` | `ArcGISGateway`: sign-in, hosted layer creation, paged reads, edits, attachments, task domains |
| `backend/gis/schema.py` | Layer definitions. `internal` flag removed: every layer is hosted |
| `config/settings.py` | `store` mode, `CityView` default, `GeoAIOps` refusal |
| `backend/platform.py` | Builds the store, starts the refresh loop, no automatic regeneration in ArcGIS mode |
| `backend/api/app.py` | Maps `StoreWriteError` to HTTP 503, health output |
| `tests/fakes.py` | `FakeGateway`, used by every test that needs hosted-layer behaviour |
| `scripts/make_env.py`, `setup_arcgis.py`, `create_feature_layers.py`, `initialize_demo.py` | Account setup, each a dry run by default |

---

### Task 1: Copy the City project and get its tests green

**Files:**
- Create: the whole tree under `Riyadh_City_View/` (copy), `.gitignore`

- [ ] **Step 1: Copy** `Agentic_AI_City` into `Riyadh_City_View` with `robocopy /E`, excluding: `.env`, `.venv`, `.pytest_cache`, `__pycache__`, `data\geoai.sqlite`, `data\backups`, `data\evidence`, `docs\*.docx`, `docs\*.pdf`, `docs\docx_spec*.json`. Keep the existing `docs\superpowers` folder.
- [ ] **Step 2: Write `.gitignore`** with `.env`, `.venv/`, `__pycache__/`, `.pytest_cache/`, `data/evidence/`, `data/backups/`, `*.sqlite`.
- [ ] **Step 3: Create the virtual environment** `.venv` and install `requirements.txt` without the `arcgis` line (installed in Task 10).
- [ ] **Step 4: Run the baseline.** `.venv\Scripts\python.exe -m pytest -q`. Expected: 156 passed. Record the real count and time; later tasks compare against it.
- [ ] **Step 5: `git init`, commit** "chore: copy of Agentic_AI_City as the starting point".

### Task 2: Rename, own port, remove legacy pages

**Files:**
- Modify: `backend/main.py` (port 8020), `frontend/home.html`, `frontend/index.html`, `frontend/strategic_dashboard.html`, `frontend/field.html` (titles), `frontend/i18n.js` (title strings), `backend/api/app.py`, `README.md`
- Delete: `frontend/classic.html`, `frontend/app.js`, `frontend/styles.css`, `frontend/operational_dashboard.html`, `frontend/operational_dashboard.js`, `backend/workflows/demo.py`, the `/api/demo/*` routes, the "Classic view" footer link, and tests that cover only these
- Test: `tests/test_api.py`

- [ ] **Step 1: Check what the legacy files are used by** (`grep` for `classic`, `app.js`, `styles.css`, `demo`). A file another kept page still loads is kept; note it in the commit message.
- [ ] **Step 2: Write the failing tests**

```python
def test_legacy_pages_are_gone(client):
    assert client.get("/classic.html").status_code == 404
    assert client.get("/api/demo/scenes").status_code == 404

def test_home_page_is_named_riyadh_city_view(client):
    assert "Riyadh City View" in client.get("/home.html").text
```

- [ ] **Step 3: Run them.** Expected: FAIL (200 and old title).
- [ ] **Step 4: Make the changes** listed under Files. Product name everywhere: "Riyadh City View".
- [ ] **Step 5: Run the full suite.** Expected: baseline count minus the deleted legacy tests, all passing.
- [ ] **Step 6: Commit** "feat: rename to Riyadh City View, port 8020, remove legacy pages".

### Task 3: Replace the SQLite store with a working copy in memory

**Files:**
- Modify: `backend/gis/store.py` (rewrite), `backend/platform.py`, `backend/workflows/approvals.py:47-53`, `backend/workflows/actions.py:56-64`, `backend/api/app.py:109`, `backend/services/synthetic.py`, `scripts/generate_riyadh_data.py`, `tests/conftest.py`, `tests/test_gis.py`, `tests/test_field_maps.py`
- Test: `tests/test_store.py` (new)

**Interfaces:**
- Produces:

```python
class StoreWriteError(RuntimeError): ...          # carries .layer and .fid

class Store:                                      # working copy in memory; this class alone is the test and development stand-in
    write_hooks: dict[str, Callable[[dict], dict]]
    def get(self, layer: str, fid: str) -> dict | None            # {"id", "attrs", "geom"}
    def all(self, layer: str) -> list[dict]                       # ordered by id, as today
    def query(self, layer: str, where=None, **eq) -> list[dict]
    def count(self, layer: str) -> int
    def bbox_query(self, layer, xmin, ymin, xmax, ymax, limit=5000) -> list[dict]
    def geojson(self, layer: str, where=None) -> dict
    def next_id(self, prefix: str, width: int = 4) -> str
    def upsert(self, layer, attrs, geom=None, *, merge=False, persist=True) -> dict
    def update(self, layer: str, fid: str, **changes) -> dict
    def upsert_many(self, layer, rows) -> int
    def delete(self, layer: str, fid: str) -> None
    def clear(self, layers=None) -> None
    def batch(self)                                               # context manager: one _persist_many per layer at exit
    # hooks a subclass overrides; the base versions do nothing
    def _persist(self, layer: str, op: str, fid: str, attrs: dict, geom: dict | None) -> None   # op: "add" | "update" | "delete"
    def _persist_many(self, layer: str, rows: list[tuple[str, str, dict, dict | None]]) -> None
    def _persist_clear(self, layers: list[str]) -> None
```

- Removed from `Store`: `attach_mirror`, `has_mirror`, `mirror_pending`, `flush_mirror`, `mirror_errors`, `mirror_lock`, `muted`, `MIRROR_SKIP`, the `mirror=` argument (renamed `persist=`), the `path` argument.
- `store.is_hosted: bool` replaces `has_mirror` (False on `Store`, True on `ArcGISStore`).

- [ ] **Step 1: Write the failing tests** in `tests/test_store.py`

```python
def test_rows_come_back_ordered_by_id():
    s = Store(); s.upsert(S.WORKERS, {"Worker_ID": "WRK-002"}); s.upsert(S.WORKERS, {"Worker_ID": "WRK-001"})
    assert [f["id"] for f in s.all(S.WORKERS)] == ["WRK-001", "WRK-002"]

def test_next_id_counts_up_per_prefix():
    s = Store()
    assert [s.next_id("INC"), s.next_id("INC"), s.next_id("LOG", 6)] == ["INC-0001", "INC-0002", "LOG-000001"]

def test_a_failed_write_changes_nothing():
    class Failing(Store):
        def _persist(self, layer, op, fid, attrs, geom): raise StoreWriteError("ArcGIS Online is unreachable")
    s = Failing()
    with pytest.raises(StoreWriteError):
        s.upsert(S.WORKERS, {"Worker_ID": "WRK-001"})
    assert s.get(S.WORKERS, "WRK-001") is None

def test_persist_is_called_before_the_copy_changes():
    seen = []
    class Spy(Store):
        def _persist(self, layer, op, fid, attrs, geom): seen.append((op, fid, self.get(layer, fid) is None))
    s = Spy(); s.upsert(S.WORKERS, {"Worker_ID": "WRK-001"}); s.update(S.WORKERS, "WRK-001", Name="Nawaf"); s.delete(S.WORKERS, "WRK-001")
    assert seen == [("add", "WRK-001", True), ("update", "WRK-001", False), ("delete", "WRK-001", False)]

def test_persist_false_skips_the_hook_and_the_write_hooks():   # rows that came from ArcGIS Online
    ...

def test_batch_sends_one_persist_many_per_layer():
    ...

def test_bbox_query_returns_only_rows_in_the_box():
    ...
```

- [ ] **Step 2: Run them.** Expected: FAIL (`Store()` takes a path; no `StoreWriteError`).
- [ ] **Step 3: Rewrite `Store`** as dictionaries `{layer: {id: row}}` plus a counter dictionary, behind one `threading.RLock`. Keep `_validate`, `_bbox`, `utcnow`, `ValidationError` as they are. Rows handed out are copies, so callers cannot change the working copy by accident.
- [ ] **Step 4: Update the callers.** `Platform` builds `Store()`; drop `sync_mirror`, `pull_mirror`, the mirror attach, and `with self.store.muted()`. `approvals.py`: drop the `mirror_errors` warning. `actions.py` and `platform.py:245`: `store.is_hosted`. `app.py:109`: drop `arcgis_pending_writes`.
- [ ] **Step 5: Update the tests.** `conftest.py`: `Settings(...)` without `db_path`, `Platform(settings=s)`. Delete the mirror-queue tests in `test_gis.py` (lines 95-150). `test_field_maps.py:102`: replaced in Task 6.
- [ ] **Step 6: Run the full suite.** Expected: all passing; no `sqlite3` import left (`grep -r sqlite backend config scripts` is empty).
- [ ] **Step 7: Commit** "feat: working copy in memory replaces the SQLite store".

### Task 4: Settings, the `CityView` default and the `GeoAIOps` refusal

**Files:**
- Modify: `config/settings.py`, `.env.example`, `backend/platform.py`
- Test: `tests/test_settings.py` (new)

**Interfaces:**
- Produces: `Settings.store: str` (`"arcgis"` default, or `"memory"`, from `GEOAI_STORE`), `Settings.arcgis_layer_prefix = "CityView"`, `class ConfigError(ValueError)`, `Platform(settings=None, gateway=None, init=True)`, `Platform.data_ready: bool`.

- [ ] **Step 1: Write the failing tests**

```python
def test_default_prefix_is_cityview(monkeypatch):
    monkeypatch.delenv("ARCGIS_LAYER_PREFIX", raising=False)
    assert load_settings().arcgis_layer_prefix == "CityView"

@pytest.mark.parametrize("prefix", ["GeoAIOps", "geoaiops", "GEOAIOPS"])
def test_the_city_projects_prefix_is_refused(monkeypatch, prefix):
    monkeypatch.setenv("ARCGIS_LAYER_PREFIX", prefix)
    with pytest.raises(ConfigError, match="GeoAIOps"):
        load_settings()

def test_arcgis_mode_without_credentials_does_not_start():
    with pytest.raises(ConfigError, match="ARCGIS_USERNAME"):
        Platform(settings=Settings(store="arcgis", arcgis_username="", arcgis_password=""))

def test_memory_mode_generates_demo_data_on_start():
    assert Platform(settings=Settings(store="memory")).store.count(S.INFRA) > 0

def test_arcgis_mode_never_regenerates_by_itself():
    gw = FakeGateway()                       # empty hosted layers
    p = Platform(settings=Settings(store="arcgis", arcgis_username="u", arcgis_password="p"), gateway=gw)
    assert p.data_ready is False and gw.writes == []
```

- [ ] **Step 2: Run them.** Expected: FAIL.
- [ ] **Step 3: Implement.** Remove `db_path` and the `GEOAI_OFFLINE` handling. `Platform`: memory mode keeps today's "generate when empty" rule; ArcGIS mode loads and sets `data_ready = store.count(S.INFRA) > 0`, and never calls `reset()` on its own. Remove the `synthetic.data_version()` start-up check.
- [ ] **Step 4: Run the full suite.** Expected: all passing (the last test passes after Task 6; mark it `xfail` until then).
- [ ] **Step 5: Commit** "feat: CityView prefix, GeoAIOps refused, no automatic regeneration".

### Task 5: `ArcGISGateway`

**Files:**
- Modify: `backend/gis/agol.py` (class renamed from `ArcGISOnlineMirror`), `backend/gis/schema.py` (drop `internal`)
- Create: `tests/fakes.py`
- Test: `tests/test_gateway.py` (new)

**Interfaces:**
- Produces:

```python
class ArcGISGateway:
    def __init__(self, settings: Settings, gis=None)        # gis injected in tests
    def title(self, layer: str) -> str                      # f"{prefix}_{layer}"
    def create_layers(self, only=None, dry_run=True) -> list[dict]   # {"layer","title","action": "create"|"exists"|"add_fields","fields": [...]}
    def rows(self, layer: str, since_ms: int | None = None, where: str | None = None) -> list[dict]   # {"id","attrs","geom","oid","edited_ms"}; follows paging to the end
    def ids(self, layer: str) -> set[str]
    def add(self, layer: str, attrs: dict, geom: dict | None) -> int          # returns OBJECTID
    def update(self, layer: str, oid: int, attrs: dict, geom: dict | None) -> None
    def delete(self, layer: str, oid: int) -> None
    def apply_many(self, layer: str, adds: list, updates: list, deletes: list[int]) -> list[int]     # batches of 200
    def truncate(self, layer: str) -> None
    def add_attachment(self, layer: str, oid: int, name: str, data: bytes) -> str
    def attachment(self, layer: str, oid: int, name: str) -> bytes
    def ensure_fields(self, layer: str) -> list[str]
    def ensure_task_domains(self, layer: str, types: list[str], users: dict[str, str]) -> bool
```

- Every edit method raises `StoreWriteError` naming the layer when ArcGIS Online reports failure or cannot be reached.
- New services are created with editor tracking on, so `EditDate` exists. Tags: `CityView-Riyadh`, `SYNTHETIC-DEMO`. Sharing: private.
- `tests/fakes.py::FakeGateway`: same methods over dictionaries, plus `writes: list`, `fail_next: Exception | None`, `page_size: int = 2000`, `outside_edit(layer, attrs, geom=None)`, `outside_delete(layer, fid)`.

- [ ] **Step 1: Write the failing tests** against a `FakeFeatureLayer` that mimics `query`, `edit_features`, `properties.fields`:

```python
def test_rows_follows_paging_to_the_end():          # 2,800 rows, 2,000 per page
    assert len(gateway_with(n_rows=2800, page=2000).rows(S.SENSORS)) == 2800

def test_a_rejected_edit_raises_and_names_the_layer():
    with pytest.raises(StoreWriteError, match="Riyadh_Work_Orders"): ...

def test_text_longer_than_the_field_is_refused_not_cut():
    with pytest.raises(StoreWriteError, match="Trail.*4000"):
        gw.add(S.NOTIFICATIONS, {"Notif_ID": "NTF-0001", "Trail": "x" * 4001}, None)

def test_create_layers_dry_run_changes_nothing():
    plan = gw.create_layers(dry_run=True)
    assert {p["action"] for p in plan} == {"create"} and fake_gis.created == []

def test_create_layers_never_touches_a_title_without_the_prefix(): ...
```

- [ ] **Step 2: Run them.** Expected: FAIL.
- [ ] **Step 3: Implement** on top of the existing `agol.py` code (`_clean`, `to_esri_geometry`, `from_esri_geometry`, `_definition`, `ensure_task_domains` stay). Field length check uses the hosted layer's own field `length`.
- [ ] **Step 4: Run them.** Expected: PASS.
- [ ] **Step 5: Commit** "feat: ArcGISGateway with paged reads, checked edits and dry-run layer creation".

### Task 6: `ArcGISStore`

**Files:**
- Modify: `backend/gis/store.py`, `backend/platform.py` (refresh loop replaces `pull_field_updates`' pull and `start_field_sync`), `tests/test_field_maps.py`
- Test: `tests/test_arcgis_store.py` (new)

**Interfaces:**
- Consumes: `ArcGISGateway` or `FakeGateway` (Task 5), `Store` hooks (Task 3).
- Produces:

```python
class StoreLockedError(RuntimeError): ...
class ArcGISStore(Store):
    is_hosted = True
    def __init__(self, gateway, audit_days: int = 7, lock: bool = True)   # loads every layer, then takes the server lock
    def refresh(self) -> dict[str, list[str]]        # layer -> ids added, changed or removed since the last call
    last_refresh: str | None
    def release(self) -> None                        # clears the server lock
```

- Refresh rule: rows edited since the last call, every 15 s, for every layer; a count check and id reconciliation every fourth call (60 s), which is how outside deletions are seen.
- Lock rule: a `Riyadh_Learning_Config` row `server.lock` holding host, process id and a heartbeat. A heartbeat younger than 60 s from another host or process stops start-up with `StoreLockedError`. The heartbeat is rewritten on every fourth refresh.
- Id counters: seeded per prefix from the highest id in each layer at load. The audit log loads the last `audit_days` days; its counter comes from a separate highest-id query.
- `Platform.field_sync()` = `store.refresh()` followed by today's assessment code, called every `field_sync_seconds`.

- [ ] **Step 1: Write the failing tests**

```python
def test_restart_reloads_the_same_data():
    gw = FakeGateway(); a = ArcGISStore(gw, lock=False); a.upsert(S.WORKERS, {"Worker_ID": "WRK-001", "Name": "Nawaf"})
    assert ArcGISStore(gw, lock=False).get(S.WORKERS, "WRK-001")["attrs"]["Name"] == "Nawaf"

def test_a_write_arcgis_refuses_leaves_the_copy_unchanged():
    gw = FakeGateway(); s = ArcGISStore(gw, lock=False); gw.fail_next = StoreWriteError("offline")
    with pytest.raises(StoreWriteError): s.upsert(S.WORKERS, {"Worker_ID": "WRK-001"})
    assert s.get(S.WORKERS, "WRK-001") is None and gw.rows(S.WORKERS) == []

def test_an_outside_edit_shows_after_refresh():
    ...; gw.outside_edit(S.WORK_ORDERS, {"Work_Order_ID": "WO-0001", "Field_Verdict": "Confirmed"})
    assert s.refresh()[S.WORK_ORDERS] == ["WO-0001"] and s.get(S.WORK_ORDERS, "WO-0001")["attrs"]["Field_Verdict"] == "Confirmed"

def test_an_outside_delete_leaves_the_copy_within_four_refreshes(): ...

def test_ids_continue_after_a_restart():
    ...  # INC-0007 exists in ArcGIS Online -> next_id("INC") == "INC-0008"

def test_audit_loads_seven_days_but_the_counter_uses_the_highest_id(): ...

def test_a_second_server_refuses_to_start():
    gw = FakeGateway(); ArcGISStore(gw)
    with pytest.raises(StoreLockedError, match="already running"): ArcGISStore(gw)

def test_arcgis_dropping_mid_scan_stops_the_scan_and_the_next_one_runs(platform_on_fake):
    p, gw = platform_on_fake; gw.fail_after(3, StoreWriteError("offline"))
    with pytest.raises(StoreWriteError): p.crew.run_cycle()
    gw.fail_after(None); assert p.crew.run_cycle()["cycle"] == 2
```

- [ ] **Step 2: Run them.** Expected: FAIL.
- [ ] **Step 3: Implement.** Each row in the working copy carries its OBJECTID, so an update is one request.
- [ ] **Step 4: Port `tests/test_field_maps.py`** to `FakeGateway.outside_edit` in place of the `Spy` mirror and `pull_updates`.
- [ ] **Step 5: Run the full suite.** Expected: all passing; remove the `xfail` from Task 4.
- [ ] **Step 6: Commit** "feat: ArcGISStore, ArcGIS Online as the system of record".

### Task 7: Errors reach the operator; health shows the record

**Files:**
- Modify: `backend/api/app.py`, `backend/orchestration/crew.py` (`_loop`), `frontend/nccc.js`, `frontend/i18n.js`, `backend/services/i18n.py`
- Test: `tests/test_api.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_a_refused_write_is_a_503_with_a_plain_message(client_on_fake):
    client, gw = client_on_fake; gw.fail_next = StoreWriteError("offline")
    r = client.post("/api/approvals/APR-0001/approve")
    assert r.status_code == 503 and "ArcGIS Online did not accept the change" in r.json()["detail"]

def test_the_approval_stays_proposed_after_a_refused_write(client_on_fake): ...

def test_health_names_the_system_of_record(client_on_fake):
    h = client.get("/api/health").json()
    assert h["store"] == "ArcGIS Online (CityView)" and "last_refresh" in h and "arcgis_pending_writes" not in h
```

- [ ] **Step 2: Run them.** Expected: FAIL.
- [ ] **Step 3: Implement.** One FastAPI exception handler for `StoreWriteError`. The autopilot loop catches it, raises one "ArcGIS Online unavailable" alert in memory (not stored), and tries again next cycle. The page shows the 503 message as a toast, in English and Arabic. The footer mode text reads "System of record: ArcGIS Online".
- [ ] **Step 4: Run the full suite.** Expected: all passing.
- [ ] **Step 5: Commit** "feat: write failures shown to the operator; health names ArcGIS Online".

### Task 8: Photos as attachments

**Files:**
- Modify: `backend/services/field.py:59-90`, `backend/api/app.py:402-408`, `backend/platform.py:69-74`, `config/settings.py` (drop `evidence_dir`)
- Test: `tests/test_field_maps.py`

- [ ] **Step 1: Write the failing test**

```python
def test_a_photo_from_the_investigator_page_becomes_an_attachment(client_on_fake):
    client, gw = client_on_fake
    r = submit_report(client, photo=("leak.jpg", b"\xff\xd8jpeg"))
    vid = r.json()["verification_id"]
    assert gw.attachments[(S.VERIFICATION, vid)] == {"leak.jpg": b"\xff\xd8jpeg"}
    assert client.get(f"/api/evidence/{vid}/leak.jpg").content == b"\xff\xd8jpeg"
```

- [ ] **Step 2: Run it.** Expected: FAIL.
- [ ] **Step 3: Implement.** `Store.add_attachment(layer, fid, name, data)` and `Store.attachment(layer, fid, name)`; the plain `Store` keeps them in memory, `ArcGISStore` calls the gateway. `Photo_URL` holds `/api/evidence/<verification id>/<name>`.
- [ ] **Step 4: Run the full suite.** Expected: all passing; no `evidence_dir` left.
- [ ] **Step 5: Commit** "feat: investigator photos stored as ArcGIS Online attachments".

### Task 9: Account scripts, each a dry run by default

**Files:**
- Create: `scripts/make_env.py`
- Modify: `scripts/setup_arcgis.py`, `scripts/create_feature_layers.py`, `scripts/initialize_demo.py`, `scripts/setup_field_maps_form.py:36`, `scripts/add_task_answer_action.py:32`
- Delete: `scripts/populate_feature_layers.py`, `scripts/generate_riyadh_data.py`
- Test: `tests/test_scripts.py` (new)

- [ ] **Step 1: Write the failing tests**

```python
def test_make_env_copies_only_the_three_arcgis_lines_and_prints_no_value(tmp_path, capsys):
    src = tmp_path / "src.env"; src.write_text("ARCGIS_URL=https://www.arcgis.com\nARCGIS_USERNAME=someone\nARCGIS_PASSWORD=s3cret\nARCGIS_LAYER_PREFIX=GeoAIOps\nGEOAI_DB_PATH=x\n")
    make_env.main([str(src), "--out", str(tmp_path / ".env")])
    out = (tmp_path / ".env").read_text()
    assert "ARCGIS_PASSWORD=s3cret" in out and "ARCGIS_LAYER_PREFIX=CityView" in out and "GeoAIOps" not in out and "GEOAI_DB_PATH" not in out
    assert "s3cret" not in capsys.readouterr().out and "someone" not in capsys.readouterr().out

def test_make_env_refuses_to_overwrite_an_existing_env(tmp_path): ...

def test_field_map_scripts_have_no_default_web_map():
    for mod in (setup_field_maps_form, add_task_answer_action):
        with pytest.raises(SystemExit): mod.main([])            # --webmap is required

def test_initialize_demo_dry_run_writes_nothing(): ...
```

- [ ] **Step 2: Run them.** Expected: FAIL.
- [ ] **Step 3: Implement.** `create_feature_layers.py` prints the plan from `create_layers(dry_run=True)`; `--apply` creates. `initialize_demo.py` prints the row count per layer it would delete and load; `--apply` runs `Platform.reset()`. `setup_arcgis.py` stays read-only and adds a check that the account may create hosted feature layers.
- [ ] **Step 4: Run the full suite.** Expected: all passing.
- [ ] **Step 5: Commit** "feat: account scripts, dry run by default, no City web-map defaults".

### Task 10: Connect to ArcGIS Online (each change waits for the user's yes)

No code is written in this task except fixes for what it finds. Each `--apply` step stops until the user answers.

- [ ] **Step 1: Toolkit check.** If the Esri documentation server is connected, use it; otherwise read the official documentation on the web and say so. Load `follow-arcgis-authentication-patterns` and `build-with-arcgis-api-for-python`.
- [ ] **Step 2: Check against the documentation,** and record each answer in `docs/arcgis_checks.md`:
  - the largest length a hosted string field may have, and whether a longer field than 4,000 suits the alert trail and approval payload;
  - how editor tracking is switched on when a hosted service is created;
  - the default and largest page size of a hosted layer query;
  - whether an API key can edit features, change a layer definition and add attachments (the sign-in decision in the spec);
  - that `arcgis` supports the installed Python version.
- [ ] **Step 3: Install** `arcgis` and `six` in `.venv`.
- [ ] **Step 4: Ask the user** which `.env` to copy the three ArcGIS lines from, then run `scripts/make_env.py <that file>`.
- [ ] **Step 5: Run `scripts/setup_arcgis.py`** (read-only). Report the account name, organisation and whether it may create hosted layers.
- [ ] **Step 6: Run `scripts/create_feature_layers.py`** (dry run). Show the user the list. **Stop for a yes.** Then `--apply`, and read back the item titles and ids.
- [ ] **Step 7: Run `scripts/initialize_demo.py`** (dry run). Show the counts. **Stop for a yes.** Then `--apply`, and read back the row count of every layer.
- [ ] **Step 8: Start the app** (`.venv\Scripts\python.exe -m backend.main`) and measure, three runs each: start-up load, one write, one full crew scan, Reset demo. Record them in `docs/arcgis_checks.md` and correct the spec's section 8.
- [ ] **Step 9: Live checks.** One approval end to end; a write with the network cut shows the error and changes nothing; a restart shows the same incidents; a row edited in Map Viewer shows within 15 s.
- [ ] **Step 10: Checkpoint 1.** Open the Operation page and the Executive Hub in the browser, in English and Arabic, run the four City events, and report to the user with the measurements.
- [ ] **Step 11: Commit** "docs: ArcGIS Online checks and measured timings".
