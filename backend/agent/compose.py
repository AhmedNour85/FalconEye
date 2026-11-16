"""Deterministic reply composers for the offline (rule-based) planner. Every number is read from a tool result."""
from __future__ import annotations


def _fmt(v):
    return "n/a" if v is None else v


def detect_water_leaks(r: dict) -> str:
    if not r["suspected_leaks"]:
        lines = [f"I evaluated {r['sensors_evaluated']} pressure/flow sensors ({r['scope']}) and found **no suspected leaks** right now - nothing meets the rule "
                 f"(pressure at least {r['rule']['min_pressure_drop_pct']:g}% below the same hours yesterday and z-score at least {r['rule']['min_z_score']})."]
        for c in r.get("closest_candidates", []):
            lines.append(f"- Closest: {c['sensor_id']} ({c['area']}, {c['pipeline_id']}): pressure {c['pressure_drop_pct']:+}% vs yesterday, z={c['z_score']} - normal variation.")
        lines.append("\nLowering the risk threshold would not change this: it only hides detections after the rule has fired.")
        lines.append("_To see a detection:_ " + r.get("how_to_see_a_detection", "inject a leak scenario (Command Center > Simulation engine) or run Guided Demo scene 1."))
        return "\n".join(lines)
    lines = [f"I evaluated {r['sensors_evaluated']} sensors ({r['scope']}) and found **{r['suspected_leaks']} suspected leak(s)** - suspected, not confirmed:"]
    for d in r["detections"][:5]:
        loc = d["probable_location"]
        lines.append(f"- **{d['detection_id']}** {d['area']} / {d['pipeline_id']}: risk **{d['risk_score']}** ({d['severity']}), pressure -{d['pressure_drop_pct']}%, flow {d['flow_change_pct']:+}% "
                     f"(sensor {d['sensor_id']}, {len(d['corroborating_sensors'])} corroborating). Probable position {loc['lat']}, {loc['lon']} (+/-{loc['uncertainty_radius_m']} m).")
    top = r["detections"][0]
    lines.append(f"\n**Why suspicious:** {top['why_suspicious']}")
    lines.append("\n_Next:_ ask which is most critical, or say 'create incidents'.")
    return "\n".join(lines)


def predict_streetlight_failures(r: dict) -> str:
    if not r["predicted_failures"]:
        return f"I scored {r['lights_evaluated']} streetlights; none exceed the {r['threshold']:.2f} failure-probability threshold."
    lines = [f"I scored {r['lights_evaluated']} streetlights and **{r['predicted_failures']}** exceed the {r['threshold']:.2f} probability threshold. These are **predicted**, not confirmed, failures."]
    for c in r["clusters"]:
        lines.append(f"- **Cluster {c['cluster_id']}** on {c['corridor']} ({c['area']}): {c['lights']} lights, mean probability {c['mean_probability']:.0%}, top priority score {c['max_priority_score']}.")
    for d in r["detections"][:5]:
        dr = d["drivers"]
        lines.append(f"- {d['asset_id']} p={d['probability']:.0%} risk {d['risk_score']} ({d['criticality']} criticality) - drift {dr['power_trend_pct']:+}%, {dr['flicker_30d']} flickers/30d, {dr['faults_12m']} faults/12m")
    lines.append(f"\n_Model:_ {r['model']}.\n_Next:_ 'create incidents' to group the cluster into a preventive-maintenance incident.")
    return "\n".join(lines)


def detect_imagery_changes(r: dict) -> str:
    lines = [f"I compared **{r['previous_epoch']}** with **{r['current_epoch']}** over {r['area']}. Imagery and processing are **simulated**; results are candidates, not confirmed construction.",
             f"Method: {r['method']} (threshold {r['threshold']})."]
    for c in r["changes"]:
        lines.append(f"- **{c['change_id']}** {c['type']}: {c['area_sqm']:,} m2, confidence {c['confidence']}" + (" - **significant**" if c["significant"] else " - not significant"))
    lines.append(f"\n**{r['significant_count']} significant** candidate(s). Vegetation-only differences are not counted because they may be seasonal.")
    chk = r["simulation_check"]
    lines.append(f"_Simulation check:_ recovered {chk['recovered']} of {chk['injected_real_changes']} injected real changes.")
    lines.append("_Next:_ 'extract buildings and roads around the detected changes'.")
    return "\n".join(lines)


def extract_geoai_features(r: dict) -> str:
    return (f"For **{r['change_id']}** ({r['area']}) the simulated GeoAI extraction found **{len(r['buildings'])} building footprint(s)** (total {r['tot_building_area_sqm']:,} m2) "
            f"and **{len(r['roads'])} road segment(s)** (total {r['tot_road_length_m']:,} m). Source: {r['source']}. No deep-learning model was executed.\n"
            "_Next:_ run a spatial analysis to see which assets and facilities are nearby.")


def spatial_analysis(r: dict) -> str:
    t = r["target"]
    pa = r["potentially_affected"]
    lines = [f"Spatial analysis around **{t['type']} {t['id']}** (radius {r['radius_m']:.0f} m)" + (f", footprint {t['area_sqm']:,} m2" if "area_sqm" in t else "") + ":",
             f"- Water pipes: **{pa['pipes']}**; streetlights: **{pa['lights']}**; real buildings: **{pa.get('buildings', 0)}**; facilities: **{pa['facilities']}**; road corridors: {', '.join(r['road_corridors']) or 'none nearby'}"]
    for f in r["facilities"][:4]:
        lines.append(f"  - {f['name']} ({f['type']}) {f['distance_m']} m")
    for p in r["water_pipes"][:3]:
        lines.append(f"  - pipe {p['pipeline_id']} {p['diameter_mm']} mm {p['material']} at {p['distance_m']} m")
    if r["open_incidents_nearby"]:
        lines.append("- Open incidents nearby: " + ", ".join(f"{i['incident_id']} ({i['type']}, {i['distance_m']} m)" for i in r["open_incidents_nearby"][:4]))
    if r["extracted_features"]:
        lines.append(f"- Extracted features nearby: {len(r['extracted_features'])} (simulated)")
    lines.append(f"_{r['note']}_")
    return "\n".join(lines)


def executive_summary(r: dict) -> str:
    k = r["kpis"]
    lines = ["**Executive overview (computed from stored records)**",
             f"- Open incidents **{k['open_incidents']}** of {k['total_incidents']} (critical: **{k['critical_incidents']}**) | open work orders **{k['open_work_orders']}** | unassigned **{k['unassigned_work_orders']}**",
             f"- Suspected leaks **{k['suspected_water_leaks']}** | predicted streetlight failures **{k['predicted_streetlight_failures']}** | significant urban changes **{k['detected_urban_changes']}**",
             f"- Verification rate **{_fmt(k['verification_rate_pct'])}%** | resolution rate **{_fmt(k['incident_resolution_rate_pct'])}%** | avg response **{_fmt(k['avg_response_time_hours'])} h**"]
    if r["hotspots"]:
        lines.append("- Hotspots: " + "; ".join(f"{h['area']} ({h['score']})" for h in r["hotspots"][:3]))
    if r["recommendations"]:
        lines.append("\n**Intervention priorities**")
        for x in r["recommendations"][:4]:
            lines.append(f"{x['rank']}. {x['incident_id']} ({x['priority']}, {x['area']}): {x['recommended_action']} - {'; '.join(x['evidence'])}")
    return "\n".join(lines)


def rank_incidents(r: dict) -> str:
    if not r["ranked"]:
        return "There are no open incidents."
    lines = [f"Top of **{r['open_total']}** open incidents by urgency ({r['ordering']}):"]
    for x in r["ranked"]:
        lines.append(f"{x['rank']}. **{x['incident_id']}** {x['type']} - {x['priority']}, risk {x['risk_score']}, {x['area']}, status {x['status']} ({'; '.join(x['evidence'])})")
    lines.append(f"\nMost critical: **{r['ranked'][0]['incident_id']}**. _Next:_ 'create a work order for that one'.")
    return "\n".join(lines)


def create_incidents_from_detections(r: dict) -> str:
    if not r["created"] and not r["already_existing"]:
        return r.get("message") or "No detections were available to convert. Run a detection first."
    lines = []
    if r["created"]:
        lines.append(f"Created **{len(r['created'])} incident(s)** (status Open; no external action taken):")
        for c in r["created"]:
            lines.append(f"- **{c['incident_id']}** {c['type']} - {c['priority']} / {c['severity']}, risk {c['risk_score']}, {c['area']}, team {c['assigned_team']}")
    if r["already_existing"]:
        lines.append(f"Already had incidents (not duplicated): {', '.join(r['already_existing'])}.")
    lines.append("_Next:_ 'which is most critical?' or 'create a work order for that one'.")
    return "\n".join(lines)


def list_incidents(r: dict) -> str:
    if not r["count"]:
        return "No incidents match."
    lines = [f"**{r['count']}** incident(s) (showing {len(r['incidents'])}):"]
    for x in r["incidents"]:
        lines.append(f"- {x['incident_id']} {x['type']} {x['priority']} risk {x['risk_score']} {x['area']} - {x['status']}" + (f" / verified: {x['verification']}" if x["verification"] else ""))
    return "\n".join(lines)


def get_incident(r: dict) -> str:
    i = r["incident"]
    return (f"**{i['Incident_ID']}** {i['Incident_Type']} - {i['Priority']}/{i['Severity']} risk {i['Risk_Score']} in {i['Area_Name']}; status **{i['Status']}**; team {i['Assigned_Team']}.\n"
            f"Detections: {', '.join(d['id'] for d in r['detections'])}; work orders: {', '.join(w['Work_Order_ID'] + ' (' + w['Status'] + ')' for w in r['work_orders']) or 'none'}; "
            f"verifications: {len(r['verifications'])}.")


def _approval_block(a: dict) -> str:
    return (f"**Approval requested - {a['Approval_ID']}**\n- Action: {a['Summary']}\n- Target: {a['Target']} | Location: {a['Location'] or 'n/a'} | Priority: {a['Priority'] or 'n/a'} | Team: {a['Team'] or 'n/a'}\n"
            f"- Expected result: {a['Expected_Result']}\n\n**Nothing has been created yet.** Reply **approve** (or use the Approval panel) to execute, or **reject**.")


def propose_work_order(r: dict) -> str:
    return _approval_block(r["approval"])


def propose_work_orders_bulk(r: dict) -> str:
    lines = [f"Prepared **{len(r['proposals'])}** work-order proposal(s); none exist until approved:"]
    for a in r["proposals"]:
        lines.append(f"- {a['Approval_ID']}: {a['Summary']}")
    for s in r["skipped"]:
        lines.append(f"- skipped {s['incident_id']}: {s['reason']}")
    lines.append("\nReply **approve all** to execute them, or approve individually in the Approval panel.")
    return "\n".join(lines)


def propose_field_assignment(r: dict) -> str:
    w = r["recommended_worker"]
    return f"Recommended worker: **{w['name']}** ({w['team']}), score {w['score']} - {w['rationale']}.\n\n" + _approval_block(r["approval"])


def propose_incident_closure(r: dict) -> str:
    return _approval_block(r["approval"])


propose_asset_status_change = propose_incident_closure


def verify_outcome(r: dict) -> str:
    if not r["verified"]:
        return f"**{r['incident_id']}** has no field verification yet. {r['message']}"
    v = r["latest_verification"]
    return (f"**Verification for {r['incident_id']}** (system status: **{r['incident_status']}**, outcome: {r['verification_outcome'] or 'pending'})\n"
            f"- Field worker {v['Worker_ID']}{' (simulated)' if v['Simulated_Worker'] == 'Yes' else ''} reported **{v['Verification_Status']}** at {v['GPS_Location']} ({v['Distance_To_Detection_M']} m from the detection).\n"
            f"- Observation: {v['Observation']}\n- Photo evidence: {v['Photo_URL'] or 'none attached'}\n- **Comparison:** {r['agent_assessment']}\n_Next:_ {r['next_step']}")


def evaluate_outcomes(r: dict) -> str:
    e = r["evaluation"]
    lines = [f"**Prediction vs. verified outcome** - {e['total_verified']} verified of {e['total_detections']} detections (verification rate {_fmt(e['verification_rate'])}); overall precision {_fmt(e['overall_precision'])}."]
    for c, v in e["categories"].items():
        lines.append(f"- {c}: TP {v['verified_true']} / FP {v['verified_false']} / awaiting {v['awaiting_verification']}; precision {_fmt(v['precision'])}; recall {_fmt(v['recall'])}; calibration x{v['calibration']}")
    if r["calibration_update"]:
        lines.append("Risk calibration refreshed from verified outcomes.")
    lines.append(f"_{r['disclaimer']}_ {e['notes']}")
    return "\n".join(lines)


def sensor_intelligence(r: dict) -> str:
    lines = [f"{r['sensors_evaluated']} sensors evaluated, **{r['anomalous']} anomalous**."]
    for s in r["sensors"][:5]:
        lines.append(f"- {s['sensor_id']} ({s['area']}, {s['pipeline_id']}): pressure {s['drop_pct']:+}% drop, z={s['z']}, flow {s['flow_change_pct']:+}%" + (" **ANOMALOUS**" if s["anomalous"] else ""))
    return "\n".join(lines)


def count_incidents(r: dict) -> str:
    sc = r["scope"]
    scope = " ".join(x for x in (sc.get("severity"), sc.get("category"), "incidents", f"in {sc['area']}" if sc.get("area") else "") if x)
    if not r["count"]:
        return f"There are **no {'open ' if r['open_only'] else ''}{scope}** right now ({r['total_all_time']} incidents recorded in total)."
    lines = [f"**{r['count']} {'open ' if r['open_only'] else ''}{scope}** ({r['critical']} critical)."]
    names = {"water": "water", "lighting": "streetlight", "change": "urban change", "distortion": "visual distortion", "land_use": "land-use", "mobility": "traffic and mobility"}
    if len(r["by_area"]) > 1 or not sc.get("area"):
        lines.append("- By area: " + ", ".join(f"{k} {v}" for k, v in r["by_area"].items()))
    if len(r["by_category"]) > 1 or not sc.get("category"):
        lines.append("- By type: " + ", ".join(f"{names.get(k, k)} {v}" for k, v in r["by_category"].items()))
    lines.append("- By priority: " + ", ".join(f"{k} {v}" for k, v in sorted(r["by_priority"].items())))
    lines.append("- By status: " + ", ".join(f"{k} {v}" for k, v in r["by_status"].items()))
    if r["awaiting_approval"]:
        lines.append(f"\n{r['awaiting_approval']} decision(s) are waiting for your approval.")
    return "\n".join(lines)


def feeds_summary(r: dict) -> str:
    lines = [f"**{r['reports']} citizen reports** ({r['scope']}): {r['waiting']} waiting for corroboration, {r['linked_to_incidents']} attached to incidents."]
    if r["by_category"]:
        lines.append("- By type: " + ", ".join(f"{k} {v}" for k, v in r["by_category"].items()))
    if r["by_area"]:
        lines.append("- By area: " + ", ".join(f"{k} {v}" for k, v in list(r["by_area"].items())[:6]))
    lines.append(f"_{r['caveat']}_")
    return "\n".join(lines)


def monitor_poles(r: dict) -> str:
    if not r["flagged"]:
        return f"I checked **{r['poles_evaluated']} poles** ({r['scope']}); none exceed the limits (tilt {r['limits']['tilt_deg']}°, corrosion {r['limits']['corrosion']})."
    lines = [f"I checked **{r['poles_evaluated']} poles** ({r['scope']}) and **{r['flagged']}** exceed the safety limits. These are **predicted** structural risks, not confirmed failures."]
    for d in r["detections"][:6]:
        lines.append(f"- **{d['asset_id']}** on {d['corridor']}: tilt {d['tilt_deg']:.1f}°, {d['corrosion'].lower()} corrosion, risk **{d['risk_score']}** ({d['severity']}).")
    lines.append("\n_Next:_ 'create incidents' to group them into one inspection incident.")
    return "\n".join(lines)


def detect_visual_distortion(r: dict) -> str:
    if not r["flagged"]:
        return f"I compared **{r['previous_epoch']}** with **{r['current_epoch']}** over {r['area']} ({r['buildings_evaluated']} buildings): no visual distortion above the threshold."
    lines = [f"I compared the two imagery dates over {r['area']} ({r['buildings_evaluated']} buildings, **simulated** imagery) and **{r['flagged']}** show visual distortion."]
    for d in r["detections"][:6]:
        if d.get("visual_type"):
            lines.append(f"- **{d['kind']}** near {d['name']}: visual-distortion score {d['edge_warp_index']:.2f} (z={d['z_score']}), risk **{d['risk_score']}** ({d['severity']})" + (f", near {d['near_facility']}" if d["near_facility"] else "") + ".")
        else:
            lines.append(f"- **{d['name']}**: {d['kind']}, edge-warp index {d['edge_warp_index']:.2f} (z={d['z_score']}), risk **{d['risk_score']}** ({d['severity']})" + (f", near {d['near_facility']}" if d["near_facility"] else "") + ".")
    lines.append("\n_These are candidates for a field inspection or a structural survey, not final verdicts._")
    return "\n".join(lines)


def analyze_land_use(r: dict) -> str:
    lines = [f"**{r['area']}** is zoned *{r['zone']}* (permitted new uses: {', '.join(r['permitted_uses']) or 'none'}). I classified **{r['significant_changes']}** significant change(s) from the imagery (simulated) and found **{r['violations']}** zoning violation candidate(s)."]
    for d in r["detections"][:5]:
        lines.append(f"- **{d['change_id']}** {d['land_use']} ~{d['area_sqm']:,.0f} m²: {d['why']}. Risk **{d['risk_score']}** ({d['severity']}).")
    lines.append("\n_Candidates for site inspection, not enforcement decisions._")
    return "\n".join(lines)


COMPOSERS = {k: v for k, v in globals().items() if callable(v) and not k.startswith("_") and k not in ("COMPOSERS",)}
