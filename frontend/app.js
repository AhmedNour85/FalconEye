/* GeoAI Operations Center | Riyadh — single-page client (vanilla JS + ArcGIS Maps SDK for JavaScript 4.30) */
"use strict";
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const icon = n => `<svg class="icon" aria-hidden="true"><use href="#i-${n}"/></svg>`;
const state = { sid: "ui-" + Math.random().toString(36).slice(2, 8), tab: "exec", cfg: null, selInc: null, worker: null, task: null, tools: [], incRows: [], incSort: { key: "urgency", dir: "desc" }, approvals: [] };
const store = { get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }, set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* storage unavailable */ } } };

state.sid = store.get("geoai.sid") || state.sid; store.set("geoai.sid", state.sid);

async function api(path, opts = {}) {
  let r;
  try { r = await fetch(path, opts); } catch (e) { throw new Error("Cannot reach the server. Is it still running?"); }
  let body = null; try { body = await r.json(); } catch (e) { /* not JSON */ }
  if (!r.ok) throw new Error((body && (body.detail || body.error)) || r.statusText || `HTTP ${r.status}`);
  return body;
}
const post = (p, body) => api(p, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) });
const fmtErr = e => (e && e.message) || String(e);

/* ------------------------------------------------------------------ feedback: toasts, dialogs, busy buttons */
const TOAST_ICON = { ok: "check-c", bad: "octagon", warn: "alert", info: "info" };
function toast(msg, kind = "info", ms = 4600) {
  const host = $("#toasts"); while (host.children.length >= 4) host.firstChild.remove();
  const t = document.createElement("div"); t.className = `toast ${kind}`; t.setAttribute("role", kind === "bad" ? "alert" : "status");
  t.innerHTML = `${icon(TOAST_ICON[kind] || "info")}<div class="t-body">${esc(msg)}</div><button type="button" aria-label="Dismiss">${icon("x")}</button>`;
  const close = () => { t.classList.add("leaving"); setTimeout(() => t.remove(), 200); };
  t.querySelector("button").onclick = close; host.appendChild(t); if (ms) setTimeout(close, ms);
}
function confirmDialog({ title, text, ok = "Confirm", danger = false }) {
  const d = $("#confirm"); $("#cf-title").textContent = title; $("#cf-text").textContent = text;
  const b = $("#cf-ok"); b.textContent = ok; b.className = "btn " + (danger ? "bad" : "");
  return new Promise(res => { d.returnValue = ""; d.addEventListener("close", () => res(d.returnValue === "ok"), { once: true }); d.showModal(); });
}
async function busy(btn, fn) {
  if (btn) btn.dataset.loading = "1";
  try { return await fn(); } finally { if (btn) delete btn.dataset.loading; }
}
function md(s) {
  const h = esc(s).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/(^|\s)_(.+?)_(?=\s|$|[.,])/g, "$1<i>$2</i>");
  let out = "", inl = false;
  for (const l of h.split("\n")) {
    const m = l.match(/^\s*(?:-|\d+\.)\s+(.*)$/);
    if (m) { if (!inl) { out += "<ul>"; inl = true; } out += `<li>${m[1]}</li>`; }
    else { if (inl) { out += "</ul>"; inl = false; } out += l ? `<div>${l}</div>` : '<div style="height:6px"></div>'; }
  }
  return out + (inl ? "</ul>" : "");
}
const pill = (t, c) => `<span class="pill ${esc(c || t)}">${esc(t)}</span>`;
const empty = (ic, title, text = "") => `<div class="empty">${icon(ic)}<b>${esc(title)}</b>${text ? `<p>${esc(text)}</p>` : ""}</div>`;
const skeleton = (n = 3, h = 44) => Array.from({ length: n }, () => `<div class="skeleton" style="height:${h}px;margin:8px 0"></div>`).join("");

/* ------------------------------------------------------------------ theme */
const THEMES = { dark: "Dark", light: "Light", nccc: "NCCC" };
const esriCss = () => $("#esri-css");
const isDarkTheme = t => t === "dark";
function applyTheme(t, persist = true) {
  if (t === "nhc") t = "nccc";   // migrate the earlier theme key
  if (!THEMES[t]) t = "nccc";
  document.documentElement.dataset.theme = t; document.body.classList.toggle("calcite-mode-dark", isDarkTheme(t)); document.body.classList.toggle("calcite-mode-light", !isDarkTheme(t));   // explicit: Calcite otherwise follows the OS setting
  if (esriCss()) esriCss().href = `https://js.arcgis.com/4.30/esri/themes/${isDarkTheme(t) ? "dark" : "light"}/main.css`;   // light and NCCC share the light Esri widgets
  $$("#theme-switch [data-theme-set]").forEach(b => b.setAttribute("aria-pressed", b.dataset.themeSet === t));
  if (persist) store.set("geoai.theme", t);
  if (M) M.view.closePopup();  // an open popup would otherwise keep the previous theme's styling
  if (M && !store.get("geoai.basemap")) { state.basemap = null; setBasemap(defaultBasemap(), false); }
}
const currentTheme = () => document.documentElement.dataset.theme || "nccc";
$("#theme-switch").addEventListener("click", e => { const b = e.target.closest("[data-theme-set]"); if (b) { applyTheme(b.dataset.themeSet); toast(`${THEMES[b.dataset.themeSet]} theme`, "info", 1800); } });

/* ------------------------------------------------------------------ overview filters (shared by KPIs, lists and the map) */
const FILTERS = { area: "#f-area", category: "#f-cat", priority: "#f-pri", since: "#f-since" };
const FILTER_LABEL = { area: "Area", category: "Category", priority: "Priority", since: "Since" };
const CAT_LABEL = { water: "Water leaks", lighting: "Streetlights", change: "Urban change" };
state.filters = {};
const readFilters = () => Object.fromEntries(Object.entries(FILTERS).map(([k, s]) => [k, $(s).value]).filter(([, v]) => v));
function filterParams(extra) { const q = new URLSearchParams(extra || {}); for (const [k, v] of Object.entries(state.filters)) q.set(k, v); return q; }
const filtersActive = () => Object.keys(state.filters).length > 0;
function renderFilterNote(k) {
  const f = state.filters, box = $("#f-active"), note = $("#map-filter-note");
  if (!filtersActive()) { box.innerHTML = ""; note.innerHTML = ""; return; }
  const chips = Object.entries(f).map(([key, v]) => `<button type="button" class="chip" data-unfilter="${key}" title="Remove this filter">${FILTER_LABEL[key]}: <b>${esc(key === "category" ? CAT_LABEL[v] || v : v)}</b> ${icon("x")}</button>`).join("");
  const none = k && k.total_incidents === 0 && k.total_detections === 0 && k.candidate_changes_total === 0;
  box.innerHTML = `<span class="muted" style="font-size:var(--fs-sm)">Filtered view${k ? ` · ${k.total_incidents} incident(s), ${k.total_detections} detection(s)` : ""}</span>${chips}<button type="button" class="btn quiet small" data-unfilter="all">Clear all</button>`
    + (none ? `<div class="alert warn" style="flex:1 1 100%">${icon("alert")}<div>No records match these filters. Try widening the area, category, priority or date.</div></div>` : "");
  note.innerHTML = `<div class="alert info" style="margin-bottom:var(--sp-3)">${icon("sliders")}<div style="flex:1">The map follows the Overview filters: ${Object.entries(f).map(([key, v]) => `${FILTER_LABEL[key].toLowerCase()} <b>${esc(key === "category" ? CAT_LABEL[v] || v : v)}</b>`).join(" · ")}. <button type="button" class="link-btn" data-unfilter="all">Clear</button></div></div>`;
}
function setFormFilters(f) { for (const [k, s] of Object.entries(FILTERS)) $(s).value = f[k] || ""; }
function focusArea() {
  if (!M) return;
  M.layers.focus.removeAll();
  if (state.filters.area) { const c = state.cfg.areas[state.filters.area].center; M.view.goTo({ center: c, zoom: 14 }, { duration: 900 }).catch(() => { }); }
  else M.view.goTo({ center: [46.68, 24.70], zoom: 11 }, { duration: 900 }).catch(() => { });
}
let filterTimer = null;
function applyFilters() {
  clearTimeout(filterTimer);
  const prev = state.filters; state.filters = readFilters();
  if (JSON.stringify(prev) === JSON.stringify(state.filters) && execLoaded) return;
  try { sessionStorage.setItem("geoai.filters", JSON.stringify(state.filters)); } catch (e) { /* storage unavailable */ }
  renderFilterNote();
  loadExec();
  if (M) { refreshLayers(); loadBuildings().catch(() => { }); if (prev.area !== state.filters.area) focusArea(); }
}
$("#f-form").addEventListener("change", () => { clearTimeout(filterTimer); filterTimer = setTimeout(applyFilters, 120); });
$("#f-form").onsubmit = e => { e.preventDefault(); applyFilters(); };
$("#f-clear").onclick = () => { setFormFilters({}); applyFilters(); };
document.addEventListener("click", e => {
  const b = e.target.closest("[data-unfilter]"); if (!b) return;
  if (b.dataset.unfilter === "all") setFormFilters({}); else $(FILTERS[b.dataset.unfilter]).value = "";
  applyFilters();
});

/* ------------------------------------------------------------------ lifecycle bar */
function setStages(list) {
  const set = new Set((list || []).filter(Boolean).map(s => s.split("/")[0].toUpperCase()));
  $$(".stage").forEach(el => { if (el.classList.contains("active")) el.classList.add("done"); el.classList.toggle("active", set.has(el.dataset.stage)); });
}

/* ------------------------------------------------------------------ map */
let M = null; // {view, layers, Graphic, map}
const LAYERS = {
  Riyadh_Reference_Buildings: { label: "Real buildings (OSM)", vis: true, color: "#7fa6e0", bbox: true },
  Riyadh_Water_Network: { label: "Water network (synthetic, on real streets)", vis: true, color: "#3ddcff" },
  Riyadh_Reference_Facilities: { label: "Facilities (landmarks approx.)", vis: true, color: "#c9a8ff" },
  Riyadh_Infrastructure_Assets: { label: "Streetlights & sensors (synthetic)", vis: true, color: "#ffd23f", filter: p => p.Asset_Type !== "Water Pipe Segment" },
  Riyadh_Sensor_Readings: { label: "Sensor latest readings", vis: false, color: "#b388ff", q: "?latest=true" },
  Riyadh_Change_Detection: { label: "Change candidates (simulated)", vis: true, color: "#ff9f1c" },
  Riyadh_Extracted_Features: { label: "Extracted features (simulated)", vis: true, color: "#2de2a6" },
  Riyadh_AI_Detections: { label: "AI detections", vis: true, color: "#ff4d4d" },
  Riyadh_Operational_Incidents: { label: "Operational incidents", vis: true, color: "#ff6b6b" },
  Riyadh_Work_Orders: { label: "Work orders", vis: false, color: "#4cc9f0" },
  Riyadh_Field_Verification: { label: "Field verifications", vis: false, color: "#2e8b57" },
  Riyadh_Field_Workers: { label: "Field workers (simulated)", vis: false, color: "#00a3a3" },
};
const SEV = { Critical: "#c0392b", High: "#e67e22", Medium: "#d4ac0d", Low: "#2e8b57" };
function symbolFor(name, p, gtype) {
  const c = LAYERS[name].color;
  if (gtype === "polyline") return { type: "simple-line", color: p.Status === "In Service" ? c : "#e31a1c", width: 2.2 };
  if (name === "Riyadh_Reference_Buildings") return { type: "simple-fill", color: [127, 166, 224, .28], outline: { color: [150, 185, 240, .75], width: .6 } };
  if (gtype === "polygon") return { type: "simple-fill", color: name.includes("Change") ? (p.Significant === "Yes" ? [255, 127, 0, .35] : [150, 150, 150, .25]) : [27, 158, 119, .4], outline: { color: c, width: 1.5 } };
  switch (name) {
    case "Riyadh_Infrastructure_Assets": return p.Asset_Type === "Streetlight" ? { type: "simple-marker", style: "circle", size: 5, color: "#e0b000", outline: { color: "#7a5f00", width: .5 } } : { type: "simple-marker", style: "square", size: 8, color: "#7b4fb3", outline: { color: "#fff", width: 1 } };
    case "Riyadh_AI_Detections": return { type: "simple-marker", style: "diamond", size: 13, color: SEV[p.Severity] || c, outline: { color: "#0b2540", width: 1.5 } };
    case "Riyadh_Operational_Incidents": return { type: "simple-marker", style: "circle", size: 17, color: [0, 0, 0, 0], outline: { color: SEV[p.Severity] || c, width: 3 } };
    case "Riyadh_Work_Orders": return { type: "simple-marker", style: "triangle", size: 12, color: c, outline: { color: "#fff", width: 1 } };
    case "Riyadh_Field_Verification": return { type: "simple-marker", style: "circle", size: 9, color: p.Verification_Status === "Rejected" ? "#c0392b" : c, outline: { color: "#fff", width: 1 } };
    case "Riyadh_Field_Workers": return { type: "simple-marker", style: "cross", size: 12, color: c, outline: { color: c, width: 2 } };
    case "Riyadh_Reference_Facilities": return { type: "simple-marker", style: "square", size: 8, color: c, outline: { color: "#fff", width: 1 } };
    default: return { type: "simple-marker", size: 7, color: c, outline: { color: "#fff", width: 1 } };
  }
}
function geomFor(g) {
  if (g.type === "Point") return { type: "point", longitude: g.coordinates[0], latitude: g.coordinates[1] };
  if (g.type === "LineString") return { type: "polyline", paths: [g.coordinates] };
  return { type: "polygon", rings: g.coordinates };
}
function attrTable(a) { return `<table><tbody>${Object.entries(a).filter(([k, v]) => v !== null && v !== "" && k !== "Evidence").map(([k, v]) => `<tr><td class="muted" style="white-space:nowrap">${esc(k)}</td><td>${esc(v)}</td></tr>`).join("")}</tbody></table>${a.Evidence ? `<p>${esc(a.Evidence)}</p>` : ""}`; }

/* ---- map legend: mirrors symbolFor() so the legend always matches what is drawn ---- */
const SEV_LIST = [["Critical", "#c0392b"], ["High", "#e67e22"], ["Medium", "#d4ac0d"], ["Low", "#2e8b57"]];
const LEGEND = {
  Riyadh_Reference_Buildings: [{ k: "fill", c: "#7fa6e0", t: "Real building (OSM)" }],
  Riyadh_Water_Network: [{ k: "line", c: "#3ddcff", t: "Water pipe (synthetic)" }],
  Riyadh_Reference_Facilities: [{ k: "square", c: "#c9a8ff", t: "Facility / landmark" }],
  Riyadh_Infrastructure_Assets: [{ k: "dot", c: "#ffd23f", t: "Streetlight" }, { k: "square", c: "#b388ff", t: "Pressure / flow sensor" }],
  Riyadh_Sensor_Readings: [{ k: "square", c: "#b388ff", t: "Sensor (latest reading)" }],
  Riyadh_Change_Detection: [{ k: "fill", c: "#ff9f1c", t: "Significant change" }, { k: "fill", c: "#9aa0a6", t: "Minor change" }],
  Riyadh_Extracted_Features: [{ k: "fill", c: "#2de2a6", t: "Extracted feature" }],
  Riyadh_AI_Detections: SEV_LIST.map(([n, c]) => ({ k: "diamond", c, t: n })),
  Riyadh_Operational_Incidents: SEV_LIST.map(([n, c]) => ({ k: "ring", c, t: n })),
  Riyadh_Work_Orders: [{ k: "triangle", c: "#4cc9f0", t: "Work order" }],
  Riyadh_Field_Verification: [{ k: "circle", c: "#2e8b57", t: "Confirmed" }, { k: "circle", c: "#c0392b", t: "Rejected" }],
  Riyadh_Field_Workers: [{ k: "cross", c: "#00a3a3", t: "Field worker" }],
};
function swatch(i) {
  const c = i.c, s = {
    fill: `<rect x="2" y="3" width="12" height="10" rx="2" fill="${c}" fill-opacity=".45" stroke="${c}" stroke-width="1.4"/>`,
    line: `<path d="M1 12 L6 5 L11 10 L15 3" fill="none" stroke="${c}" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>`,
    square: `<rect x="3" y="3" width="10" height="10" fill="${c}" stroke="#ffffff" stroke-width="1.2"/>`,
    dot: `<circle cx="8" cy="8" r="3.4" fill="${c}" stroke="#7a5f00" stroke-width=".8"/>`,
    circle: `<circle cx="8" cy="8" r="5" fill="${c}" stroke="#ffffff" stroke-width="1.2"/>`,
    diamond: `<path d="M8 1.5 L14.5 8 L8 14.5 L1.5 8 Z" fill="${c}" stroke="#0b2540" stroke-width="1.2"/>`,
    ring: `<circle cx="8" cy="8" r="5.6" fill="none" stroke="${c}" stroke-width="2.6"/>`,
    triangle: `<path d="M8 2 L14.5 13.5 L1.5 13.5 Z" fill="${c}" stroke="#ffffff" stroke-width="1.2"/>`,
    cross: `<path d="M8 2 V14 M2 8 H14" stroke="${c}" stroke-width="2.6" stroke-linecap="round"/>`,
  }[i.k];
  return `<svg class="lg-sw" width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">${s}</svg>`;
}
const legendOpenDefault = () => { const v = store.get("geoai.legend"); return v ? v === "open" : window.innerWidth > 720; };
function buildLegendWidget() {
  const el = document.createElement("section"); el.className = "maplegend"; el.setAttribute("aria-label", "Map legend"); el.id = "maplegend";
  el.addEventListener("click", e => { if (e.target.closest(".lg-head")) { const open = !el.classList.contains("open"); el.classList.toggle("open", open); store.set("geoai.legend", open ? "open" : "closed"); $(".lg-head", el).setAttribute("aria-expanded", open); } });
  el.classList.toggle("open", legendOpenDefault());
  return el;
}
function renderLegend() {
  const el = $("#maplegend"); if (!el || !M) return;
  const open = el.classList.contains("open");
  const rows = Object.entries(LAYERS).filter(([n]) => M.layers[n] && M.layers[n].visible).map(([n, cfg]) => {
    const count = M.layers[n].graphics.length, hint = cfg.bbox && M.view.zoom < 15 ? "zoom in" : count;
    const items = (LEGEND[n] || []).map(i => `<li>${swatch(i)}<span>${esc(i.t)}</span></li>`).join("");
    return `<div class="lg-layer"><div class="lg-title"><span>${esc(cfg.label.replace(/ \(.*\)$/, ""))}</span><span class="lg-count num">${hint}</span></div><ul class="${(LEGEND[n] || []).length > 2 ? "lg-grid" : ""}">${items}</ul></div>`;
  }).join("");
  const filt = filtersActive() ? `<div class="lg-note">${icon("sliders")}<span>Filtered by Overview filters</span></div>` : "";
  el.innerHTML = `<button type="button" class="lg-head" aria-expanded="${open}">${icon("layers")}<span>Legend</span><span class="lg-chev">${icon("chev")}</span></button><div class="lg-body">${filt}${rows || '<div class="lg-empty">No layers are visible. Turn some on in the Layers panel.</div>'}<div class="lg-foot">Operational layers are synthetic or simulated.</div></div>`;
}

/* ---- basemaps: every id below was verified to load without an API key ---- */
const BASEMAPS = [
  ["Dark", [["streets-night-vector", "Esri Streets Night"], ["dark-gray-vector", "Esri Dark Gray"]]],
  ["Streets", [["streets-vector", "Esri Streets"], ["streets-navigation-vector", "Esri Navigation"], ["streets-relief-vector", "Esri Streets Relief"], ["osm", "OpenStreetMap"]]],
  ["Light / topographic", [["gray-vector", "Esri Light Gray"], ["topo-vector", "Esri Topographic"], ["terrain", "Esri Terrain"]]],
  ["Imagery", [["satellite", "Esri World Imagery"], ["hybrid", "Esri Imagery Hybrid"]]],
];
const KEY_BASEMAPS = ["Needs ARCGIS_JS_API_KEY", [["arcgis/navigation-night", "Navigation Night"], ["arcgis/imagery/standard", "Imagery Standard"], ["arcgis/outdoor", "Outdoor"],
  ["arcgis/nova", "Nova"], ["arcgis/charted-territory", "Charted Territory"], ["arcgis/community", "Community"]]];
const basemapOptions = () => ((state.cfg && state.cfg.arcgis_api_key) ? [...BASEMAPS, KEY_BASEMAPS] : BASEMAPS)
  .map(([g, items]) => `<optgroup label="${g}">${items.map(([v, l]) => `<option value="${v}">${esc(l)}</option>`).join("")}</optgroup>`).join("");
const defaultBasemap = () => isDarkTheme(currentTheme()) ? "dark-gray-vector" : "gray-vector";
const savedBasemap = () => store.get("geoai.basemap") || defaultBasemap();
async function setBasemap(id, remember = true) {
  if (!M) return;
  const prev = state.basemap || savedBasemap();
  try { M.map.basemap = id; await M.map.basemap.load(); state.basemap = id; if (remember) store.set("geoai.basemap", id); }
  catch (err) { M.map.basemap = prev; toast("That basemap is not available (it may need an ArcGIS API key).", "warn"); }
  $$("select.bmsel").forEach(s => { s.value = state.basemap || prev; });
}

/* ---- feature popups ---- */
const ID_FIELD = {
  Riyadh_Water_Network: "Pipeline_ID", Riyadh_Infrastructure_Assets: "Asset_ID", Riyadh_Sensor_Readings: "Sensor_ID", Riyadh_AI_Detections: "Detection_ID",
  Riyadh_Change_Detection: "Change_ID", Riyadh_Extracted_Features: "Feature_ID", Riyadh_Operational_Incidents: "Incident_ID", Riyadh_Work_Orders: "Work_Order_ID",
  Riyadh_Field_Verification: "Verification_ID", Riyadh_Field_Workers: "Worker_ID", Riyadh_Reference_Facilities: "Facility_ID", Riyadh_Reference_Buildings: "Building_ID"
};
function dataBadge(dc) {
  const [txt, cls] = !dc ? ["", ""] : dc.startsWith("OSM") ? ["Real · OpenStreetMap", "ok"] : dc.startsWith("SYNTHETIC") ? ["Synthetic demo data", "warn"] :
    dc.startsWith("SIMULATED") ? ["Simulated processing", "violet"] : dc.startsWith("REFERENCE") ? ["Approximate reference", ""] : ["Demo operational", "info"];
  return txt ? `<span class="badge ${cls}" style="margin-bottom:6px">${txt}</span>` : "";
}
function popupFor(name, p) {
  const id = p[ID_FIELD[name]] ?? "";
  return {
    title: `${LAYERS[name].label.replace(/ \(.*\)$/, "")} · ${id}`, outFields: ["*"],
    content: () => {
      const el = document.createElement("div"); el.className = "gpop";
      const rest = Object.fromEntries(Object.entries(p).filter(([k]) => k !== "Data_Classification" && k !== "Evidence"));
      el.innerHTML = dataBadge(p.Data_Classification) + attrTable(rest);
      if (p.Evidence) el.insertAdjacentHTML("beforeend", `<p style="margin:6px 0 0"><b>Why:</b> ${esc(p.Evidence)}</p>`);
      const inc = p.Incident_ID && /^INC-/.test(p.Incident_ID) ? p.Incident_ID : "";
      if (inc) { const b = document.createElement("button"); b.className = "btn small"; b.style.marginTop = "8px"; b.textContent = `Open ${inc} in Command Center`; b.onclick = () => { switchTab("cmd"); selectIncident(inc, false); }; el.appendChild(b); }
      return el;
    },
  };
}
function highlight(g) {
  if (!M || !g || !g.geometry) return;
  M.layers.focus.removeAll();
  const t = g.geometry.type;
  const sym = t === "point" ? { type: "simple-marker", style: "circle", size: 30, color: [76, 201, 240, .15], outline: { color: "#4cc9f0", width: 2.5 } }
    : t === "polyline" ? { type: "simple-line", color: [76, 201, 240, .9], width: 6 } : { type: "simple-fill", color: [76, 201, 240, .18], outline: { color: "#4cc9f0", width: 3 } };
  M.layers.focus.add(new M.Graphic({ geometry: g.geometry, symbol: sym }));
}

let bTimer = null;
const initMap = () => new Promise(resolve => {
  if (typeof require === "undefined") { resolve(null); return; }
  require(["esri/Map", "esri/views/MapView", "esri/layers/GraphicsLayer", "esri/Graphic", "esri/config"], (Map, MapView, GraphicsLayer, Graphic, esriConfig) => {
    const key = state.cfg && state.cfg.arcgis_api_key; if (key) esriConfig.apiKey = key;
    const layers = {};
    state.basemap = savedBasemap();
    const map = new Map({ basemap: state.basemap });
    for (const n of Object.keys(LAYERS)) { layers[n] = new GraphicsLayer({ title: LAYERS[n].label, visible: LAYERS[n].vis }); map.add(layers[n]); }
    layers.focus = new GraphicsLayer(); map.add(layers.focus);
    const view = new MapView({ container: "mapview", map, center: [46.68, 24.70], zoom: 11, popup: { dockEnabled: false, collapseEnabled: false, alignment: "auto", autoOpenEnabled: true, visibleElements: { featureNavigation: true } } });
    const ctl = document.createElement("div"); ctl.className = "bmctl";
    ctl.innerHTML = `<select class="bmsel" title="Basemap" aria-label="Basemap">${basemapOptions()}</select>`;
    view.ui.add(buildLegendWidget(), "bottom-left");
    view.ui.add(ctl, "top-right"); const sel = ctl.querySelector("select"); sel.value = state.basemap; sel.onchange = e => setBasemap(e.target.value);
    view.on("click", async ev => {
      const hit = await view.hitTest(ev); const g = hit.results.find(r => r.graphic && r.graphic.attributes && r.graphic.attributes._layer);
      if (!g) return; const a = g.graphic.attributes; highlight(g.graphic);
      $("#inspector").classList.remove("muted");
      $("#inspector").innerHTML = `<div class="section-title" style="margin-top:0">${esc(a._layer.replace("Riyadh_", "").replace(/_/g, " "))}</div>` + dataBadge(a.Data_Classification) + attrTable(Object.fromEntries(Object.entries(a).filter(([k]) => k !== "_layer" && k !== "Data_Classification")));
      if (a.Incident_ID && a.Incident_ID.startsWith("INC")) selectIncident(a.Incident_ID, false);
    });
    view.watch("stationary", s => { if (s) { clearTimeout(bTimer); bTimer = setTimeout(() => loadBuildings().then(renderLegend).catch(() => { }), 250); } });
    resolve({ view, layers, Graphic, map });
  }, err => { console.warn("ArcGIS SDK failed", err); resolve(null); });
});

async function loadLayer(name) {
  if (!M) return; const cfg = LAYERS[name];
  const gj = await api(`/api/layers/${name}?${filterParams(new URLSearchParams(cfg.q ? cfg.q.slice(1) : ""))}`);
  const lyr = M.layers[name]; lyr.removeAll();
  const gs = [];
  for (const f of gj.features) {
    if (!f.geometry || (cfg.filter && !cfg.filter(f.properties))) continue;
    const gt = f.geometry.type === "Point" ? "point" : f.geometry.type === "LineString" ? "polyline" : "polygon";
    gs.push(new M.Graphic({ geometry: geomFor(f.geometry), symbol: symbolFor(name, f.properties, gt), attributes: { ...f.properties, _layer: name }, popupTemplate: popupFor(name, f.properties) }));
  }
  lyr.addMany(gs);
}
async function loadBuildings() {
  if (!M || !M.layers.Riyadh_Reference_Buildings.visible || M.view.zoom < 15) { if (M) M.layers.Riyadh_Reference_Buildings.removeAll(); return; }
  const e = M.view.extent.clone().expand(1.1);
  const ll = await new Promise(r => require(["esri/geometry/support/webMercatorUtils"], u => r(u.webMercatorToGeographic(e))));
  const gj = await api(`/api/layers/Riyadh_Reference_Buildings?${filterParams({ bbox: `${ll.xmin},${ll.ymin},${ll.xmax},${ll.ymax}` })}`);
  const lyr = M.layers.Riyadh_Reference_Buildings; lyr.removeAll();
  lyr.addMany(gj.features.filter(f => f.geometry).map(f => new M.Graphic({ geometry: geomFor(f.geometry), symbol: symbolFor("Riyadh_Reference_Buildings", f.properties, "polygon"), attributes: { ...f.properties, _layer: "Riyadh_Reference_Buildings" }, popupTemplate: popupFor("Riyadh_Reference_Buildings", f.properties) })));
}
const refreshLayers = async only => { if (!M) return; await Promise.all((only || Object.keys(LAYERS).filter(n => !LAYERS[n].bbox)).map(n => loadLayer(n).catch(e => console.warn(n, e)))); renderLegend(); };
function zoomTo(lon, lat, zoom, label) {
  if (!M || lon == null) return;
  M.view.goTo({ center: [lon, lat], zoom: zoom || 16 }, { duration: 900 }).catch(() => { });
  M.layers.focus.removeAll();
  M.layers.focus.add(new M.Graphic({ geometry: { type: "point", longitude: lon, latitude: lat }, symbol: { type: "simple-marker", style: "circle", size: 34, color: [76, 201, 240, .15], outline: { color: "#4cc9f0", width: 2 } } }));
  if (label) M.layers.focus.add(new M.Graphic({ geometry: { type: "point", longitude: lon, latitude: lat }, symbol: { type: "text", text: label, color: "#ffffff", haloColor: "#0b2540", haloSize: 2, yoffset: 26, font: { size: 11, weight: "bold" } } }));
}
function placeMap(tab) {
  const box = $("#mapbox"), slot = $(`.mapslot[data-for="${tab}"]`);
  if (slot) { slot.appendChild(box); box.classList.add("shown"); } else { box.classList.remove("shown"); document.body.appendChild(box); }
}

/* ------------------------------------------------------------------ overview */
const KPI_GROUPS = [
  ["Operational picture", [
    ["open_incidents", "Open incidents", "octagon", "info", "hero"], ["critical_incidents", "Critical incidents", "alert", "crit", "hero"], ["suspected_water_leaks", "Suspected water leaks", "drop", "warn"],
    ["predicted_streetlight_failures", "Predicted streetlight failures", "bulb", "warn"], ["detected_urban_changes", "Significant urban changes", "build", "info"],
    ["total_detected_anomalies", "Detected anomalies", "pulse", "info"], ["_areas", "High-risk areas", "target", "crit"]]],
  ["Workflow & outcomes", [
    ["open_work_orders", "Open work orders", "clip", "info"], ["outstanding_field_assignments", "Outstanding field assignments", "users", "info"],
    ["verified_incidents", "Verified incidents", "check-c", "ok"], ["resolved_incidents", "Resolved incidents", "shield", "ok"], ["avg_response_time_hours", "Avg response time", "clock", "info", "", "h"],
    ["verification_rate_pct", "Verification rate", "percent", "ok", "", "%"], ["incident_resolution_rate_pct", "Resolution rate", "percent", "ok", "", "%"]]],
];
const execQuery = () => filterParams().toString();
let execLoaded = false;
async function loadExec() {
  if (!execLoaded) { $("#kpis").innerHTML = `<div class="kpis">${Array.from({ length: 8 }, () => '<div class="skeleton" style="height:96px;border-radius:14px"></div>').join("")}</div>`; $("#recs").innerHTML = skeleton(3); $("#hotspots").innerHTML = skeleton(3); }
  let r; try { r = await api("/api/executive?" + execQuery()); } catch (e) { $("#kpis").innerHTML = `<div class="alert warn">${icon("alert")}<div>Could not load the overview: ${esc(fmtErr(e))}</div></div>`; return; }
  if (!r.ok) { toast(r.error, "bad"); return; }
  execLoaded = true;
  const d = r.result, k = d.kpis; renderFilterNote(k);
  $("#kpis").innerHTML = KPI_GROUPS.map(([title, items]) => `<div class="kpi-section"><div class="kpi-label">${title}</div><div class="kpis">${items.map(([key, label, ic, tone, size, unit]) => {
    const raw = key === "_areas" ? (k.high_risk_areas.join(", ") || "None") : k[key];
    const val = raw === null || raw === undefined ? '<span class="muted">n/a</span>' : esc(raw) + (unit ? `<span class="k-unit">${unit}</span>` : "");
    return `<div class="kpi ${tone} ${size || ""}"><div class="k-top"><span>${label}</span><span class="k-ico">${icon(ic)}</span></div><b class="${key === "_areas" ? "small" : ""}">${val}</b></div>`;
  }).join("")}</div></div>`).join("");
  $("#recs").innerHTML = d.recommendations.length ? d.recommendations.map(x => `<button class="item" type="button" data-inc="${esc(x.incident_id)}"><div class="row1"><span class="rank">${x.rank}</span><span class="id">${esc(x.incident_id)}</span>${pill(x.priority)}<span class="muted">${esc(x.area)}</span></div>
      <div style="margin-top:6px">${esc(x.recommended_action)}</div><div class="sub">${esc(x.evidence.join(" · "))}</div></button>`).join("") : empty("check-c", "No open incidents", "Run a detection from AI Operations Agents or the guided demo.");
  $("#hotspots").innerHTML = d.hotspots.length ? d.hotspots.map(h => `<button class="item" type="button" data-zoom="${h.lon},${h.lat}"><div class="row1"><b>${esc(h.area)}</b><span class="spacer"></span><span class="num muted">score ${h.score}</span></div>
      <div class="sub">${h.open_incidents} open · ${Object.entries(h.categories).map(([c, n]) => `${esc(c)} ${n}`).join(", ")}</div><div class="meter" role="img" aria-label="Risk score ${h.score} of 100"><i style="width:${Math.min(100, h.score)}%"></i></div></button>`).join("") : empty("target", "No hotspots", "Nothing is currently elevated.");
  $("#ranked").innerHTML = d.ranked_incidents.length ? `<div class="tablewrap"><table class="stack-sm"><thead><tr><th>#</th><th>Incident</th><th>Type</th><th>Priority</th><th class="num">Risk</th><th>Area</th><th>Status</th></tr></thead><tbody>${d.ranked_incidents.map(x => `<tr class="row" tabindex="0" role="button" data-inc="${esc(x.incident_id)}"><td data-label="Rank">${x.rank}</td><td data-label="Incident"><span class="id">${esc(x.incident_id)}</span></td><td data-label="Type">${esc(x.type)}</td><td data-label="Priority">${pill(x.priority)}</td><td class="num" data-label="Risk">${x.risk_score}</td><td data-label="Area">${esc(x.area)}</td><td data-label="Status"><span class="pill st">${esc(x.status)}</span></td></tr>`).join("")}</tbody></table></div>` : empty("inbox", "No open incidents to rank");
  $("#page-sub").textContent = PAGES.exec.sub + " · updated " + new Date().toLocaleTimeString();
}
document.addEventListener("click", e => {
  const inc = e.target.closest("[data-inc]"); if (inc) { selectIncident(inc.dataset.inc, true); return; }
  const z = e.target.closest("[data-zoom]"); if (z) { const [lo, la] = z.dataset.zoom.split(",").map(Number); zoomTo(lo, la, 14); }
});
document.addEventListener("keydown", e => { const r = e.target.closest && e.target.closest("tr.row"); if (r && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); r.click(); } });

/* ------------------------------------------------------------------ approvals */
function renderApprovals(list) {
  state.approvals = list;
  const html = list.length ? list.map(a => `<div class="approval"><div class="a-head">${icon("shield")}<span>Needs your approval · <span class="id">${esc(a.Approval_ID)}</span></span></div><div class="a-sum">${esc(a.Summary)}</div>
    <dl class="kv"><dt>Target</dt><dd>${esc(a.Target)}</dd><dt>Location</dt><dd>${esc(a.Location || "n/a")}</dd><dt>Priority</dt><dd>${esc(a.Priority || "n/a")}</dd><dt>Team</dt><dd>${esc(a.Team || "n/a")}</dd><dt>Expected</dt><dd>${esc(a.Expected_Result)}</dd></dl>
    <div class="btnrow"><button class="btn small ok" type="button" data-approve="${esc(a.Approval_ID)}">${icon("check")}Approve</button><button class="btn small bad-quiet" type="button" data-reject="${esc(a.Approval_ID)}">${icon("x")}Reject</button></div></div>`).join("")
    : empty("shield", "Nothing waiting", "Actions that change records appear here for approval before anything is executed.");
  $$("[data-approvals]").forEach(el => el.innerHTML = html);
  const n = $("#nav-approvals"); n.textContent = list.length; n.classList.toggle("hidden", !list.length);
}
async function loadApprovals() { try { renderApprovals(await api("/api/approvals?pending=true")); } catch (e) { /* transient */ } }
document.addEventListener("click", async e => {
  const ap = e.target.closest("[data-approve]"), rj = e.target.closest("[data-reject]");
  if (!ap && !rj) return;
  const btn = ap || rj, id = btn.dataset.approve || btn.dataset.reject;
  await busy(btn, async () => {
    try {
      const r = await post(`/api/approvals/${id}/${ap ? "approve" : "reject"}`);
      toast(ap ? `Executed ${id}: ${r.work_order_id || r.incident_id || r.worker || r.status}` + (r.warning ? ` — ${r.warning}` : "") : `Rejected ${id}`, ap ? "ok" : "info");
      setStages(["ACT"]); await afterAction();
    } catch (err) { toast("Could not complete that: " + fmtErr(err), "bad"); await loadApprovals(); }
  });
});
async function afterAction() { await Promise.all([loadApprovals(), refreshLayers(["Riyadh_Operational_Incidents", "Riyadh_Work_Orders", "Riyadh_Field_Workers", "Riyadh_AI_Detections", "Riyadh_Field_Verification", "Riyadh_Change_Detection", "Riyadh_Extracted_Features", "Riyadh_Water_Network"]), refreshActive()]); }
async function refreshActive() {
  const t = state.tab;
  try {
    if (t === "exec") await loadExec();
    if (t === "cmd") { await Promise.all([loadIncidents(), loadAudit(), loadSim()]); if (state.selInc) selectIncident(state.selInc, false); }
    if (t === "intel") await loadIntel();
    if (t === "field") await loadTasks();
  } catch (e) { toast(fmtErr(e), "bad"); }
}

/* ------------------------------------------------------------------ copilot */
function addMsg(who, html) {
  const d = document.createElement("div"); d.className = "msg " + who;
  d.innerHTML = `<div class="avatar" aria-hidden="true">${who === "a" ? icon("spark") : icon("users")}</div><div class="bubble">${html}</div>`;
  $("#chat").appendChild(d); $("#chat").scrollTop = $("#chat").scrollHeight; return d.querySelector(".bubble");
}
let chatBusy = false;
const CHAT_KEY = "geoai.chat";
function saveChat() {
  try {
    const msgs = $$("#chat .msg").filter(m => !m.querySelector(".typing")).slice(-80)
      .map(m => ({ who: m.classList.contains("u") ? "u" : "a", html: m.querySelector(".bubble").innerHTML.slice(0, 30000) }));
    if (!msgs.length) { localStorage.removeItem(CHAT_KEY); return; }
    localStorage.setItem(CHAT_KEY, JSON.stringify({ sid: state.sid, msgs, trace: $("#trace").innerHTML, traceEmpty: $("#trace").classList.contains("muted"), ctx: $("#ctxchips").innerHTML, suggest: $("#suggest").innerHTML, mode: $("#chatmode").textContent }));
  } catch (e) { /* storage full or unavailable: the chat simply will not persist */ }
}
function restoreChat() {
  try {
    const d = JSON.parse(localStorage.getItem(CHAT_KEY) || "null");
    if (!d || d.sid !== state.sid || !d.msgs || !d.msgs.length) return;
    d.msgs.forEach(m => addMsg(m.who, m.html));
    if (d.trace) { $("#trace").innerHTML = d.trace; $("#trace").classList.toggle("muted", !!d.traceEmpty); }
    $("#ctxchips").innerHTML = d.ctx || ""; if (d.suggest) $("#suggest").innerHTML = d.suggest; if (d.mode) $("#chatmode").textContent = d.mode;
  } catch (e) { /* unreadable saved chat: start fresh */ }
}
window.addEventListener("pagehide", saveChat); document.addEventListener("visibilitychange", () => { if (document.visibilityState === "hidden") saveChat(); });
async function newChat() {
  if ($$("#chat .msg").length > 1 && !(await confirmDialog({ title: "Start a new chat?", text: "The current conversation and the agent's working context (focus incident, last detections) are cleared. Incidents, work orders and approvals already in the system are not affected.", ok: "New chat" }))) return;
  state.sid = "ui-" + Math.random().toString(36).slice(2, 8); store.set("geoai.sid", state.sid); try { localStorage.removeItem(CHAT_KEY); } catch (e) { /* ignore */ }
  $("#chat").innerHTML = ""; $("#ctxchips").innerHTML = ""; $("#suggest").innerHTML = ""; $("#trace").className = "trace muted"; $("#trace").textContent = "No tools run yet."; welcome(); toast("New chat started", "info", 2200);
}
async function send(text) {
  text = (text || "").trim(); if (!text || chatBusy) return; chatBusy = true;
  addMsg("u", esc(text)); saveChat(); $("#chatin").value = ""; $("#chatin").disabled = true;
  const wait = addMsg("a", '<span class="typing" aria-label="Agent is working"><i></i><i></i><i></i></span>');
  try {
    const r = await post("/api/chat", { message: text, session_id: state.sid });
    wait.innerHTML = md(r.reply);
    $("#chatmode").textContent = r.mode === "claude" ? "Claude API" : r.mode === "rules" ? "Offline planner" : r.mode;
    $("#trace").classList.remove("muted");
    $("#trace").innerHTML = r.trace.length ? r.trace.map(t => `<div class="${t.ok ? "" : "bad"}"><div class="t-head"><span class="badge info">${esc(t.stage || "")}</span><span class="id">${esc(t.tool)}</span>${t.duration_ms != null ? `<span class="muted num">${t.duration_ms} ms</span>` : ""}</div><code>${esc(JSON.stringify(t.input))} → ${esc(t.summary)}</code></div>`).join("") : '<span class="muted">No tools were needed for this turn.</span>';
    setStages(r.trace.map(t => t.stage));
    $("#ctxchips").innerHTML = Object.entries(r.context).map(([k, v]) => `<span class="chip ctx">${esc(k.replace("focus_", ""))}: ${esc(v)}</span>`).join("");
    $("#suggest").innerHTML = r.suggestions.map(s => `<button type="button" class="chip" data-say="${esc(s)}">${esc(s)}</button>`).join("");
    renderApprovals(r.pending_approvals); await refreshLayers();
    const f = r.context.focus_incident; if (f) focusIncident(f);
  } catch (e) { wait.innerHTML = `<span style="color:var(--bad)">${icon("alert")} ${esc(fmtErr(e))}</span>`; }
  finally { saveChat(); chatBusy = false; $("#chatin").disabled = false; if (state.tab === "copilot") $("#chatin").focus(); }
}
async function focusIncident(id) { try { const r = await api("/api/layers/Riyadh_Operational_Incidents/" + id); zoomTo(r.geom.coordinates[0], r.geom.coordinates[1], 15, id); } catch (e) { /* ignore */ } }
document.addEventListener("click", e => { const c = e.target.closest("[data-say]"); if (c) { switchTab("copilot"); send(c.dataset.say); } });
document.addEventListener("click", e => { if (e.target.closest("#chat-new")) newChat(); });
$("#chatform").onsubmit = e => { e.preventDefault(); send($("#chatin").value); };
function welcome() {
  if ($("#chat").children.length) return;
  addMsg("a", md("Hello — I'm the **GeoAI Operations Agent**. One conversation covers sensing, imagery, analysis, decisions, work orders, field verification and learning. Anything that changes records needs your approval.\n\n_Start here:_ inject the Olaya leak in **Command Center → Simulation engine** (or run Guided Demo scene 1), then ask me to **detect possible water leaks in Riyadh**."));
  $("#suggest").innerHTML = ["Detect possible water leaks in Riyadh", "Identify streetlights with a high probability of failure on King Fahd Road", "Compare imagery epochs in Olaya District", "Identify the highest-risk geographic areas"].map(s => `<button type="button" class="chip" data-say="${esc(s)}">${esc(s)}</button>`).join("");
}

/* ------------------------------------------------------------------ command center */
const INC_COLS = [["incident_id", "Incident"], ["type", "Type"], ["priority", "Priority"], ["risk_score", "Risk", "num"], ["area", "Area"], ["status", "Status"], ["team", "Team"]];
async function loadIncidents() {
  if (!state.incRows.length) $("#inc-table").innerHTML = skeleton(4, 40);
  const q = new URLSearchParams(); if ($("#c-open").checked) q.set("open_only", "true"); if ($("#c-cat").value) q.set("category", $("#c-cat").value); if ($("#c-pri").value) q.set("priority", $("#c-pri").value);
  const r = (await api("/api/incidents?" + q)).result; state.incRows = r.incidents; renderIncidents();
}
function renderIncidents() {
  const term = ($("#c-q").value || "").toLowerCase().trim(), { key, dir } = state.incSort;
  let rows = state.incRows.filter(x => !term || [x.incident_id, x.type, x.area, x.team, x.status, x.priority].join(" ").toLowerCase().includes(term));
  rows = [...rows].sort((a, b) => { const x = a[key], y = b[key]; const c = typeof x === "number" ? x - y : String(x).localeCompare(String(y)); return dir === "asc" ? c : -c; });
  if (!rows.length) { $("#inc-table").innerHTML = empty("inbox", state.incRows.length ? "No incidents match your filters" : "No incidents yet", state.incRows.length ? "Try clearing the search or filters." : "Create incidents from detections, or run the guided demo."); return; }
  $("#inc-table").innerHTML = `<div class="tablewrap"><table class="stack-sm"><thead><tr>${INC_COLS.map(([k, l, c]) => `<th class="${c || ""}" data-sort="${k}" ${state.incSort.key === k ? `aria-sort="${dir === "asc" ? "ascending" : "descending"}"` : ""}>${l}</th>`).join("")}</tr></thead>
    <tbody>${rows.map(x => `<tr class="row ${x.incident_id === state.selInc ? "sel" : ""}" tabindex="0" role="button" data-inc="${esc(x.incident_id)}"><td data-label="Incident"><span class="id">${esc(x.incident_id)}</span></td><td data-label="Type">${esc(x.type)}</td><td data-label="Priority">${pill(x.priority)}</td><td class="num" data-label="Risk">${x.risk_score}</td><td data-label="Area">${esc(x.area)}</td><td data-label="Status"><span class="pill st">${esc(x.status)}</span></td><td data-label="Team">${esc(x.team || "–")}</td></tr>`).join("")}</tbody></table></div>
    <div class="muted" style="font-size:var(--fs-xs);margin-top:8px">${rows.length} of ${state.incRows.length} incident(s)</div>`;
}
$("#inc-table").addEventListener("click", e => { const th = e.target.closest("th[data-sort]"); if (!th) return; const k = th.dataset.sort; state.incSort = { key: k, dir: state.incSort.key === k && state.incSort.dir === "desc" ? "asc" : "desc" }; renderIncidents(); });
$("#c-q").oninput = renderIncidents; ["#c-cat", "#c-pri", "#c-open"].forEach(s => $(s).onchange = () => loadIncidents().catch(e => toast(fmtErr(e), "bad")));

async function selectIncident(id, zoom) {
  state.selInc = id;
  if (state.tab === "cmd") renderIncidents();
  try {
    const r = (await api("/api/incidents/" + id)).result, i = r.incident;
    if (zoom) {
      zoomTo(r.location.lon, r.location.lat, 16, id);
      const g = M && M.layers.Riyadh_Operational_Incidents.graphics.find(x => x.attributes.Incident_ID === id);
      if (g) setTimeout(() => M.view.openPopup({ features: [g], location: g.geometry }), 950);
    }
    const wo = r.work_orders.filter(w => !["Completed", "Cancelled"].includes(w.Status)).slice(-1)[0];
    const box = $("#inc-detail"); box.classList.remove("muted");
    box.innerHTML = `<div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap"><span class="id" style="font-size:var(--fs-lg)">${esc(i.Incident_ID)}</span>${pill(i.Priority)}${pill(i.Severity)}<span class="pill st">${esc(i.Status)}</span></div>
      <p style="margin:8px 0 6px">${esc(i.Description)}</p>
      <dl class="kv"><dt>Risk</dt><dd class="num">${i.Risk_Score}</dd><dt>Area</dt><dd>${esc(i.Area_Name)}</dd><dt>Team</dt><dd>${esc(i.Assigned_Team || "–")}</dd><dt>Verification</dt><dd>${esc(i.Verification_Outcome || "pending")}</dd></dl>
      <h4>Detections</h4>${r.detections.map(d => `<div class="d-block"><span class="id">${esc(d.id)}</span> · ${esc(d.status)} · conf ${d.confidence}<div class="muted" style="margin-top:2px">${esc(d.evidence)}</div></div>`).join("") || '<span class="muted">none</span>'}
      <h4>Work orders</h4>${r.work_orders.map(w => `<div class="d-block"><span class="id">${esc(w.Work_Order_ID)}</span> · ${esc(w.Status)} · ${esc(w.Assigned_Worker || "unassigned")}</div>`).join("") || '<span class="muted">none</span>'}
      <h4>Field verification</h4>${r.verifications.map(v => `<div class="d-block"><b>${esc(v.Verification_Status)}</b> by ${esc(v.Worker_ID)}${v.Simulated_Worker === "Yes" ? ' <span class="badge violet">simulated</span>' : ""} · ${esc(v.Distance_To_Detection_M)} m from detection<div class="muted" style="margin-top:2px">${esc(v.Agent_Assessment)}</div>${v.Photo_URL ? `<a href="${esc(v.Photo_URL)}" target="_blank" rel="noopener">View photo evidence</a>` : ""}</div>`).join("") || '<span class="muted">none</span>'}
      <div class="btnrow" style="margin-top:var(--sp-4)"><button class="btn small" type="button" data-act="propose_work_order">Propose work order</button><button class="btn small" type="button" data-act="propose_field_assignment" data-wo="${wo ? esc(wo.Work_Order_ID) : ""}">Propose assignment</button>
      <button class="btn small secondary" type="button" data-act="verify_outcome">Verify outcome</button><button class="btn small secondary" type="button" data-act="propose_incident_closure">Propose closure</button></div>`;
  } catch (e) { toast(fmtErr(e), "bad"); }
}
document.addEventListener("click", async e => {
  const b = e.target.closest("[data-act]"); if (!b || !state.selInc) return;
  const args = { incident_id: state.selInc };
  if (b.dataset.act === "propose_field_assignment") { if (!b.dataset.wo) { toast("No open work order for this incident — propose and approve one first.", "warn"); return; } delete args.incident_id; args.work_order_id = b.dataset.wo; }
  await busy(b, async () => {
    try {
      const r = await post("/api/tools/" + b.dataset.act, { args, session_id: state.sid }); setStages([r.stage]);
      if (r.ok) toast(r.result.status === "AWAITING_APPROVAL" ? "Proposal created — approve it in the Approval panel." : (r.result.agent_assessment || r.result.message || "Done"), r.result.status === "AWAITING_APPROVAL" ? "info" : "ok");
      else toast(r.error, "bad");
      await afterAction();
    } catch (err) { toast(fmtErr(err), "bad"); }
  });
});
$("#c-from-det").onclick = e => busy(e.currentTarget, async () => {
  try { const r = await post("/api/tools/create_incidents_from_detections", { args: {}, session_id: state.sid }); if (r.ok) toast(r.result.message || (r.result.created.length ? `${r.result.created.length} incident(s) created` : "No new detections to convert"), r.result.created.length ? "ok" : "info", r.result.created.length ? 4600 : 7000); else toast(r.error, "bad"); setStages(["DECIDE"]); await afterAction(); }
  catch (err) { toast(fmtErr(err), "bad"); }
});
async function loadAudit() {
  const a = await api("/api/audit?n=40");
  $("#audit").innerHTML = a.length ? a.map(r => `<div><b>${esc(r.Agent_Action)}</b><div class="muted">${esc(r.Timestamp.slice(11, 19))} · ${esc(r.Actor)}${r.Related_Incident_ID ? " · " + esc(r.Related_Incident_ID) : ""}${r.Approval_Status !== "N/A" ? " · " + esc(r.Approval_Status) : ""}</div></div>`).join("") : empty("clock", "No actions recorded yet");
}
async function loadSim() {
  const s = await api("/api/sim/status");
  $("#simstatus").innerHTML = `<span class="dot ${s.running ? "ok" : ""}" style="display:inline-block;margin-right:6px"></span>${s.running ? "Running" : "Paused"} · ${s.ticks} ticks`;
  $("#simevents").innerHTML = s.events.length ? s.events.map(e => `<div>${esc(e.Timestamp.slice(11, 19))} [${esc(e.Kind)}] ${esc(e.Message)}</div>`).join("") : '<div>No simulation events yet.</div>';
}
document.addEventListener("click", async e => {
  const s = e.target.closest("[data-sim]"), sc = e.target.closest("[data-scn]"); if (!s && !sc) return;
  const btn = s || sc;
  if (s && s.dataset.sim === "reset" && !(await confirmDialog({ title: "Reset the environment?", text: "This regenerates all synthetic data from the seed and removes incidents, work orders and verifications created in this session.", ok: "Reset environment", danger: true }))) return;
  await busy(btn, async () => {
    try {
      if (s) { if (s.dataset.sim === "reset") { await post("/api/sim/reset"); execLoaded = false; state.incRows = []; toast("Environment regenerated from seed", "ok"); await refreshLayers(); } else await post("/api/sim/" + s.dataset.sim); }
      if (sc) { const r = await post("/api/sim/scenario/" + sc.dataset.scn); toast("Scenario injected: " + (r.event || sc.dataset.scn), "ok"); setStages(["SENSE"]); }
      await Promise.all([loadSim(), refreshLayers(["Riyadh_Sensor_Readings"]), loadApprovals()]);
    } catch (err) { toast(fmtErr(err), "bad"); }
  });
});

/* ------------------------------------------------------------------ field portal */
async function loadWorkers() {
  const w = await api("/api/workers"); $("#wk").innerHTML = w.map(x => `<option value="${esc(x.Worker_ID)}">${esc(x.Name)}${x.Open_Tasks ? ` (${x.Open_Tasks})` : ""}</option>`).join("");
  const keep = state.worker && w.find(x => x.Worker_ID === state.worker); $("#wk").value = keep ? state.worker : (w.find(x => x.Open_Tasks > 0) || w[0]).Worker_ID; state.worker = $("#wk").value; state.workers = w;
}
async function loadTasks() {
  await loadWorkers(); const w = state.workers.find(x => x.Worker_ID === state.worker);
  $("#wkprofile").innerHTML = `${esc(w.Team)} · ${esc(w.Skills.replace(/,/g, ", "))} · <b>${esc(w.Status)}</b> · ${w.Open_Tasks} open task(s)`;
  const t = await api("/api/field/tasks/" + state.worker); state.tasks = t;
  $("#tasks").innerHTML = t.length ? t.map((x, i) => `<button type="button" class="task ${state.task === x.work_order.Work_Order_ID ? "sel" : ""}" data-task="${i}"><div class="row1" style="display:flex;gap:6px;align-items:center;flex-wrap:wrap"><span class="id">${esc(x.work_order.Work_Order_ID)}</span>${pill(x.work_order.Priority)}<span class="pill st">${esc(x.work_order.Status)}</span></div>
      <div style="margin-top:4px">${esc(x.incident.Incident_Type)} · ${esc(x.incident.Area_Name)}</div><div class="muted" style="font-size:var(--fs-sm)">${esc(x.instructions)}</div></button>`).join("")
    : empty("inbox", "No assigned tasks", "Create and approve a work order, then assign this worker from the Command Center.");
  if (!t.find(x => x.work_order.Work_Order_ID === state.task)) { state.task = null; $("#fform").classList.add("hidden"); }
}
$("#wk").onchange = () => { state.worker = $("#wk").value; state.task = null; loadTasks().catch(e => toast(fmtErr(e), "bad")); };
document.addEventListener("click", e => {
  const t = e.target.closest("[data-task]"); if (!t) return; const x = state.tasks[+t.dataset.task]; state.task = x.work_order.Work_Order_ID; state.taskLoc = x.location;
  $("#fform").classList.remove("hidden"); $("#ftitle").textContent = `${x.work_order.Work_Order_ID} · ${x.incident.Incident_ID}`;
  $("#ffinding").innerHTML = x.ai_finding.map(f => `<b>AI finding (${esc(f.type)}, confidence ${f.confidence}):</b> ${esc(f.evidence)}`).join("<hr class='divider'>");
  $("#fresult").textContent = ""; clearFieldErrors(); zoomTo(x.location.lon, x.location.lat, 18, "Task location"); $$(".task", $("#tasks")).forEach(el => el.classList.toggle("sel", el === t));
  $("#fobs").scrollIntoView({ block: "nearest", behavior: "smooth" });
});
$("#fgps").onclick = () => navigator.geolocation ? navigator.geolocation.getCurrentPosition(p => { $("#flat").value = p.coords.latitude.toFixed(6); $("#flon").value = p.coords.longitude.toFixed(6); toast("GPS captured", "ok", 2500); }, () => toast("GPS unavailable — use the task location instead.", "warn")) : toast("GPS is not supported on this device.", "warn");
$("#ftask").onclick = () => { if (state.taskLoc) { $("#flat").value = (state.taskLoc.lat + 0.00005).toFixed(6); $("#flon").value = (state.taskLoc.lon + 0.00005).toFixed(6); } };
function clearFieldErrors() { ["fobs", "flat", "flon"].forEach(i => $("#" + i).removeAttribute("aria-invalid")); $("#ferr-obs").textContent = ""; $("#ferr-gps").textContent = ""; }
function validateField() {
  clearFieldErrors(); let first = null;
  if ($("#fobs").value.trim().length < 5) { $("#fobs").setAttribute("aria-invalid", "true"); $("#ferr-obs").textContent = "Describe what you observed (at least 5 characters)."; first = first || $("#fobs"); }
  const lat = parseFloat($("#flat").value), lon = parseFloat($("#flon").value);
  if (!(lat >= -90 && lat <= 90) || !(lon >= -180 && lon <= 180)) { ["flat", "flon"].forEach(i => $("#" + i).setAttribute("aria-invalid", "true")); $("#ferr-gps").textContent = "Capture your GPS position or use the task location."; first = first || $("#flat"); }
  if (first) first.focus(); return !first;
}
$("#fform").onsubmit = async e => {
  e.preventDefault(); if (!validateField()) return;
  const fd = new FormData(); fd.append("work_order_id", state.task); fd.append("worker_id", state.worker); fd.append("status", $("#fstatus").value);
  fd.append("observation", $("#fobs").value); fd.append("lat", $("#flat").value); fd.append("lon", $("#flon").value); if ($("#fphoto").files[0]) fd.append("photo", $("#fphoto").files[0]);
  await busy($("#fsubmit"), async () => {
    try {
      const r = await api("/api/field/submit", { method: "POST", headers: { "X-Role": "worker" }, body: fd });
      $("#fresult").innerHTML = `<div class="alert info">${icon("check-c")}<div><b>${esc(r.outcome)}</b><br>${esc(r.assessment)}</div></div>`; setStages(["VERIFY", "LEARN"]); toast("Verification recorded: " + r.outcome, "ok");
      $("#fobs").value = ""; $("#fphoto").value = ""; await afterAction();
    } catch (err) { $("#fresult").innerHTML = `<div class="alert warn">${icon("alert")}<div>${esc(fmtErr(err))}</div></div>`; }
  });
};
async function simField(repair, btn) {
  if (!state.task) { toast("Select a task first.", "warn"); return; }
  await busy(btn, async () => { try { const r = await post(`/api/sim/field-response/${state.task}?repair=${repair}`); toast("Simulated worker: " + r.outcome, "ok"); setStages(["VERIFY"]); await afterAction(); } catch (e) { toast(fmtErr(e), "bad"); } });
}
$("#simfield").onclick = e => simField(false, e.currentTarget); $("#simrepair").onclick = e => simField(true, e.currentTarget);

/* ------------------------------------------------------------------ intelligence */
function bars(t) {
  const n = t.dates.length; if (!n) return empty("pulse", "No detections yet");
  const tot = t.dates.map((_, i) => t.series.water[i] + t.series.lighting[i] + t.series.change[i]); const mx = Math.max(...tot, 1);
  return `<div class="bar" role="img" aria-label="Detections per day, ${t.dates[0]} to ${t.dates[n - 1]}">${t.dates.map((d, i) => `<span title="${d}: water ${t.series.water[i]}, lighting ${t.series.lighting[i]}, change ${t.series.change[i]}" style="height:${Math.max(4, 100 * tot[i] / mx)}%"></span>`).join("")}</div>
    <div class="muted" style="font-size:var(--fs-xs);display:flex;justify-content:space-between;margin-top:6px"><span>${t.dates[0]}</span><span>peak ${mx}/day</span><span>${t.dates[n - 1]}</span></div>`;
}
async function loadIntel() {
  const [ev, tr] = await Promise.all([api("/api/evaluation"), api("/api/trends")]);
  const dash = v => v ?? "n/a";
  $("#evaltable").innerHTML = `<div class="statrow"><div class="stat"><b>${ev.total_verified}</b><span>verified of ${ev.total_detections}</span></div><div class="stat"><b>${dash(ev.overall_precision)}</b><span>overall precision</span></div><div class="stat"><b>${dash(ev.verification_rate)}</b><span>verification rate</span></div><div class="stat"><b>${ev.streetlight_threshold}</b><span>streetlight threshold</span></div></div>
    <div class="tablewrap"><table><thead><tr><th>Category</th><th class="num">True+</th><th class="num">False+</th><th class="num">Awaiting</th><th class="num">FN*</th><th class="num">Precision</th><th class="num">Recall*</th><th class="num">Calibration</th></tr></thead><tbody>${Object.entries(ev.categories).map(([c, v]) => `<tr><td><b>${esc(c)}</b></td><td class="num">${v.verified_true}</td><td class="num">${v.verified_false}</td><td class="num">${v.awaiting_verification}</td><td class="num">${dash(v.false_negatives_known)}</td><td class="num">${dash(v.precision)}</td><td class="num">${dash(v.recall)}</td><td class="num">×${v.calibration}</td></tr>`).join("")}</tbody></table></div>`;
  $("#evalnote").textContent = "* " + ev.notes + " Calibration is a configurable risk multiplier updated from verified outcomes — no model is retrained.";
  $("#trend").innerHTML = bars(tr);
  $("#outcomes").innerHTML = ev.outcomes.slice(-24).map(o => `<span class="pill ${o.outcome === "Verified-True" ? "P4" : "P1"}" title="${esc(o.date)} · ${esc(o.category)}">${o.outcome === "Verified-True" ? "True" : "False"}</span>`).join("") || '<span class="muted">None yet</span>';
  if (!state.tools.length) { state.tools = await api("/api/tools"); $("#toollist").innerHTML = state.tools.map(t => `<div><b class="stg">${esc(t.stage)}</b><code>${esc(t.name)}</code>${t.consequential ? ` <span class="badge warn">${icon("lock")}approval</span>` : ""}<div class="muted">${esc(t.description)}</div></div>`).join(""); }
}

const colLabel = k => String(k).replace(/_/g, " ");
function scalar(v) {
  if (v === null || v === undefined || v === "") return '<span class="muted">—</span>';
  if (typeof v === "boolean") return `<span class="pill ${v ? "P4" : "P1"}">${v ? "yes" : "no"}</span>`;
  if (typeof v === "number") return `<span class="num">${esc(v)}</span>`;
  return esc(v);
}
/* a list of records becomes a nested table (scalar fields as columns); anything else deeper stays available as JSON */
function subTable(arr) {
  const recs = arr.filter(x => x && typeof x === "object" && !Array.isArray(x)), extra = arr.filter(x => !(x && typeof x === "object"));
  const cols = [...new Set(recs.flatMap(r => Object.keys(r).filter(k => r[k] === null || typeof r[k] !== "object")))].slice(0, 6);
  if (!recs.length || !cols.length) return null;
  const hidden = Object.keys(recs[0]).filter(k => !cols.includes(k)).length;
  return `<div class="subwrap"><table class="restbl sub"><thead><tr>${cols.map(c => `<th>${esc(colLabel(c))}</th>`).join("")}</tr></thead><tbody>${recs.map(r => `<tr>${cols.map(c => `<td>${scalar(r[c])}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`
    + (extra.length ? `<div class="muted" style="font-size:11px;margin-top:4px">${esc(extra.join(" "))}</div>` : "")
    + (hidden ? `<details class="nest"><summary>${hidden} more field${hidden === 1 ? "" : "s"} per record</summary><pre>${esc(JSON.stringify(arr, null, 1))}</pre></details>` : "");
}
function resultVal(v) {
  if (v === null || typeof v !== "object") return scalar(v);
  const isArr = Array.isArray(v), n = isArr ? v.length : Object.keys(v).length;
  if (!n) return '<span class="muted">none</span>';
  if (isArr) {
    if (v.every(x => x === null || typeof x !== "object")) return v.map(x => scalar(x)).join(", ");   // list of scalars
    const t = subTable(v); if (t) return t;
  }
  return `<details class="nest"><summary>${n} ${isArr ? "item" : "field"}${n === 1 ? "" : "s"}</summary><pre>${esc(JSON.stringify(v, null, 1))}</pre></details>`;
}
function resultList(res) {
  if (res === null || typeof res !== "object") return `<code class="clip">${esc(res)}</code>`;
  if (Array.isArray(res)) return resultVal(res);
  const entries = Object.entries(res);
  if (!entries.length) return '<span class="muted">empty</span>';
  const row = ([k, v]) => `<tr><th scope="row">${esc(colLabel(k))}</th><td>${resultVal(v)}</td></tr>`;
  const first = entries.slice(0, 6).map(row).join(""), rest = entries.slice(6).map(row).join("");
  return `<table class="restbl"><thead><tr><th>Field</th><th>Value</th></tr></thead><tbody>${first}</tbody>${rest ? `<tbody class="more hidden">${rest}</tbody>` : ""}</table>`
    + (rest ? `<button type="button" class="link-btn" data-more="${entries.length}" aria-expanded="false">Show all ${entries.length} fields</button>` : "");
}
document.addEventListener("click", e => {
  const b = e.target.closest("[data-more]"); if (!b) return;
  const more = b.previousElementSibling.querySelector("tbody.more"), open = more.classList.toggle("hidden") === false;
  b.setAttribute("aria-expanded", open); b.textContent = open ? "Show fewer" : `Show all ${b.dataset.more} fields`;
});
function toolCallsTable(calls) {
  if (!calls || !calls.length) return empty("wrench", "No tool calls in this scene");
  const inp = i => (i === undefined || i === null || (typeof i === "object" && !Object.keys(i).length)) ? '<span class="muted">—</span>' : `<code class="clip" title="${esc(JSON.stringify(i))}">${esc(JSON.stringify(i))}</code>`;
  const result = t => t.result !== undefined && t.result !== null ? resultList(t.result) : `<button type="button" class="clip-btn" aria-expanded="false" title="Click to expand"><code class="clip">${esc(t.summary)}</code></button><div class="muted" style="font-size:11px;margin-top:4px">Restart the server to see results as a table.</div>`;
  return `<div class="tablewrap"><table class="stack-sm calls"><caption class="sr-only">Tool calls executed by the agent in this scene, each followed by its result</caption>
    <thead><tr><th class="num">#</th><th>Stage</th><th>Tool</th><th>Status</th><th>Input</th></tr></thead><tbody>${calls.map((t, i) => `<tr class="call">
      <td class="num" data-label="Step">${i + 1}</td><td data-label="Stage"><span class="badge info">${esc(t.stage || "—")}</span></td><td data-label="Tool"><span class="id">${esc(t.tool)}</span>${t.duration_ms != null ? `<div class="muted num" style="font-size:var(--fs-xs)">${t.duration_ms} ms</div>` : ""}</td>
      <td data-label="Status">${t.ok ? '<span class="pill P4">OK</span>' : '<span class="pill P1">Failed</span>'}</td><td data-label="Input">${inp(t.input)}</td></tr>
      <tr class="res-row"><td></td><td colspan="4" data-label="Result"><div class="res-label">Result</div>${result(t)}</td></tr>`).join("")}</tbody></table></div>`;
}
document.addEventListener("click", e => { const b = e.target.closest(".clip-btn"); if (!b) return; const open = b.classList.toggle("open"); b.setAttribute("aria-expanded", open); b.title = open ? "Click to collapse" : "Click to expand"; });

/* ------------------------------------------------------------------ guided demo */
const SCENE_BLURB = { 1: "Inject a pressure anomaly near Olaya; the agent detects a suspected leak.", 2: "Compare two imagery epochs (simulated) and find change candidates.", 3: "Extract buildings and roads, run spatial analysis.", 4: "Create incidents, recompute KPIs, rank and recommend.", 5: "Propose work order and field assignment; the operator approves.", 6: "Field evidence is compared with the AI finding.", 7: "Close the loop: repair, closure approval, metrics, calibration.", 8: "Same agent, King Fahd Road streetlight cluster, end to end." };
async function loadScenes() {
  const sc = await api("/api/demo/scenes");
  $("#scenes").innerHTML = sc.map(s => `<div class="sc" id="sc${s.scene}"><b>${s.scene === 8 ? "+" : s.scene}</b><div><span class="s-stage">${esc(s.stage)}</span><div class="s-title">${esc(s.title)}</div><small>${esc(SCENE_BLURB[s.scene])}</small></div><button class="btn small secondary" type="button" data-scene="${s.scene}">${icon("play")}Run</button></div>`).join("");
}
document.addEventListener("click", async e => {
  const b = e.target.closest("[data-scene]"); if (!b) return;
  const row = $(`#sc${b.dataset.scene}`); row.classList.add("run");
  await busy(b, async () => {
    try {
      const r = await post(`/api/demo/run/${b.dataset.scene}?auto_approve=${$("#d-auto").checked}`);
      setStages([r.stage === "BONUS" ? "SENSE" : r.stage]); row.classList.toggle("ok", !!r.complete);
      $("#d-out").innerHTML = `<div class="card-head"><h3>Scene ${r.scene} · ${esc(r.stage)}</h3><small>${esc(r.title)}</small><span class="spacer"></span>${r.complete ? '<span class="badge ok">Complete</span>' : r.awaiting_approval ? '<span class="badge warn">Awaiting approval</span>' : '<span class="badge">Incomplete</span>'}</div>
        <div class="card-body">${(r.narrative || []).map(n => `<p class="out-p">${esc(n)}</p>`).join("")}
        ${r.awaiting_approval ? `<div class="alert warn">${icon("shield")}<div>Waiting for operator approval — approve the proposal on the left, then run this scene again.</div></div>` : ""}
        ${r.imagery ? `<div class="imgs" style="margin:12px 0"><figure><img src="/api/imagery/Olaya/A.png" alt="Epoch A"><figcaption>Epoch A · simulated</figcaption></figure><figure><img src="/api/imagery/Olaya/B.png" alt="Epoch B"><figcaption>Epoch B · simulated</figcaption></figure></div>` : ""}
        <div class="section-title">Tool calls (live) <span class="muted" style="text-transform:none;letter-spacing:0;font-weight:500">· ${r.tool_calls.length} call(s)</span></div>${toolCallsTable(r.tool_calls)}</div>`;
      (r.layers || []).forEach(l => { if (M && M.layers[l]) M.layers[l].visible = true; }); syncLayerBoxes();
      await afterAction(); if (r.map) zoomTo(r.map.lon, r.map.lat, r.map.zoom, r.map.label);
    } catch (err) { toast(fmtErr(err), "bad"); } finally { row.classList.remove("run"); }
  });
});
$("#d-reset").onclick = async e => {
  if (!(await confirmDialog({ title: "Reset the demo?", text: "Synthetic data is regenerated from the seed and anything created during the walkthrough is removed.", ok: "Reset demo", danger: true }))) return;
  await busy(e.currentTarget, async () => {
    try {
      await post("/api/demo/reset"); execLoaded = false; state.incRows = []; $$(".sc").forEach(s => s.classList.remove("ok"));
      $("#d-out").innerHTML = `<div class="card-head"><h3>Scene output</h3></div><div class="card-body">${empty("refresh", "Environment reset", "Run scene 1 to start the story again.")}</div>`;
      setStages([]); $$(".stage").forEach(s => s.classList.remove("done")); toast("Demo reset", "ok"); await afterAction(); await refreshLayers();
    } catch (err) { toast(fmtErr(err), "bad"); }
  });
};

/* ------------------------------------------------------------------ navigation, palette, boot */
const PAGES = {
  exec: { title: "Overview", sub: "Citywide operational picture, computed from stored records" },
  map: { title: "Operations Map", sub: "Real Riyadh streets and buildings with synthetic operational layers" },
  copilot: { title: "AI Operations Agents", sub: "One agent, one conversation, human-approved actions" },
  cmd: { title: "Command Center", sub: "Incidents, approvals, simulation and the audit trail" },
  field: { title: "Field Portal", sub: "Assigned tasks, GPS and photo evidence" },
  intel: { title: "Intelligence", sub: "Prediction quality, trends and the agent's toolset" },
  demo: { title: "Guided Demo", sub: "Sense → See → Understand → Decide → Act → Verify → Learn" },
};
function switchTab(t, fromHash = false) {
  if (!PAGES[t]) t = "exec";
  state.tab = t; $$("#tabs .nav-item").forEach(b => { const on = b.dataset.tab === t; b.setAttribute("aria-selected", on); b.tabIndex = on ? 0 : -1; });
  $$(".tab").forEach(s => s.classList.toggle("on", s.id === "tab-" + t));
  $("#page-title").textContent = PAGES[t].title; $("#page-sub").textContent = PAGES[t].sub; document.title = `${PAGES[t].title} · GeoAI Operations Center | Riyadh`;
  if (!fromHash && location.hash !== "#/" + t) history.pushState(null, "", "#/" + t);
  placeMap(t); refreshActive(); if (t === "copilot") welcome(); window.scrollTo({ top: 0 });
}
window.addEventListener("hashchange", () => switchTab((location.hash.match(/^#\/(\w+)/) || [])[1] || "exec", true));
$("#tabs").addEventListener("click", e => { const b = e.target.closest(".nav-item"); if (b) switchTab(b.dataset.tab); });
$("#tabs").addEventListener("keydown", e => {
  const items = $$("#tabs .nav-item"), i = items.indexOf(document.activeElement); if (i < 0) return;
  const step = { ArrowDown: 1, ArrowRight: 1, ArrowUp: -1, ArrowLeft: -1 }[e.key]; if (step) { e.preventDefault(); const n = items[(i + step + items.length) % items.length]; n.focus(); switchTab(n.dataset.tab); }
});
$("#rail-toggle").onclick = () => { const a = $("#app"), c = a.dataset.rail !== "collapsed"; a.dataset.rail = c ? "collapsed" : "expanded"; store.set("geoai.rail", a.dataset.rail); $("#rail-toggle").setAttribute("aria-label", c ? "Expand sidebar" : "Collapse sidebar"); setTimeout(() => window.dispatchEvent(new Event("resize")), 250); };
function syncLayerBoxes() { $$("#layerlist input").forEach(i => { if (M && M.layers[i.dataset.l]) i.checked = M.layers[i.dataset.l].visible; }); renderLegend(); }
function buildLayerList() {
  $("#layerlist").innerHTML = Object.entries(LAYERS).map(([n, c]) => `<label><input type="checkbox" data-l="${n}" ${c.vis ? "checked" : ""}>${swatch(LEGEND[n][0])}${esc(c.label)}</label>`).join("");
  $("#layerlist").onchange = e => { const l = e.target.dataset.l; if (M) { M.layers[l].visible = e.target.checked; renderLegend(); if (LAYERS[l].bbox) loadBuildings().then(renderLegend).catch(() => { }); } };
  $("#basemap").innerHTML = basemapOptions(); $("#basemap").value = savedBasemap(); $("#basemap").onchange = e => setBasemap(e.target.value);
  $("#goarea").innerHTML = Object.keys(state.cfg.areas).map(a => `<option>${esc(a)}</option>`).join("");
  $("#goarea").onchange = e => { const c = state.cfg.areas[e.target.value].center; zoomTo(c[0], c[1], 15); };
}

/* command palette (Ctrl/Cmd+K) */
let palItems = [], palSel = 0;
function paletteCommands() {
  const nav = Object.entries(PAGES).map(([k, p]) => ({ g: "Go to", ic: { exec: "dash", map: "map", copilot: "spark", cmd: "clip", field: "phone", intel: "chart", demo: "play-c" }[k], t: p.title, run: () => switchTab(k) }));
  const act = [
    { g: "Actions", ic: "refresh", t: "Reset demo environment", run: () => { switchTab("demo"); $("#d-reset").click(); } },
    { g: "Actions", ic: "drop", t: "Inject Olaya leak scenario", run: () => post("/api/sim/scenario/olaya_leak").then(r => { toast("Scenario injected: " + r.event, "ok"); setStages(["SENSE"]); }).catch(e => toast(fmtErr(e), "bad")) },
    { g: "Actions", ic: "spark", t: "Create incidents from latest detections", run: () => { switchTab("cmd"); $("#c-from-det").click(); } },
    ...Object.entries(THEMES).map(([k, label]) => ({ g: "Theme", ic: k === "dark" ? "moon" : k === "light" ? "sun" : "spark", t: `Switch to ${label} theme`, run: () => applyTheme(k) })),
    { g: "Actions", ic: "panel", t: "Collapse / expand sidebar", run: () => $("#rail-toggle").click() },
  ];
  const ask = ["Detect possible water leaks in Riyadh", "Identify streetlights with a high probability of failure", "Compare imagery epochs in Olaya District", "Which incidents require immediate intervention?", "Create work orders for the top five priority incidents", "Show me which incidents have been verified", "Compare the AI predictions with actual field observations"]
    .map(t => ({ g: "Ask the agent", ic: "chat", t, run: () => { switchTab("copilot"); send(t); } }));
  return [...nav, ...act, ...ask];
}
function renderPalette() {
  const q = $("#pal-q").value.toLowerCase().trim(); const words = q.split(/\s+/).filter(Boolean);
  palItems = paletteCommands().filter(c => words.every(w => (c.g + " " + c.t).toLowerCase().includes(w))); palSel = Math.min(palSel, Math.max(0, palItems.length - 1));
  let g = "", html = "";
  palItems.forEach((c, i) => { if (c.g !== g) { g = c.g; html += `<div class="pal-group">${esc(g)}</div>`; } html += `<button type="button" role="option" class="pal-item" data-i="${i}" aria-selected="${i === palSel}">${icon(c.ic)}<span>${esc(c.t)}</span></button>`; });
  $("#pal-list").innerHTML = html || empty("search", "No matches", "Try a page name or an action.");
  $("#pal-list .pal-item[aria-selected=true]")?.scrollIntoView({ block: "nearest" });
}
function openPalette() { const d = $("#palette"); if (d.open) return; $("#pal-q").value = ""; palSel = 0; renderPalette(); d.showModal(); $("#pal-q").focus(); }
function runPalette(i) { const c = palItems[i]; if (!c) return; $("#palette").close(); c.run(); }
$("#open-palette").onclick = openPalette;
$("#pal-q").oninput = () => { palSel = 0; renderPalette(); };
$("#pal-q").onkeydown = e => {
  if (e.key === "ArrowDown") { e.preventDefault(); palSel = Math.min(palSel + 1, palItems.length - 1); renderPalette(); }
  else if (e.key === "ArrowUp") { e.preventDefault(); palSel = Math.max(palSel - 1, 0); renderPalette(); }
  else if (e.key === "Enter") { e.preventDefault(); runPalette(palSel); }
};
$("#pal-list").onclick = e => { const b = e.target.closest(".pal-item"); if (b) runPalette(+b.dataset.i); };
$("#palette").addEventListener("click", e => { if (e.target === $("#palette")) $("#palette").close(); });
document.addEventListener("keydown", e => { if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); openPalette(); } });
if (/Mac|iPhone|iPad/.test(navigator.platform)) $("#open-palette .kbd").textContent = "⌘ K";

(async function boot() {
  applyTheme(currentTheme(), false);
  $("#app").dataset.rail = store.get("geoai.rail") === "collapsed" ? "collapsed" : "expanded";
  restoreChat();
  switchTab((location.hash.match(/^#\/(\w+)/) || [])[1] || "exec", true);
  try {
    const [h, cfg] = await Promise.all([api("/api/health"), api("/api/config")]); state.cfg = cfg;
    $("#b-agent").textContent = h.agent_mode === "claude" ? "Agent: Claude" : "Agent: offline planner"; $("#d-agent").className = "dot " + (h.agent_mode === "claude" ? "ok" : "warn"); $("#b-agent").title = h.model;
    const ag = h.arcgis || ""; $("#b-arcgis").textContent = "ArcGIS: " + (ag.startsWith("disabled") ? "local mode" : ag.includes("failed") ? "sync problem" : "connected"); $("#b-arcgis").title = ag;
    $("#d-arcgis").className = "dot " + (ag.startsWith("disabled") ? "" : ag.includes("failed") ? "bad" : "ok");
    $("#f-area").innerHTML += Object.keys(cfg.areas).map(a => `<option>${esc(a)}</option>`).join("");
    try { const saved = JSON.parse(sessionStorage.getItem("geoai.filters") || "{}"); setFormFilters(saved); state.filters = readFilters(); } catch (e) { state.filters = {}; }
    renderFilterNote();
    $("#chatmode").textContent = h.agent_mode === "claude" ? "Claude API" : "Offline planner";
    buildLayerList(); await Promise.all([loadScenes(), loadApprovals()]);
    placeMap(state.tab); M = await initMap(); renderLegend();
    if (!M) toast("The ArcGIS Maps SDK did not load (offline?). Everything except the map still works.", "warn", 8000); else await refreshLayers();
    await refreshActive(); setInterval(loadApprovals, 8000);
  } catch (e) { toast("Startup problem: " + fmtErr(e), "bad", 0); console.error(e); }
})();
