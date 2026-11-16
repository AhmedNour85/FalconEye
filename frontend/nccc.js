/* NCCC command center: one screen = alerts + map + the digital crew. Vanilla JS, no build step. */
"use strict";
const $ = (s, r = document) => r.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const { T, TV } = I18N;
const wait = ms => new Promise(r => setTimeout(r, ms));
const SEV_COLOR = { Critical: "#ff4d5a", High: "#ff8a2b", Medium: "#f2b233", Low: "#4aa3ff", Info: "#5f7ea3" };
const CLOSED = ["Resolved", "Closed - False Positive"];

const S = { tab: "action", state: null, seen: null, agents: {}, busy: false, mapSig: "", selected: "", pollTimer: null };
let M = null; // map handles

async function api(path, method = "GET", body) {
  const r = await fetch(I18N.apiUrl("/api/" + path), { method, headers: body ? { "Content-Type": "application/json" } : {}, body: body ? JSON.stringify(body) : undefined });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.detail || r.statusText);
  return j;
}

function toast(msg, sev = "Low") {
  const t = document.createElement("div");
  t.className = "toast"; t.style.setProperty("--c", SEV_COLOR[sev] || "#2d8cff"); t.textContent = msg;
  $("#toasts").append(t); setTimeout(() => t.remove(), 6000);
}

function ago(iso) {
  const s = Math.max(0, (Date.now() - Date.parse(iso)) / 1000);
  return s < 60 ? T("just now") : s < 3600 ? T("{n} min ago", { n: Math.floor(s / 60) }) : s < 86400 ? T("{n} h ago", { n: Math.floor(s / 3600) }) : T("{n} d ago", { n: Math.floor(s / 86400) });
}

const avatar = (id, small) => { const a = S.agents[id]; return a ? `<span class="av${small ? " sm" : ""}" style="--ac:${a.color}" title="${esc(a.name)} · ${esc(a.role)}">${esc(a.name[0])}</span>` : ""; };
const aName = id => (S.agents[id] || {}).name || id;

/* ---------------------------------------------------------------- state + polling */
async function poll() {
  if (S.busy || document.hidden) return;
  try { render(await api("nccc/state")); } catch (e) { $("#now").textContent = T("Offline - retrying…"); }
}

function render(st) {
  S.state = st;
  S.agents = Object.fromEntries(st.crew.agents.map(a => [a.id, a]));
  const k = st.kpis;
  $("#k-pend").textContent = k.pending_approvals; $("#k-open").textContent = k.open_incidents; $("#k-crit").textContent = k.critical; $("#k-res").textContent = k.resolved;
  const u = $("#unread"); u.hidden = !k.unread; u.textContent = k.unread; document.title = (k.unread ? `(${k.unread}) ` : "") + T("NCCC | National Command & Control Center");
  if (document.activeElement !== $("#autopilot")) $("#autopilot").checked = st.crew.autopilot;
  $("#mode").textContent = T("Planner: {p}", { p: plannerName(st.planner) }) + " · " + T("Records: {s}", { s: st.store || "" });
  { const e = st.crew.record_error, key = e ? e.at : "";        // an automatic scan that ArcGIS Online refused: say so once per failure
    if (key && key !== S.recordError) toast(T("ArcGIS Online did not accept a change: {m}", { m: e.message }), "Critical");
    S.recordError = key; }
  if (st.data_ready === false && !S.warnedEmpty) { S.warnedEmpty = true; toast(T("The layers in ArcGIS Online hold no demo data yet. Run scripts/initialize_demo.py."), "High"); }
  { const b = $("#planner-open"), t = T("Planner: {p}", { p: plannerName(st.planner) }); b.title = t; b.setAttribute("aria-label", t); b.classList.toggle("on", st.agent_mode !== "rules"); }
  $("#now").textContent = st.crew.autopilot ? T("AI Agents on · every {s}s · {n} scans", { s: st.crew.interval_s, n: st.crew.cycles }) : T("AI Agents off");
  $("#now").classList.toggle("live", st.crew.autopilot);
  announceNew(st.notifications); renderBell(); renderFeeds(st.feeds || []);
  if (document.activeElement !== $("#fsim")) $("#fsim").checked = !!st.crew.simulate_field;
  renderFeed(); renderRoster(); renderActivity(); updateMap();
}

function announceNew(list) {
  const ids = new Set(list.map(n => n.Notif_ID));
  if (S.seen === null) { S.seen = ids; return; }
  const fresh = list.filter(n => !S.seen.has(n.Notif_ID));
  ids.forEach(i => S.seen.add(i));
  if (!fresh.length) return;
  fresh.slice(0, 3).forEach(n => toast(`${TV(n.Severity)}: ${n.Title}`, n.Severity));
  if (fresh.length > 3) toast(T("{n} more alerts", { n: fresh.length - 3 }));
  const b = $("#bell"); b.classList.remove("ring"); void b.offsetWidth; b.classList.add("ring");
}

/* ---------------------------------------------------------------- alerts */
const needsAction = n => (n.approval && n.approval.status === "Proposed") || (!n.approval && n.Status === "New");

function renderFeed() {
  const all = S.state.notifications, rows = S.tab === "action" ? all.filter(needsAction) : all;
  const feed = $("#feed"); const keep = feed.scrollTop;
  const sig = [S.tab, S.state.crew.autopilot, Math.floor(Date.now() / 60000), ...rows.map(n => [n.Notif_ID, n.Status, n.approval && n.approval.status, n.incident_status, n.scenario_status, n.Updated].join(":"))].join("|");
  if (sig === S.feedSig) return;          // rebuilding on every poll would swallow clicks that land mid-refresh
  S.feedSig = sig;
  if (!rows.length) {
    const idle = !all.length && !S.state.crew.autopilot;
    feed.innerHTML = `<div class="empty"><b>${all.length ? T("All clear") : T("No alerts yet")}</b>${all.length ? T("Nothing needs your action right now.") : (idle ? T("The crew is idle. Start the AI Agents and they will watch the network and alert you.") : T("The crew is watching. New faults and changes will appear here."))}` +
      (idle ? `<br><button class="btn primary" id="start-ap" type="button">${T("Start AI Agents")}</button>` : "") + `</div>`;
    const b = $("#start-ap"); if (b) b.onclick = () => setAutopilot(true);
    return;
  }
  feed.innerHTML = rows.map(card).join("");
  feed.scrollTop = keep;
  feed.querySelectorAll("[data-act]").forEach(b => b.onclick = () => act(b.dataset.act, b.dataset.id, b));
  feed.querySelectorAll("details.how").forEach(d => { d.ontoggle = () => { S.open = S.open || new Set(); d.open ? S.open.add(d.dataset.id) : S.open.delete(d.dataset.id); }; });
}

function lifeStrip(l) {
  if (!l || !l.steps) return "";
  const dots = l.steps.map(s => `<li class="ls-${esc(s.state)}"${s.state === "current" ? ' aria-current="step"' : ""}><i></i><span>${T(s.key)}</span></li>`).join("");
  return `<ol class="life" aria-label="${T("Progress of this incident")}">${dots}</ol>` + (l.outcome === "rejected" ? `<p class="c-meta life-note">${T("The proposal was rejected. Nothing was carried out.")}</p>` : "");
}

function card(n) {
  const ap = n.approval, pend = ap && ap.status === "Proposed", c = S.agents[n.Agent] || { color: "#7df0b3" };
  let actions = "";
  if (pend) actions = `<button class="btn primary" data-act="approve" data-id="${esc(ap.id)}">${T("Approve")}</button><button class="btn" data-act="reject" data-id="${esc(ap.id)}">${T("Reject")}</button>`;
  else if (ap) actions = `<span class="state ${ap.status === "Executed" ? "" : "no"}">${ap.status === "Executed" ? T("✓ Approved and done") : esc(TV(ap.status))}</span>`;
  else if (n.Status === "New") actions = `<button class="btn" data-act="ack" data-id="${esc(n.Notif_ID)}">${T("Got it")}</button>`;
  if (!ap && n.Incident_ID && n.incident_status === "Open" && !n.active_work_order && (n.Kind === "fault" || n.Kind === "change")) actions += `<button class="btn" data-act="inspect" data-id="${esc(n.Incident_ID)}" title="${T("Prepare a work order to send a team to check this")}">${T("Request inspection")}</button>`;
  if (n.Kind === "verified") actions += `<button class="btn primary" data-act="report" data-id="${esc(n.Ref_ID)}" data-nid="${esc(n.Notif_ID)}">${T("View report")}</button>`;
  if (n.Kind === "verified" && n.incident_status === "Confirmed" && n.active_work_order) actions += `<button class="btn" data-act="simrepair" data-id="${esc(n.Incident_ID)}" title="${T("Report the repair as a simulated crew so the incident can be closed")}">${T("Simulate repair")}</button>`;
  if (n.Kind === "dispatch" && ap && ap.status === "Executed" && ap.worker_id) actions += `<button class="btn" data-act="investigator" data-id="${esc(ap.worker_id)}" title="${T("Open the page the assigned investigator sees (new tab)")}">${T("Open investigator view")}</button>`;
  if (n.scenario_id && n.scenario_status === "Completed" && n.Lon != null) actions += `<button class="btn" data-act="impact" data-id="${esc(n.scenario_id)}" title="${T("Show the closed road, the worse road sections and the detours (modelled)")}">${T("View impact on map")}</button>`;
  if (n.Kind === "change") actions += `<button class="link" data-act="compare" data-id="${esc(n.Notif_ID)}">${T("Compare epochs")}</button>`;
  if (n.Lon != null) actions += `<button class="link" data-act="show" data-id="${esc(n.Notif_ID)}">${T("Show on map")}</button>`;
  const trail = n.Trail.map(t => `<li>${avatar(t.agent, true)}<span><b style="--ac:${(S.agents[t.agent] || {}).color}">${esc(aName(t.agent))}</b> ${esc(t.did)}</span></li>`).join("");
  const open = S.open && S.open.has(n.Notif_ID) ? " open" : "";
  return `<article class="card ${esc(n.Severity)}${n.Status === "New" ? " new" : ""}${ap && ap.status !== "Proposed" ? " done" : ""}" id="n-${esc(n.Notif_ID)}" data-inc="${esc(n.Incident_ID)}" style="--ac:${c.color}">
    <div class="c-top">${avatar(n.Agent)}<div class="c-main"><div class="c-title">${esc(n.Title)}</div>
      <div class="c-meta"><span class="sev">${esc(TV(n.Severity))}</span><span>${ago(n.Created)}</span>${n.Incident_ID ? `<span>${esc(n.Incident_ID)}</span>` : ""}</div></div></div>
    ${lifeStrip(n.lifecycle)}
    <p class="c-msg">${esc(n.Message)}</p>
    ${ap && pend && ap.expected ? `<p class="c-meta" style="margin:6px 0 0">${T("If approved: ")}${esc(ap.expected)}</p>` : ""}
    <div class="c-act">${actions}</div>
    <details class="how" data-id="${esc(n.Notif_ID)}"${open}><summary>${T("How the crew handled this")}</summary><ul class="trail">${trail}</ul></details></article>`;
}

async function act(kind, id, btn) {
  try {
    if (kind === "report") { openReport(id); if (btn.dataset.nid) api("nccc/notifications/" + btn.dataset.nid + "/ack", "POST").then(poll).catch(() => {}); return; }
    if (kind === "investigator") { window.open("/field.html?worker=" + encodeURIComponent(id), "_blank", "noopener"); return; }
    if (kind === "impact") {
      if (M && M.mob) { M.mob.showImpact(id); const r = $(".mapbox").getBoundingClientRect(); if (r.top < 70 || r.bottom > innerHeight - 10) window.scrollTo({ top: Math.max(0, scrollY + r.top - 80) }); }
      else toast(T("The impact drawing needs the map, which needs internet access."), "High");
      return;
    }
    if (kind === "compare") { const n = S.state.notifications.find(x => x.Notif_ID === id); if (n) openCompare(n.Area_Name, n.Incident_ID); return; }
    if (kind === "show") { const n = S.state.notifications.find(x => x.Notif_ID === id); if (n) { goTo(n.Lon, n.Lat, n.Incident_ID); api("nccc/notifications/" + id + "/ack", "POST").catch(() => {}); } return; }
    btn.disabled = true;
    if (kind === "simrepair") { await api(`nccc/incidents/${id}/simulate-repair`, "POST"); toast(T("Repair reported by a simulated crew. The closure is ready for your approval."), "Low"); }
    if (kind === "inspect") { await api(`nccc/incidents/${id}/inspection`, "POST"); toast(T("Work order prepared. Approve it to send a team."), "Low"); }
    if (kind === "ack") await api("nccc/notifications/" + id + "/ack", "POST");
    if (kind === "approve") {
      const r = await api(`approvals/${id}/approve`, "POST");
      toast(r.work_order_id ? T("Approved. Work order {id} created.", { id: r.work_order_id }) : r.worker ? (r.field_maps_sent ? T("Approved. The assignment for {who} was sent to ArcGIS Field Maps.", { who: r.worker }) : T("Approved. {who} gets a pop-up to confirm the assignment.", { who: r.worker })) : T("Approved and done."), "Low");
      await followThrough();
    }
    if (kind === "reject") { await api(`approvals/${id}/reject`, "POST"); toast(T("Rejected. Nothing was changed.")); }
    await poll();
  } catch (e) { toast(e.message, "High"); btn.disabled = false; }
}

/* ---------------------------------------------------------------- live feeds */
function renderFeeds(list) {
  const box = $("#feeds"); S.feedAt = S.feedAt || {};
  box.innerHTML = list.map(f => {
    const fresh = S.feedAt[f.id] !== undefined && S.feedAt[f.id] !== f.at && f.at; S.feedAt[f.id] = f.at;
    const ag = S.agents[f.agent] || { color: "#7df0b3", name: "" };
    return `<div class="fchip${f.alert ? " alert" : ""}${fresh ? " fresh" : ""}" style="--ac:${ag.color}"><b><i></i>${esc(f.name)}</b><span>${esc(f.detail)}</span><small>${f.at ? T("updated {t}", { t: ago(f.at) }) : T("waiting for data")} · ${T("read by {n}", { n: esc(ag.name) })}</small></div>`;
  }).join("");
}

/* ---------------------------------------------------------------- imagery epoch comparison */
const CMP = { area: "Olaya", data: null, inc: "", sel: "", pos: 50, changes: true, normalise: true };

async function openCompare(area, inc, sel) {
  CMP.area = area || CMP.area; CMP.inc = inc || ""; CMP.sel = sel || ""; CMP.pos = 50;
  $("#cmp").hidden = false; await loadCompare(); $("#cmp-close").focus();
}
function closeCompare() { $("#cmp").hidden = true; }
async function loadCompare() {
  $("#cmp-body").innerHTML = '<p class="m">${T("Loading imagery…")}</p>';
  try { CMP.data = await api("nccc/imagery/" + encodeURIComponent(CMP.area)); } catch (e) { $("#cmp-body").innerHTML = `<p>${esc(e.message)}</p>`; return; }
  if (!CMP.sel && CMP.inc) { const c = CMP.data.changes.find(x => x.incident_id === CMP.inc); if (c) CMP.sel = c.id; }
  renderCompare();
}
const centroidOf = ring => [ring.reduce((a, p) => a + p[0], 0) / ring.length, ring.reduce((a, p) => a + p[1], 0) / ring.length];

function renderCompare() {
  const d = CMP.data, b = d.bounds, base = "/api/imagery/" + encodeURIComponent(d.area);
  const pt = p => `${((p[0] - b.xmin) / (b.xmax - b.xmin) * 100).toFixed(2)},${((b.ymax - p[1]) / (b.ymax - b.ymin) * 100).toFixed(2)}`;
  const sig = d.changes.filter(c => c.significant).length;
  const polys = d.changes.map(c => `<polygon class="chg ${c.significant ? "sig" : "minor"}${c.id === CMP.sel ? " on" : ""}" data-ch="${esc(c.id)}" points="${c.ring.map(pt).join(" ")}"><title>${esc(TV(c.type))}</title></polygon>`).join("");
  const list = d.changes.map(c => {
    const hasAlert = c.incident_id && S.state && S.state.notifications.some(n => n.Incident_ID === c.incident_id);
    const [lon, lat] = centroidOf(c.ring);
    return `<li class="chg-i ${c.significant ? "sig" : ""}${c.id === CMP.sel ? " on" : ""}" data-ch="${esc(c.id)}"><b>${esc(TV(c.type))}</b>
      <span class="m">${esc(c.id)} · ${T("{n} m²", { n: Math.round(c.area_sqm).toLocaleString(I18N.locale) })} · ${T("confidence")} ${Math.round(c.confidence * 100)}% · ${c.significant ? "<b style=\"display:inline;color:#ff8a92\">" + T("significant") + "</b>" : T("minor or possibly seasonal")}${c.incident_id ? " · " + esc(c.incident_id) : ""}</span>
      <div class="row"><button class="btn" data-cm="map" data-lon="${lon}" data-lat="${lat}" data-inc="${esc(c.incident_id)}" type="button">${T("Show on map")}</button>${hasAlert ? `<button class="btn" data-cm="alert" data-inc="${esc(c.incident_id)}" type="button">${T("Open alert")}</button>` : ""}</div></li>`;
  }).join("");
  $("#cmp-body").innerHTML = `<div>
      <div class="cmp-tools"><label>${T("Area")} <select id="cmp-area">${d.areas.map(a => `<option value="${esc(a)}"${a === d.area ? " selected" : ""}>${esc(TV(a))}</option>`).join("")}</select></label>
        <label><input type="checkbox" id="cmp-chg"${CMP.changes ? " checked" : ""}> ${T("Show changes")}</label>
        <label title="${T("Matches the brightness of the two dates, as the detector does")}"><input type="checkbox" id="cmp-norm"${CMP.normalise ? " checked" : ""}> ${T("Match brightness")}</label></div>
      <div class="cmp-view" id="cmp-view"><img alt="${T("Satellite image, after: {d}", { d: esc(d.after) })}" src="${base}/${CMP.normalise ? "Bn" : "B"}.png"><img id="cmp-before" alt="${T("Satellite image, before: {d}", { d: esc(d.before) })}" src="${base}/A.png" style="clip-path:inset(0 ${100 - CMP.pos}% 0 0)">
        <svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-label="${T("Detected changes")}"${CMP.changes ? "" : " hidden"}>${polys}</svg><i class="handle" id="cmp-handle" style="left:${CMP.pos}%"></i>
        <span class="tag l">${T("Before · {d}", { d: esc(d.before) })}</span><span class="tag r">${T("After · {d}", { d: esc(d.after) })}</span></div>
      <input type="range" id="cmp-pos" min="0" max="100" value="${CMP.pos}" aria-label="${T("Drag to swipe between the before and after images")}">
      <p class="cmp-note">${T("False-colour composite (SWIR, NIR, red). Red outlines are significant candidate changes; grey dashed outlines are minor or possibly seasonal. Imagery and processing are SIMULATED; candidates are not confirmed until a field crew verifies them.")}</p></div>
    <div><div class="cmp-sum"><div><b>${d.changes.length}</b><span class="m">${T("changes found")}</span></div><div><b style="color:#ff8a92">${sig}</b><span class="m">${T("significant")}</span></div></div>
      <div class="cmp-tools"><button class="btn primary" id="cmp-scan" type="button">${d.scanned ? T("Rescan this area") : T("Scan this area")}</button><span class="m">${T("Zayed compares the two dates and opens incidents for significant change.")}</span></div>
      ${d.scanned ? `<ul class="chg-list">${list}</ul>` : '<p class="m">${T("No comparison has been run for this area yet. Press Scan to compare the two dates.")}</p>'}</div>`;
  wireCompare();
}

function wireCompare() {
  const body = $("#cmp-body");
  $("#cmp-area").onchange = e => { CMP.area = e.target.value; CMP.sel = ""; CMP.inc = ""; CMP.pos = 50; loadCompare(); };
  $("#cmp-chg").onchange = e => { CMP.changes = e.target.checked; body.querySelector("svg").hidden = !CMP.changes; };
  $("#cmp-norm").onchange = e => { CMP.normalise = e.target.checked; renderCompare(); };
  $("#cmp-pos").oninput = e => { CMP.pos = +e.target.value; $("#cmp-before").style.clipPath = `inset(0 ${100 - CMP.pos}% 0 0)`; $("#cmp-handle").style.left = CMP.pos + "%"; };
  const select = id => { CMP.sel = id; body.querySelectorAll("[data-ch]").forEach(el => el.classList.toggle("on", el.dataset.ch === id)); };
  body.querySelectorAll("polygon[data-ch]").forEach(el => el.onclick = () => select(el.dataset.ch));
  body.querySelectorAll("li[data-ch]").forEach(el => el.onclick = () => select(el.dataset.ch));
  body.querySelectorAll("[data-cm]").forEach(b => b.onclick = e => {
    e.stopPropagation(); closeCompare();
    if (b.dataset.cm === "map") goTo(+b.dataset.lon, +b.dataset.lat, b.dataset.inc);
    else focusAlert(b.dataset.inc);
  });
  $("#cmp-scan").onclick = async e => {
    e.target.disabled = true; e.target.textContent = T("Comparing…");
    try { const r = await api("nccc/imagery/" + encodeURIComponent(CMP.area) + "/scan", "POST"); const n = (r.new_notifications || []).length; toast(n ? T("Zayed found change events: {n} new alert(s).", { n }) : T("Comparison complete. No new alerts.")); await loadCompare(); poll(); }
    catch (err) { toast(err.message, "High"); renderCompare(); }
  };
}

$("#cmp-open").onclick = () => openCompare(CMP.area);
$("#cmp-close").onclick = closeCompare;
$("#cmp").addEventListener("click", e => { if (e.target.id === "cmp") closeCompare(); });
document.addEventListener("keydown", e => { if (e.key === "Escape" && !$("#cmp").hidden) closeCompare(); });

/* ---------------------------------------------------------------- planner choice (offline rules, Claude, OpenAI, Gemini, local models) */
const plannerName = label => String(label || "").split(" · ").map(x => TV(x)).join(" · ");
const PL = { info: null };

async function openPlanner() {
  $("#pl").hidden = false; $("#pl-body").innerHTML = `<p class="m">${T("Loading…")}</p>`;
  try { PL.info = await api("planner"); } catch (e) { $("#pl-body").innerHTML = `<p>${esc(e.message)}</p>`; return; }
  renderPlanner(PL.info.active.provider, true);
  $("#pl-close").focus();
}
function closePlanner() { $("#pl").hidden = true; }

function renderPlanner(sel, first) {
  const { active, presets } = PL.info, p = presets.find(x => x.id === sel) || presets[0];
  const same = active.provider === p.id;
  const group = (kind, label) => `<optgroup label="${T(label)}">${presets.filter(x => x.kind === kind).map(x => `<option value="${esc(x.id)}"${x.id === p.id ? " selected" : ""}>${esc(T(x.label))}</option>`).join("")}</optgroup>`;
  const compat = !["rules", "claude"].includes(p.id);
  $("#pl-body").innerHTML = `<form id="pl-form" autocomplete="off">
    <label class="pl-f"><span>${T("Planner")}</span><select id="pl-sel">${group("offline", "Offline")}${group("cloud", "Online (API)")}${group("local", "Local or your own server")}${presets.some(x => x.kind === "custom") ? group("custom", "Other") : ""}</select></label>
    ${p.id === "rules" ? `<p class="pl-note">${T("The offline planner answers from fixed rules. It needs no internet and no key, and sends nothing anywhere.")}</p>` : `
    <label class="pl-f"><span>${T("Model")}</span><input id="pl-model" dir="ltr" list="pl-models" value="${esc(same ? active.model : p.model)}" spellcheck="false" required><datalist id="pl-models">${p.models.map(m => `<option value="${esc(m)}">`).join("")}</datalist><div class="pl-chips" id="pl-chips" dir="ltr"></div></label>
    ${compat ? `<label class="pl-f"><span>${T("Server address")}</span><input id="pl-url" dir="ltr" type="url" value="${esc(same && active.base_url ? active.base_url : p.base_url)}" placeholder="http://localhost:1234/v1" spellcheck="false" required><small>${T("OpenAI-compatible address, usually ending in")} <bdi dir="ltr">/v1</bdi></small></label>` : ""}
    ${p.kind === "local" || p.id === "custom" ? "" : `<label class="pl-f"><span>${T("API key")}</span><input id="pl-key" dir="ltr" type="password" autocomplete="new-password" placeholder="${same && active.has_key ? T("A key is set. Leave empty to keep it.") : p.key_in_env ? T("Using the key from the server settings. Leave empty to keep it.") : T("Paste the key")}"><small>${T("Kept in the server's memory only. It is never saved to disk or shown again.")}</small></label>`}
    ${p.id === "custom" ? `<label class="pl-f"><span>${T("API key (optional)")}</span><input id="pl-key" dir="ltr" type="password" autocomplete="new-password" placeholder="${T("Only if the server asks for one")}"></label>` : ""}
    <p class="pl-note">${p.kind === "local" ? T("A local model keeps your data on this machine. Pick a model that supports tool calling (Hermes, Llama 3.1, Qwen 2.5 ...).") : T("Questions and the incident data the tools return are sent to this provider. Demo data is synthetic. The AI can only propose actions; a person still approves them.")}</p>`}
    <div class="pl-act"><button class="btn primary" id="pl-apply" type="submit">${p.id === "rules" ? T("Use this planner") : T("Save and test")}</button><button class="btn" id="pl-cancel" type="button">${T("Close")}</button></div>
    <div id="pl-res" aria-live="polite"></div></form>`;
  $("#pl-sel").onchange = e => renderPlanner(e.target.value);
  if (p.id !== "rules") loadModels(p);
  $("#pl-cancel").onclick = closePlanner;
  $("#pl-form").onsubmit = async e => {
    e.preventDefault();
    const btn = $("#pl-apply"), res = $("#pl-res"); btn.disabled = true; res.className = ""; res.textContent = "";
    try {
      PL.info = await api("planner", "POST", { provider: p.id, model: ($("#pl-model") || {}).value || "", base_url: ($("#pl-url") || {}).value || "", api_key: ($("#pl-key") || {}).value || "" });
      S.rosterSig = ""; await poll();
      if (p.id === "rules") { res.className = "pl-res ok"; res.textContent = T("The offline planner is active."); return; }
      res.className = "pl-res"; res.textContent = T("Testing the connection…");
      const t = await api("planner/test", "POST");
      res.className = "pl-res " + (t.ok ? "ok" : "bad");
      res.innerHTML = t.ok ? T("Connected ({ms} ms). This planner now answers in the crew chat.", { ms: t.ms })
        : T("Saved, but the test failed: {e}. Questions fall back to the offline planner until it works.", { e: esc(t.error) }) + (t.detail ? `<div class="pl-detail" dir="ltr">${esc(t.detail)}</div>` : "");
      if (!t.ok) loadModels(p);
    } catch (err) { res.className = "pl-res bad"; res.textContent = err.message; }
    finally { btn.disabled = false; }
  };
}
/* the models the server says it has: a wrong model name is the most common mistake, so they are one click away */
async function loadModels(p) {
  const box = $("#pl-chips"); if (!box) return;
  box.textContent = "…";
  let names = [], up = false;
  try { const r = await api("planner/models", "POST", { provider: p.id, base_url: ($("#pl-url") || {}).value || "", api_key: ($("#pl-key") || {}).value || "" }); names = r.models; up = r.reachable; } catch (e) { /* bad address */ }
  if (!$("#pl-chips")) return;
  if (p.kind === "cloud") names = names.filter(n => !/embed|tts|audio|image|imagen|veo|live|vision|aqa|robotics|computer-use|transcri|moderation|whisper|dall-e|davinci|babbage|realtime/i.test(n));
  const inp = $("#pl-model");
  if (inp && names.length && !names.includes(inp.value) && inp.value === p.model) {      // the suggested default is not offered by this account/server: start from one that is
    inp.value = names.find(n => /flash/i.test(n)) || names.find(n => /mini|small|haiku/i.test(n)) || names[0];
  }
  const cur = ($("#pl-model") || {}).value;
  box.innerHTML = names.length ? `<small dir="${I18N.rtl ? "rtl" : "ltr"}">${T("Installed on the server (click to use):")}</small><div>${names.slice(0, 14).map(n => `<button type="button" class="chip${n === cur ? " on" : ""}" data-m="${esc(n)}">${esc(n)}</button>`).join("")}</div>`
    : up && p.kind === "local" ? `<small dir="${I18N.rtl ? "rtl" : "ltr"}">${T("The server is running but has no models installed. For Ollama, run: ollama pull llama3.1")}</small>` : "";
  box.querySelectorAll("[data-m]").forEach(b => b.onclick = () => { $("#pl-model").value = b.dataset.m; box.querySelectorAll(".chip").forEach(x => x.classList.toggle("on", x === b)); });
}
$("#planner-open").onclick = openPlanner;
$("#pl-close").onclick = closePlanner;
$("#pl").addEventListener("click", e => { if (e.target.id === "pl") closePlanner(); });
document.addEventListener("keydown", e => { if (e.key === "Escape" && !$("#pl").hidden) closePlanner(); });

/* ---------------------------------------------------------------- investigator report */
async function openReport(vid) {
  $("#rep").hidden = false; $("#rep-body").innerHTML = '<p class="m">${T("Loading the report…")}</p>';
  let r; try { r = await api("nccc/field-report/" + encodeURIComponent(vid)); } catch (e) { $("#rep-body").innerHTML = `<p>${esc(e.message)}</p>`; return; }
  const good = ["Confirmed", "Repaired"].includes(r.status), bad = r.status === "Rejected";
  const label = { Confirmed: T("Incident confirmed"), Repaired: T("Repair completed"), Rejected: T("Not found (false alarm)"), "Needs Further Inspection": T("Needs a further inspection"), Escalate: T("Escalated") }[r.status] || TV(r.status);
  const hasAlert = S.state && S.state.notifications.some(n => n.Incident_ID === r.incident.id && n.Kind !== "verified");
  $("#rep-sub").textContent = `${r.worker.name} · ${r.worker.team} · ${ago(r.time)}${r.simulated ? " · " + T("SIMULATED crew") : ""}`;
  $("#rep-body").innerHTML = `<p><span class="badge ${good ? "go" : bad ? "bad" : "wait"}">${esc(label)}</span></p>
    <dl class="kv"><dt>${T("Incident")}</dt><dd><b>${esc(TV(r.incident.type))}</b> · ${esc(r.incident.id)} · ${esc(r.incident.priority)} ${esc(TV(r.incident.severity))} · ${esc(TV(r.incident.area))}</dd>
      <dt>${T("Work order")}</dt><dd>${esc(r.work_order)}</dd><dt>${T("Reported from")}</dt><dd>${esc(r.gps)} · ${T("{n} m from the detected point", { n: r.distance_m == null ? "?" : Math.round(r.distance_m) })}</dd></dl>
    <div class="rep-obs"><b>${T("What the investigator saw")}</b><br>${esc(r.observation)}</div>
    ${r.photo ? `<p class="m">${T("Photo evidence")}</p><a href="${esc(r.photo)}" target="_blank" rel="noopener"><img class="rep-photo" src="${esc(r.photo)}" alt="${T("Photo taken by the investigator")}"></a>` : `<p class="m">${T("No photo was attached.")}</p>`}
    <div class="ai"><b>${T("AI assessment")}</b><br>${esc(r.assessment || T("Not available."))}</div>
    <div class="row" style="display:flex;gap:8px;flex-wrap:wrap;margin-top:12px"><button class="btn" id="rep-map" type="button">${T("Show on map")}</button>${hasAlert ? `<button class="btn" id="rep-alert" type="button">${T("Open the incident alert")}</button>` : ""}<button class="btn" id="rep-ok" type="button">${T("Close")}</button></div>`;
  $("#rep-map").onclick = () => { closeReport(); goTo(r.location.lon, r.location.lat, r.incident.id); };
  if (hasAlert) $("#rep-alert").onclick = () => { closeReport(); focusAlert(r.incident.id); };
  $("#rep-ok").onclick = closeReport;
}
function closeReport() { $("#rep").hidden = true; }
$("#rep-close").onclick = closeReport;
$("#rep").addEventListener("click", e => { if (e.target.id === "rep") closeReport(); });
document.addEventListener("keydown", e => { if (e.key === "Escape" && !$("#rep").hidden) closeReport(); });
$("#fsim").onchange = e => api(`nccc/field-sim?on=${e.target.checked}`, "POST").then(() => toast(e.target.checked ? T("Simulated crew will answer assigned work orders.") : T("Assigned work orders now wait for the investigator."), "Low")).catch(err => toast(err.message, "High"));

/* ---------------------------------------------------------------- bell */
function closeBell() { $("#bellmenu").hidden = true; $("#bell").setAttribute("aria-expanded", "false"); }
function renderBell() {
  const m = $("#bellmenu"); if (!S.state) return;
  const unread = S.state.notifications.filter(n => n.Status === "New");
  $("#bell").setAttribute("aria-label", unread.length ? T("{n} unread alerts", { n: unread.length }) : T("Alerts, none unread"));
  if (m.hidden) return;
  m.innerHTML = `<div class="bm-h"><span>${unread.length ? T("{n} unread", { n: unread.length }) : T("Alerts")}</span><button class="link" data-bm="all" type="button">${T("Mark all read")}</button></div><div class="bm-list">` +
    (unread.length ? unread.slice(0, 12).map(n => `<button class="bm-i" data-bm="${esc(n.Notif_ID)}" type="button" style="--c:${SEV_COLOR[n.Severity] || "#4aa3ff"}"><i></i><span><b>${esc(n.Title)}</b><small>${esc(TV(n.Severity))} · ${ago(n.Created)}</small></span></button>`).join("") : '<div class="bm-e">${T("You are all caught up.")}</div>') +
    `</div>`;
  m.querySelectorAll("[data-bm]").forEach(b => b.onclick = async e => {
    e.stopPropagation();
    if (b.dataset.bm === "all") { await api("nccc/notifications/ack-all", "POST"); closeBell(); return poll(); }
    const n = S.state.notifications.find(x => x.Notif_ID === b.dataset.bm); closeBell();
    api("nccc/notifications/" + b.dataset.bm + "/ack", "POST").catch(() => {});
    if (n && n.Lon != null) goTo(n.Lon, n.Lat, n.Incident_ID);
    if (n) { S.tab = "all"; syncTabs(); S.feedSig = ""; focusAlert(n.Incident_ID, n.Notif_ID); }
    poll();
  });
}

/* ---------------------------------------------------------------- crew */
function renderRoster() {
  const sig = [S.detail, Math.floor(Date.now() / 60000), ...S.state.crew.agents.map(a => a.working + a.last_at)].join("|");
  if (sig === S.rosterSig) return;
  S.rosterSig = sig;
  const tier = { executive: "exec", operations: "ops", specialist: "" };
  $("#roster").innerHTML = S.state.crew.agents.map(a => `<button class="ag ${tier[a.tier]}" style="--ac:${a.color}" data-id="${a.id}" type="button" aria-expanded="${S.detail === a.id}">${avatar(a.id)}
    <span class="ag-t"><b>${esc(a.name)}</b><small>${esc(a.working ? T("Working…") : a.last_at ? T("Active {t}", { t: ago(a.last_at) }) : a.role)}</small></span></button>`).join("");
  $("#roster").querySelectorAll(".ag").forEach(b => b.onclick = () => { S.detail = S.detail === b.dataset.id ? "" : b.dataset.id; renderRoster(); });
  const d = $("#agent-detail"), a = S.agents[S.detail];
  d.hidden = !a;
  if (a) d.innerHTML = `<b style="color:${a.color}">${esc(a.name)}</b> · ${esc(a.role)}<br>${esc(a.focus)}.<br>${T("Tools:")} ${a.tools.map(t => `<code>${esc(t)}</code>`).join(" ")}`;
}

function renderActivity() {
  $("#activity").innerHTML = S.state.crew.activity.slice(0, 4).map(s => `<li><b style="--ac:${(S.agents[s.agent] || {}).color}">${esc(aName(s.agent))}</b> ${esc(s.action)}${s.detail ? " · " + esc(s.detail) : ""}</li>`).join("");
}

async function playback(steps) {
  const ids = (steps || []).slice(0, 12);
  for (const s of ids) {
    document.querySelectorAll(".ag").forEach(b => b.classList.toggle("active", b.dataset.id === s.agent));
    $("#now").textContent = `${aName(s.agent)}: ${s.action}`; $("#now").classList.add("live");
    await wait(480);
  }
  document.querySelectorAll(".ag.active").forEach(b => b.classList.remove("active"));
}

async function runScan(call, label) {
  if (S.busy) return;
  S.busy = true; document.querySelectorAll("#scan,#sim").forEach(e => e.disabled = true); $("#now").textContent = label; $("#now").classList.add("live");
  try {
    const r = await call();
    S.busy = false;
    await poll();
    await playback((r.scan || r).steps);
    const n = ((r.scan || r).new_notifications || []).length;
    toast(n ? T("Crew raised {n} new alert(s).", { n }) : T("Scan complete. Nothing new."));
  } catch (e) { toast(e.message, "High"); }
  finally { S.busy = false; document.querySelectorAll("#scan,#sim").forEach(e => e.disabled = false); $("#sim").value = ""; poll(); }
}

async function followThrough() { if (!S.state.crew.autopilot) await api("nccc/scan?follow=true", "POST").catch(() => {}); }   // the crew picks up the next step after a decision, without re-scanning the other feeds
async function setAutopilot(on) {
  try { await api(`nccc/autopilot?on=${on}&interval=60`, "POST"); toast(on ? T("AI Agents on. They are watching the network.") : T("AI Agents paused.")); await poll(); }
  catch (e) { toast(e.message, "High"); $("#autopilot").checked = !on; }
}

/* ---------------------------------------------------------------- map */
function showMapMode() {
  const b = $("#map-mode"); if (!b) return;
  b.querySelector(".mm").textContent = M.three ? "3D" : "2D"; b.title = T(M.three ? "Map: 3D" : "Map: 2D"); b.classList.toggle("on", M.three);
}

/* 2D map or 3D scene on the same layers (same camera as the Executive Hub); the choice is shared with it and remembered */
function toggleMapMode() {
  if (!M) return;
  M.three = !M.three;
  M.view.map = null; M.view.destroy();               // detach the map first: destroying a view would destroy it too
  M.view = M.makeView(M.three); M.wire(M.view);
  try { localStorage.setItem("geoai.map3d", M.three ? "1" : "0"); } catch (e) { /* optional */ }
  showMapMode(); clearPick(); updateMap(true);
}

function initMap() {
  if (typeof require !== "function") { $("#map").innerHTML = `<div class="empty"><b>${T("Map unavailable")}</b>${T("The ArcGIS map needs internet access. Alerts still work.")}</div>`; return; }
  require([
    "esri/Map", 
    "esri/views/MapView", 
    "esri/views/SceneView", 
    "esri/layers/GraphicsLayer", 
    "esri/Graphic", 
    "esri/widgets/Search"
  ], (Map, MapView, SceneView, GraphicsLayer, Graphic, Search) => {
    const chg = new GraphicsLayer(), rep = new GraphicsLayer(), layer = new GraphicsLayer(), sel = new GraphicsLayer();
    const map = new Map({ basemap: "dark-gray-vector", layers: [chg, rep, layer, sel] });
    const makeView = three => three
      ? new SceneView({ container: "map", map, camera: { position: [46.67, 24.54, 12000], tilt: 45 }, popup: { autoOpenEnabled: false }, ui: { components: ["zoom"] } })
      : new MapView({ container: "map", map, center: [46.68, 24.70], zoom: 11, constraints: { snapToZoom: false }, popup: { autoOpenEnabled: false }, ui: { components: ["zoom"] } });
    const wire = v => { v.ui.add(new Search({ view: v }), "top-right"); v.on("click", e => pickAt(e.x, e.y)); };      // search sits inside the map, clear of the zoom buttons
    let three = false; try { three = localStorage.getItem("geoai.map3d") === "1"; } catch (e) { /* 2D by default */ }
    const view = makeView(three);
    M = { view, map, layer, rep, sel, chg, Graphic, MapView, SceneView, makeView, wire, three };
    if (window.Mobility) {                                  // traffic (modelled), metro, bus and hospitals: off until switched on
      if (matchMedia("(max-width:640px)").matches) $("#maplayers").open = false;
      M.mob = Mobility.attach({ map, GraphicsLayer, Graphic, panel: $("#maplayers"), host: document.querySelector(".mapbox"), view: () => M.view });
    }
    wire(view); showMapMode();
    let on = false; try { on = localStorage.getItem("geoai.layer.change") === "1"; } catch (e) { /* off by default */ }
    $("#l-change").checked = on; chg.visible = on;
    $("#l-change").onchange = e => { chg.visible = e.target.checked; try { localStorage.setItem("geoai.layer.change", e.target.checked ? "1" : "0"); } catch (err) { /* optional */ } if (chg.visible) updateChanges(true); };
    updateMap(true);
  });
}

/* the feature closest to the click (within a finger-sized radius) is selected; incidents win over citizen reports */
function pickAt(x, y) {
  let best = null, bd = 26;
  for (const [layer, kind, bias] of [[M.rep, "report", -8], [M.layer, "incident", 0]]) {
    for (const g of layer.graphics.items) {
      const sp = M.view.toScreen(g.geometry); if (!sp) continue;
      const d = Math.hypot(sp.x - x, sp.y - y) - bias;
      if (d < bd) { bd = d; best = { kind, id: g.attributes.id, lon: g.geometry.longitude, lat: g.geometry.latitude }; }
    }
  }
  if (!best) { clearPick(); return; }
  ring(best.lon, best.lat);
  S.selected = best.id; showPick(best);
}

function ring(lon, lat) {
  M.sel.removeAll();
  M.sel.add(new M.Graphic({ geometry: { type: "point", longitude: lon, latitude: lat }, symbol: { type: "simple-marker", style: "circle", color: [0, 0, 0, 0], size: 34, outline: { color: "#7df0b3", width: 3 } } }));
}
function clearPick() { M && M.sel.removeAll(); $("#pick").hidden = true; S.selected = ""; }

async function showPick(p) {
  const box = $("#pick"); box.hidden = false; box.style.setProperty("--c", "#7df0b3");
  const close = `<button class="x" aria-label="${T("Close")}" type="button">×</button>`;
  try {
    if (p.kind === "report") {
      const r = (S.reports || []).find(x => x.Report_ID === p.id); if (!r) return clearPick();
      box.innerHTML = `${close}<h4>${T("Citizen report · {t}", { t: esc(r.Title) })}</h4><div class="m">${esc(r.Report_ID)} · ${esc(r.Channel)} · ${ago(r.Reported_At)}</div><p>${esc(r.Description)}</p><p class="m">${esc(TV(r.Area_Name))} · ${T("status: {s}", { s: esc(TV(r.Status)) })}${r.Linked_Incident ? " · " + T("supports {id}", { id: esc(r.Linked_Incident) }) : ""}</p>` +
        (r.Linked_Incident ? `<div class="row"><button class="btn" data-pk="inc" data-id="${esc(r.Linked_Incident)}" type="button">${T("Open {id}", { id: esc(r.Linked_Incident) })}</button></div>` : "");
    } else {
      const d = (await api("incidents/" + p.id)).result, a = d.incident, wo = d.work_orders[d.work_orders.length - 1], n = (S.reports || []).filter(x => x.Linked_Incident === p.id).length;
      box.style.setProperty("--c", SEV_COLOR[a.Severity] || "#7df0b3");
      box.innerHTML = `${close}<h4>${esc(TV(a.Incident_Type))}</h4><div class="m"><b style="color:${SEV_COLOR[a.Severity]}">${esc(TV(a.Severity))}</b> · ${esc(a.Priority)} · ${esc(TV(a.Status))} · ${esc(TV(a.Area_Name))}</div><p>${esc((a.Description || "").slice(0, 210))}${(a.Description || "").length > 210 ? "…" : ""}</p>` +
        `<p class="m">${esc(p.id)} · ${T("team: {t}", { t: esc(a.Assigned_Team || T("not assigned")) })}${wo ? " · " + esc(wo.Work_Order_ID) + " " + esc(TV(wo.Status)) + (wo.Assigned_Worker ? " (" + esc(wo.Assigned_Worker) + ")" : "") : " · " + T("no work order yet")}${n ? " · " + T("{n} citizen report(s)", { n }) : ""}</p>` +
        `<div class="row">${S.state && S.state.notifications.some(x => x.Incident_ID === p.id) ? `<button class="btn" data-pk="inc" data-id="${esc(p.id)}" type="button">${T("Show alert")}</button>` : ""}${a.Category === "change" ? `<button class="btn" data-pk="cmp" data-area="${esc(a.Area_Name)}" data-id="${esc(p.id)}" type="button">${T("Compare epochs")}</button>` : ""}<button class="btn" data-pk="ask" data-id="${esc(p.id)}" type="button">${T("Ask the crew")}</button></div>`;
    }
  } catch (e) { box.innerHTML = `${close}<p>${esc(e.message)}</p>`; }
  box.querySelector(".x").onclick = clearPick;
  box.querySelectorAll("[data-pk]").forEach(b => b.onclick = () => b.dataset.pk === "ask" ? ask(T("Tell me about incident {id}", { id: b.dataset.id })) : b.dataset.pk === "cmp" ? openCompare(b.dataset.area, b.dataset.id) : focusAlert(b.dataset.id));
}

async function updateReports() {
  let rows; try { rows = await api("nccc/reports"); } catch { return; }
  S.reports = rows;
  const sig = rows.map(r => r.Report_ID + r.Status).join("|"); if (sig === S.repSig) return; S.repSig = sig;
  const col = { water: "#7fd6ff", lighting: "#ffe08a", other: "#9fb2c8" };
  M.rep.removeAll();
  M.rep.addMany(rows.map(r => new M.Graphic({ geometry: { type: "point", longitude: r.lon, latitude: r.lat }, attributes: { id: r.Report_ID },
    symbol: { type: "simple-marker", style: "diamond", color: col[r.Category] || "#9fb2c8", size: r.Status === "Linked" ? 11 : 9, outline: { color: "#0b1d36", width: 1 } } })));
}

/* the satellite-comparison polygons, drawn under the incidents (loaded only while the layer is switched on) */
async function updateChanges(force) {
  if (!M || !M.chg.visible) return;
  let gj; try { gj = await api("layers/Riyadh_Change_Detection"); } catch { return; }
  const sig = gj.features.map(f => f.id + (f.properties || {}).Significant).join("|");
  if (sig === S.chgSig && !force) return; S.chgSig = sig;
  M.chg.removeAll();
  M.chg.addMany(gj.features.filter(f => f.geometry && f.geometry.type !== "Point").map(f => new M.Graphic({
    geometry: { type: "polygon", rings: f.geometry.coordinates },
    symbol: { type: "simple-fill", color: [31, 179, 107, (f.properties || {}).Significant === "Yes" ? 0.4 : 0.15], outline: { color: [31, 179, 107], width: (f.properties || {}).Significant === "Yes" ? 1.6 : 0.8 } } })));
}

async function updateMap(force) {
  if (!M || !S.state) return;
  updateReports(); updateChanges(force); if (M.mob) M.mob.refreshClosures();
  const pend = new Set(S.state.approvals.map(a => a.Incident_ID));
  let gj; try { gj = await api("layers/Riyadh_Operational_Incidents"); } catch { return; }
  const open = gj.features.filter(f => !CLOSED.includes(f.properties.Status));
  const sig = open.map(f => f.id + f.properties.Status + f.properties.Severity + pend.has(f.id)).join("|");
  if (sig === S.mapSig && !force) return; S.mapSig = sig;
  M.layer.removeAll();
  M.layer.addMany(open.map(f => new M.Graphic({
    geometry: { type: "point", longitude: f.geometry.coordinates[0], latitude: f.geometry.coordinates[1] }, attributes: { id: f.id },
    symbol: { type: "simple-marker", style: "circle", color: SEV_COLOR[f.properties.Severity] || "#4aa3ff", size: { P1: 15, P2: 13, P3: 11, P4: 9 }[f.properties.Priority] || 10,
      outline: pend.has(f.id) ? { color: "#ffffff", width: 2.5 } : { color: "#0b1d36", width: 1 } } })));
}

function goTo(lon, lat, inc) {
  if (!M) return;
  ring(lon, lat);
  const target = { center: [lon, lat], zoom: 15 };
  M.view.goTo(target, { duration: 700 }).catch(() => {});
  setTimeout(() => {        // some browsers stall the fly-to animation; if the view has not arrived, jump there
    const c = M.view.center;
    if (Math.abs(c.longitude - lon) > 0.0005 || Math.abs(c.latitude - lat) > 0.0005 || M.view.zoom < 14.9) M.view.goTo(target, { animate: false }).catch(() => {});
  }, 1400);
  S.selected = inc; if (inc) showPick({ kind: "incident", id: inc, lon, lat });
  const r = $(".mapbox").getBoundingClientRect();     // on narrow screens the map sits below the alerts: bring it fully into view
  if (r.top < 70 || r.bottom > innerHeight - 10) window.scrollTo({ top: Math.max(0, scrollY + r.top - 80) });
}

function focusAlert(inc, nid) {
  S.tab = "all"; syncTabs(); S.feedSig = ""; renderFeed();
  const el = (nid && $("#n-" + nid)) || [...document.querySelectorAll(".card")].find(c => c.dataset.inc === inc); if (!el) return;
  const feed = $("#feed"); feed.scrollTop += el.getBoundingClientRect().top - feed.getBoundingClientRect().top - 12;
  el.classList.remove("flash"); void el.offsetWidth; el.classList.add("flash");
}

/* ---------------------------------------------------------------- ask the crew */
function md(t) {
  const out = []; let list = false;
  for (const line of esc(t).split("\n")) {
    const b = line.replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/_(.+?)_/g, "<i>$1</i>");
    if (/^\s*[-•]\s+/.test(line)) { if (!list) { out.push("<ul>"); list = true; } out.push("<li>" + b.replace(/^\s*[-•]\s+/, "") + "</li>"); }
    else { if (list) { out.push("</ul>"); list = false; } if (line.trim()) out.push("<p>" + b.replace(/^&gt;\s?/, "") + "</p>"); }
  }
  return out.join("") + (list ? "</ul>" : "");
}

async function ask(text) {
  const box = $("#answer"); box.hidden = false; box.innerHTML = `<p style="color:var(--mut)">${T("The crew is working on it…")}</p>`; box.scrollIntoView({ block: "nearest" });
  try {
    const r = await api("nccc/ask", "POST", { message: text, session_id: "nccc" });
    box.innerHTML = `<button class="x" aria-label="${T("Close answer")}" type="button">×</button><div class="by">${T("Handled by")} ${r.agents.map(a => avatar(a, true)).join(" ")} ${r.agents.map(aName).join(" → ")}</div>${md(r.reply)}` +
      (r.suggestions && r.suggestions.length ? `<div class="chips">${r.suggestions.map(s => `<button type="button">${esc(s)}</button>`).join("")}</div>` : "");
    box.querySelector(".x").onclick = () => box.hidden = true;
    box.querySelectorAll(".chips button").forEach(b => b.onclick = () => ask(b.textContent));
    box.scrollIntoView({ block: "nearest" }); poll();
  } catch (e) { box.innerHTML = `<button class="x" type="button">×</button><p>${esc(e.message)}</p>`; box.querySelector(".x").onclick = () => box.hidden = true; }
}

/* ---------------------------------------------------------------- wiring */
function syncTabs() { $("#t-action").setAttribute("aria-selected", S.tab === "action"); $("#t-all").setAttribute("aria-selected", S.tab === "all"); }
$("#t-action").onclick = () => { S.tab = "action"; syncTabs(); S.state && renderFeed(); };
$("#t-all").onclick = () => { S.tab = "all"; syncTabs(); S.state && renderFeed(); };
$("#ack-all").onclick = async () => { await api("nccc/notifications/ack-all", "POST"); poll(); };
$("#bell").onclick = e => { e.stopPropagation(); const m = $("#bellmenu"); m.hidden = !m.hidden; $("#bell").setAttribute("aria-expanded", !m.hidden); if (!m.hidden) renderBell(); };
document.addEventListener("click", e => { if (!e.target.closest(".bellwrap")) closeBell(); });
document.addEventListener("keydown", e => { if (e.key === "Escape") closeBell(); });
$("#autopilot").onchange = e => setAutopilot(e.target.checked);
$("#scan").onclick = () => runScan(() => api("nccc/scan", "POST"), T("Crew is scanning…"));
$("#sim").onchange = e => { const v = e.target.value; if (v) runScan(() => api("nccc/events/" + v, "POST"), T("Event received - crew is reacting…")); };
$("#ask").onsubmit = e => { e.preventDefault(); const q = $("#q").value.trim(); if (q) { ask(q); $("#q").value = ""; } };
$("#map-mode").onclick = toggleMapMode;
$("#reset").onclick = async () => { if (!confirm(T("Reset the demo to a clean state? All alerts, open incidents and approvals will be cleared; only the closed history stays."))) return; await api("demo/reset", "POST"); S.seen = null; S.mapSig = ""; S.feedSig = ""; S.rosterSig = ""; S.repSig = ""; S.feedAt = {}; M && clearPick(); toast(T("Demo reset.")); poll(); };
document.addEventListener("visibilitychange", () => { if (!document.hidden) poll(); });

initMap(); poll(); S.pollTimer = setInterval(poll, 3500);
