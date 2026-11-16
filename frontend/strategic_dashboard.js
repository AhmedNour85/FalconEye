/* Executive Hub: city-health hero, KPIs, trend, hotspots, land-use/incident map with layer toggles, briefs, printable daily report. */
require(["esri/Map", "esri/views/MapView", "esri/views/SceneView", "esri/layers/GraphicsLayer", "esri/Graphic"], (Map, MapView, SceneView, GraphicsLayer, Graphic) => {
  const { esc, api, toast } = R;
  const { T, TV } = I18N;
  const $ = id => document.getElementById(id);
  const layers = { change: new GraphicsLayer(), inc: new GraphicsLayer() };
  const map = new Map({ basemap: (window.THEME ? THEME.basemap() : "gray-vector"), layers: [layers.change, layers.inc] });
  if (window.Mobility) Mobility.attach({ map, GraphicsLayer, Graphic, panel: document.querySelector(".layers"), host: document.querySelector(".mapwrap"), view: () => view });   // traffic (modelled), metro, bus, hospitals
  // 2D map or 3D scene on the same layers; the choice is remembered
  const makeView = three => three
    ? new SceneView({ container: "map", map, camera: { position: [46.67, 24.54, 12000], tilt: 45 } })
    : new MapView({ container: "map", map, center: [46.67, 24.71], zoom: 11 });
  let three = false; try { three = localStorage.getItem("geoai.map3d") === "1"; } catch (e) { /* 2D by default */ }
  let view = makeView(three);
  const modeBtn = $("mapmode");
  const showMode = () => { modeBtn.querySelector(".mm").textContent = three ? "3D" : "2D"; modeBtn.title = T(three ? "Map: 3D" : "Map: 2D"); modeBtn.setAttribute("aria-label", T("Switch between 2D and 3D view")); modeBtn.classList.toggle("on", three); };
  showMode();
  modeBtn.onclick = () => {
    three = !three; view.map = null; view.destroy(); view = makeView(three); showMode();      // detach the map first: destroying a view would destroy it too
    try { localStorage.setItem("geoai.map3d", three ? "1" : "0"); } catch (e) { /* optional */ }
  };
  let last = null, filter = "crit", incFeatures = [];

  const changeSym = () => ({ type: "simple-fill", color: [31, 179, 107, 0.35], outline: { color: [31, 179, 107], width: 1.2 } });
  const isCrit = p => p.Priority === "P1" || p.Severity === "Critical";
  const incSym = p => ({ type: "simple-marker", color: isCrit(p) ? "#d92d20" : "#dc6803", size: isCrit(p) ? 13 : 9, outline: { color: "white", width: 1 } });

  const ICON = {
    crit: '<svg viewBox="0 0 24 24"><path d="M12 3 2 21h20L12 3zM12 10v5M12 18h.01"/></svg>',
    city: '<svg viewBox="0 0 24 24"><path d="M3 21V9l6-4v16M9 21V3l6 4v14M15 21V11l6 3v7"/></svg>',
    clock: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>',
    gate: '<svg viewBox="0 0 24 24"><path d="m5 12 5 5 9-10"/></svg>',
  };
  const card = (ic, color, label, val, sub) => `<div class="card kpi" style="--k:${color}"><div class="label">${ICON[ic]}${esc(label)}</div><div class="val">${esc(val)}</div><div class="sub">${esc(sub)}</div></div>`;

  // City-health score: 100 minus weighted open pressure, floored at 0 (computed from the same KPIs the API returns).
  const health = k => Math.max(0, Math.round(100 - (6 * k.critical_incidents + 1.5 * (k.open_incidents - k.critical_incidents) + 2 * k.unassigned_work_orders)));

  function renderHero(k) {
    const h = health(k);
    const [state, color] = h >= 75 ? [T("Stable"), "var(--ok)"] : h >= 50 ? [T("Needs attention"), "var(--warn)"] : [T("Degraded"), "var(--bad)"];
    const why = k.critical_incidents ? T("{n} critical incident(s) are pulling the score down.", { n: k.critical_incidents }) : k.open_incidents ? T("{n} open incident(s), none critical.", { n: k.open_incidents }) : T("No open incidents.");
    $("hero").innerHTML = `<div class="ring" style="--p:${h};--c:${color}" role="img" aria-label="${T("City health {n} percent", { n: h })}"><b>${h}%</b></div>
      <div><div class="label">${T("Overall city overview")}</div><div class="state" style="color:${color}">${state}</div><div class="why">${esc(why)}</div></div>`;
  }

  // Four mobility numbers from the traffic model (Modelled). Before the model is ready they say so instead of showing zero.
  function mobilityCards(m) {
    const na = T("Not available yet"), mod = T("Modelled"), none = !m;
    const v = x => none || x == null ? "–" : x;
    return card("clock", "var(--info)", T("Peak delay ratio"), none || m.peak_delay_ratio == null ? "–" : m.peak_delay_ratio + "×", none || m.peak_delay_ratio == null ? na : `${mod} · ${T("busiest hour {h}:00", { h: m.peak_hour })}`) +
      card("crit", "var(--warn)", T("Severe sections"), v(m && m.severe_segments), none || m.severe_segments == null ? na : mod) +
      card("crit", "var(--bad)", T("Hospital access"), none || m.worst_hospital_minutes == null ? "–" : m.worst_hospital_minutes + (I18N.rtl ? " د" : " min"), none || m.worst_hospital_minutes == null ? na : mod) +
      card("gate", "var(--info)", T("Planned closures"), none ? "–" : m.planned_closures, none ? na : T("Open or coming up"));
  }

  function sparkline(t) {
    const cats = [["water", "#1570ef"], ["lighting", "#dc6803"], ["distortion", "#d92d20"], ["land_use", "#a78bfa"], ["change", "#1b8354"], ["mobility", "#14b8a6"]];
    const n = t.dates.length;
    if (n < 2) return `<div class="empty">${T("Not enough history yet.")}</div>`;
    const cats0 = cats; cats.splice(0, cats.length, ...cats0.filter(([c]) => Array.isArray(t.series[c])));   // an older server may not send every line
    const max = Math.max(1, ...cats.flatMap(([c]) => t.series[c]));
    const W = 300, H = 110, top = 6, bot = 4, ih = H - top - bot;
    const X = i => (i / (n - 1) * W).toFixed(1), Y = v => (top + ih - v / max * ih).toFixed(1);
    const line = c => t.series[c].map((v, i) => `${i ? "L" : "M"}${X(i)},${Y(v)}`).join("");
    const area = c => `${line(c)}L${W},${H - bot}L0,${H - bot}Z`;
    const grid = [0, .5, 1].map(f => `<line x1="0" x2="${W}" y1="${(top + ih * (1 - f)).toFixed(1)}" y2="${(top + ih * (1 - f)).toFixed(1)}" stroke="var(--border)" stroke-width="1" stroke-dasharray="${f ? "3 4" : "0"}" vector-effect="non-scaling-stroke"/>`).join("");
    const total = c => t.series[c].reduce((a, b) => a + b, 0);
    const d0 = t.dates[0].slice(5), d1 = t.dates[n - 1].slice(5);
    return `<div class="spark-wrap"><div class="spark-y"><span>${max}</span><span>${Math.round(max / 2)}</span><span>0</span></div>
      <svg class="spark" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img" aria-label="${T("Detections per day by category")}">
        ${grid}${cats.map(([c, col]) => `<path d="${area(c)}" fill="${col}" fill-opacity=".10" stroke="none"/><path d="${line(c)}" fill="none" stroke="${col}" stroke-width="2" stroke-linejoin="round" vector-effect="non-scaling-stroke"/>`).join("")}</svg></div>
      <div class="spark-x"><span>${esc(d0)}</span><span>${esc(d1)}</span></div>
      <div class="legend-inline">${cats.map(([c, col]) => `<span style="--c:${col}">${T(c)} <b>${total(c)}</b></span>`).join("")}</div>`;
  }

  function renderBriefs() {
    if (!last) return;
    const rows = last.notes.filter(n => filter === "all" ? true : n.Severity === "Critical" || n.Agent === "faisal");
    const crit = last.notes.filter(n => n.Severity === "Critical" || n.Agent === "faisal").length;
    $("brief-count").textContent = crit;
    $("briefs").innerHTML = rows.length ? rows.slice(0, 25).map(b =>
      `<div class="card click" tabindex="0" data-lon="${b.Lon ?? ""}" data-lat="${b.Lat ?? ""}"><div class="meta"><span>${esc(TV(I18N.agentName ? I18N.agentName(b.Agent) : b.Agent))}${b.Area_Name ? " · " + esc(TV(b.Area_Name)) : ""}</span><span>${esc((b.Created || "").slice(0, 10))}</span></div>
       <div class="title">${esc(b.Title)}<span class="sev ${esc(b.Severity)}">${esc(TV(b.Severity))}</span></div><div class="desc">${esc(b.Message)}</div></div>`).join("")
      : `<div class="empty">${T("Nothing here. The crew escalates P1 events to this panel.")}</div>`;
  }

  function applyLayerToggles() {
    layers.change.visible = $("l-change").checked;
    layers.inc.visible = $("l-inc").checked;
    layers.inc.graphics.forEach(g => { g.visible = !$("l-crit").checked || isCrit(g.attributes); });
  }

  async function refresh() {
    try {
      const [k, hotspots, st, ap, tr, mob] = await Promise.all([api("/api/kpis"), api("/api/hotspots"), api("/api/nccc/state"), api("/api/approvals?pending=true"), api("/api/trends"),
        api("/api/mobility/numbers").catch(() => null)]);       // an older server, or a model still building, never stops the page
      const e = { hotspots };
      last = { k, ex: e, notes: st.notifications, approvals: ap };
      renderHero(k);
      $("kpis").innerHTML =
        card("crit", "var(--bad)", T("Critical incidents"), k.critical_incidents, T("{n} open in total", { n: k.open_incidents })) +
        card("city", "var(--ok)", T("Urban changes"), k.detected_urban_changes, T("{n} candidates scanned", { n: k.candidate_changes_total })) +
        card("gate", "var(--ok)", T("Resolved"), k.resolved_incidents ?? 0, T("{n}% resolved", { n: k.incident_resolution_rate_pct ?? 0 })) +
        card("crit", "var(--warn)", T("Open incidents"), k.open_incidents ?? 0, T("{n} critical", { n: k.critical_incidents ?? 0 })) +
        card("clock", "var(--info)", T("Avg response"), (k.avg_response_time_hours ?? 0) + (I18N.rtl ? " س" : " h"), T("Per resolved incident")) +
        card("gate", "var(--warn)", T("Awaiting approval"), ap.length, ap.length ? T("Decisions pending") : T("Nothing pending")) + mobilityCards(mob && mob.summary);
      $("trend").innerHTML = sparkline(tr);
      const cong = ((mob && mob.hotspots) || []).slice(0, 2).map(h => ({ area: h.road, score: h.score, lon: h.lon, lat: h.lat, congestion: true }));
      const hs = (e.hotspots || []).slice(0, 5).concat(cong);
      $("hotspots").innerHTML = hs.length ? hs.map(x => {
        const c = x.score >= 66 ? "var(--bad)" : x.score >= 33 ? "var(--warn)" : "var(--ok)";
        return `<div class="card click" tabindex="0" data-lon="${x.lon}" data-lat="${x.lat}"><div class="meta"><span>${x.congestion ? T("Congestion now") + " · " + T("Modelled") : T("{o} open · {c} critical", { o: esc(x.open_incidents), c: esc(x.critical) })}</span><span>${Math.round(x.score)}/100</span></div>
          <div class="title">${esc(TV(x.area))}</div><div class="bar"><i style="width:${Math.round(x.score)}%;--c:${c}"></i></div></div>`;
      }).join("") : `<div class="empty">${T("No hotspots.")}</div>`;
      renderBriefs();
      await Promise.all([R.loadLayer(layers.change, "Riyadh_Change_Detection", changeSym, Graphic, "", p => ({ title: TV(p.Change_Type) || p.Change_ID, html: `<b>${esc(TV(p.Area_Name))}</b><br>${T("{n} m²", { n: esc(Math.round(p.Area_Sqm)) })} · ${T("Confidence")} ${esc(p.Confidence)}<br>${esc(p.Notes || "")}` })), R.loadLayer(layers.inc, "Riyadh_Operational_Incidents", incSym, Graphic, "", p => ({ title: `${p.Incident_ID} · ${TV(p.Incident_Type)}`, html: `<b>${esc(TV(p.Area_Name))}</b> · ${esc(p.Priority)} ${esc(TV(p.Severity))} · ${esc(TV(p.Status))}<br>${esc(p.Description || "")}` }), p => !["Resolved", "Closed - False Positive"].includes(p.Status))]);
      applyLayerToggles();
      $("upd").textContent = T("Updated {t}", { t: new Date().toLocaleTimeString(I18N.locale, { hour: "2-digit", minute: "2-digit", second: "2-digit" }) });
    } catch (err) { $("upd").textContent = T("Update failed"); toast(T("Refresh failed"), err.message, true); }
  }

  const fly = el => { if (el.dataset.lon && el.dataset.lat) view.goTo({ center: [+el.dataset.lon, +el.dataset.lat], zoom: 14 }, { duration: 700 }); };
  document.addEventListener("click", e => { const c = e.target.closest(".card.click"); if (c) fly(c); });
  document.addEventListener("keydown", e => { if (e.key === "Enter" && e.target.classList?.contains("click")) fly(e.target); });
  document.querySelector(".tabs").addEventListener("click", e => {
    const b = e.target.closest("button[data-f]"); if (!b) return;
    filter = b.dataset.f;
    document.querySelectorAll(".tabs button").forEach(x => x.classList.toggle("on", x === b));
    renderBriefs();
  });
  ["l-change", "l-inc", "l-crit"].forEach(id => $(id).addEventListener("change", applyLayerToggles));

  // Executive daily report: a clean printable page the browser can save as PDF.
  async function report() {
    if (!last) return toast(T("Not ready"), T("Data is still loading."), true);
    let ex;
    try { const r = await api("/api/executive"); ex = r.result || r; } catch (err) { return toast(T("Report failed"), err.message, true); }
    const { k, notes } = last;
    const rows = (ex.ranked_incidents || []).map(r => `<tr><td>${esc(r.incident_id)}</td><td>${esc(r.priority)}</td><td>${esc(TV(r.area))}</td><td>${esc(r.risk_score)}</td><td>${esc((r.evidence || []).join("; "))}</td></tr>`).join("");
    const recs = (ex.recommendations || []).map(r => `<li><b>${esc(r.incident_id)}</b>: ${esc(r.recommended_action)}</li>`).join("");
    const frame = document.createElement("iframe");           // printed from a hidden frame: no pop-up window that a blocker could stop
    frame.style.cssText = "position:fixed;right:0;bottom:0;width:0;height:0;border:0";
    document.body.appendChild(frame);
    const w = frame.contentWindow;
    w.document.open();
    w.document.write(`<!doctype html><html lang="${I18N.lang}" dir="${I18N.rtl ? "rtl" : "ltr"}"><title>${T("Daily City Health Report")}</title><style>body{font:14px Segoe UI,Tahoma,Arial;margin:40px;color:#111}h2{margin-top:28px;border-bottom:2px solid #1b8354}
      table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccc;padding:6px;text-align:start;font-size:12px}.k{display:inline-block;margin:0 24px 12px 0}.k b{font-size:24px;display:block}</style>
      <h1>${T("Falcon Eye")}</h1><div>${T("Daily City Health Report")} · ${new Date().toLocaleString(I18N.locale)} · ${T("SYNTHETIC DEMO DATA")}</div>
      <h2>${T("City health")}</h2><div class="k"><b>${health(k)}%</b>${T("health score")}</div><div class="k"><b>${k.critical_incidents}</b>${T("critical")}</div><div class="k"><b>${k.open_incidents}</b>${T("open incidents")}</div>
      <div class="k"><b>${k.detected_urban_changes}</b>${T("urban changes")}</div><div class="k"><b>${k.avg_response_time_hours ?? 0}</b>${T("avg response (h)")}</div>
      <h2>${T("Highest-priority incidents")}</h2><table><tr><th>${T("ID")}</th><th>${T("Priority")}</th><th>${T("Area")}</th><th>${T("Risk")}</th><th>${T("Evidence")}</th></tr>${rows}</table>
      <h2>${T("Recommended actions")}</h2><ul>${recs}</ul>
      <h2>${T("Hotspots")}</h2><ul>${(ex.hotspots || []).map(h => `<li>${esc(TV(h.area))} — ${T("risk")} ${Math.round(h.score)}/100</li>`).join("")}</ul>
      <h2>${T("Crew escalations")}</h2><ul>${notes.filter(n => n.Severity === "Critical").slice(0, 10).map(n => `<li>${esc(n.Title)} (${esc(TV(n.Area_Name))})</li>`).join("") || `<li>${T("None")}</li>`}</ul>
      <p style="margin-top:30px;color:#666">${T("Figures computed from stored records at generation time. Use Print → Save as PDF.")}</p>`);
    w.document.close();
    setTimeout(() => { w.focus(); w.print(); setTimeout(() => frame.remove(), 60000); }, 400);
    toast(T("Report generated"), T("Use Save as PDF in the print dialog."));
  }

  $("gen").onclick = report;
  $("refresh").onclick = () => refresh().then(() => toast(T("Refreshed")));
  refresh();
  setInterval(() => { if (!document.hidden) refresh(); }, 10000);
});
