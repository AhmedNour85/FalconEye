"""FastAPI application: REST API for the UI, the agent chat endpoint, field portal, simulation controls and guided demo."""
from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend.agent import providers
from backend.agent.agent import GeoAIAgent
from backend.gis import schema as S
from backend.gis.store import StoreWriteError
from backend.mobility import traffic, transit
from backend.orchestration import crew as crewmod
from backend.platform import Platform
from backend.security import guard as guardmod
from backend.services import brief as briefmod, field, i18n, imagery, learning, mobility_numbers, pdf_arabic
from backend.services.filters import make_filter
from backend.services.synthetic import AREAS, CORRIDORS
from backend.tools import executive, registry
from backend.workflows.demo import SCENES, Demo
from config.settings import ROOT

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

PUBLIC_LAYERS = [n for n, d in S.LAYERS.items() if not d.internal and d.geometry and not d.static]   # the mobility reference layers have their own routes


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    session_id: str | None = None


class ToolIn(BaseModel):
    args: dict = Field(default_factory=dict)
    session_id: str | None = "ui"


class PlannerIn(BaseModel):
    provider: str = Field(min_length=1, max_length=30)
    model: str = Field(default="", max_length=120)
    base_url: str = Field(default="", max_length=300)
    api_key: str = Field(default="", max_length=400)


class SensorMod(BaseModel):
    sensor_id: str
    pressure_drop_pct: float = Field(ge=0, le=90)
    flow_rise_pct: float = Field(ge=-50, le=300)
    hours: int = Field(default=4, ge=1, le=24)


ROLES = {"viewer": 0, "worker": 1, "operator": 2}
FORM_OFF = "The in-app investigator form is disabled. Field teams report through the ArcGIS Field Maps app; their reports are pulled in automatically."
FIELD_PAGE = """<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><title>Investigator form disabled</title>
<style>body{font:16px/1.6 Segoe UI,system-ui,sans-serif;background:#f3f4f6;color:#111827;display:grid;place-items:center;min-height:100vh;margin:0}
main{max-width:520px;padding:32px;background:#ffffff;border:1px solid #e5e7eb;border-radius:14px}h1{margin:0 0 8px;font-size:22px}a{color:#1b8354}</style>
<main><h1>Investigator form disabled</h1><p>Field teams now report through the <b>ArcGIS Field Maps</b> app. Open your assigned map in Field Maps, add a report on the
Field Verification layer and sync. It appears in the command center within about 15 seconds.</p><p><a href="/index.html">Back to the command center</a></p></main>"""


def create_app(platform: Platform | None = None, agent: GeoAIAgent | None = None) -> FastAPI:
    app = FastAPI(title="Falcon Eye", version="1.0")
    p = platform or Platform()
    ag = agent or GeoAIAgent(p)
    demo = Demo(ag)
    app.state.p, app.state.agent, app.state.demo = p, ag, demo

    @app.middleware("http")
    async def revalidate_ui(request, call_next):
        """UI files change between releases; make browsers revalidate them instead of serving a stale cached copy."""
        resp = await call_next(request)
        if not request.url.path.startswith("/api/"):
            resp.headers["Cache-Control"] = "no-cache"
        return resp

    @app.middleware("http")
    async def localize_api(request, call_next):
        """`?lang=ar` (or `X-Lang: ar`) returns the backend-written text of an API response in Arabic. Ids, codes and numbers never change."""
        lang = i18n.pick(request.query_params.get("lang") or request.headers.get("x-lang"))
        token = i18n.CURRENT.set(lang)
        try:
            resp = await call_next(request)
        finally:
            i18n.CURRENT.reset(token)
        if lang != "ar" or not request.url.path.startswith("/api/") or "json" not in resp.headers.get("content-type", ""):
            return resp
        body = b"".join([chunk async for chunk in resp.body_iterator])
        try:
            data = json.dumps(i18n.localize(json.loads(body), lang), ensure_ascii=False, default=str).encode("utf-8")
        except ValueError:
            data = body
        headers = {k: v for k, v in resp.headers.items() if k.lower() not in ("content-length", "content-type")}
        return Response(content=data, status_code=resp.status_code, headers=headers, media_type="application/json")

    gd = guardmod.Guard(p.settings.api_tokens)
    app.state.guard = gd

    @app.middleware("http")
    async def guard_every_api_route(request: Request, call_next):
        """One guard in front of every /api route except the health check; security headers on every response."""
        if request.url.path.startswith("/api/") and request.url.path not in guardmod.OPEN_PATHS:
            try:
                request.state.role = gd.check(request)
            except HTTPException as exc:
                resp = JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
                guardmod.apply_headers(resp)
                return resp
        resp = await call_next(request)
        guardmod.apply_headers(resp)
        return resp

    app.add_middleware(GZipMiddleware, minimum_size=20000)   # added last = outermost: the road and bus layers are several MB of JSON

    @app.exception_handler(StoreWriteError)
    async def record_refused(request, exc: StoreWriteError):
        """The system of record did not take a change. Nothing was changed; the operator is told why."""
        logging.getLogger("geoai.api").warning("refused by the system of record: %s", exc)
        return JSONResponse(status_code=503, content={"detail": f"ArcGIS Online did not accept the change, so nothing was changed. {exc}", "layer": exc.layer, "id": exc.fid})

    @app.on_event("shutdown")
    def give_the_lock_back():
        """A clean stop frees the one-server lock at once, so the next start does not have to wait for it to go stale."""
        release = getattr(p.store, "release", None)
        if release:
            release()

    def role(minimum: str):
        """The role the guard found: the token's role in token mode, the X-Role header (default operator) in local mode."""
        def dep(request: Request):
            r = getattr(request.state, "role", None) or "operator"
            if ROLES.get(r, -1) < ROLES[minimum]:
                raise HTTPException(403, f"role '{r}' cannot perform this action (needs {minimum})")
            return r
        return dep

    # ---------------------------------------------------------------- meta
    @app.get("/api/health")
    def health():
        return {"status": "ok", "agent_mode": ag.mode, "model": (ag.cfg.model if ag.uses_llm else "offline rule-based planner"), "planner": ag.cfg.label,
                "arcgis": p.mirror_status, "store": p.mirror_status, "data_ready": p.data_ready, "last_refresh": getattr(p.store, "last_refresh", None), "field_form": p.settings.field_form, "field_reports": "ArcGIS Field Maps" if p.mirror else "simulated crew only (no ArcGIS Online connection)", "data_mode": "SYNTHETIC-DEMO", "counts": {k: p.store.count(k) for k in PUBLIC_LAYERS + [S.WORKERS]}}

    @app.get("/api/config")
    def config():
        return {"arcgis_api_key": p.settings.arcgis_js_api_key, "areas": {k: {"center": v["center"]} for k, v in AREAS.items()}, "layers": PUBLIC_LAYERS,
                "corridors": list(CORRIDORS), "agent_mode": ag.mode, "arcgis": p.mirror_status,
                "disclosure": "Operational assets, sensors, workers and imagery processing are SYNTHETIC/SIMULATED. Area centres, corridors and landmarks are approximate reference geography."}

    # ---------------------------------------------------------------- layers
    @app.get("/api/layers/{name}")
    def layer(name: str, latest: bool = False, area: str | None = None, category: str | None = None, priority: str | None = None, since: str | None = None,
              bbox: str | None = None):
        """GeoJSON for a layer. area/category/priority/since apply the same Overview filters used by the KPIs (see services/filters.py)."""
        d = S.LAYERS.get(name)
        if not d or d.internal:
            raise HTTPException(404, "unknown layer")
        where = make_filter(p.store, name, area, category, priority, since)
        if bbox:
            try:
                x0, y0, x1, y1 = (float(v) for v in bbox.split(","))
            except ValueError:
                raise HTTPException(422, "bbox must be xmin,ymin,xmax,ymax")
            rows = p.store.bbox_query(name, x0, y0, x1, y1, limit=4000)
            return {"type": "FeatureCollection", "features": [{"type": "Feature", "id": f["id"], "geometry": f["geom"], "properties": f["attrs"]} for f in rows if where(f["attrs"])]}
        gj = p.store.geojson(name, where)
        if latest and name == S.SENSORS:
            last: dict = {}
            for f in gj["features"]:
                sid = f["properties"]["Sensor_ID"]
                if sid not in last or f["properties"]["Timestamp"] >= last[sid]["properties"]["Timestamp"]:
                    last[sid] = f
            gj["features"] = list(last.values())
        return gj

    @app.get("/api/layers/{name}/{fid}")
    def feature(name: str, fid: str):
        f = p.store.get(name, fid) if name in S.LAYERS and not S.LAYERS[name].internal else None
        if not f:
            raise HTTPException(404, "not found")
        return f

    # ---------------------------------------------------------------- mobility (reference layers and MODELLED traffic)
    def mobility_not_ready():
        """The model is built in the background. Until it is there the page gets a plain "not ready yet" with progress, never a long wait."""
        traffic.warm()
        st = traffic.status()
        if st["error"]:
            raise HTTPException(500, f"The traffic model could not be built: {st['error']}")
        return JSONResponse(status_code=503, headers={"Retry-After": "3"},
                            content={"detail": "The traffic model is still being built. Try again in a few seconds.", "ready": False, "hours_ready": st["hours_ready"], "hours_total": 24})

    @app.get("/api/mobility/status")
    def mobility_status():
        return traffic.status()

    @app.get("/api/mobility/roads")
    def mobility_roads():
        if not traffic.status()["network"]:
            return mobility_not_ready()
        return traffic.roads_geojson()

    @app.get("/api/mobility/traffic")
    def mobility_traffic(hour: int = Query(..., ge=0, le=23)):
        if hour not in traffic.status()["hours_ready"]:
            return mobility_not_ready()
        return traffic.state(hour)

    @app.get("/api/mobility/layers/{kind}")
    def mobility_layer(kind: str):
        if kind not in transit.KINDS:
            raise HTTPException(404, "unknown mobility layer: use " + ", ".join(transit.KINDS))
        return transit.geojson(kind, p.store)

    # closures that matter on a map: asked for, approved or in place (ended and rejected ones are history)
    @app.get("/api/mobility/closures")
    def mobility_closures():
        feats = []
        for f in p.store.all(S.CLOSURES):
            a = f["attrs"]
            if a.get("Status") not in ("Requested", "Approved", "In Place") or not f.get("geom") or mobility_numbers.window_over(a):
                continue
            feats.append({"type": "Feature", "id": f["id"], "geometry": f["geom"],
                          "properties": {"id": f["id"], "road": a.get("Section") or a.get("Corridor") or "", "corridor": a.get("Corridor") or "", "lanes_closed": a.get("Lanes_Closed"),
                                         "full_closure": a.get("Full_Closure") == "Yes", "start_time": a.get("Start_Time") or "", "end_time": a.get("End_Time") or "",
                                         "status": a["Status"], "reason": a.get("Reason") or "", "incident_id": a.get("Incident_ID") or ""}})
        return {"type": "FeatureCollection", "features": feats}

    @app.get("/api/mobility/numbers")
    def mobility_numbers_route():
        """The four mobility numbers of the Executive Hub and the congestion hotspots. Modelled; None where the model is not ready."""
        return {"summary": mobility_numbers.summary(p), "hotspots": mobility_numbers.hotspots(p)}

    @app.get("/api/brief.pdf")
    def daily_brief(lang: str = "en"):
        """The one-page daily brief, built from the records and the traffic model now. Nothing is stored."""
        lang = "ar" if lang == "ar" else "en"
        try:
            pdf = briefmod.build(p, lang)
        except pdf_arabic.ArabicUnavailable as exc:
            raise HTTPException(503, str(exc))
        return Response(content=pdf, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="riyadh-city-view-brief-{lang}.pdf"'})

    @app.get("/api/mobility/scenarios/{scenario_id}")
    def mobility_scenario(scenario_id: str):
        row = p.jobs.row(scenario_id)
        if not row:
            raise HTTPException(404, f"simulation {scenario_id} not found")
        return {**row, "job": p.jobs.status(scenario_id)}

    @app.get("/api/mobility/scenarios/{scenario_id}/strategies")
    def mobility_scenario_strategies(scenario_id: str):
        """The comparison of the response strategies of a closure simulation, as stored with its result. Modelled, with its assumptions."""
        row = p.jobs.row(scenario_id)
        if not row:
            raise HTTPException(404, f"simulation {scenario_id} not found")
        sm = row.get("summary") or {}
        if row.get("Status") != "Completed" or not sm.get("strategies"):
            raise HTTPException(409, f"simulation {scenario_id} has no strategy comparison (status: {row.get('Status') or 'unknown'})")
        rec = row.get("Recommended") or ""
        return {"scenario_id": scenario_id, "label": "Modelled", "recommended": rec, "verdict": row.get("Verdict") or "", "assumptions": sm.get("assumptions") or [],
                "strategies": [{**x, "strategy_name": x["name"], "recommended": x["id"] == rec} for x in sm["strategies"]]}

    @app.get("/api/mobility/scenarios/{scenario_id}/map")
    def mobility_scenario_map(scenario_id: str):
        """The drawing of a simulation: the closed section, the road sections that change and the detour routes. When it is no longer held it is
        calculated again in the background; the page asks again in a few seconds."""
        try:
            hit = p.jobs.request_preview(scenario_id)
        except KeyError:
            raise HTTPException(404, f"simulation {scenario_id} not found")
        except ValueError as exc:
            raise HTTPException(409, str(exc))
        if hit is None:
            return JSONResponse(status_code=503, headers={"Retry-After": "3"}, content={"detail": "The map drawing is being calculated again. Try again in a few seconds.", "ready": False})
        return hit

    @app.get("/api/sensors/{sensor_id}/series")
    def series(sensor_id: str):
        rows = sorted((f["attrs"] for f in p.store.all(S.SENSORS) if f["attrs"]["Sensor_ID"] == sensor_id), key=lambda a: a["Timestamp"])
        return {"sensor_id": sensor_id, "readings": rows[-72:]}

    # ---------------------------------------------------------------- agent
    @app.post("/api/chat")
    def chat(body: ChatIn, _=Depends(role("operator"))):
        return ag.chat(body.session_id, body.message)

    @app.post("/api/tools/{name}")
    def run_tool(name: str, body: ToolIn, _=Depends(role("operator"))):
        if name not in registry.BY_NAME:
            raise HTTPException(404, "unknown tool")
        return registry.execute(ag.session(body.session_id or "ui").ctx, name, body.args)

    @app.get("/api/tools")
    def tools():
        return [{"name": t.name, "stage": t.stage, "description": t.description, "consequential": t.consequential} for t in registry.TOOLS]

    # ---------------------------------------------------------------- approvals
    @app.get("/api/approvals")
    def approvals(pending: bool = False):
        return p.approvals.pending() if pending else p.approvals.all()[:50]

    @app.post("/api/approvals/{aid}/approve")
    def approve(aid: str, _=Depends(role("operator"))):
        res = ag.approve_via_ui(aid)
        if not res.get("ok"):
            raise HTTPException(409, res.get("error", "failed"))
        return res

    @app.post("/api/approvals/{aid}/reject")
    def reject(aid: str, _=Depends(role("operator"))):
        res = p.approvals.reject(aid, actor="operator (UI)")
        if not res.get("ok"):
            raise HTTPException(409, res.get("error", "failed"))
        return res

    # ---------------------------------------------------------------- NCCC crew (multi-agent automation + notifications)
    @app.get("/api/nccc/state")
    def nccc_state():
        """Everything the simplified command-center screen needs, in one call."""
        k = executive.compute_kpis(p.store)
        pend = p.approvals.pending()
        notes = p.crew.notifications(limit=60)
        return {"crew": {**p.crew.status(), "agents": p.crew.roster(), "activity": list(p.crew.activity)[:25]}, "feeds": p.crew.feed_status(),
                "kpis": {"open_incidents": k["open_incidents"], "critical": k["critical_incidents"], "pending_approvals": len(pend), "resolved": sum(1 for f in p.store.all(S.INCIDENTS) if f["attrs"]["Status"] in executive.CLOSED and not (f["attrs"]["Description"] or "").startswith("Historical")),
                         "unread": sum(1 for n in notes if n["Status"] == "New")},
                "notifications": notes, "approvals": pend, "agent_mode": ag.mode, "planner": ag.cfg.label, "store": p.mirror_status, "data_ready": p.data_ready}

    @app.get("/api/nccc/imagery/{area}")
    def nccc_imagery(area: str):
        """Everything the epoch-comparison viewer needs: scene bounds, the two epochs and the change events found between them."""
        if area not in AREAS:
            raise HTTPException(404, "unknown area")
        incident_of = {d["attrs"]["Related_Asset_ID"]: d["attrs"]["Incident_ID"] for d in p.store.query(S.DETECTIONS, Category="change") if d["attrs"]["Incident_ID"]}
        rows = []
        for f in p.store.query(S.CHANGES, Area_Name=area):
            a = f["attrs"]
            rows.append({"id": f["id"], "type": a["Change_Type"], "area_sqm": a["Area_Sqm"], "confidence": a["Confidence"], "significant": a["Significant"] == "Yes",
                         "status": a["Status"], "notes": a["Notes"], "incident_id": incident_of.get(f["id"], ""), "ring": f["geom"]["coordinates"][0]})
        rows.sort(key=lambda r: (not r["significant"], -r["area_sqm"]))
        return {"area": area, "areas": list(AREAS), "bounds": imagery.scene_bounds(area), "before": imagery.EPOCH_A, "after": imagery.EPOCH_B, "changes": rows, "scanned": bool(rows),
                "simulated": True}

    @app.post("/api/nccc/imagery/{area}/scan")
    def nccc_imagery_scan(area: str, _=Depends(role("operator"))):
        if area not in AREAS:
            raise HTTPException(404, "unknown area")
        return p.crew.run_cycle(deep=area)

    @app.get("/api/nccc/reports")
    def nccc_reports():
        return p.feeds.reports()

    @app.post("/api/nccc/incidents/{iid}/inspection")
    def nccc_inspection(iid: str, _=Depends(role("operator"))):
        res = p.crew.request_inspection(iid)
        if not res["ok"]:
            raise HTTPException(409, res["error"])
        return res

    @app.post("/api/nccc/incidents/{iid}/simulate-repair")
    def nccc_simulate_repair(iid: str, _=Depends(role("operator"))):
        """Report the repair of a confirmed fault as a SIMULATED crew, so the incident can go on to closure (still approved by a person)."""
        try:
            return p.simulate_repair(iid)
        except (ValueError, field.FieldError) as exc:
            raise HTTPException(409, str(exc))

    @app.get("/api/nccc/field-report/{vid}")
    def nccc_field_report(vid: str):
        """One investigator report in full: who, what they saw, where, the photo and how it compares with the AI finding."""
        v = p.store.get(S.VERIFICATION, vid)
        if not v:
            raise HTTPException(404, "report not found")
        a = v["attrs"]
        w, inc = p.store.get(S.WORKERS, a["Worker_ID"]), p.store.get(S.INCIDENTS, a["Incident_ID"])
        ia = inc["attrs"] if inc else {}
        return {"id": vid, "status": a["Verification_Status"], "observation": a["Observation"], "time": a["Timestamp"], "gps": a["GPS_Location"], "distance_m": a["Distance_To_Detection_M"],
                "photo": a["Photo_URL"], "assessment": a["Agent_Assessment"], "simulated": a["Simulated_Worker"] == "Yes", "work_order": a["Work_Order_ID"],
                "location": {"lon": v["geom"]["coordinates"][0], "lat": v["geom"]["coordinates"][1]},
                "worker": {"id": a["Worker_ID"], "name": w["attrs"]["Name"] if w else a["Worker_ID"], "team": w["attrs"]["Team"] if w else ""},
                "incident": {"id": ia.get("Incident_ID", ""), "type": ia.get("Incident_Type", ""), "area": ia.get("Area_Name", ""), "severity": ia.get("Severity", ""),
                             "priority": ia.get("Priority", ""), "status": ia.get("Status", ""), "description": ia.get("Description", "")}}

    @app.post("/api/nccc/field-sim")
    def nccc_field_sim(on: bool = True, _=Depends(role("operator"))):
        p.crew.simulate_field = on
        return p.crew.status()

    @app.post("/api/nccc/scan")
    def nccc_scan(deep: bool = False, follow: bool = False, _=Depends(role("operator"))):
        """follow=true is the step after a decision (dispatch, closure, field results only): it watches no feed, so it never opens incidents from other use cases."""
        return p.crew.run_cycle(deep=deep, scope=frozenset() if follow else None)

    @app.post("/api/nccc/autopilot")
    def nccc_autopilot(on: bool = True, interval: float = 60.0, _=Depends(role("operator"))):
        return p.crew.start(interval) if on else p.crew.stop()

    @app.post("/api/nccc/events/{name}")
    def nccc_event(name: str, _=Depends(role("operator"))):
        """Inject a demo event (a fault or a change) for the crew to find. Events are SIMULATED."""
        try:
            return p.crew.inject(name)
        except ValueError as exc:
            raise HTTPException(400, str(exc))

    @app.post("/api/nccc/notifications/{nid}/ack")
    def nccc_ack(nid: str, _=Depends(role("operator"))):
        return {"acknowledged": p.crew.acknowledge(nid)}

    @app.post("/api/nccc/notifications/ack-all")
    def nccc_ack_all(_=Depends(role("operator"))):
        return {"acknowledged": p.crew.acknowledge(None)}

    # ---------------------------------------------------------------- planner choice (offline rules, Claude, OpenAI, Gemini, local servers)
    @app.get("/api/planner")
    def planner_get():
        """The active planner and the choices. API keys are never returned, only whether one is set."""
        return ag.planner_info()

    @app.post("/api/planner")
    def planner_set(body: PlannerIn, _=Depends(role("operator"))):
        try:
            ag.set_planner(body.provider, body.model, body.base_url, body.api_key)
        except providers.PlannerError as exc:
            raise HTTPException(400, str(exc))
        p.audit.log("operator", f"PLANNER set to {ag.cfg.label}", "planner", "", {"provider": ag.cfg.provider, "model": ag.cfg.model, "base_url": ag.cfg.base_url}, "key not logged")
        return ag.planner_info()

    @app.post("/api/planner/models")
    def planner_models(body: PlannerIn, _=Depends(role("operator"))):
        """The models the chosen server says it has (so a wrong model name is easy to fix). The key is used for the call and never returned."""
        try:
            names, up = ag.list_models(body.provider, body.base_url, body.api_key)
            return {"models": names, "reachable": up}
        except providers.PlannerError as exc:
            raise HTTPException(400, str(exc))

    @app.post("/api/planner/test")
    def planner_test(_=Depends(role("operator"))):
        return ag.test_planner()

    @app.post("/api/nccc/ask")
    def nccc_ask(body: ChatIn, _=Depends(role("operator"))):
        """Ask the crew in plain language; the reply names which agent used which tool."""
        res = ag.chat(body.session_id or "nccc", body.message)
        for t in res.get("trace", []):
            t["agent"] = crewmod.agent_for_tool(t["tool"])
        res["agents"] = list(dict.fromkeys(["mansour"] + [t["agent"] for t in res.get("trace", [])]))
        return res

    # ---------------------------------------------------------------- intelligence
    @app.get("/api/executive")
    def exec_summary(area: str | None = None, category: str | None = None, priority: str | None = None, since: str | None = None):
        return registry.execute(ag.session("ui").ctx, "executive_summary", {k: v for k, v in dict(area=area, category=category, priority=priority, since=since).items() if v})

    @app.get("/api/kpis")
    def kpis(area: str | None = None, category: str | None = None, priority: str | None = None, since: str | None = None):
        return executive.compute_kpis(p.store, area, category, priority, since)

    @app.get("/api/hotspots")
    def hot(area: str | None = None, category: str | None = None, priority: str | None = None, since: str | None = None):
        return executive.hotspots(p.store, area, category, priority, since)

    @app.get("/api/trends")
    def trend(area: str | None = None, category: str | None = None, priority: str | None = None, since: str | None = None):
        return executive.trends(p.store, 45, area, category, priority, since)

    @app.get("/api/evaluation")
    def evaluation():
        return learning.evaluation(p.store)

    @app.get("/api/audit")
    def audit(n: int = 60, incident: str | None = None):
        return p.audit.recent(min(n, 300), incident)

    @app.get("/api/incidents")
    def incidents(open_only: bool = False, category: str | None = None, area: str | None = None, priority: str | None = None, since: str | None = None):
        return registry.execute(ag.session("ui").ctx, "list_incidents", {k: v for k, v in dict(open_only=open_only or None, category=category, area=area, priority=priority, since=since, limit=100).items() if v})

    @app.get("/api/incidents/{iid}")
    def incident(iid: str):
        r = registry.execute(ag.session("ui").ctx, "get_incident", {"incident_id": iid})
        if not r["ok"]:
            raise HTTPException(404, r["error"])
        return r

    # ---------------------------------------------------------------- field portal
    @app.get("/api/workers")
    def workers():
        return [{**f["attrs"], "location": f["geom"]["coordinates"]} for f in p.store.all(S.WORKERS)]

    @app.get("/field.html")
    def field_page():
        if p.settings.field_form:
            return FileResponse("frontend/field.html")
        return HTMLResponse(FIELD_PAGE)

    @app.get("/api/field/tasks/{worker_id}")
    def tasks(worker_id: str, _=Depends(role("worker"))):
        if not p.store.get(S.WORKERS, worker_id):
            raise HTTPException(404, "worker not found")
        return field.tasks_for_worker(p.store, worker_id)

    @app.post("/api/field/submit")
    async def submit(work_order_id: str = Form(...), worker_id: str = Form(...), status: str = Form(...), observation: str = Form(...), lat: float = Form(...),
                     lon: float = Form(...), photo: UploadFile | None = File(None), _=Depends(role("worker"))):
        if not p.settings.field_form:
            raise HTTPException(410, FORM_OFF)
        data = await photo.read() if photo is not None and photo.filename else None
        try:
            res = field.submit(p.store, p.audit, work_order_id, worker_id, status, observation, lat, lon, data, photo.filename if photo else "")
        except field.FieldError as exc:
            raise HTTPException(422, str(exc))
        p.crew.field_update()                         # the operator sees the report straight away
        return res

    @app.post("/api/field/accept")
    def accept(work_order_id: str = Form(...), worker_id: str = Form(...), _=Depends(role("worker"))):
        if not p.settings.field_form:
            raise HTTPException(410, FORM_OFF)
        try:
            res = field.accept(p.store, p.audit, work_order_id, worker_id)
        except field.FieldError as exc:
            raise HTTPException(422, str(exc))
        if not res["already"]:
            p.crew.field_accepted(work_order_id, worker_id)
        return res

    @app.get("/api/evidence/{vid}/{name}")
    def evidence(vid: str, name: str):
        """A photo an investigator attached to a report. It is read from the report's row in the system of record."""
        data = p.store.attachment(S.VERIFICATION, vid, Path(name).name)
        if data is None:
            raise HTTPException(404)
        kind = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}.get(Path(name).suffix.lower(), "application/octet-stream")
        return Response(content=data, media_type=kind)

    # ---------------------------------------------------------------- simulation
    @app.get("/api/sim/status")
    def sim_status():
        return {**p.sim.status(), "events": p.sim.events(25)}

    @app.post("/api/sim/start")
    def sim_start(interval: float = 5.0, _=Depends(role("operator"))):
        return p.sim.start(max(1.0, interval))

    @app.post("/api/sim/pause")
    def sim_pause(_=Depends(role("operator"))):
        return p.sim.pause()

    @app.post("/api/sim/tick")
    def sim_tick(_=Depends(role("operator"))):
        return p.sim.tick()

    @app.post("/api/sim/anomaly-rate")
    def sim_rate(rate: float = 0.0, _=Depends(role("operator"))):
        p.sim.anomaly_rate = max(0.0, min(1.0, rate))
        return p.sim.status()

    @app.post("/api/sim/scenario/{name}")
    def sim_scenario(name: str, _=Depends(role("operator"))):
        try:
            return p.sim.scenario(name)
        except ValueError as exc:
            raise HTTPException(400, str(exc))

    @app.post("/api/sim/modify-sensor")
    def sim_modify(body: SensorMod, _=Depends(role("operator"))):
        try:
            return p.sim.modify_sensor(body.sensor_id, body.pressure_drop_pct, body.flow_rise_pct, body.hours)
        except ValueError as exc:
            raise HTTPException(400, str(exc))

    @app.post("/api/sim/field-response/{work_order_id}")
    def sim_field(work_order_id: str, repair: bool = False, _=Depends(role("operator"))):
        try:
            return p.simulate_field_response(work_order_id, repair)
        except (ValueError, field.FieldError) as exc:
            raise HTTPException(409, str(exc))

    @app.post("/api/sim/reset")
    def sim_reset(_=Depends(role("operator"))):
        return demo.reset()

    # ---------------------------------------------------------------- demo
    @app.get("/api/demo/scenes")
    def scenes():
        return [{"scene": n, "stage": s, "title": t} for n, s, t in SCENES]

    @app.post("/api/demo/run/{scene}")
    def demo_run(scene: int, auto_approve: bool = False, _=Depends(role("operator"))):
        try:
            return demo.run(scene, auto_approve)
        except ValueError as exc:
            raise HTTPException(400, str(exc))

    @app.post("/api/demo/reset")
    def demo_reset(_=Depends(role("operator"))):
        return demo.reset()

    # ---------------------------------------------------------------- imagery
    @app.get("/api/imagery/{area}/{epoch}.png")
    def img(area: str, epoch: str):
        if area not in AREAS or epoch not in ("A", "B", "Bn"):
            raise HTTPException(404)
        return Response(imagery.render_png(area, epoch, p.settings.seed), media_type="image/png")

    @app.get("/api/imagery/{area}/bounds")
    def bounds(area: str):
        if area not in AREAS:
            raise HTTPException(404)
        return {**imagery.scene_bounds(area), "epochs": {"A": imagery.EPOCH_A, "B": imagery.EPOCH_B}, "simulated": True}

    fe = ROOT / "frontend"
    @app.get("/")
    def read_root():
        return FileResponse("frontend/home.html")

    if fe.exists():
        app.mount("/", StaticFiles(directory=str(fe), html=True), name="ui")
    return app


def app_factory() -> FastAPI:  # uvicorn --factory backend.api.app:app_factory
    return create_app()
