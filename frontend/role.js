/* Shared helpers for the role pages: API calls, toasts, escaping, GeoJSON -> map graphics. */
window.R = {
  esc: s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])),
  async api(url, opts) {
    const r = await fetch(I18N.apiUrl(url), { headers: { "X-Role": "operator" }, ...opts });
    const body = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(body.detail || body.error || r.statusText);
    return body;
  },
  toast(title, msg = "", err = false) {
    let box = document.getElementById("toasts");
    if (!box) { box = document.createElement("div"); box.id = "toasts"; document.body.appendChild(box); }
    const t = document.createElement("div");
    t.className = "toast" + (err ? " err" : "");
    t.innerHTML = `<b>${R.esc(title)}</b>${R.esc(msg)}`;
    box.appendChild(t);
    setTimeout(() => t.remove(), 4500);
  },
  /* Load /api/layers/<name> GeoJSON into a GraphicsLayer. symbol(props) -> symbol JSON. Returns the feature count. */
  async loadLayer(layer, name, symbol, Graphic, query = "", popup = null, keep = null) {
    const gj = await R.api(`/api/layers/${name}${query}`);
    layer.removeAll();
    let n = 0;
    for (const f of gj.features) {
      if (!f.geometry || (keep && !keep(f.properties))) continue;
      n++;
      const geometry = f.geometry.type === "Point"
        ? { type: "point", longitude: f.geometry.coordinates[0], latitude: f.geometry.coordinates[1] }
        : { type: "polygon", rings: f.geometry.coordinates };
      let popupTemplate;
      if (popup) {
        const p = popup(f.properties);
        popupTemplate = { title: p.title, content: () => { const d = document.createElement("div"); d.innerHTML = p.html; return d; } };
      }
      layer.add(new Graphic({ geometry, symbol: symbol(f.properties), attributes: { ...f.properties, _id: f.id }, popupTemplate }));
    }
    return n;
  },
};
