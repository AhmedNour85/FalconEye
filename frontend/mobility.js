/* Mobility map layers, shared by the Operation page and the Executive Hub.

   Traffic is MODELLED, not measured: the server calculates it from the road network and a synthetic demand profile.
   Roads are (c) OpenStreetMap contributors; metro and bus come from RCRC open data; hospital positions are approximate.

   Mobility.attach({ map, GraphicsLayer, Graphic, panel, host, view })
     view: optional, a function that returns the current view (the map page can switch between 2D and 3D)
     returns { layers, state, refresh, refreshClosures, showImpact(scenarioId), clearImpact() }
     panel: element that receives the layer checkboxes and the hour slider
     host:  the map's container element; the legend and the credits are placed in it
   Every layer is off at start, is loaded only when it is first switched on, and sits under the incident layers. */
(function () {
  const { T, TV } = I18N;
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const FLOW = { free: "#2faa4a", slow: "#dc6803", heavy: "#d92d20", stopped: "#8b1117" };
  const WIDTH = { slow: 2.6, heavy: 3.2, stopped: 3.8 };
  const LAYERS = [["traffic", "Traffic"], ["metro", "Metro"], ["bus", "Bus"], ["hosp", "Hospitals"], ["closures", "Planned closures"]];
  const CLOSURE = { Requested: "#dc6803", Approved: "#b54708", "In Place": "#d92d20" };       // asked for, approved, in place
  const LEVEL = { severe: "#8b1117", heavy: "#d92d20", busy: "#dc6803" };
  const pad = h => String(h).padStart(2, "0") + ":00";
  const riyadhHour = () => (new Date().getUTCHours() + 3) % 24;
  const remember = (k, v) => { try { localStorage.setItem("geoai.layer." + k, v ? "1" : "0"); } catch (e) { /* optional */ } };
  const recall = k => { try { return localStorage.getItem("geoai.layer." + k) === "1"; } catch (e) { return false; } };

  /* Plain fetch: these answers hold ids, numbers and coordinates only, so they are not sent through the translation step. */
  async function get(path) {
    const r = await fetch(/^(closures|layers\/hospitals)/.test(path) && window.I18N ? I18N.apiUrl("/api/mobility/" + path) : "/api/mobility/" + path);
    if (r.status === 503) { const j = await r.json().catch(() => ({})); const e = new Error("building"); e.building = j; throw e; }
    if (!r.ok) { const j = await r.json().catch(() => ({})); throw new Error(j.detail || r.statusText); }
    return r.json();
  }

  function attach({ map, GraphicsLayer, Graphic, panel, host, view }) {
    const L = { traffic: new GraphicsLayer({ visible: false }), bus: new GraphicsLayer({ visible: false }), metro: new GraphicsLayer({ visible: false }), hosp: new GraphicsLayer({ visible: false }),
      closures: new GraphicsLayer({ visible: false }) };
    const impact = new GraphicsLayer();                                            // the drawing of one simulation, shown on request
    const stops = new GraphicsLayer({ visible: false, minScale: 90000 });      // 3,010 stops: drawn only when zoomed in
    map.addMany([L.traffic, L.bus, stops, L.metro, L.closures, impact, L.hosp], 0);   // under the incident layers
    const st = { hour: riyadhHour(), roads: null, base: null, hours: {}, loaded: {}, credit: {}, timer: 0, seq: 0, impact: null, impactSeq: 0, impactTimer: 0, closureAt: 0 };

    // ---- controls -------------------------------------------------------------------------------
    const box = document.createElement("div");
    box.className = "mob";
    box.innerHTML = LAYERS.map(([k, label]) => `<label><input type="checkbox" data-mob="${k}"> <span>${T(label)}</span></label>`).join("") +
      `<div class="mob-hour" hidden><label for="mob-h">${T("Hour")}</label><input id="mob-h" type="range" min="0" max="23" step="1" value="${st.hour}" aria-describedby="mob-hv"><output id="mob-hv" dir="ltr">${pad(st.hour)}</output></div>`;
    panel.appendChild(box);
    /* Legend and credits: a box the user can fold. Open on a tall map; folded on a short one (a phone, a small window),
       where it would cover the map and the layer box. The folded line still says the traffic is modelled. */
    const info = document.createElement("details");
    info.className = "mob-info"; info.hidden = true; info.open = host.clientHeight >= 500;
    info.innerHTML = `<summary></summary><div class="mob-body" role="status"></div>`;
    host.appendChild(info);
    const infoHead = info.querySelector("summary"), infoBody = info.querySelector(".mob-body");
    infoBody.addEventListener("click", e => { if (e.target.closest("[data-clear]")) clearImpact(); });
    const hourRow = box.querySelector(".mob-hour"), slider = box.querySelector("#mob-h"), out = box.querySelector("#mob-hv");
    const on = k => box.querySelector(`[data-mob="${k}"]`).checked;

    function renderInfo(note) {
      const rows = [];
      let head = `<b>${T("Map sources")}</b>`;
      if (on("traffic")) {
        head = `<b>${T("Traffic at {h}", { h: `<span dir="ltr">${pad(st.hour)}</span>` })}</b> · <b class="mob-mod">${T("Modelled")}</b>`;
        rows.push(`<div class="mob-leg">` +
          [["free", "Free"], ["slow", "Slow"], ["heavy", "Heavy"], ["stopped", "Stop-and-go"]].map(([c, n]) => `<span><i style="background:${FLOW[c]}"></i>${T(n)}</span>`).join("") + `</div>` +
          `<div class="mob-note"><b>${T("Modelled")}</b> · ${T("calculated from the road network and synthetic demand, not measured")}</div>`);
        if (st.totals) rows.push(`<div class="mob-note">${T("{n} road sections slow or worse", { n: st.totals.busy })} · ${T("average speed {v} km/h", { v: st.totals.speed })}</div>`);
        rows.push(`<div class="mob-credit">${T("Roads")}: © OpenStreetMap contributors</div>`);
      }
      if (on("metro") || on("bus")) rows.push(`<div class="mob-credit">${T("Metro and bus")}: ${T("Royal Commission for Riyadh City (RCRC) open data, KSA Open Data License")}</div>`);
      if (on("bus")) rows.push(`<div class="mob-note">${T("Bus stops appear when you zoom in")}</div>`);
      if (on("hosp")) rows.push(`<div class="mob-note">${T("Hospitals")}: ${T("approximate positions")}</div>`);
      if (on("closures")) rows.push(`<div class="mob-leg">` + ["Requested", "Approved", "In Place"].map(c => `<span><i style="background:${CLOSURE[c]}"></i>${T(c)}</span>`).join("") + `</div>`);
      if (st.impact) {
        head = `<b>${T("Impact of {id}", { id: `<span dir="ltr">${esc(st.impact)}</span>` })}</b> · <b class="mob-mod">${T("Modelled")}</b>`;
        rows.push(`<div class="mob-leg">` + [["#d92d20", "Closed section"], ["#dc6803", "Worse after the closure"], ["#0284c7", "Detour"], ["#4b5563", "Usual route"]].map(([c, n]) => `<span><i style="background:${c}"></i>${T(n)}</span>`).join("") + `</div>` +
          `<div class="mob-note"><b>${T("Modelled")}</b> · ${T("calculated from the road network and synthetic demand, not measured")}</div>` +
          `<button class="mob-clear" type="button" data-clear>${T("Clear the impact drawing")}</button>`);
      }
      if (note) { rows.push(`<div class="mob-wait">${esc(note)}</div>`); info.open = true; }      // a wait or an error must be seen
      infoHead.innerHTML = head;
      infoBody.innerHTML = rows.join("");
      info.hidden = !rows.length;
    }

    /* The model is built in the background on the server. While it builds, say so and try again. */
    function waiting(e, again) {
      if (e.building) {
        const b = e.building, n = (b.hours_ready || []).length;
        renderInfo(T("Building the traffic model… {n} of 24 hours ready", { n }));
        clearTimeout(st.timer); st.timer = setTimeout(again, 3000);
      } else renderInfo(T("Could not load this layer: {m}", { m: e.message }));
    }

    // ---- traffic --------------------------------------------------------------------------------
    const line = (paths, color, width) => new Graphic({ geometry: { type: "polyline", paths, spatialReference: { wkid: 4326 } }, symbol: { type: "simple-line", color, width, cap: "round", join: "round" } });

    async function showTraffic() {
      if (!on("traffic")) return;
      const seq = ++st.seq, hour = st.hour;
      try {
        if (!st.roads) {
          const gj = await get("roads");
          st.roads = new Map(gj.features.map(f => [f.id, f.geometry.coordinates]));
          st.base = line([...st.roads.values()], [47, 170, 74, 0.45], 1);          // every modelled road, in the "free" colour, drawn once
        }
        const s = st.hours[hour] || (st.hours[hour] = await get("traffic?hour=" + hour));
        if (seq !== st.seq || !on("traffic")) return;                              // the slider moved on while this was loading
        const by = { slow: [], heavy: [], stopped: [] };
        for (const [id, v] of Object.entries(s.segments)) { const p = st.roads.get(id); if (p && by[v[1]]) by[v[1]].push(p); }
        L.traffic.removeAll();
        L.traffic.addMany([st.base, ...Object.keys(by).filter(c => by[c].length).map(c => line(by[c], FLOW[c], WIDTH[c]))]);
        st.totals = { busy: (s.counts.slow + s.counts.heavy + s.counts.stopped).toLocaleString(I18N.locale), speed: s.totals.avg_speed_kph };
        renderInfo();
      } catch (e) { if (seq === st.seq) waiting(e, showTraffic); }
    }

    // ---- metro, bus, hospitals --------------------------------------------------------------------
    const name = p => (I18N.rtl && p.Name_AR) || p.Name || "";
    const popup = (title, html) => ({ title: esc(title), content: html });

    async function loadMetro() {
      const [lines, stations] = await Promise.all([get("layers/metro_lines"), get("layers/metro_stations")]);
      const color = {};
      L.metro.addMany(lines.features.map(f => {
        const p = f.properties; color[p.Line_ID] = p.Color || "#4b5563";
        return new Graphic({ geometry: { type: "polyline", paths: [f.geometry.coordinates], spatialReference: { wkid: 4326 } }, attributes: p,
          symbol: { type: "simple-line", color: color[p.Line_ID], width: 3.2, cap: "round" }, popupTemplate: popup(name(p), esc((I18N.rtl && p.Terminals_AR) || p.Terminals || "")) });
      }));
      L.metro.addMany(stations.features.map(f => {
        const p = f.properties;
        return new Graphic({ geometry: { type: "point", longitude: f.geometry.coordinates[0], latitude: f.geometry.coordinates[1] }, attributes: p,
          symbol: { type: "simple-marker", style: "circle", color: "#ffffff", size: 6.5, outline: { color: color[p.Line_ID] || "#4b5563", width: 2 } },
          popupTemplate: popup(name(p), `${T("Metro station")} · ${esc(p.Line_Name || "")}`) });
      }));
    }

    async function loadBus() {
      const [routes, pts] = await Promise.all([get("layers/bus_routes"), get("layers/bus_stops")]);
      L.bus.add(line(routes.features.map(f => f.geometry.coordinates), [56, 189, 248, 0.75], 1.4));                       // one drawing for the 117 routes
      stops.add(new Graphic({ geometry: { type: "multipoint", points: pts.features.map(f => f.geometry.coordinates), spatialReference: { wkid: 4326 } },
        symbol: { type: "simple-marker", style: "circle", color: [56, 189, 248, 0.95], size: 4.5, outline: { color: "#ffffff", width: 0.6 } } }));
    }

    async function loadHosp() {
      const gj = await get("layers/hospitals");
      for (const f of gj.features) {
        const g = { type: "point", longitude: f.geometry.coordinates[0], latitude: f.geometry.coordinates[1] }, p = f.properties;
        L.hosp.add(new Graphic({ geometry: g, attributes: p, symbol: { type: "simple-marker", style: "square", color: "#ffffff", size: 14, outline: { color: "#d92d20", width: 1.6 } },
          popupTemplate: popup(p.Name, `${T("Hospital")} · ${T("approximate position")}`) }));
        L.hosp.add(new Graphic({ geometry: g, symbol: { type: "text", text: "H", color: "#d92d20", font: { size: 9, weight: "bold" }, yoffset: -3.5 } }));
      }
    }

    // ---- planned closures: asked for, approved or in place (the server decides which rows count) ----------------
    async function loadClosures(force) {
      if (!on("closures")) return;
      if (!force && Date.now() - st.closureAt < 8000) return;          // the page refreshes often; the closures change rarely
      st.closureAt = Date.now();
      const gj = await get("closures");
      L.closures.removeAll();
      for (const f of gj.features) {
        const p = f.properties, g = f.geometry; if (!g) continue;
        const paths = g.type === "MultiLineString" ? g.coordinates : [g.coordinates];
        const lanes = p.full_closure ? T("whole road closed") : T("{n} lane(s) closed", { n: p.lanes_closed });
        L.closures.add(new Graphic({ geometry: { type: "polyline", paths, spatialReference: { wkid: 4326 } }, attributes: p,
          symbol: { type: "simple-line", color: CLOSURE[p.status] || "#b54708", width: 5, style: p.status === "Requested" ? "short-dash" : "solid", cap: "round" },
          popupTemplate: popup(T("Planned closure") + ": " + (p.road || ""), `<b>${esc(TV(p.status))}</b> · ${esc(lanes)}<br><span dir="ltr">${esc(String(p.start_time).replace("T", " ").slice(0, 16))} → ${esc(String(p.end_time).replace("T", " ").slice(0, 16))}</span>` +
            `<br>${esc(TV(p.reason))}${p.incident_id ? "<br>" + esc(p.incident_id) : ""}`) }));
      }
    }

    // ---- the drawing of one simulation: closed section, worse road sections, detours (always MODELLED) -------------
    function clearImpact() {
      st.impact = null; st.impactSeq++; clearTimeout(st.impactTimer); impact.removeAll(); renderInfo();
    }
    async function showImpact(scenarioId) {
      const seq = ++st.impactSeq; clearTimeout(st.impactTimer);
      st.impact = scenarioId; info.open = true; renderInfo(T("Calculating the map drawing…"));
      try {
        const d = await get(`scenarios/${encodeURIComponent(scenarioId)}/map`);
        if (seq !== st.impactSeq) return;
        impact.removeAll();
        const lines = (coords, color, width, style) => new Graphic({ geometry: { type: "polyline", paths: coords, spatialReference: { wkid: 4326 } }, symbol: { type: "simple-line", color, width, style: style || "solid", cap: "round", join: "round" } });
        const paths = g => !g ? [] : g.type === "MultiLineString" ? g.coordinates : [g.coordinates];
        for (const f of (d.routes && d.routes.features) || []) {
          const k = f.properties.kind; if (k === "scenario") continue;
          impact.add(lines(paths(f.geometry), k === "detour" ? "#0284c7" : "#4b5563", k === "detour" ? 3.4 : 2, k === "detour" ? "solid" : "short-dash"));
        }
        for (const f of (d.segments && d.segments.features) || []) {
          const p = f.properties; if (p.status !== "worse" && p.status !== "new") continue;
          impact.add(lines(paths(f.geometry), LEVEL[p.scenario_level] || "#dc6803", 4.2));
        }
        if (d.closed && d.closed.geometry) impact.add(lines(paths(d.closed.geometry), "#d92d20", 6.5));
        renderInfo();
        const v = view && view();
        if (v && d.closed && d.closed.geometry) {                                       // bring the closed section into view
          const pts = paths(d.closed.geometry).flat(); const lon = pts.reduce((a, c) => a + c[0], 0) / pts.length, lat = pts.reduce((a, c) => a + c[1], 0) / pts.length;
          v.goTo({ center: [lon, lat], zoom: 13 }, { duration: 600 }).catch(() => {});
        }
      } catch (e) {
        if (seq !== st.impactSeq) return;
        if (e.building) st.impactTimer = setTimeout(() => showImpact(scenarioId), 3000);      // the drawing is being calculated again on the server
        else { st.impact = null; renderInfo(T("The impact drawing is not available: {m}", { m: e.message })); }
      }
    }

    const LOAD = { metro: loadMetro, bus: loadBus, hosp: loadHosp };
    async function show(k) {
      L[k].visible = on(k);
      if (k === "bus") stops.visible = on(k);
      hourRow.hidden = !on("traffic");
      renderInfo();
      if (!on(k)) { if (k === "traffic") clearTimeout(st.timer); return; }
      if (k === "traffic") return showTraffic();
      if (k === "closures") { try { await loadClosures(true); } catch (e) { waiting(e, () => show(k)); } return; }
      if (st.loaded[k]) return;
      st.loaded[k] = true;
      try { await LOAD[k](); } catch (e) { st.loaded[k] = false; waiting(e, () => show(k)); }
    }

    box.querySelectorAll("[data-mob]").forEach(c => {
      c.checked = recall(c.dataset.mob);
      c.addEventListener("change", () => { remember(c.dataset.mob, c.checked); show(c.dataset.mob); });
      if (c.checked) show(c.dataset.mob);
    });
    let debounce = 0;
    slider.addEventListener("input", () => {
      st.hour = +slider.value; out.textContent = pad(st.hour);
      clearTimeout(debounce); debounce = setTimeout(showTraffic, 120);
    });
    const refreshClosures = () => loadClosures(false).catch(() => {});
    return { layers: L, state: st, refresh: showTraffic, refreshClosures, showImpact, clearImpact };
  }

  window.Mobility = { attach };
})();
