/* Operational Center (Mansour): crew status, triage queue, approvals with toasts, actionable map points, demo event controls. */
require(["esri/Map", "esri/views/MapView", "esri/layers/GraphicsLayer", "esri/Graphic"], (Map, MapView, GraphicsLayer, Graphic) => {
  const { esc, api, toast } = R;
  const layers = { inc: new GraphicsLayer(), workers: new GraphicsLayer(), pick: new GraphicsLayer() };
  const map = new Map({ basemap: "dark-gray-vector", layers: [layers.inc, layers.workers, layers.pick] });
  const view = new MapView({ container: "map", map, center: [46.67, 24.71], zoom: 11 });
  let state = null;

  const EVENTS = [["olaya_leak", "Water main leak · Olaya"], ["multi_incident", "Pressure faults · 3 areas"], ["king_fahd_lights", "Streetlight decay · King Fahd Rd"],
    ["imagery_change", "New satellite pass"], ["imagery_critical", "Critical urban change"], ["citizen_surge", "Citizen reports · Al Malaz"], ["random", "Random city event"]];
  document.getElementById("ev").innerHTML = EVENTS.map(([v, t]) => `<option value="${v}">${esc(t)}</option>`).join("");

  const incSym = p => {
    const crit = p.Priority === "P1" || p.Severity === "Critical";
    return { type: "simple-marker", color: crit ? "#f0564a" : "#f5a524", size: crit ? 13 : 9, outline: { color: "white", width: 1 } };
  };
  const workerSym = () => ({ type: "simple-marker", style: "diamond", color: "#34c38f", size: 10, outline: { color: "white", width: 1 } });

  function renderCrew(agents) {
    document.getElementById("agents").innerHTML = agents.map(a => {
      const on = !!a.working;
      return `<div class="chip" title="${esc(a.role)}"><b>${esc(a.name)}</b><span><i class="dot ${on ? "on" : ""}"></i><em>${esc(on ? a.working : a.last_action || "Idle")}</em></span></div>`;
    }).join("");
  }

  function renderTriage(notes) {
    const q = notes.filter(n => n.Status === "New");
    document.getElementById("tcount").textContent = q.length;
    document.getElementById("triage").innerHTML = q.length ? q.slice(0, 30).map(n =>
      `<div class="card click" data-nid="${esc(n.Notif_ID)}" data-inc="${esc(n.Incident_ID)}" data-lon="${n.Lon ?? ""}" data-lat="${n.Lat ?? ""}">
        <div class="meta"><span>${esc(n.Agent)} · ${esc(n.Area_Name)}</span><span>${esc(n.Severity)}</span></div><div class="title">${esc(n.Title)}</div>
        <div class="desc">${esc(n.Message)}</div></div>`).join("") : `<div class="empty">Queue is clear. Inject an event to watch the crew react.</div>`;
  }

  function renderApprovals(list) {
    document.getElementById("acount").textContent = list.length;
    document.getElementById("approvals").innerHTML = list.length ? list.map(a =>
      `<div class="card" id="ap-${esc(a.Approval_ID)}" data-loc="${esc(a.Target || "")}">
        <div class="meta"><span>${esc(a.Action_Type)} · ${esc(a.Team || "")}</span><span>${esc(a.Priority || "")}</span></div>
        <div class="title">${esc(a.Summary)}</div><div class="desc">Expected: ${esc(a.Expected_Result || "")}</div>
        <div class="btns"><button class="b go" data-act="approve" data-id="${esc(a.Approval_ID)}">Approve</button><button class="b" data-act="reject" data-id="${esc(a.Approval_ID)}">Reject</button></div></div>`).join("")
      : `<div class="empty">Nothing waiting. The AI proposes, you approve.</div>`;
  }

  function renderActivity(act) {
    document.getElementById("activity").innerHTML = act.slice(0, 8).map(s =>
      `<div class="card"><div class="meta"><span>${esc(s.agent)}</span><span>${esc((s.at || "").slice(11, 19))}</span></div><div class="title">${esc(s.action)}</div><div class="desc">${esc(s.detail || "")}</div></div>`).join("")
      || `<div class="empty">No activity yet.</div>`;
  }

  async function refresh() {
    try {
      state = await api("/api/nccc/state");
      renderCrew(state.crew.agents);
      renderTriage(state.notifications);
      renderApprovals(state.approvals);
      renderActivity(state.crew.activity);
      const au = document.getElementById("auto");
      au.textContent = "Autopilot: " + (state.crew.autopilot ? "on" : "off");
      await Promise.all([R.loadLayer(layers.inc, "Riyadh_Operational_Incidents", incSym, Graphic, "", p => ({ title: `${p.Incident_ID} · ${p.Incident_Type}`, html: `<b>${esc(p.Area_Name)}</b> · ${esc(p.Priority)} ${esc(p.Severity)} · ${esc(p.Status)}<br>${esc(p.Description || "")}` })), R.loadLayer(layers.workers, "Riyadh_Field_Workers", workerSym, Graphic)]);
    } catch (e) { toast("Refresh failed", e.message, true); }
  }

  const fly = (lon, lat, z = 15) => view.goTo({ center: [lon, lat], zoom: z }, { duration: 700 });

  async function decide(id, act) {
    const btns = document.querySelectorAll(`#ap-${CSS.escape(id)} button`);
    btns.forEach(b => b.disabled = true);
    try {
      const r = await api(`/api/approvals/${id}/${act}`, { method: "POST" });
      toast(act === "approve" ? "Approved" : "Rejected", act === "approve" ? (r.work_order_id ? `Work order ${r.work_order_id} created and confirmed by read-back.` : r.message || `${id} executed and confirmed.`) : `${id} rejected. Nothing was executed.`);
    } catch (e) { toast("Action failed", e.message, true); }
    await refresh();
  }

  document.addEventListener("click", async e => {
    const b = e.target.closest("button[data-act]");
    if (b) return decide(b.dataset.id, b.dataset.act);
    const c = e.target.closest(".card.click");
    if (c) {
      if (c.dataset.lon && c.dataset.lat) fly(+c.dataset.lon, +c.dataset.lat);
      if (c.dataset.nid) api(`/api/nccc/notifications/${c.dataset.nid}/ack`, { method: "POST" }).then(refresh).catch(() => {});
      // Find an approval tied to this incident and highlight it.
      const ap = state && state.notifications.find(n => n.Notif_ID === c.dataset.nid)?.approval;
      if (ap) highlight(ap.id);
    }
  });

  function highlight(aid) {
    const el = document.getElementById("ap-" + aid);
    if (!el) return;
    el.scrollIntoView({ behavior: "smooth", block: "center" });
    el.classList.add("highlight");
    setTimeout(() => el.classList.remove("highlight"), 2500);
  }

  // Actionable map point: click an incident -> fly, show details and open its approval card if one is waiting.
  view.on("click", async ev => {
    const hit = (await view.hitTest(ev, { include: [layers.inc] })).results[0];
    if (!hit) return;
    const a = hit.graphic.attributes;
    const note = state && state.notifications.find(n => n.Incident_ID === a.Incident_ID && n.approval && n.approval.status === "Proposed");
    if (note) highlight(note.approval.id);
  });

  const busy = (btn, on) => { btn.disabled = on; };
  document.getElementById("inject").onclick = async function () {
    const name = document.getElementById("ev").value;
    busy(this, true);
    try {
      const r = await api(`/api/nccc/events/${name}`, { method: "POST" });
      const n = (r.scan?.new_incidents || []).length;
      toast("Event injected", n ? `Crew opened ${n} new incident(s).` : "Crew is analysing the event.");
    } catch (e) { toast("Event failed", e.message, true); }
    busy(this, false);
    refresh();
  };
  document.getElementById("scan").onclick = async function () {
    busy(this, true);
    try { await api("/api/nccc/scan?deep=true", { method: "POST" }); toast("Scan complete", "The crew checked sensors, lights and imagery."); } catch (e) { toast("Scan failed", e.message, true); }
    busy(this, false);
    refresh();
  };
  document.getElementById("auto").onclick = async function () {
    const on = !state?.crew.autopilot;
    try { await api(`/api/nccc/autopilot?on=${on}&interval=20`, { method: "POST" }); toast("Autopilot " + (on ? "on" : "off")); } catch (e) { toast("Failed", e.message, true); }
    refresh();
  };

  refresh();
  setInterval(refresh, 8000);
});
