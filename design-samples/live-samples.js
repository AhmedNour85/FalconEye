/* Falcon Eye layout samples, set 2. Everything is drawn with the Operation page's own classes (frontend/nccc.css, mobility.css),
   so only the layout differs from the real page. Made-up data; nothing here calls the app's API. */
const AGENTS = [
  ["faisal", "Faisal", "Executive GeoCoworker", "exec", "#1fb36b"], ["mansour", "Mansour", "Operations GeoCoworker", "ops", "#2d8cff"],
  ["sarah", "Sarah", "Fault & Leak GeoCoworker", "", "#9b6cff"], ["abdullah", "Abdullah", "Asset Health GeoCoworker", "", "#ff8a2b"],
  ["zayed", "Zayed", "Change & Planning GeoCoworker", "", "#ff5a5f"], ["reem", "Reem", "Service Impact GeoCoworker", "", "#22c7b8"],
  ["turki", "Turki", "Field Operations GeoCoworker", "", "#f2b233"], ["maha", "Maha", "Performance GeoCoworker", "", "#4aa3ff"],
  ["nasser", "Nasser", "Traffic GeoCoworker", "", "#e0559a"], ["noura", "Noura", "Mobility Simulation GeoCoworker", "", "#7cc242"],
  ["fahad", "Fahad", "Road Safety & Assets GeoCoworker", "", "#c98a3b"],
].map(([id, name, role, tier, color]) => ({ id, name, role, tier, color }));
const AG = Object.fromEntries(AGENTS.map(a => [a.id, a]));
const WORKING = { noura: "Modelling the King Fahd Road closure", turki: "Matching a crew to WO-0023" };
const ACTIVE = { faisal: "1 min", mansour: "2 min", sarah: "2 min", abdullah: "6 min", zayed: "40 min", reem: "3 min", maha: "1 h", nasser: "9 min", fahad: "9 min" };
const STEPS = ["Detected", "Analysed", "Proposed", "Approved", "Dispatched", "Verified", "Resolved"];

const ALERTS = [
  { id: "NTF-0041", inc: "INC-0034", apr: "APR-0006", sev: "Critical", agent: "sarah", stage: 2, ago: "2 min ago", lon: 46.685, lat: 24.694,
    title: "Water Leak (Suspected) - Olaya", msg: "Pressure on main W-118 dropped 31 % overnight while flow stayed level. Two citizen reports of water on Olaya Street.",
    expected: "work order P1 for the nearest leak team, and a 2-lane closure on Olaya Street from 22:00 to 06:00.",
    trail: [["sarah", "Spotted the pressure drop on W-118"], ["reem", "Found 1 school and 2 clinics within 300 m"], ["nasser", "Modelled the closure: small impact at night"], ["mansour", "Prepared work order P1"]] },
  { id: "NTF-0040", inc: "INC-0049", apr: "APR-0008", sev: "Critical", agent: "abdullah", stage: 2, ago: "6 min ago", lon: 46.735, lat: 24.662,
    title: "Streetlight Failure (Predicted) - Al Malaz", msg: "Twelve lamps on feeder F-07 show the voltage pattern that came before the last three failures.",
    expected: "work order P1 to inspect feeder F-07 before dark.", trail: [["abdullah", "Predicted the failure on feeder F-07"], ["turki", "Prepared work order P1"]] },
  { id: "NTF-0039", inc: "INC-0036", apr: "APR-0010", sev: "High", agent: "noura", stage: 2, ago: "9 min ago", lon: 46.672, lat: 24.722,
    title: "Traffic plan - King Fahd Road closure", msg: "Full closure requested for 20 Nov, 08:00 to 16:00, for a utility crossing. Modelled: 1,340 extra trip-hours with no plan.",
    expected: "strategy B: detour by Olaya Street with timed signals (modelled 420 extra trip-hours).", trail: [["nasser", "Received the closure request"], ["noura", "Compared 5 response strategies"]] },
  { id: "NTF-0038", inc: "INC-0029", apr: "APR-0009", sev: "High", agent: "turki", stage: 3, ago: "12 min ago", lon: 46.641, lat: 24.764,
    title: "Dispatch Khalid Al-Otaibi to INC-0029", msg: "Best match for WO-0023: skill match, 0.3 km away, no open tasks.",
    expected: "Khalid gets the task in ArcGIS Field Maps.", trail: [["turki", "Recommended Khalid Al-Otaibi"]] },
  { id: "NTF-0037", inc: "INC-0033", apr: "APR-0007", sev: "Medium", agent: "sarah", stage: 2, ago: "18 min ago", lon: 46.725, lat: 24.676,
    title: "Water Leak (Suspected) - Al Malaz", msg: "Night flow on DMA-4 rose 14 % for three nights in a row.", expected: "work order P2 for a leak survey this week.", trail: [["sarah", "Flagged the night flow on DMA-4"]] },
  { id: "NTF-0035", inc: "INC-0027", sev: "Medium", agent: "abdullah", stage: 5, ago: "1 h ago", lon: 46.622, lat: 24.684, kind: "verified",
    title: "Repair reported - pole PL-2210, Diplomatic Quarter", msg: "The crew replaced the pole base. Photo and readings are attached; the incident can be closed.", trail: [["maha", "Compared the report with the prediction"]] },
  { id: "NTF-0042", sev: "Info", agent: "faisal", stage: -1, ago: "4 min ago", kind: "brief",
    title: "Executive brief", msg: "8 open incidents, 2 critical, 5 decisions waiting. Busiest area: Olaya.", trail: [["faisal", "Briefed leadership"]] },
];
const ACTIVITY = [["noura", "Modelled the King Fahd Road closure", "3 strategies"], ["turki", "Recommended a crew", "Khalid Al-Otaibi for WO-0023"], ["sarah", "Spotted a pressure drop", "W-118, Olaya"], ["faisal", "Briefed leadership", "5 decisions waiting"]];
const FEEDS = [["Water sensors", "48 sensors · hourly", "1 min ago", "sarah"], ["Streetlights & poles", "183 lamps · telemetry, tilt & corrosion", "1 min ago", "abdullah"], ["Satellite imagery", "change scan on each new pass", "", "zayed"],
  ["Visual distortion (imagery)", "street-level problems and building shape", "", "zayed"], ["Land use / zoning", "construction vs. zoning rules", "", "zayed"], ["Traffic & road reports", "traffic state modelled, 0 road reports", "just now", "nasser"], ["Closures & events", "1 closure request · 0 event notices", "just now", "noura", true]];

const $ = (s, r = document) => r.querySelector(s), $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const avatar = (id, sm) => { const a = AG[id]; return `<span class="av${sm ? " sm" : ""}" style="--ac:${a.color}" title="${esc(a.name)} · ${esc(a.role)}">${a.name[0]}</span>`; };
const S = { state: new URLSearchParams(location.search).get("state") || "normal", tab: "action", open: new Set(), crewOpen: false, detail: "", flow: false };
const waiting = () => ALERTS.filter(a => a.apr && !a.done);
/* "Long names": the longest real-world strings the layout must survive. */
if (S.state === "long") {
  ALERTS[0].title = "Water Leak (Suspected) - Prince Mohammed bin Abdulaziz Road (Tahlia Street) near Al Faisaliah, northern carriageway";
  ALERTS[0].msg += " The pressure logger PL-W-118-NORTH-0007 has reported the same drop on every hourly reading since 01:00, and the nearest valve chamber is under the service road.";
  ALERTS[3].title = "Dispatch Abdulrahman bin Abdulaziz Al-Mutairi Al-Qahtani to INC-0029";
}
/* Set 3 only (S.flow): a decision shows its progress, its result, or what failed. APR-0008 fails once, to show one card failing without touching the rest. */
const FAIL_ONCE = new Set(["APR-0008"]);
const WO = { "APR-0006": "WO-0031", "APR-0008": "WO-0032", "APR-0010": "TP-0004", "APR-0009": "WO-0023", "APR-0007": "WO-0033" };
function announce(t) { let r = $("#live"); if (!r) { r = document.createElement("div"); r.id = "live"; r.className = "sr-only"; r.setAttribute("role", "status"); document.body.append(r); } r.textContent = ""; setTimeout(() => { r.textContent = t; }, 50); }
async function decide(b, act, after) {
  const id = b.dataset.id, n = ALERTS.find(a => a.apr === id), card = b.closest("article") || document;
  card.querySelectorAll(".c-act button").forEach(x => x.disabled = true);
  card.setAttribute("aria-busy", "true"); b.textContent = act === "approve" ? "Approving…" : "Rejecting…";
  await new Promise(r => setTimeout(r, 900));
  card.removeAttribute("aria-busy");
  if (act === "approve" && FAIL_ONCE.has(id)) {
    FAIL_ONCE.delete(id); n.error = `Couldn't approve ${id}: ArcGIS Online refused the change because the layer is busy. Nothing was changed.`;
    after(); announce(n.error); const retry = document.querySelector(`[data-act="retry"][data-id="${id}"]`); if (retry) retry.focus(); return;
  }
  n.error = ""; n.done = act;
  n.result = act === "approve" ? `✓ Approved and done · ${WO[id]} created` : "Rejected · nothing was changed";
  after(); announce(`${id} ${act === "approve" ? "approved. " + WO[id] + " created." : "rejected. Nothing was changed."}`);
  const next = document.querySelector("#go-next") || document.querySelector('[data-act="approve"]:not([disabled])') || document.querySelector("#alerts-h, h2");
  if (next) { if (!next.hasAttribute("tabindex") && next.tagName === "H2") next.tabIndex = -1; next.focus(); }
}
const isViewer = () => S.state === "viewer";

/* Decisions first, then what needs a look, then information. The real page sorts by time only. */
function sorted(list) { const rank = a => a.apr && !a.done ? 0 : a.kind === "verified" ? 1 : a.done ? 3 : 2; return [...list].sort((x, y) => rank(x) - rank(y)); }
function visible() { return sorted(S.tab === "action" ? ALERTS.filter(a => a.apr || a.kind === "verified") : ALERTS); }

function lifeStrip(stage) {
  if (stage < 0) return "";
  return `<ol class="life" aria-label="Progress of this incident">${STEPS.map((s, k) => `<li class="${k < stage ? "ls-done" : k === stage ? "ls-current" : "ls-todo"}"${k === stage ? ' aria-current="step"' : ""}><i></i><span>${s}</span></li>`).join("")}</ol>`;
}
/* The real card, with two changes: the message is clamped to two lines until opened, and a brief is "Info". */
function card(n, compact = true) {
  const ref = [n.inc || n.id, n.title].join(" · "), lab = t => ` aria-label="${esc(t + " · " + ref)}"`;
  let acts = "";
  if (n.done) acts = `<span class="state${n.done === "reject" ? " no" : ""}">${esc(n.result)}</span>`;
  else if (n.error && !isViewer()) acts = `<p class="c-err" role="alert">${esc(n.error)}</p><button class="btn primary" data-act="retry" data-id="${n.apr}"${lab("Try again to approve")}>Try again</button><button class="btn" data-act="reject" data-id="${n.apr}"${lab("Reject")}>Reject</button>`;
  else if (n.apr && !isViewer()) acts = `<button class="btn primary" data-act="approve" data-id="${n.apr}"${lab("Approve")}>Approve</button><button class="btn" data-act="reject" data-id="${n.apr}"${lab("Reject")}>Reject</button>`;
  else if (n.apr) acts = `<span class="state no">Waiting for an operator to decide</span>`;
  else if (n.kind === "verified") acts = `<button class="btn primary" data-act="report"${lab("View report")}>View report</button>`;
  else acts = `<button class="btn" data-act="ack"${lab("Got it")}>Got it</button>`;
  if (n.lon) acts += `<button class="link" data-act="show" data-id="${n.id}"${lab("Show on map")}>Show on map</button>`;
  const open = S.open.has(n.id);
  const trail = n.trail.map(([a, d]) => `<li>${avatar(a, true)}<span><b style="--ac:${AG[a].color}">${esc(AG[a].name)}</b> ${esc(d)}</span></li>`).join("");
  return `<article class="card ${n.sev}${n.apr && !n.done ? " new" : ""}${n.done ? " done" : ""}" id="n-${n.id}" style="--ac:${AG[n.agent].color}">
    <div class="c-top">${avatar(n.agent)}<div class="c-main"><div class="c-title">${esc(n.title)}</div>
      <div class="c-meta"><span class="sev">${n.sev}</span><span>${n.ago}</span>${n.inc ? `<span>${n.inc}</span>` : ""}${n.apr ? `<span>${n.apr}</span>` : ""}</div></div></div>
    ${lifeStrip(n.stage)}
    <p class="c-msg${compact && !open ? " clamp" : ""}">${esc(n.msg)}</p>
    ${n.expected && (open || !compact) ? `<p class="c-meta" style="margin:6px 0 0">If approved: ${esc(n.expected)}</p>` : ""}
    <div class="c-act">${acts}</div>
    <details class="how" data-id="${n.id}"${open ? " open" : ""}><summary${lab("Details and how the crew handled this")}>${n.expected ? "Details and how the crew handled this" : "How the crew handled this"}</summary><ul class="trail">${trail}</ul></details></article>`;
}
function roster() {
  return AGENTS.map(a => `<button class="ag ${a.tier}" style="--ac:${a.color}" data-agent="${a.id}" type="button" aria-expanded="${S.detail === a.id}">${avatar(a.id)}
    <span class="ag-t"><b>${a.name}</b><small>${WORKING[a.id] ? "Working…" : "Active " + ACTIVE[a.id] + " ago"}</small></span></button>`).join("");
}
const activity = (n = 4) => ACTIVITY.slice(0, n).map(([a, act, d]) => `<li><b style="--ac:${AG[a].color}">${AG[a].name}</b> ${esc(act)} · ${esc(d)}</li>`).join("");
const feeds = () => FEEDS.map(([name, d, at, a, alert]) => `<div class="fchip${alert ? " alert" : ""}" style="--ac:${AG[a].color}"><b><i></i>${name}</b><span>${d}</span><small>${at ? "updated " + at : "waiting for data"} · read by ${AG[a].name}</small></div>`).join("");

function kpis() {
  const w = waiting().length;
  return `<button class="kpi hot" type="button" data-kfilter="action" aria-pressed="${S.tab === "action"}" title="Show only what needs a decision"><b>${w}</b><span>Waiting for your decision</span></button>
    <div class="kpi"><b>8</b><span>Open incidents</span></div><div class="kpi crit"><b>2</b><span>Critical</span></div><div class="kpi ok"><b>14</b><span>Resolved</span></div>`;
}

/* The states every layout must handle, chosen from the sample bar. */
function feedState(box) {
  if (S.state === "loading") { box.innerHTML = `<div role="status" aria-busy="true" aria-label="Loading alerts">${'<div class="skel"></div>'.repeat(3)}</div>`; return true; }
  if (S.state === "empty") { box.innerHTML = `<div class="emptystate" role="status"><b>No alerts right now</b><span>The crew is watching the feeds. New findings appear here.</span><button class="btn" type="button" data-act="scan">Scan now</button></div>`; return true; }
  if (S.state === "offline") { box.innerHTML = `<div class="emptystate err" role="alert"><b>Can't reach the server</b><span>Showing nothing rather than old data. Trying again every 5 seconds.</span><button class="btn" type="button" data-act="retry">Try again now</button></div>`; return true; }
  return false;
}
function renderFeed(box) {
  if (feedState(box)) return;
  const list = visible();
  box.innerHTML = (isViewer() ? `<p class="viewer-note" role="note">You are signed in as a viewer: you can follow every alert, but only an operator can approve or reject.</p>` : "") + list.map(n => card(n)).join("");
}

/* Approve and Reject: first press arms, a second within 5 s acts (the real page's rule). */
function wire(root, after) {
  root.addEventListener("click", e => {
    const ag = e.target.closest("[data-agent]");
    if (ag) { S.detail = S.detail === ag.dataset.agent ? "" : ag.dataset.agent; after(); return; }
    const k = e.target.closest("[data-kfilter]"); if (k) { S.tab = S.tab === "action" ? "all" : "action"; after(); return; }
    const b = e.target.closest("[data-act]"); if (!b) return;
    const act = b.dataset.act;
    if (act === "approve" || act === "reject") {
      if (!b.dataset.armed) { b.dataset.armed = "1"; b.dataset.text = b.textContent; b.textContent = "Confirm?"; b._t = setTimeout(() => { delete b.dataset.armed; b.textContent = b.dataset.text; }, 5000); return; }
      clearTimeout(b._t); delete b.dataset.armed; b.textContent = b.dataset.text;
      if (S.flow) return decide(b, act, after);
      return toast(act === "approve" ? `Sample only: ${b.dataset.id} would be approved and carried out.` : `Sample only: ${b.dataset.id} would be rejected. Nothing changes.`);
    }
    if (act === "retry") return decide(b, "approve", after);         /* the person already confirmed; a retry is one press */
    if (act === "show") { const n = ALERTS.find(a => a.id === b.dataset.id); if (n) showOnMap(n); return; }
    toast("Sample only: nothing is changed.");
  });
  root.addEventListener("toggle", e => { const d = e.target; if (d.matches && d.matches("details.how")) { d.open ? S.open.add(d.dataset.id) : S.open.delete(d.dataset.id); const c = d.closest(".card"); const m = c && c.querySelector(".c-msg"); if (m) m.classList.toggle("clamp", !d.open); } }, true);
}
function toast(t) { let box = $(".toasts"); if (!box) { box = document.createElement("div"); box.className = "toasts"; box.setAttribute("aria-live", "polite"); document.body.append(box); }
  const d = document.createElement("div"); d.className = "toast"; d.textContent = t; box.append(d); setTimeout(() => d.remove(), 3500); }

/* The real map: ArcGIS Maps SDK 4.30, the gray basemap, one point per alert. Without internet the box says so. */
let MAP = null;
function initMap(id = "map") {
  const box = document.getElementById(id);
  if (S.state === "offline" || !window.require) { box.innerHTML = `<div class="emptystate map-off" role="status"><b>Map unavailable</b><span>The map needs internet access to js.arcgis.com.</span></div>`; return; }
  require(["esri/Map", "esri/views/MapView", "esri/layers/GraphicsLayer", "esri/Graphic"], (Map, MapView, GraphicsLayer, Graphic) => {
    const layer = new GraphicsLayer();
    const col = { Critical: "#d92d20", High: "#dc6803", Medium: "#f79009", Low: "#1570ef" };
    ALERTS.filter(a => a.lon).forEach(a => layer.add(new Graphic({ geometry: { type: "point", longitude: a.lon, latitude: a.lat },
      symbol: { type: "simple-marker", color: col[a.sev], size: a.sev === "Critical" ? 14 : 11, outline: { color: "#ffffff", width: 2 } }, attributes: { id: a.id } })));
    const view = new MapView({ container: id, map: new Map({ basemap: "gray-vector", layers: [layer] }), center: [46.68, 24.71], zoom: 11, ui: { components: ["zoom"] }, popup: { autoOpenEnabled: false } });
    view.on("click", ev => view.hitTest(ev).then(r => { const g = r.results.find(x => x.graphic && x.graphic.attributes && x.graphic.attributes.id); if (g) focusCard(g.graphic.attributes.id); }));
    MAP = { view };
  });
}
function showOnMap(n) { if (MAP) MAP.view.goTo({ center: [n.lon, n.lat], zoom: 14 }, { duration: 600 }); }
function focusCard(id) { const el = document.getElementById("n-" + id); if (el) { el.scrollIntoView({ block: "nearest", behavior: "smooth" }); el.classList.add("flash"); setTimeout(() => el.classList.remove("flash"), 1500); } }

const HEADER = `<header class="top"><h1 class="sr-only">Falcon Eye</h1>
  <div class="brand"><svg viewBox="0 0 24 24" class="logo" aria-hidden="true"><path d="M2 11C5 6 8.5 4.5 12 4.5S19 6 22 11C19 16 15.5 17.5 12 17.5S5 16 2 11Z"/><circle cx="12" cy="11" r="3.8"/><circle cx="12" cy="11" r="1.5" fill="#1b8354" stroke="none"/><path d="M12 17.5c0 2-.8 3.2-2.6 4.2"/></svg><div><b>Falcon Eye</b></div></div>
  <div class="tools"><label class="switch" title="When on, the AI agents keep watching and raise alerts by themselves"><input type="checkbox" role="switch" checked><span class="track"></span><span class="lbl">AI Agents</span></label>
    <details class="demo"><summary class="btn">Demo tools</summary><div class="demo-pop"><button class="btn" data-act="scan" type="button">Scan now</button><button class="btn" data-act="cmp" type="button">Compare imagery</button>
      <label>Simulate an event<select aria-label="Simulate an event"><option>Water leak</option><option>Road closure</option><option>Major event</option></select></label></div></details>
    <button class="bell" type="button" aria-label="Alerts, 5 unread"><svg viewBox="0 0 24 24"><path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9M10.3 21a1.94 1.94 0 0 0 3.4 0"/></svg><span id="unread">5</span></button>
    <button class="btn lang-toggle" type="button" lang="ar">العربية</button></div></header>`;

function sampleBar(name, onState) {
  const bar = document.createElement("div"); bar.className = "sbar";
  bar.innerHTML = `<b>${name}</b><span>Made-up data; the buttons only show what would happen.</span>
    <label>Preview a state <select id="state">${[["normal", "Normal"], ["loading", "Loading"], ["empty", "No alerts"], ["offline", "Server offline"], ["viewer", "Signed in as viewer"], ["long", "Long names"]].map(([v, t]) => `<option value="${v}"${S.state === v ? " selected" : ""}>${t}</option>`).join("")}</select></label>
    <a href="index.html">Back to the choices</a>`;
  document.body.prepend(bar);
  $("#state").onchange = e => { const u = new URL(location.href); u.searchParams.set("state", e.target.value); location.href = u; };
}
