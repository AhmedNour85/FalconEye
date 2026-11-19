/* Set 4: shadcn/ui patterns rebuilt in plain HTML with the Tailwind CDN (samples only; the app has no build step).
   Data, the states menu values and the real map come from live-samples.js; nothing here calls the app's API.
   Names start with uk so they never collide with live-samples.js. */
tailwind.config = {
  darkMode: "class",
  theme: { extend: {
    colors: {
      border: "hsl(var(--border))", input: "hsl(var(--input))", ring: "hsl(var(--ring))", background: "hsl(var(--background))", foreground: "hsl(var(--foreground))",
      primary: { DEFAULT: "hsl(var(--primary))", foreground: "hsl(var(--primary-foreground))" },
      secondary: { DEFAULT: "hsl(var(--secondary))", foreground: "hsl(var(--secondary-foreground))" },
      destructive: { DEFAULT: "hsl(var(--destructive))", foreground: "hsl(var(--destructive-foreground))" },
      muted: { DEFAULT: "hsl(var(--muted))", foreground: "hsl(var(--muted-foreground))" },
      accent: { DEFAULT: "hsl(var(--accent))", foreground: "hsl(var(--accent-foreground))" },
      card: { DEFAULT: "hsl(var(--card))", foreground: "hsl(var(--card-foreground))" },
      popover: { DEFAULT: "hsl(var(--popover))", foreground: "hsl(var(--popover-foreground))" },
    },
    borderRadius: { lg: "var(--radius)", md: "calc(var(--radius) - 2px)", sm: "calc(var(--radius) - 4px)" },
    fontFamily: { sans: ['"IBM Plex Sans Arabic"', "system-ui", "sans-serif"] },
  } },
};

/* theme: saved per viewer; a page can default to dark */
function ukTheme(defaultDark) {
  let saved = null; try { saved = localStorage.getItem("fe-sample-theme"); } catch (e) {}
  const dark = saved ? saved === "dark" : !!defaultDark;
  document.documentElement.classList.toggle("dark", dark);
}
function ukToggleTheme() {
  const dark = !document.documentElement.classList.contains("dark");
  document.documentElement.classList.toggle("dark", dark);
  try { localStorage.setItem("fe-sample-theme", dark ? "dark" : "light"); } catch (e) {}
  if (typeof MAP !== "undefined" && MAP && MAP.view) MAP.view.map.basemap = dark ? "dark-gray-vector" : "gray-vector";   // MAP is a let in live-samples.js, so not on window
  $$("[data-uk=theme]").forEach(b => b.setAttribute("aria-pressed", dark));
}

/* Button, Badge, Card: the shadcn variants */
const UK_BTN = "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-medium transition-colors ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 active:scale-[.98]";
const UK_VAR = { default: "bg-primary text-primary-foreground shadow-sm hover:bg-primary/90", outline: "border border-input bg-background shadow-sm hover:bg-accent hover:text-accent-foreground",
  secondary: "bg-secondary text-secondary-foreground hover:bg-secondary/80", ghost: "hover:bg-accent hover:text-accent-foreground", destructive: "bg-destructive text-destructive-foreground hover:bg-destructive/90",
  link: "text-primary underline-offset-4 hover:underline" };
const UK_SIZE = { default: "h-9 px-4 py-2", sm: "h-8 px-3 text-xs", lg: "h-10 px-6", icon: "h-9 w-9" };
const ukBtn = (label, v = "default", s = "default", attrs = "") => `<button type="button" class="${UK_BTN} ${UK_VAR[v]} ${UK_SIZE[s]}" ${attrs}>${label}</button>`;
const UK_SEV = { Critical: "border-red-500/25 bg-red-500/10 text-red-700 dark:text-red-400", High: "border-orange-500/25 bg-orange-500/10 text-orange-700 dark:text-orange-400",
  Medium: "border-amber-500/30 bg-amber-500/10 text-amber-800 dark:text-amber-300", Low: "border-blue-500/25 bg-blue-500/10 text-blue-700 dark:text-blue-400", Info: "border-border bg-muted text-muted-foreground" };
const UK_DOT = { Critical: "bg-red-600", High: "bg-orange-500", Medium: "bg-amber-500", Low: "bg-blue-600", Info: "bg-slate-400" };
const ukBadge = (text, sev) => `<span class="inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 text-xs font-semibold ${UK_SEV[sev] || UK_SEV.Info}"><span class="h-1.5 w-1.5 rounded-full ${UK_DOT[sev] || UK_DOT.Info}" aria-hidden="true"></span>${text}</span>`;
const ukCard = (inner, cls = "") => `<div class="rounded-lg border bg-card text-card-foreground shadow-sm ${cls}">${inner}</div>`;
const ukAvatar = (id, size = "h-8 w-8 text-xs") => { const a = AG[id]; return `<span class="inline-grid ${size} shrink-0 place-items-center rounded-full font-semibold text-[#08130e] ring-2 ring-background" style="background:${a.color}" title="${esc(a.name)} · ${esc(a.role)}">${a.name[0]}</span>`; };
const ukStatus = n => n.done ? (n.done === "approve" ? "Approved" : "Rejected") : n.error ? "Failed" : n.apr ? "Needs decision" : n.kind === "verified" ? "Ready to check" : "Info";

/* lifecycle as a segmented progress bar with its step named */
function ukLife(stage) {
  if (stage < 0) return "";
  return `<div class="mt-3"><div class="flex gap-1" role="img" aria-label="Progress: ${STEPS[stage]}, step ${stage + 1} of ${STEPS.length}">${STEPS.map((s, k) =>
    `<span class="h-1.5 flex-1 rounded-full ${k < stage ? "bg-primary" : k === stage ? "bg-blue-500" : "bg-muted"}" title="${s}"></span>`).join("")}</div>
    <p class="mt-1.5 text-xs text-muted-foreground"><span class="font-medium text-foreground">${STEPS[stage]}</span> · step ${stage + 1} of ${STEPS.length}${STEPS[stage + 1] ? " · next: " + STEPS[stage + 1] : ""}</p></div>`;
}
function ukActions(n, size = "sm") {
  const ref = esc((n.inc || n.id) + " · " + n.title);
  let h = "";
  if (n.done) h = `<p class="flex items-center gap-2 text-sm font-medium ${n.done === "approve" ? "text-primary" : "text-muted-foreground"}">${n.done === "approve" ? "✓ " : ""}${esc(n.result)}</p>`;
  else if (n.error && !isViewer()) h = `<div role="alert" class="w-full rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-700 dark:text-red-400">${esc(n.error)}</div>`
    + ukBtn("Try again", "default", size, `data-uk="retry" data-id="${n.apr}" aria-label="Try again to approve ${ref}"`) + ukBtn("Reject", "outline", size, `data-uk="reject" data-id="${n.apr}" aria-label="Reject ${ref}"`);
  else if (n.apr && !isViewer()) h = ukBtn("Approve", "default", size, `data-uk="approve" data-id="${n.apr}" aria-label="Approve ${ref}"`) + ukBtn("Reject", "outline", size, `data-uk="reject" data-id="${n.apr}" aria-label="Reject ${ref}"`);
  else if (n.apr) h = `<p class="text-sm text-muted-foreground">Waiting for an operator to decide</p>`;
  else if (n.kind === "verified") h = ukBtn("View report", "outline", size, `data-uk="ack" aria-label="View report for ${ref}"`);
  else h = ukBtn("Got it", "ghost", size, `data-uk="ack" aria-label="Got it: ${ref}"`);
  if (n.lon && !n.done) h += ukBtn("Show on map", "link", size, `data-uk="show" data-id="${n.id}" aria-label="Show ${ref} on the map"`);
  return `<div class="flex flex-wrap items-center gap-2">${h}</div>`;
}
function ukTrail(n) {
  return `<ul class="space-y-2">${n.trail.map(([a, d]) => `<li class="flex items-center gap-2 text-sm">${ukAvatar(a, "h-6 w-6 text-[11px]")}<span class="min-w-0"><span class="font-medium">${AG[a].name}</span> <span class="text-muted-foreground">${esc(d)}</span></span></li>`).join("")}</ul>`;
}
/* the full alert, as used in a sheet, a card list or a map overlay */
function ukDetail(n, headingTag = "h3") {
  return `<div class="flex items-start gap-3">${ukAvatar(n.agent, "h-9 w-9 text-sm")}<div class="min-w-0 flex-1">
      <div class="flex flex-wrap items-center gap-2">${ukBadge(n.sev, n.sev)}<span class="text-xs text-muted-foreground">${n.ago}${n.inc ? " · " + n.inc : ""}${n.apr ? " · " + n.apr : ""}</span></div>
      <${headingTag} class="mt-1.5 font-semibold leading-snug [overflow-wrap:anywhere]">${esc(n.title)}</${headingTag}></div></div>
    ${ukLife(n.stage)}
    <p class="mt-3 text-sm leading-relaxed [overflow-wrap:anywhere]">${esc(n.msg)}</p>
    ${n.expected && !n.done ? `<div class="mt-3 rounded-md border bg-muted/50 px-3 py-2 text-sm"><span class="block text-xs font-medium uppercase tracking-wide text-muted-foreground">If approved</span>${esc(n.expected)}</div>` : ""}
    <div class="mt-4">${ukActions(n)}</div>
    <details class="group mt-4 border-t pt-3"><summary class="flex cursor-pointer list-none items-center justify-between rounded-sm text-sm font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">How the crew handled this<span class="text-muted-foreground transition-transform group-open:rotate-180" aria-hidden="true">▾</span></summary><div class="pt-3">${ukTrail(n)}</div></details>`;
}

/* states: loading, empty, offline, viewer (long is handled in the data) */
function ukStateBlock() {
  if (S.state === "loading") return `<div role="status" aria-busy="true" aria-label="Loading alerts" class="space-y-3 p-4">${'<div class="h-20 animate-pulse rounded-md bg-muted"></div>'.repeat(3)}</div>`;
  if (S.state === "empty") return `<div role="status" class="grid justify-items-center gap-2 px-6 py-12 text-center"><p class="font-semibold">No alerts right now</p><p class="text-sm text-muted-foreground">The crew is watching the feeds. New findings appear here.</p>${ukBtn("Scan now", "outline", "sm", 'data-uk="ack"')}</div>`;
  if (S.state === "offline") return `<div role="alert" class="m-4 rounded-lg border border-red-500/30 bg-red-500/10 p-4"><p class="font-semibold text-red-700 dark:text-red-400">Can't reach the server</p><p class="mt-1 text-sm">Showing nothing rather than old data. Trying again every 5 seconds.</p><div class="mt-3">${ukBtn("Try again now", "outline", "sm", 'data-uk="ack"')}</div></div>`;
  return "";
}
const ukViewerNote = () => isViewer() ? `<div role="note" class="rounded-md border border-blue-500/25 bg-blue-500/10 px-3 py-2 text-sm text-blue-700 dark:text-blue-300">You are signed in as a viewer: you can follow every alert, but only an operator can approve or reject.</div>` : "";

/* Toast (sonner-like) and the screen-reader live region */
function ukToast(t, tone = "") {
  let box = $("#uk-toasts"); if (!box) { box = document.createElement("div"); box.id = "uk-toasts"; box.className = "fixed bottom-4 right-4 z-50 flex w-[min(380px,calc(100vw-2rem))] flex-col gap-2"; document.body.append(box); }
  const d = document.createElement("div"); d.className = `rounded-lg border bg-popover px-4 py-3 text-sm text-popover-foreground shadow-lg ${tone}`; d.textContent = t; box.append(d); setTimeout(() => d.remove(), 4000);
}

/* AlertDialog: the confirm step for Approve and Reject (replaces the real page's two-press button) */
let UK_LAST = null;
function ukDialogs() {
  document.body.insertAdjacentHTML("beforeend", `<dialog id="uk-confirm" class="uk-modal w-[min(460px,calc(100vw-2rem))] rounded-lg border bg-background p-0 shadow-lg" aria-labelledby="uk-c-t" aria-describedby="uk-c-d">
    <form method="dialog" class="grid gap-4 p-6"><div class="grid gap-2"><h2 id="uk-c-t" class="text-lg font-semibold"></h2><p id="uk-c-d" class="text-sm text-muted-foreground"></p></div>
    <div class="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">${ukBtn("Cancel", "outline", "default", 'value="cancel" id="uk-c-no" type="submit" autofocus')}${ukBtn("", "default", "default", 'id="uk-c-yes"')}</div></form></dialog>`);
  $("#uk-confirm").addEventListener("close", () => { if (UK_LAST && document.contains(UK_LAST)) UK_LAST.focus(); });
}
function ukConfirm(btn, act) {
  const id = btn.dataset.id, n = ALERTS.find(a => a.apr === id), d = $("#uk-confirm"), yes = $("#uk-c-yes");
  UK_LAST = btn;
  $("#uk-c-t").textContent = act === "approve" ? `Approve ${id}?` : `Reject ${id}?`;
  $("#uk-c-d").textContent = act === "approve" ? `${n.title}. If approved: ${n.expected}` : `${n.title}. Nothing will be carried out, and the crew records that you rejected it.`;
  yes.textContent = act === "approve" ? `Approve ${id}` : `Reject ${id}`;
  yes.className = `${UK_BTN} ${UK_VAR[act === "approve" ? "default" : "destructive"]} ${UK_SIZE.default}`;
  yes.disabled = false; d.removeAttribute("aria-busy");
  yes.onclick = () => ukRun(id, act, true);
  d.showModal();
}
async function ukRun(id, act, fromDialog) {
  const n = ALERTS.find(a => a.apr === id), d = $("#uk-confirm"), yes = $("#uk-c-yes");
  if (fromDialog) { yes.disabled = true; $("#uk-c-no").disabled = true; d.setAttribute("aria-busy", "true"); yes.textContent = act === "approve" ? "Approving…" : "Rejecting…"; }
  else $$(`[data-id="${id}"]`).forEach(b => { b.disabled = true; if (b.dataset.uk === "retry") b.textContent = "Approving…"; });
  await new Promise(r => setTimeout(r, 900));
  $("#uk-c-no").disabled = false; UK_LAST = null;
  if (d.open) d.close();
  if (act === "approve" && FAIL_ONCE.has(id)) {
    FAIL_ONCE.delete(id); n.error = `Couldn't approve ${id}: ArcGIS Online refused the change because the layer is busy. Nothing was changed.`;
    UK.render(); announce(n.error); const r = $(`[data-uk="retry"][data-id="${id}"]`); if (r) r.focus(); return;
  }
  n.error = ""; n.done = act; n.result = act === "approve" ? `Approved and done · ${WO[id]} created` : "Rejected · nothing was changed";
  UK.render();
  const msg = act === "approve" ? `${id} approved. ${WO[id]} created.` : `${id} rejected. Nothing was changed.`;
  announce(msg); ukToast("Sample only: " + msg);
  const next = $('[data-uk="approve"]:not([disabled])') || $("#alerts-h"); if (next) { if (next.tagName === "H2") next.tabIndex = -1; next.focus(); }
}

/* the real ArcGIS map, light or dark basemap */
function ukMap(id = "map", onPick) {
  const box = document.getElementById(id);
  if (S.state === "offline" || !window.require) { box.innerHTML = `<div class="grid h-full place-items-center bg-muted p-6 text-center" role="status"><div><p class="font-semibold">Map unavailable</p><p class="text-sm text-muted-foreground">The map needs internet access to js.arcgis.com.</p></div></div>`; return; }
  require(["esri/Map", "esri/views/MapView", "esri/layers/GraphicsLayer", "esri/Graphic"], (Map, MapView, GraphicsLayer, Graphic) => {
    const layer = new GraphicsLayer(), col = { Critical: "#dc2626", High: "#f97316", Medium: "#f59e0b", Low: "#2563eb" };
    ALERTS.filter(a => a.lon).forEach(a => layer.add(new Graphic({ geometry: { type: "point", longitude: a.lon, latitude: a.lat },
      symbol: { type: "simple-marker", color: col[a.sev], size: a.sev === "Critical" ? 14 : 11, outline: { color: "#ffffff", width: 2 } }, attributes: { id: a.id } })));
    const dark = document.documentElement.classList.contains("dark");
    const view = new MapView({ container: id, map: new Map({ basemap: dark ? "dark-gray-vector" : "gray-vector", layers: [layer] }), center: [46.68, 24.71], zoom: 11, ui: { components: ["zoom"] }, popup: { autoOpenEnabled: false } });
    view.on("click", ev => view.hitTest(ev).then(r => { const g = r.results.find(x => x.graphic && x.graphic.attributes && x.graphic.attributes.id); if (g && onPick) onPick(g.graphic.attributes.id); }));
    MAP = { view };
  });
}

/* the header every set-4 page shares */
const UK_LOGO = `<svg viewBox="0 0 24 24" class="h-7 w-7 fill-none stroke-primary" stroke-width="1.7" stroke-linecap="round" aria-hidden="true"><path d="M2 11C5 6 8.5 4.5 12 4.5S19 6 22 11C19 16 15.5 17.5 12 17.5S5 16 2 11Z"/><circle cx="12" cy="11" r="3.8"/><circle cx="12" cy="11" r="1.5" class="fill-primary stroke-none"/></svg>`;
function ukTools(extra = "") {
  return `<div class="flex items-center gap-1 sm:gap-2">${extra}
    <label class="hidden items-center gap-2 text-sm sm:flex"><input type="checkbox" checked class="peer sr-only" role="switch" aria-label="AI Agents"><span class="relative h-5 w-9 rounded-full bg-input transition-colors peer-checked:bg-primary peer-focus-visible:ring-2 peer-focus-visible:ring-ring after:absolute after:left-0.5 after:top-0.5 after:h-4 after:w-4 after:rounded-full after:bg-background after:shadow after:transition-transform peer-checked:after:translate-x-4"></span><span aria-hidden="true">AI Agents</span></label>
    <details class="relative"><summary class="${UK_BTN} ${UK_VAR.outline} ${UK_SIZE.sm} list-none" aria-label="Demo tools"><span class="hidden sm:inline">Demo tools</span><span class="sm:hidden" aria-hidden="true">•••</span></summary>
      <div class="absolute right-0 z-40 mt-2 w-56 rounded-md border bg-popover p-1 text-popover-foreground shadow-md">
        ${["Scan now", "Compare imagery", "Simulate a water leak", "Simulate a road closure", "Simulate a major event"].map(t => `<button type="button" data-uk="ack" class="flex w-full rounded-sm px-2 py-1.5 text-left text-sm hover:bg-accent focus-visible:bg-accent focus-visible:outline-none">${t}</button>`).join("")}</div></details>
    ${ukBtn('<svg viewBox="0 0 24 24" class="h-4 w-4 fill-none stroke-current" stroke-width="2" aria-hidden="true"><path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/></svg>', "ghost", "icon", 'data-uk="theme" aria-label="Dark mode" aria-pressed="false"')}
    <button type="button" class="${UK_BTN} ${UK_VAR.ghost} ${UK_SIZE.icon} relative" aria-label="Alerts, 5 unread"><svg viewBox="0 0 24 24" class="h-4 w-4 fill-none stroke-current" stroke-width="2" aria-hidden="true"><path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9M10.3 21a1.94 1.94 0 0 0 3.4 0"/></svg><span class="absolute -right-0.5 -top-0.5 rounded-full bg-destructive px-1.5 text-[10px] font-semibold leading-4 text-destructive-foreground">5</span></button>
    ${ukBtn('<span class="hidden sm:inline">العربية</span><span class="sm:hidden">ع</span>', "ghost", "sm", 'lang="ar" aria-label="العربية"')}</div>`;
}
function ukStats() {
  const w = waiting().length, st = (label, v, sub, cls = "", attrs = "") => `<div class="rounded-lg border bg-card p-4 shadow-sm ${cls}" ${attrs}><p class="text-sm font-medium text-muted-foreground">${label}</p><p class="mt-1 text-2xl font-semibold tabular-nums">${v}</p><p class="mt-0.5 text-xs text-muted-foreground">${sub}</p></div>`;
  return st("Waiting for your decision", `<span class="text-primary">${w}</span>`, "Oldest waiting 18 min", "ring-1 ring-primary/30") + st("Open incidents", 8, "3 in Olaya") + st("Critical", `<span class="text-red-600 dark:text-red-400">2</span>`, "Both water and power") + st("Resolved", 14, "This week");
}
function ukSampleBar(name) {
  const bar = document.createElement("div");
  bar.className = "flex flex-wrap items-center gap-x-4 gap-y-2 bg-zinc-900 px-4 py-2 text-[13px] text-zinc-200";
  bar.innerHTML = `<b class="text-white">${name}</b><span>Made-up data; the buttons only show what would happen.</span>
    <label class="flex items-center gap-2">Preview a state <select id="uk-state" class="rounded-md border border-zinc-700 bg-zinc-800 px-2 py-1 text-white">${[["normal", "Normal"], ["loading", "Loading"], ["empty", "No alerts"], ["offline", "Server offline"], ["viewer", "Signed in as viewer"], ["long", "Long names"]].map(([v, t]) => `<option value="${v}"${S.state === v ? " selected" : ""}>${t}</option>`).join("")}</select></label>
    <a class="inline-flex min-h-8 items-center text-emerald-300 underline-offset-4 hover:underline" href="index.html">Back to the choices</a>`;
  document.body.prepend(bar);
  $("#uk-state").onchange = e => { const u = new URL(location.href); u.searchParams.set("state", e.target.value); location.href = u; };
}

/* one click handler for every page; a page sets UK.render and UK.open */
const UK = { render() {}, open() {} };
function ukWire() {
  ukDialogs();
  document.addEventListener("click", e => {
    const b = e.target.closest("[data-uk]"); if (!b) return;
    const k = b.dataset.uk;
    if (k === "approve" || k === "reject") return ukConfirm(b, k);
    if (k === "retry") return ukRun(b.dataset.id, "approve", false);
    if (k === "theme") return ukToggleTheme();
    if (k === "show") { const n = ALERTS.find(a => a.id === b.dataset.id); if (n && MAP) MAP.view.goTo({ center: [n.lon, n.lat], zoom: 14 }, { duration: 600 }); return; }
    if (k === "open") return UK.open(b.dataset.id);
    ukToast("Sample only: nothing is changed.");
  });
  $$("[data-uk=theme]").forEach(b => b.setAttribute("aria-pressed", document.documentElement.classList.contains("dark")));
}
