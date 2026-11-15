"""Scenario engine: builds a separate scenario network per run, compares it with the (untouched) baseline,
and persists full inputs/outputs for reproducibility.

Classification of outputs (always shown to users):
  * NETWORK ANALYSIS      - connectivity, alternative routes, distances (deterministic graph computations)
  * ESTIMATED IMPACTS     - static-assignment travel-time / congestion estimates (documented assumptions)
  * NOT PREDICTIVE ANALYTICS / NOT MICROSIMULATION - see services/predictive_analytics.py and sumo_adapter.py
"""
from __future__ import annotations

import datetime as dt
import json
import threading
import time
from collections import defaultdict
from typing import Callable, Dict, List, Optional

from backend.data import riyadh_network as RN
from backend.gis import feature_source, store
from backend.services.osm_service import haversine_km
from backend.services.synthetic_data import demand_factor
from backend.simulation import accessibility as acc
from backend.simulation import alternative_routes as alt
from backend.simulation import event_impact, network_resilience as res_mod, road_closure, traffic_demand
from backend.simulation.network_model import ASSUMPTIONS, NetworkModel, get_model, level

TYPES = ("closure", "demand", "event", "infrastructure")
DEFAULT_WINDOW = {"closure": (8, 16), "demand": (7, 10), "event": (17, 21), "infrastructure": (7, 19)}
LIMITATIONS = ASSUMPTIONS + [
    "Road geometry is an approximate schematic skeleton unless replaced by OSM/authoritative data.",
    "Not a microsimulation: no signal phasing, queue spillback, lane-changing or driver behaviour.",
    "All traffic inputs are synthetic; results are for relative comparison between scenarios only.",
]


def _parse(ts):
    if not ts:
        return None
    try:
        return dt.datetime.fromisoformat(str(ts).replace("Z", ""))
    except ValueError:
        raise ValueError(f"invalid datetime '{ts}' (use ISO 8601, e.g. 2026-11-13T08:00)")


def window_hours(p: dict) -> Dict:
    s, e = _parse(p.get("start_time")), _parse(p.get("end_time"))
    d0, d1 = DEFAULT_WINDOW[p["scenario_type"]]
    if s and not e and p.get("duration_hours"):
        e = s + dt.timedelta(hours=float(p["duration_hours"]))
    if s and e:
        if e <= s:
            raise ValueError("end_time must be after start_time")
        n = max(1, int((e - s).total_seconds() // 3600))
        hours = [(s.hour + i) % 24 for i in range(min(n, 24))]
        weekend = s.weekday() in (4, 5)  # Fri/Sat
    else:
        hours, n, weekend = list(range(d0, d1)), d1 - d0, False
    k = max(1, int(p.get("max_hours") or 4))   # sampled hours per run (strategy studies use fewer to stay fast)
    sample = list(hours) if len(hours) <= k else ([hours[0]] if k == 1 else [hours[round(i * (len(hours) - 1) / (k - 1))] for i in range(k)])
    peak = max(hours, key=lambda h: demand_factor(h, weekend))
    if peak not in sample:
        sample[-1] = peak
    sample = sorted(set(sample), key=lambda h: demand_factor(h, weekend))  # peak evaluated last
    return {"hours": hours, "sample_hours": sample, "peak_hour": peak, "duration_h": n, "weekend": weekend,
            "peak_scale": demand_factor(peak, weekend), "start": s.isoformat() if s else None, "end": e.isoformat() if e else None}


# ------------------------------------------------------------------------------------------------
def _setup(p: dict, base: NetworkModel, wh: dict):
    """Returns (scenario_model, od_mult, extra_od, info)."""
    sm = base.clone()
    info: Dict = {}
    od_mult, extra_od = None, None
    t = p["scenario_type"]
    if t == "closure":
        corridor = road_closure.resolve_corridor(p.get("corridor") or p.get("road") or "")
        if not corridor:
            raise ValueError("closure scenario requires a known corridor (e.g. 'King Fahd Road')")
        ref = base.clone().assign(wh["peak_scale"], use_cache=False)["edges"]
        sel = road_closure.select_closure(base, corridor, ref, p.get("segment_ids"), p.get("near"), p.get("section"), float(p.get("span_km") or 2.0))
        if not sel["ids"]:
            raise ValueError(sel["why"])
        sm.close_segments(sel["ids"])
        info = {"corridor": corridor, **sel}
    elif t == "demand":
        nodes = traffic_demand.resolve_area(sm, p.get("area"))
        pct = float(p.get("demand_change_pct", 20))
        od_mult = traffic_demand.area_multiplier(nodes, pct)
        info = {"area": p.get("area") or "whole city", "area_nodes": len(nodes), "demand_change_pct": pct}
    elif t == "event":
        ev = event_impact.build_event(sm, p.get("place") or p.get("location") or "KAFD", **(p.get("event") or {}))
        extra_od = ev["extra_od"]
        info = {"event": ev["info"], "venue_node": ev["node"]}
        if p.get("demand_change_pct"):
            od_mult = traffic_demand.area_multiplier(set(sm.G.nodes), float(p["demand_change_pct"]))
    elif t == "infrastructure":
        nl = p.get("new_link") or {}
        a = sm.resolve_place(nl.get("from") or "KAFD")
        b = sm.resolve_place(nl.get("to") or "RiyadhFront")
        if not a or not b or a == b:
            raise ValueError("infrastructure scenario needs two distinct places/nodes in new_link.from/to")
        sid = sm.add_link(a, b, int(nl.get("lanes", 3)), float(nl.get("speed", 80)), nl.get("name", "Proposed link (scenario)"))
        info = {"new_link": sm.added[-1], "new_segment_id": sid}
    # ---- response-strategy modifiers (applied to the SCENARIO network only; the baseline is never touched) ----
    mods = p.get("modifiers") or {}
    cb = mods.get("capacity_boost")
    if cb and cb.get("segment_ids"):
        ids, f, n = set(cb["segment_ids"]), 1 + float(cb.get("pct", 15)) / 100.0, 0
        for _u, _v, e in sm.G.edges(data=True):
            if e["seg"] in ids:
                e["cap"] *= f; n += 1
        info["capacity_boost"] = {"segments": len(ids), "pct": float(cb.get("pct", 15)), "edges": n}
    ds = mods.get("demand_shift")
    if ds and info.get("geometry"):
        import numpy as np
        r, pct = float(ds.get("radius_km", 5)), float(ds.get("pct", -10))
        pts = np.array([c for ln in info["geometry"]["coordinates"] for c in ln][::2] or [info["geometry"]["coordinates"][0][0]])
        nodes = list(sm.G.nodes)
        xy = np.array([sm.node_ll(n) for n in nodes])
        d = np.sqrt(((xy[:, None, 0] - pts[None, :, 0]) * 101.0) ** 2 + ((xy[:, None, 1] - pts[None, :, 1]) * 110.6) ** 2).min(axis=1)
        near = {n for n, dist in zip(nodes, d) if dist <= r}
        f, prev = 1 + pct / 100.0, od_mult
        od_mult = lambda o, dd, _p=prev: (_p(o, dd) if _p else 1.0) * (f if (o in near or dd in near) else 1.0)
        info["demand_shift"] = {"pct": pct, "radius_km": r, "zones_affected": len(near)}
    return sm, od_mult, extra_od, info


def acc_name(model, node):
    from backend.data import riyadh_network as RN
    for k, n in model.zones.items():
        if n == node:
            return RN.LOCATIONS[k][0]
    return f"Zone near node {node}"


_memo: Dict[str, dict] = {}
_memo_locks: Dict[str, "threading.Lock"] = {}
_memo_guard = threading.Lock()


def run_scenario(params: dict, progress: Optional[Callable[[int, str], None]] = None, persist: bool = True,
                 actor: str = "system") -> Dict:
    """Non-persisted runs (agent what-if studies) are memoised per identical inputs for 10 minutes and computed once even when
    several agents ask concurrently; persisted runs (user-saved scenarios) always execute."""
    if persist:
        return _run_scenario(params, progress, True, actor)
    key = json.dumps({k: v for k, v in params.items() if k != "name"}, sort_keys=True, default=str) + "|" + str((getattr(get_model(), "provenance", None) or {}).get("fingerprint"))
    with _memo_guard:
        lock = _memo_locks.setdefault(key, threading.Lock())
    with lock:
        hit = _memo.get(key)
        if hit and time.time() - hit[0] < 600:
            return hit[1]
        r = _run_scenario(params, progress, False, actor)
        _memo[key] = (time.time(), r)
        return r


def _run_scenario(params: dict, progress: Optional[Callable[[int, str], None]] = None, persist: bool = True,
                  actor: str = "system") -> Dict:
    t0 = time.time()
    P = dict(params)
    P["scenario_type"] = P.get("scenario_type") or "closure"
    if P["scenario_type"] not in TYPES:
        raise ValueError(f"scenario_type must be one of {TYPES}")
    P.setdefault("name", f"{P['scenario_type'].title()} scenario")
    say = progress or (lambda *_: None)
    base = get_model()
    wh = window_hours(P)
    say(5, "Baseline network loaded (unchanged)")
    sm, od_mult, extra_od, info = _setup(P, base, wh)
    say(15, "Scenario network created as a separate copy")

    excl = sm.cut_off_zones() - base.cut_off_zones()
    if excl:  # zones cut off by the scenario cannot be compared fairly: drop their trips from BOTH runs and report them
        mult = od_mult
        od_mult = (lambda o, d: 0.0 if (o in excl or d in excl) else (mult(o, d) if mult else 1.0))
        extra_od = [x for x in (extra_od or []) if x[0] not in excl and x[1] not in excl] or None
    base_mult = (lambda o, d: 0.0 if (o in excl or d in excl) else 1.0) if excl else None
    per_hour = []
    sres = bres = None
    for i, h in enumerate(wh["sample_hours"]):
        sc = demand_factor(h, wh["weekend"])
        b = base.assign(sc) if not excl else base.clone().assign(sc, base_mult, use_cache=False)  # baseline is never mutated by scenarios
        s = sm.assign(sc, od_mult, extra_od)
        per_hour.append({"hour": h, "scale": round(sc, 2), "baseline_vht": round(b["totals"]["vht"]), "scenario_vht": round(s["totals"]["vht"]),
                         "delta_vht": round(s["totals"]["vht"] - b["totals"]["vht"]),
                         # per-trip delay (no credit for trips that vanish when demand is reduced): change in mean trip time x baseline trips
                         "extra_trip_hours": round((s["totals"]["mean_od_time_min"] - b["totals"]["mean_od_time_min"]) / 60.0 * b["totals"]["trips_per_hour"], 1)})
        sres = s
        say(15 + int(55 * (i + 1) / len(wh["sample_hours"])), f"Assigned traffic for hour {h:02d}:00")
    bm = base.clone()
    bres = bm.assign(wh["peak_scale"], base_mult, use_cache=False)  # clone keeps congested times for routing
    sres = sm.assign(wh["peak_scale"], od_mult, extra_od)
    say(75, "Comparing baseline and scenario")

    be, se = bres["edges"], sres["edges"]
    affected, feats = [], []
    for sid in sorted(set(be) | set(se) | set(sm.segments)):
        b, s = be.get(sid), se.get(sid)
        seg = sm.segments.get(sid) or base.segments.get(sid)
        if not seg:
            continue
        closed = sid in sm.closed
        new = str(sid).startswith("new-")
        bvc, svc = (b or {}).get("vc", 0.0), (s or {}).get("vc", 0.0)
        bt, st = (b or {}).get("time_min"), (s or {}).get("time_min")
        dvc = svc - bvc
        tchg = ((st / bt - 1) if (bt and st) else 0)
        if closed or new or abs(dvc) >= 0.05 or abs(tchg) >= 0.10:
            status = "closed" if closed else "new" if new else "worse" if dvc > 0 else "better"
            row = {"segment_id": sid, "name": seg.get("name") or seg["corridor"], "corridor": seg["corridor"], "status": status,
                   "baseline_vc": round(bvc, 2), "scenario_vc": round(svc, 2), "delta_vc": round(dvc, 2),
                   "baseline_level": level(bvc), "scenario_level": level(svc) if not closed else "closed",
                   "baseline_flow": round((b or {}).get("flow", 0)), "scenario_flow": round((s or {}).get("flow", 0)),
                   "baseline_speed_kph": round((b or {}).get("speed_kph", 0), 1), "scenario_speed_kph": round((s or {}).get("speed_kph", 0), 1),
                   "time_change_pct": round(tchg * 100, 1)}
            affected.append(row)
            feats.append({"type": "Feature", "id": sid, "geometry": seg["geometry"], "properties": row})
    affected.sort(key=lambda r: (r["status"] != "closed", -abs(r["delta_vc"])))

    bt_, st_ = bres["totals"], sres["totals"]
    mean_pct = (st_["mean_od_time_min"] / bt_["mean_od_time_min"] - 1) * 100
    pairs = alt.key_od_pairs(bm, sm, top=6)
    routes_fc = []
    for r in pairs[:4]:
        label = f"{r['from']} → {r['to']}"
        routes_fc.append({"type": "Feature", "geometry": r.pop("baseline_geometry"),
                          "properties": {"kind": "baseline", "od": label, "minutes": r["baseline_min"], "via": " > ".join(r["baseline_via"])}})
        g = r.pop("scenario_geometry", None)
        if g:
            routes_fc.append({"type": "Feature", "geometry": g, "properties": {"kind": "scenario", "od": label, "minutes": r["scenario_min"],
                                                                                "via": " > ".join(r["scenario_via"])}})
    for r in pairs[4:]:
        r.pop("baseline_geometry", None); r.pop("scenario_geometry", None)

    access = acc.compare_accessibility(acc.accessibility(bm), acc.accessibility(sm))
    conn_b, conn_s = res_mod.connectivity(base), res_mod.connectivity(sm)
    say(85, "Accessibility and connectivity evaluated")

    extra: Dict = {}
    if "event" in info:
        extra["event"] = info["event"]
    if P["scenario_type"] == "closure":
        first = base.segments[info["ids"][0]]
        if (first.get("attributes") or {}).get("oneway"):
            nxt = {}
            for i in info["ids"]:
                sg = base.segments[i]
                nxt.setdefault(sg["from_node"], []).append(sg["to_node"])
            starts = {sg for sg in nxt} - {t for v in nxt.values() for t in v} or {first["from_node"]}
            best = (-1, first["from_node"], first["to_node"])
            for s0 in starts:  # follow each closed carriageway chain from its start to its end
                cur, hops, seen_ = s0, 0, {s0}
                while cur in nxt and hops < 50:
                    cur = nxt[cur][0]
                    if cur in seen_:
                        break
                    seen_.add(cur); hops += 1
                if hops > best[0]:
                    best = (hops, s0, cur)
            a_, b_ = best[1], best[2]
            # extend along the corridor until the endpoints are re-joinable from elsewhere (>=2 ways in at the end, >=2 ways out at the start)
            corr = first["corridor"]
            for _ in range(40):
                if base.G.in_degree(b_) >= 2:
                    break
                outs = [(v, d_) for _, v, d_ in base.G.out_edges(b_, data=True) if d_["seg"] not in info["ids"]]
                outs = [o_ for o_ in outs if o_[1]["corridor"] == corr] or outs
                if not outs:
                    break
                b_ = outs[0][0]
            for _ in range(40):
                if base.G.out_degree(a_) >= 2:
                    break
                ins = [(u, d_) for u, _, d_ in base.G.in_edges(a_, data=True) if d_["seg"] not in info["ids"]]
                ins = [i_ for i_ in ins if i_[1]["corridor"] == corr] or ins
                if not ins:
                    break
                a_ = ins[0][0]
            ends = [a_, b_]
        else:
          ends = [n for n in info["end_nodes"] if sum(1 for sid in info["ids"] if n in (base.segments[sid]["from_node"], base.segments[sid]["to_node"])) == 1] or info["end_nodes"][:2]
        if len(ends) >= 2:
            d = alt.detours_around(sm, bm, ends[0], ends[-1])
            extra["detours"] = {"from": ends[0], "to": ends[-1],
                                "direct": {k: v for k, v in (d["baseline"] or {}).items() if k != "geometry"},
                                "alternatives": [{k: v for k, v in a.items() if k != "geometry"} for a in d["alternatives"]]}
            for a in d["alternatives"]:
                routes_fc.append({"type": "Feature", "geometry": a["geometry"], "properties": {"kind": "detour", "od": "closed section detour",
                                                                                         "minutes": a["time_min"], "via": " > ".join(a["via"])}})
        night = demand_factor(2)
        nb = base.assign(night) if not excl else base.clone().assign(night, base_mult, use_cache=False)
        ns = sm.assign(night, od_mult)
        extra["off_peak_comparison"] = {"hour": 2, "delta_vht": round(ns["totals"]["vht"] - nb["totals"]["vht"]),
                                        "peak_delta_vht": round(st_["vht"] - bt_["vht"])}
        sm.assign(wh["peak_scale"], od_mult, extra_od)
        mst = [m["name"] for m in store.list_("MetroStation") if min(haversine_km(m["geometry"]["coordinates"], c)
               for sid in info["ids"] for c in base.segments[sid]["geometry"]["coordinates"]) <= 1.5]
        extra["nearby_metro_stations"] = sorted(set(mst))
        facilities = []
        for h in feature_source.list_hospitals():
            dmin = min(haversine_km(h["geometry"]["coordinates"], c) for sid in info["ids"] for c in base.segments[sid]["geometry"]["coordinates"])
            if dmin <= 2.0:
                facilities.append({"name": h["name"], "distance_km": round(dmin, 2)})
        extra["facilities_near_closure"] = facilities

    corridor_dflow: Dict[str, float] = defaultdict(float)
    for r in affected:
        corridor_dflow[r["corridor"]] += r["scenario_flow"] - r["baseline_flow"]
    top_gain = sorted(((c, f) for c, f in corridor_dflow.items() if f > 0), key=lambda x: -x[1])[:3]
    window_extra_vht = round(sum(h["delta_vht"] for h in per_hour) / len(per_hour) * wh["duration_h"])
    summary = {
        "vht_baseline_peak": round(bt_["vht"]), "vht_scenario_peak": round(st_["vht"]),
        "vht_delta_pct": round((st_["vht"] / bt_["vht"] - 1) * 100, 1),
        "avg_speed_baseline_kph": round(bt_["avg_speed_kph"], 1), "avg_speed_scenario_kph": round(st_["avg_speed_kph"], 1),
        "mean_od_time_baseline_min": round(bt_["mean_od_time_min"], 1), "mean_od_time_scenario_min": round(st_["mean_od_time_min"], 1),
        "mean_od_time_delta_pct": round(mean_pct, 1),
        "severe_segments_baseline": bt_["severe_segments"], "severe_segments_scenario": st_["severe_segments"],
        "trips_change_pct": round((st_["trips_per_hour"] / max(bt_["trips_per_hour"], 1e-9) - 1) * 100, 1), "affected_segments": len(affected), "unserved_trips_per_hour": round(st_["unserved_trips"]),
        "disconnected_named_pairs": sum(1 for p_ in pairs if p_.get("disconnected")),
        "isolated_zones": sorted({r["zone"] for r in access["rows"] if r["isolated"]} | {acc_name(sm, z) for z in excl}), "cut_off_demand_zones": len(excl),
        "worst_hospital_access_delta_min": max([r["delta_min"] or 0 for r in access["rows"]] + [0]),
        "window_extra_vehicle_hours": window_extra_vht,
        "window_extra_trip_hours": round(sum(h["extra_trip_hours"] for h in per_hour) / len(per_hour) * wh["duration_h"]), "peak_hour": wh["peak_hour"], "duration_h": wh["duration_h"],
    }
    mitig = mitigations(P, info, summary, affected, access, top_gain, extra, wh)
    result = {
        "network_provenance": getattr(base, "provenance", None),
        "engine": "networkx-static-assignment", "classification": "network analysis + estimated impacts (NOT microsimulation)",
        "data_status": "synthetic traffic inputs on approximate network geometry",
        "scenario": {**P, "resolved": {k: v for k, v in info.items() if k not in ("geometry",)}},
        "window": wh, "per_hour": per_hour, "baseline": {k: round(v, 2) for k, v in bt_.items()},
        "scenario_totals": {k: round(v, 2) for k, v in st_.items()}, "summary": summary,
        "affected_segments": affected[:60], "key_od_pairs": pairs, "accessibility": access,
        "connectivity": {"baseline": conn_b, "scenario": conn_s}, "mitigations": mitig, "extra": extra,
        "assumptions": ASSUMPTIONS, "limitations": LIMITATIONS,
        "geojson": {"segments": {"type": "FeatureCollection", "features": feats},
                    "routes": {"type": "FeatureCollection", "features": routes_fc},
                    "closed": {"type": "Feature", "geometry": info.get("geometry"), "properties": {"kind": "closure"}} if info.get("geometry") else None},
        "sumo": {"status": "not run", "microsimulation": False},
        "runtime_s": round(time.time() - t0, 2),
    }
    if persist:
        sid = P.get("scenario_id") or store.new_id("sc")
        result["scenario_id"] = sid
        store.upsert_many("SimulationScenario", [dict(id=sid, name=P["name"], scenario_type=P["scenario_type"], params=P, status="completed",
                                                      created_by=actor, source="user", data_status="synthetic")])
        store.upsert_many("SimulationResult", [dict(id=f"sr-{sid}", name=P["name"], scenario_id=sid, engine=result["engine"], summary=summary,
                                                    result=result, duration_s=result["runtime_s"], source="simulation engine",
                                                    data_status="synthetic", confidence=0.4)])
        store.audit(actor, "run_simulation", "SimulationScenario", sid, f"{P['scenario_type']} {P['name']}")
    say(100, "Scenario complete")
    return result


def mitigations(P, info, S, affected, access, top_gain, extra, wh) -> List[Dict]:
    m: List[Dict] = []
    add = lambda title, detail, priority="medium", kind="traffic": m.append({"title": title, "detail": detail, "priority": priority, "category": kind})
    t = P["scenario_type"]
    if t == "closure":
        if top_gain:
            add("Divert traffic via parallel corridors", "Highest additional load: " + "; ".join(f"{c} (+{round(f):,} veh/h)" for c, f in top_gain) +
                ". Pre-plan signal retiming and variable-message-sign diversion on these corridors.", "high")
        oc = extra.get("off_peak_comparison")
        if oc and wh["peak_hour"] in range(6, 20) and oc["peak_delta_vht"] > 0:
            add("Reschedule closure to off-peak hours", f"Estimated peak-hour delay increase is {oc['peak_delta_vht']:,} veh-h/h versus "
                f"{oc['delta_vht']:,} veh-h/h at 02:00. A night-time window would reduce impact substantially.", "high", "scheduling")
        if extra.get("nearby_metro_stations"):
            add("Increase Metro/bus frequency near the closure", "Stations within 1.5 km: " + ", ".join(extra["nearby_metro_stations"][:5]) + ". Promote transit use during the closure window.", "medium", "transit")
        if extra.get("facilities_near_closure"):
            add("Protect hospital access routes", "Hospitals within 2 km of the closed section: " + ", ".join(f["name"] for f in extra["facilities_near_closure"]) + ". Keep signed emergency access.", "high", "emergency")
    if t == "demand":
        hot = [a for a in affected if a["scenario_level"] == "severe" and a["status"] == "worse"][:5]
        if hot:
            add("Target the new bottlenecks", "Newly/more severe: " + ", ".join(f"{a['corridor']} ({a['scenario_vc']:.2f} v/c)" for a in hot) + ". Evaluate signal optimisation, ramp metering or capacity additions.", "high")
        add("Demand management", "Promote staggered working hours and transit incentives; a 20% demand increase is not absorbed evenly by the network.", "medium", "demand")
    if t == "event":
        ev = info["event"]
        if ev["parking_deficit_vehicles"] > 0:
            add("Close the parking gap", f"Estimated {ev['parking_deficit_vehicles']:,} vehicles exceed assumed parking supply. Use remote park-and-ride with shuttles.", "high", "parking")
        if ev["metro_utilisation"] and ev["metro_utilisation"] > 0.8:
            add("Add Metro capacity", f"Assumed Metro utilisation {ev['metro_utilisation']:.0%} of assumed capacity; add event services.", "high", "transit")
        add("Event traffic management plan", "Dedicated event approach routes, staggered arrival slots, temporary signal plans on the busiest access roads.", "medium")
    if t == "infrastructure":
        if S["mean_od_time_delta_pct"] > -1:
            add("Limited network benefit", f"Mean OD time change {S['mean_od_time_delta_pct']}%. Reconsider alignment/connection points before investing.", "medium", "planning")
        else:
            add("Link shows network benefit", f"Mean OD time improves by {abs(S['mean_od_time_delta_pct'])}% and peak delay by {abs(S['vht_delta_pct'])}% (synthetic demand).", "medium", "planning")
    worst = [r for r in access["most_affected"] if (r["delta_min"] or 0) >= 2 or r["isolated"]]
    if worst:
        add("Emergency access measures", "Longest hospital-access increase: " + "; ".join(f"{r['zone']} +{r['delta_min']} min" if r['delta_min'] is not None else f"{r['zone']} isolated" for r in worst[:3]) + ". Pre-position EMS and designate emergency corridors.", "high", "emergency")
    if S["isolated_zones"]:
        add("Restore connectivity", "Disconnected: " + ", ".join(S["isolated_zones"]), "critical", "emergency")
    if not m:
        add("No major mitigation needed", "Estimated network impact is small under the stated assumptions.", "low")
    return m


def compare_scenarios(ids: List[str]) -> Dict:
    rows = []
    for i in ids:
        r = store.get("SimulationResult", f"sr-{i}")
        sc = store.get("SimulationScenario", i)
        if not r or not sc:
            raise KeyError(i)
        rows.append({"scenario_id": i, "name": sc["name"], "type": sc["scenario_type"], **r["summary"]})
    return {"scenarios": rows, "metrics": ["vht_delta_pct", "mean_od_time_delta_pct", "avg_speed_scenario_kph", "severe_segments_scenario",
                                          "affected_segments", "worst_hospital_access_delta_min", "window_extra_vehicle_hours"],
            "note": "All results are estimates from a synthetic-demand static assignment; compare relatively, not absolutely."}
