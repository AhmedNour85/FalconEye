/* Light / dark choice. Light is the default; the choice is kept in this browser only. Runs in <head> so the page never flashes the wrong theme. */
(function () {
  var KEY = "falconeye.theme", dark = false;
  try { dark = localStorage.getItem(KEY) === "dark"; } catch (e) { /* storage may be blocked: stay light */ }
  var root = document.documentElement;
  root.setAttribute("data-theme", dark ? "dark" : "light");
  root.style.colorScheme = dark ? "dark" : "light";
  var link = document.querySelector('link[href*="esri/themes/"]');              // the ArcGIS widgets follow the theme
  if (link && dark) link.href = link.href.replace("/themes/light/", "/themes/dark/");

  function build() {
    var b = document.createElement("button");
    b.type = "button"; b.className = "lang-toggle theme-toggle"; b.id = "theme-toggle";
    var ar = root.lang === "ar" || root.classList.contains("rtl");
    var label = dark ? (ar ? "الوضع الفاتح" : "Light mode") : (ar ? "الوضع الداكن" : "Dark mode");
    b.textContent = dark ? "☀" : "☾"; b.title = label; b.setAttribute("aria-label", label); b.setAttribute("aria-pressed", dark ? "true" : "false");
    b.onclick = function () { try { localStorage.setItem(KEY, dark ? "light" : "dark"); } catch (e) { /* ignore */ } location.reload(); };
    var host = document.querySelector(".tools") || document.querySelector(".topright") || document.querySelector("header.top");
    if (host) host.appendChild(b); else { b.classList.add("floating"); document.body.appendChild(b); }
  }
  // After i18n.js has added its language button, so the two sit together.
  var go = function () { setTimeout(build, 0); };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", go); else go();

  window.THEME = { dark: dark, basemap: function () { return dark ? "dark-gray-vector" : "gray-vector"; } };
})();
