/* Falcon Eye layout samples: made-up data, the drawn stand-in map and the shared behaviour. Nothing here calls the app's API. */
const CREW = [
  { id: "faisal", name: "Faisal", role: "Executive", c: "#1b8354" }, { id: "mansour", name: "Mansour", role: "Operations", c: "#1570ef" },
  { id: "sarah", name: "Sarah", role: "Water and leaks", c: "#0e7490" }, { id: "abdullah", name: "Abdullah", role: "Asset health", c: "#c4560a" },
  { id: "zayed", name: "Zayed", role: "Change and planning", c: "#d92d20" }, { id: "reem", name: "Reem", role: "Service impact", c: "#0f766e" },
  { id: "turki", name: "Turki", role: "Field operations", c: "#b45309" }, { id: "maha", name: "Maha", role: "Performance", c: "#2563eb" },
  { id: "nasser", name: "Nasser", role: "Traffic", c: "#be123c" }, { id: "noura", name: "Noura", role: "Mobility simulation", c: "#4d7c0f" },
  { id: "fahad", name: "Fahad", role: "Road safety and assets", c: "#92400e" },
];
const WORKING = ["noura", "turki"];
const STAGES = ["Detected", "Analysed", "Proposed", "Approved", "Dispatched", "Verified", "Resolved"];

/* kind: decision (waiting for an approval), field (a team is out), verify (a report came back), info (no action) */
const ITEMS = [
  { id: "INC-0034", apr: "APR-0006", kind: "decision", sev: "Critical", title: "Water leak (suspected)", place: "Olaya", agent: "sarah", stage: 2, ago: "2 min",
    msg: "Pressure on main W-118 dropped 31 % overnight while flow stayed level. Two citizen reports of water on Olaya Street.", if: "Work order P1 for the nearest leak team; a 2-lane closure on Olaya Street, 22:00 to 06:00.", x: 318, y: 196 },
  { id: "INC-0049", apr: "APR-0008", kind: "decision", sev: "Critical", title: "Streetlight failure (predicted)", place: "Al Malaz", agent: "abdullah", stage: 2, ago: "6 min",
    msg: "Twelve lamps on one feeder show the voltage pattern that came before the last three failures.", if: "Work order P1 to inspect feeder F-07 before dark.", x: 418, y: 286 },
  { id: "INC-0036", apr: "APR-0010", kind: "decision", sev: "High", title: "Traffic plan for a road closure", place: "King Fahd Road", agent: "noura", stage: 2, ago: "9 min",
    msg: "Full closure requested for 20 Nov, 08:00 to 16:00, for a utility crossing. Modelled: 1,340 extra trip-hours with no plan.", if: "Strategy B: detour by Olaya Street and timed signals. Modelled 420 extra trip-hours.", x: 300, y: 150, closure: true },
  { id: "INC-0029", apr: "APR-0009", kind: "decision", sev: "High", title: "Dispatch Khalid Al-Otaibi", place: "KAFD", agent: "turki", stage: 3, ago: "12 min",
    msg: "Best match for WO-0023: skill match, 0.3 km away, no open tasks.", if: "Khalid gets the task in ArcGIS Field Maps.", x: 352, y: 108 },
  { id: "INC-0033", apr: "APR-0007", kind: "decision", sev: "Medium", title: "Water leak (suspected)", place: "Al Malaz", agent: "sarah", stage: 2, ago: "18 min",
    msg: "Night flow on DMA-4 rose 14 % for three nights in a row.", if: "Work order P2 for a leak survey this week.", x: 392, y: 304 },
  { id: "INC-0031", kind: "field", sev: "High", title: "Leak survey in progress", place: "Al Wurud", agent: "turki", stage: 4, ago: "35 min",
    msg: "Hamad Al-Ghamdi is on site with the listening kit.", x: 262, y: 128 },
  { id: "INC-0027", kind: "verify", sev: "Medium", title: "Repair reported: pole PL-2210", place: "Diplomatic Quarter", agent: "abdullah", stage: 5, ago: "1 h",
    msg: "The crew replaced the pole base. Photo and readings attached; the incident can be closed.", x: 150, y: 214 },
  { id: "BRF-0012", kind: "info", sev: "Info", title: "Executive brief", place: "Riyadh", agent: "faisal", stage: -1, ago: "4 min",
    msg: "8 open incidents, 2 critical, 5 decisions waiting. Busiest area: Olaya." },
];
const TRAIL = {
  "INC-0034": [["sarah", "Spotted the pressure drop on W-118"], ["reem", "Found 1 school and 2 clinics within 300 m"], ["nasser", "Modelled the closure: small impact at night"], ["mansour", "Prepared work order P1"]],
};
const HANDOFFS = [["noura", "Modelled the King Fahd Road closure: 3 strategies"], ["turki", "Recommended Khalid Al-Otaibi for WO-0023"], ["sarah", "Spotted a pressure drop on W-118"], ["faisal", "Briefed leadership: 5 decisions waiting"]];

const $ = (s, r = document) => r.querySelector(s), $$ = (s, r = document) => [...r.querySelectorAll(s)];
const crew = id => CREW.find(c => c.id === id);
const SEV_C = { Critical: "var(--crit)", High: "var(--high)", Medium: "var(--med)", Low: "var(--low)", Info: "var(--line2)" };
const av = (id, sm) => { const c = crew(id); return `<span class="av${sm ? " sm" : ""}${WORKING.includes(id) ? " working" : ""}" style="--ac:${c.c}" title="${c.name}, ${c.role}">${c.name[0]}</span>`; };

function counts() {
  const open = ITEMS.filter(i => i.kind !== "info");
  return { decision: ITEMS.filter(i => i.kind === "decision").length, open: open.length, crit: open.filter(i => i.sev === "Critical").length, resolved: 14 };
}
function kpis(active) {
  const n = counts();
  const k = (key, cls, v, label) => `<button class="kpi ${cls}" type="button" data-filter="${key}" aria-pressed="${active === key}"><b>${v}</b><span>${label}</span></button>`;
  return k("decision", "hot", n.decision, "Waiting for your decision") + k("open", "", n.open, "Open incidents") + k("crit", "crit", n.crit, "Critical") + k("resolved", "", n.resolved, "Resolved this week");
}
function filtered(f) {
  if (f === "decision") return ITEMS.filter(i => i.kind === "decision");
  if (f === "crit") return ITEMS.filter(i => i.sev === "Critical");
  if (f === "resolved") return [];
  return ITEMS;
}
function row(i, sel, withActs = true) {
  const acts = withActs && i.kind === "decision" ? `<div class="acts"><button class="btn sm primary" data-approve="${i.apr}">Approve</button><button class="btn sm" data-reject="${i.apr}">Reject</button></div>` : "";
  return `<li class="row${i.kind === "info" ? " info" : ""}" role="option" tabindex="0" data-id="${i.id}" aria-selected="${sel === i.id}" style="--c:${SEV_C[i.sev]}">
    <span class="bar"></span><div><div class="t">${i.title} · ${i.place}</div><div class="m"><span class="sev ${i.sev}">${i.sev}</span>${av(i.agent, true)}<span>${crew(i.agent).name}</span><span>${i.ago} ago</span>${i.apr ? `<span>${i.apr}</span>` : ""}</div></div>${acts}</li>`;
}
function life(stage) {
  if (stage < 0) return "";
  return `<ol class="life" aria-label="Progress">${STAGES.map((s, k) => `<li class="${k < stage ? "done" : k === stage ? "now" : ""}"${k === stage ? ' aria-current="step"' : ""}>${s}</li>`).join("")}</ol>`;
}
function detail(id) {
  const i = ITEMS.find(x => x.id === id) || ITEMS[0];
  const trail = (TRAIL[i.id] || [[i.agent, "Raised this alert"]]).map(([a, d]) => `<li>${av(a, true)}<span><b>${crew(a).name}</b> ${d}</span></li>`).join("");
  const acts = i.kind === "decision" ? `<button class="btn primary" data-approve="${i.apr}">Approve ${i.apr}</button><button class="btn" data-reject="${i.apr}">Reject</button><button class="btn ghost" data-show="${i.id}">Show on map</button>`
    : i.kind === "verify" ? `<button class="btn primary" data-done="${i.id}">Close the incident</button><button class="btn">View report</button>`
    : i.kind === "field" ? `<button class="btn">Open investigator view</button><button class="btn ghost" data-show="${i.id}">Show on map</button>`
    : `<button class="btn" data-done="${i.id}">Got it</button>`;
  return `<div class="detail"><div class="m" style="display:flex;gap:8px;align-items:center;color:var(--mut);font-size:13px"><span class="sev ${i.sev}">${i.sev}</span><span>${i.id}</span><span>${i.ago} ago</span></div>
    <h3 style="margin-top:8px">${i.title} · ${i.place}</h3>${life(i.stage)}<p>${i.msg}</p>${i.if ? `<div class="if"><b>If approved</b>${i.if}</div>` : ""}<div class="acts">${acts}</div>
    <ul class="trail" aria-label="How the crew handled this">${trail}</ul></div>`;
}

/* A drawn stand-in for the ArcGIS map: Riyadh's main roads, not to scale. */
function mapSVG(sel) {
  const pins = ITEMS.filter(i => i.x).map(i => `<g class="pin${sel === i.id ? " sel" : ""}" data-id="${i.id}" tabindex="0" role="button" aria-label="${i.title}, ${i.place}">
    <circle class="halo" cx="${i.x}" cy="${i.y}" r="14" stroke="${SEV_C[i.sev]}"/><circle cx="${i.x}" cy="${i.y}" r="8" fill="${SEV_C[i.sev]}" stroke="#fff" stroke-width="2.5"/></g>`).join("");
  const roads = [["M300 20 L300 400", "major"], ["M60 70 C200 40 420 40 560 80", "major"], ["M40 250 L580 250", "major"], ["M480 30 C470 160 470 300 500 410", "major"], ["M90 390 C250 370 400 380 560 360", "major"],
    ["M330 40 L330 390", "minor"], ["M120 30 L140 400", "minor"], ["M200 60 L210 400", "minor"], ["M400 50 L410 400", "minor"], ["M60 160 L560 170", "minor"], ["M60 320 L560 320", "minor"]];
  const r = roads.map(([d, k]) => `<path class="road-edge" d="${d}" stroke-width="${k === "major" ? 12 : 6}"/>`).join("") + roads.map(([d, k]) => `<path class="road ${k}" d="${d}"/>`).join("");
  const blocks = [[145, 80, 50, 70], [215, 80, 75, 70], [340, 80, 55, 70], [415, 80, 50, 70], [145, 180, 50, 60], [215, 180, 75, 60], [340, 180, 55, 60], [415, 180, 50, 60], [145, 262, 50, 50], [215, 262, 75, 50], [340, 262, 55, 50], [415, 262, 50, 50], [70, 180, 40, 60], [500, 180, 50, 60]]
    .map(([x, y, w, h]) => `<rect class="block" x="${x}" y="${y}" width="${w}" height="${h}" rx="4"/>`).join("");
  const closure = ITEMS.find(i => i.closure);
  return `<svg viewBox="0 0 600 420" preserveAspectRatio="xMidYMid meet" role="img" aria-label="Map of open incidents in Riyadh (drawn stand-in)">
    <rect width="600" height="420" fill="transparent"/><rect class="park" x="70" y="262" width="40" height="50" rx="4"/>${blocks}${r}
    ${closure ? `<path class="closure" d="M300 100 L300 210"/>` : ""}
    <text class="rlbl" x="306" y="36">KING FAHD RD</text><text class="rlbl" x="420" y="244">MAKKAH RD</text><text class="rlbl" x="470" y="70" transform="rotate(8 470 70)">NORTHERN RING</text>
    <text class="lbl" x="336" y="210">Olaya</text><text class="lbl" x="360" y="104">KAFD</text><text class="lbl" x="426" y="300">Al Malaz</text><text class="lbl" x="96" y="232">Diplomatic Quarter</text><text class="lbl" x="232" y="124">Al Wurud</text>${pins}</svg>`;
}
const mapTag = () => `<div class="map-tag"><span><i style="background:var(--crit)"></i>Critical</span><span><i style="background:var(--high)"></i>High</span><span><i style="background:var(--med)"></i>Medium</span><span style="color:var(--mut)">Drawn stand-in for the ArcGIS map</span></div>`;
const mapLayers = () => ["Traffic", "Metro", "Bus", "Hospitals", "Planned closures", "Urban change"].map((l, k) => `<button class="chip" type="button" aria-pressed="${k === 4}">${l}</button>`).join("");

function toast(t) { const d = document.createElement("div"); d.className = "toast"; d.setAttribute("role", "status"); d.textContent = t; document.body.append(d); setTimeout(() => d.remove(), 3200); }

/* Approve and Reject: the first press arms, a second press within 5 s acts, as on the real page. */
function wire(root, onSelect) {
  root.addEventListener("click", e => {
    const b = e.target.closest("[data-approve],[data-reject]");
    if (b) {
      e.stopPropagation();
      if (!b.dataset.armed) {
        b.dataset.armed = "1"; b.dataset.text = b.textContent; b.textContent = "Confirm?"; b.classList.add("armed");
        b._t = setTimeout(() => { delete b.dataset.armed; b.textContent = b.dataset.text; b.classList.remove("armed"); }, 5000); return;
      }
      clearTimeout(b._t);
      const id = b.dataset.approve || b.dataset.reject;
      toast(b.dataset.approve ? `Sample only: ${id} would be approved.` : `Sample only: ${id} would be rejected. Nothing changes.`);
      delete b.dataset.armed; b.textContent = b.dataset.text; b.classList.remove("armed"); return;
    }
    const d = e.target.closest("[data-done]"); if (d) { toast("Sample only: nothing is changed."); return; }
    const s = e.target.closest("[data-id],[data-show]"); if (s) onSelect(s.dataset.id || s.dataset.show);
  });
  root.addEventListener("keydown", e => { if ((e.key === "Enter" || e.key === " ") && e.target.matches("[data-id]")) { e.preventDefault(); onSelect(e.target.dataset.id); } });
}
const header = (extra = "") => `<header class="top"><div class="brand"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M2 11C5 6 8.5 4.5 12 4.5S19 6 22 11C19 16 15.5 17.5 12 17.5S5 16 2 11Z"/><circle cx="12" cy="11" r="3.8"/></svg>Falcon Eye</div>
  ${extra}<span class="status"><span class="pulse"></span>AI agents on · last scan 1 min ago</span>
  <details class="menu"><summary class="btn">Demo tools</summary><div class="menu-pop"><small>Run</small><button>Scan now</button><button>Compare imagery</button><small>Simulate an event</small><button>Water leak</button><button>Road closure</button><button>Major event</button></div></details>
  <button class="iconbtn" aria-label="Alerts, 5 unread"><svg viewBox="0 0 24 24"><path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9M10.3 21a1.94 1.94 0 0 0 3.4 0"/></svg><span class="n">5</span></button>
  <button class="btn ghost" lang="ar">العربية</button></header>`;
const sampleBar = name => `<div class="sample-bar"><b>Layout sample ${name}</b><span>Made-up data; buttons act only on this page.</span><a href="index.html">Back to the choices</a></div>`;
