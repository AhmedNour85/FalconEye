"""DECIDE / ACT tools: incident management, work orders, field assignment, closure. Consequential steps only PROPOSE (approval gate)."""
from __future__ import annotations

from datetime import datetime, timezone

from backend.gis import geo
from backend.gis import schema as S
from backend.gis.store import utcnow
from backend.services import learning, visual_types
from backend.services.workforce import TEAM_FOR, rank_workers
from backend.tools.common import ToolContext, ToolError, priority_of, severity_of

CLOSED = ("Resolved", "Closed - False Positive")
DUE_HOURS = {"P1": 4, "P2": 12, "P3": 48, "P4": 120}
INSTR = {"water": "Locate the suspected leak near the marked point, check for surface water / valve transients, photograph evidence, record GPS and confirm or reject.",
         "lighting": "Inspect the listed lamps for flicker, driver or cable damage, photograph evidence, record GPS and confirm or reject the predicted failure.",
         "change": "Visit the polygon, determine whether construction/clearing is present or only seasonal change, photograph evidence and confirm or reject.",
         "distortion": "Inspect the flagged building from street level, photograph cracks, bulging or leaning, record GPS and confirm or reject the structural distortion.",
         "pole_health": "Inspect the listed poles: measure tilt with an inclinometer, check base corrosion and anchor bolts, photograph evidence and confirm or reject the structural risk.",
         "land_use": "Visit the polygon, confirm what is being built, check the permit against the zoning, photograph evidence and confirm or reject the violation.",
         "mobility": "Go to the marked point on the road, confirm what is there (blocked lanes, a closure being set up, or event traffic), photograph evidence, record GPS and confirm or reject."}
MOBILITY_TYPES = {"Traffic Incident": "Traffic Incident", "Road Closure Request": "Planned Road Closure", "Major Event": "Major Event Traffic Plan"}   # detection type -> incident type


def _incident_or_focus(ctx: ToolContext, incident_id: str | None) -> dict:
    iid = incident_id or ctx.state.get("focus_incident")
    if not iid:
        raise ToolError("no incident specified and none in context; list or create incidents first")
    f = ctx.store.get(S.INCIDENTS, iid)
    if not f:
        raise ToolError(f"incident {iid} not found")
    return f


def _age_hours(a: dict) -> float:
    try:
        return (datetime.now(timezone.utc) - datetime.strptime(a["Created_Date"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)).total_seconds() / 3600
    except Exception:
        return 0.0


def urgency(a: dict) -> float:
    """Operational ranking score: risk score plus a small ageing term (max +10)."""
    return round(a["Risk_Score"] + min(10.0, _age_hours(a) / 12), 1)


def create_incidents_from_detections(ctx: ToolContext, detection_ids: list[str] | None = None) -> dict:
    """Convert detections into operational incidents (idempotent: no duplicates; lighting detections of one cluster become one incident)."""
    st = ctx.store
    active = [f for f in st.all(S.DETECTIONS) if f["attrs"]["Status"] in ("Suspected", "Predicted", "Candidate")]
    unlinked = [f["id"] for f in active if not f["attrs"]["Incident_ID"] or not st.get(S.INCIDENTS, f["attrs"]["Incident_ID"])]
    if detection_ids:
        ids = detection_ids                                                       # explicit request
    else:
        recent = [d for d in ctx.state.get("last_detections", []) if d in set(unlinked)]   # the detections this conversation just produced ...
        ids = recent or unlinked                                                  # ... else EVERYTHING still waiting for an incident
    dets = []
    for d in ids:
        f = st.get(S.DETECTIONS, d)
        if not f:
            raise ToolError(f"detection {d} not found")
        dets.append(f)
    created, existing = [], []
    groups: dict[str, list[dict]] = {}
    for d in dets:
        a = d["attrs"]
        if a["Incident_ID"] and st.get(S.INCIDENTS, a["Incident_ID"]):
            existing.append(a["Incident_ID"])
            continue
        key = a["Cluster_ID"] or d["id"]
        groups.setdefault(key, []).append(d)
    for key, ds in groups.items():
        top = max(ds, key=lambda x: x["attrs"]["Risk_Score"])
        a = top["attrs"]
        risk = float(max(x["attrs"]["Risk_Score"] for x in ds))
        cat = a["Category"]
        iid = st.next_id("INC")
        if cat == "lighting" and len(ds) > 1:
            pts = [geo.centroid(x["geom"]) for x in ds]
            c = (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
            if key.startswith("POLE-"):
                desc = f"{len(ds)} streetlight poles on {a['Location']} exceed the tilt/corrosion limits (cluster {key}). PREDICTED structural risk, not confirmed."
                itype = "Streetlight Pole Inspection"
            else:
                desc = f"{len(ds)} streetlights on {a['Location']} with elevated predicted failure probability (cluster {key}). PREDICTED, not confirmed."
                itype = "Streetlight Cluster Maintenance"
        else:
            c = geo.centroid(top["geom"])
            desc = a["Evidence"][:420]
            itype = {"water": "Water Leak (Suspected)", "lighting": "Streetlight Failure (Predicted)", "change": "Urban Change Review", "distortion": "Visual Distortion Review", "land_use": "Land-Use Violation Review",
                     "mobility": MOBILITY_TYPES.get(a["Detection_Type"], "Traffic Incident")}[cat]
            vt = visual_types.by_name(a["Detection_Type"]) if cat == "distortion" else None
            if vt:
                itype = vt["name"]                                                  # for example "Illegal Graffiti" instead of the generic review
        st.upsert(S.INCIDENTS, {"Incident_ID": iid, "Incident_Type": itype, "Priority": priority_of(risk), "Severity": severity_of(risk), "Risk_Score": risk,
                                "Location": a["Location"], "Description": desc, "Related_Asset_ID": key if len(ds) > 1 else a["Related_Asset_ID"], "Assigned_Team": TEAM_FOR[cat],
                                "Status": "Open", "Created_Date": utcnow(), "Last_Updated": utcnow(), "Detection_IDs": ",".join(x["id"] for x in ds), "Area_Name": a["Area_Name"],
                                "Category": cat, "Verification_Outcome": "", "Data_Classification": S.OPERATIONAL}, geo.point(*c))
        for x in ds:
            st.update(S.DETECTIONS, x["id"], Incident_ID=iid)
        ctx.p.audit.log(ctx.session_id, "INCIDENT CREATED", "manage_incidents", iid, {"detections": [x["id"] for x in ds]}, {"priority": priority_of(risk), "risk": risk})
        created.append({"incident_id": iid, "type": itype, "priority": priority_of(risk), "severity": severity_of(risk), "risk_score": risk, "area": a["Area_Name"],
                        "detections": [x["id"] for x in ds], "assigned_team": TEAM_FOR[cat]})
    created.sort(key=lambda r: -r["risk_score"])
    if created:
        ctx.state["focus_incident"] = created[0]["incident_id"]
        ctx.state["last_incidents"] = [c["incident_id"] for c in created]
    scope = "the requested detection(s)" if detection_ids else f"all {len(active)} active detection(s)"
    if not created and not existing:   # nothing waiting: report the incidents that already cover this conversation's detections (else all active ones)
        def linked(fs):
            return [f["attrs"]["Incident_ID"] for f in fs if f and f["attrs"]["Incident_ID"] and st.get(S.INCIDENTS, f["attrs"]["Incident_ID"])]
        mine = linked([st.get(S.DETECTIONS, d) for d in ctx.state.get("last_detections", [])])
        existing = mine or linked(active)
        scope = "the detection(s) from this conversation" if mine else f"all {len(active)} active detection(s)"
    if created:
        message = f"Created {len(created)} incident(s) from {sum(len(c['detections']) for c in created)} detection(s). Nothing has been dispatched yet."
    elif existing:
        message = f"No new detections to convert: {scope} already have incidents ({', '.join(sorted(set(existing))[:5])})."
    else:
        message = "There are no active detections to convert. Run a detection first (for example detect water leaks, predict streetlight failures or compare imagery epochs)."
    return {"created": created, "already_existing": sorted(set(existing)), "active_detections": len(active), "waiting_before": len(unlinked), "message": message,
            "note": "Incidents are created in status Open; no external action has been taken."}


def list_incidents(ctx: ToolContext, status: str | None = None, category: str | None = None, area: str | None = None, priority: str | None = None,
                   open_only: bool = False, limit: int = 15, since: str | None = None) -> dict:
    rows = []
    for f in ctx.store.all(S.INCIDENTS):
        a = f["attrs"]
        if (status and a["Status"] != status) or (category and a["Category"] != category) or (area and a["Area_Name"] != area) or (priority and a["Priority"] != priority):
            continue
        if open_only and a["Status"] in CLOSED:
            continue
        if since and a["Created_Date"] < since:
            continue
        rows.append({"incident_id": f["id"], "type": a["Incident_Type"], "priority": a["Priority"], "severity": a["Severity"], "risk_score": a["Risk_Score"], "urgency": urgency(a),
                     "status": a["Status"], "area": a["Area_Name"], "category": a["Category"], "team": a["Assigned_Team"], "verification": a["Verification_Outcome"],
                     "created": a["Created_Date"]})
    rows.sort(key=lambda r: -r["urgency"])
    if rows:
        ctx.state["last_incidents"] = [r["incident_id"] for r in rows[:limit]]
    return {"count": len(rows), "incidents": rows[:limit]}


def get_incident(ctx: ToolContext, incident_id: str | None = None) -> dict:
    f = _incident_or_focus(ctx, incident_id)
    ctx.state["focus_incident"] = f["id"]
    dets = [ctx.store.get(S.DETECTIONS, d) for d in f["attrs"]["Detection_IDs"].split(",") if d]
    wos = ctx.store.query(S.WORK_ORDERS, Incident_ID=f["id"])
    if wos:
        ctx.state["focus_work_order"] = wos[-1]["id"]
    ver = ctx.store.query(S.VERIFICATION, Incident_ID=f["id"])
    return {"incident": f["attrs"], "location": dict(zip(("lon", "lat"), geo.centroid(f["geom"]))),
            "detections": [{"id": d["id"], "type": d["attrs"]["Detection_Type"], "status": d["attrs"]["Status"], "risk_score": d["attrs"]["Risk_Score"],
                            "confidence": d["attrs"]["Confidence"], "evidence": d["attrs"]["Evidence"]} for d in dets if d],
            "work_orders": [w["attrs"] for w in wos], "verifications": [v["attrs"] for v in ver], "audit": ctx.p.audit.recent(8, f["id"])}


def rank_incidents(ctx: ToolContext, top_n: int = 5, category: str | None = None, area: str | None = None, priority: str | None = None, since: str | None = None) -> dict:
    """Rank open incidents by urgency (risk score + ageing) and explain the ordering."""
    r = list_incidents(ctx, category=category, area=area, priority=priority, since=since, open_only=True, limit=max(1, min(int(top_n), 25)))
    ranked = []
    for i, row in enumerate(r["incidents"], 1):
        inc = ctx.store.get(S.INCIDENTS, row["incident_id"])
        dets = [ctx.store.get(S.DETECTIONS, d) for d in inc["attrs"]["Detection_IDs"].split(",") if d]
        ev = [f"risk {row['risk_score']} ({row['severity']})", f"status {row['status']}"]
        if dets and dets[0]:
            ev.append(f"{len(dets)} linked detection(s); confidence {max(d['attrs']['Confidence'] for d in dets if d)}")
        ranked.append({**row, "rank": i, "evidence": ev})
    if ranked:
        ctx.state["focus_incident"] = ranked[0]["incident_id"]
    return {"ranked": ranked, "open_total": r["count"], "ordering": "urgency = risk score (calibrated by verified outcomes) + ageing (max +10)"}


# ---------------------------------------------------------------------------------------------- proposals
def propose_work_order(ctx: ToolContext, incident_id: str | None = None, instructions: str = "") -> dict:
    f = _incident_or_focus(ctx, incident_id)
    a = f["attrs"]
    if a["Status"] in CLOSED:
        raise ToolError(f"incident {f['id']} is {a['Status']}")
    for w in ctx.store.query(S.WORK_ORDERS, Incident_ID=f["id"]):
        if w["attrs"]["Status"] in ("Created", "Assigned", "In Progress"):
            raise ToolError(f"incident {f['id']} already has active work order {w['id']}")
    team = TEAM_FOR[a["Category"]]
    payload = {"incident_id": f["id"], "team": team, "task_type": "Inspect & Verify", "instructions": instructions or (visual_types.by_name(a["Incident_Type"]) or {}).get("instr") or INSTR["pole_health" if "Pole" in a["Incident_Type"] else a["Category"]], "due_hours": DUE_HOURS[a["Priority"]]}
    rec = ctx.p.approvals.propose(ctx.session_id, "create_work_order", payload, f"Create {a['Priority']} work order for {f['id']} ({a['Incident_Type']}, {a['Area_Name']})",
                                  target=f["id"], location=a["Location"], priority=a["Priority"], team=team,
                                  expected=f"Work order created in the system of record; incident moves to 'Work Order Created'; due in {DUE_HOURS[a['Priority']]} h.", incident_id=f["id"])
    ctx.state["focus_incident"] = f["id"]
    ctx.state["pending_approval"] = rec["Approval_ID"]
    return {"status": "AWAITING_APPROVAL", "approval": rec, "message": "Nothing has been created yet. The operator must approve this proposal."}


def propose_work_orders_bulk(ctx: ToolContext, top_n: int = 5) -> dict:
    ranked = rank_incidents(ctx, top_n)["ranked"]
    proposals, skipped = [], []
    for r in ranked:
        try:
            proposals.append(propose_work_order(ctx, r["incident_id"])["approval"])
        except ToolError as exc:
            skipped.append({"incident_id": r["incident_id"], "reason": str(exc)})
    return {"status": "AWAITING_APPROVAL", "proposals": proposals, "skipped": skipped, "message": "No work orders exist until each proposal is approved."}


def propose_field_assignment(ctx: ToolContext, work_order_id: str | None = None, worker_id: str | None = None) -> dict:
    wid = work_order_id or ctx.state.get("focus_work_order")
    if not wid and ctx.state.get("focus_incident"):
        wos = [w for w in ctx.store.query(S.WORK_ORDERS, Incident_ID=ctx.state["focus_incident"]) if w["attrs"]["Status"] in ("Created", "Assigned")]
        wid = wos[-1]["id"] if wos else None
    if not wid:
        raise ToolError("no work order specified or in context; create a work order first")
    wo = ctx.store.get(S.WORK_ORDERS, wid)
    if not wo:
        raise ToolError(f"work order {wid} not found")
    inc = ctx.store.get(S.INCIDENTS, wo["attrs"]["Incident_ID"])
    ranking = rank_workers(ctx.store, geo.centroid(inc["geom"]), inc["attrs"]["Category"])
    chosen = next((r for r in ranking if r["worker_id"] == worker_id), None) if worker_id else ranking[0]
    if not chosen:
        raise ToolError(f"worker {worker_id} not found")
    rec = ctx.p.approvals.propose(ctx.session_id, "assign_worker", {"work_order_id": wid, "worker_id": chosen["worker_id"]},
                                  f"Assign {chosen['name']} ({chosen['team']}) to {wid} for {inc['id']}", target=wid, location=inc["attrs"]["Location"], priority=wo["attrs"]["Priority"],
                                  team=chosen["team"], expected=f"Field task appears in {chosen['name']}'s portal; incident status becomes Assigned.", incident_id=inc["id"])
    ctx.state["focus_work_order"] = wid
    ctx.state["pending_approval"] = rec["Approval_ID"]
    return {"status": "AWAITING_APPROVAL", "recommended_worker": chosen, "alternatives": ranking[1:3], "approval": rec,
            "message": "Worker is not assigned until the operator approves."}


def propose_incident_closure(ctx: ToolContext, incident_id: str | None = None) -> dict:
    f = _incident_or_focus(ctx, incident_id)
    a = f["attrs"]
    if not a["Verification_Outcome"]:
        raise ToolError("incident has no field verification; closing is not allowed")
    if a["Verification_Outcome"] == "Confirmed" and a["Status"] != "Repair Reported":
        raise ToolError("fault confirmed but repair not yet reported by the field team; to continue in a demo, report the repair as a simulated crew (the 'Simulate repair' button on the verified alert, or say 'simulate repair for " + f["id"] + "')")
    res = "Resolved" if a["Verification_Outcome"] == "Confirmed" else "Closed - False Positive"
    rec = ctx.p.approvals.propose(ctx.session_id, "close_incident", {"incident_id": f["id"]}, f"Close incident {f['id']} as '{res}'", target=f["id"], location=a["Location"],
                                  priority=a["Priority"], team=a["Assigned_Team"], expected=f"Incident status becomes '{res}'.", incident_id=f["id"])
    ctx.state["pending_approval"] = rec["Approval_ID"]
    return {"status": "AWAITING_APPROVAL", "approval": rec}


def propose_asset_status_change(ctx: ToolContext, asset_id: str, new_status: str) -> dict:
    if not ctx.store.get(S.INFRA, asset_id):
        raise ToolError(f"asset {asset_id} not found")
    if new_status not in ("Operational", "In Service", "Under Maintenance", "Out of Service", "Isolated"):
        raise ToolError("new_status must be one of Operational, In Service, Under Maintenance, Out of Service, Isolated")
    rec = ctx.p.approvals.propose(ctx.session_id, "change_asset_status", {"asset_id": asset_id, "new_status": new_status}, f"Set {asset_id} to '{new_status}'", target=asset_id,
                                  expected="Operational asset status changes in the system of record.")
    ctx.state["pending_approval"] = rec["Approval_ID"]
    return {"status": "AWAITING_APPROVAL", "approval": rec}


def count_incidents(ctx: ToolContext, area: str | None = None, category: str | None = None, severity: str | None = None, open_only: bool = True) -> dict:
    """How many incidents, and where: counts by area, type, priority and status (all read from the incident records)."""
    from collections import Counter

    rows = [f["attrs"] for f in ctx.store.all(S.INCIDENTS)]
    sel = [a for a in rows if (not area or a["Area_Name"] == area) and (not category or a["Category"] == category) and (not severity or a["Severity"] == severity)
           and (not open_only or a["Status"] not in CLOSED)]
    order = lambda c: dict(sorted(c.items(), key=lambda kv: (-kv[1], kv[0])))  # noqa: E731
    return {"count": len(sel), "open_only": open_only, "scope": {"area": area, "category": category, "severity": severity}, "total_all_time": len(rows),
            "critical": sum(1 for a in sel if a["Severity"] == "Critical"), "by_area": order(Counter(a["Area_Name"] for a in sel)),
            "by_category": order(Counter(a["Category"] for a in sel)), "by_priority": order(Counter(a["Priority"] for a in sel)),
            "by_status": order(Counter(a["Status"] for a in sel)), "awaiting_approval": len(ctx.p.approvals.pending())}


def feeds_summary(ctx: ToolContext, area: str | None = None) -> dict:
    """What residents are telling us: citizen-report counts by status, type and area."""
    from collections import Counter

    if not ctx.p.feeds.citizen_enabled:
        raise ToolError("The citizen-report feed is disabled in this deployment (set GEOAI_CITIZEN_REPORTS=1 to enable it).")
    reps = [f["attrs"] for f in ctx.store.all(S.CITIZEN) if not area or f["attrs"]["Area_Name"] == area]
    return {"reports": len(reps), "waiting": sum(1 for r in reps if r["Status"] == "New"), "linked_to_incidents": sum(1 for r in reps if r["Linked_Incident"]),
            "by_category": dict(Counter(r["Category"] for r in reps)), "by_area": dict(sorted(Counter(r["Area_Name"] for r in reps).items(), key=lambda kv: -kv[1])),
            "latest_report": max((r["Reported_At"] for r in reps), default=None), "scope": area or "all areas",
            "caveat": "Citizen reports are a SIMULATED feed in this demo."}
