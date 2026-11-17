/* Light / dark choice. Light is the default; the choice is kept in this browser only. Runs in <head> so the page never flashes the wrong theme.
   Switching happens in place (no reload), so scroll position, open panels and the map view are kept. */
(function () {
  var KEY = "falconeye.theme", dark = false, listeners = [], btn = null;
  try { dark = localStorage.getItem(KEY) === "dark"; } catch (e) { /* storage may be blocked: stay light */ }
  var root = document.documentElement;
  var ar = function () { return root.lang === "ar" || root.classList.contains("rtl"); };

  function apply() {
    root.setAttribute("data-theme", dark ? "dark" : "light");
    root.style.colorScheme = dark ? "dark" : "light";
    var link = document.querySelector('link[href*="esri/themes/"]');            // the ArcGIS widgets follow the theme
    if (link) link.href = link.href.replace(/\/themes\/(light|dark)\//, "/themes/" + (dark ? "dark" : "light") + "/");
    THEME.dark = dark;
    if (btn) {
      var word = dark ? (ar() ? "فاتح" : "Light") : (ar() ? "داكن" : "Dark");
      var label = dark ? (ar() ? "التبديل إلى الوضع الفاتح" : "Switch to light mode") : (ar() ? "التبديل إلى الوضع الداكن" : "Switch to dark mode");
      btn.textContent = (dark ? "☀ " : "☾ ") + word;
      btn.title = label; btn.setAttribute("aria-label", label); btn.setAttribute("aria-pressed", dark ? "true" : "false");
    }
  }

  var THEME = window.THEME = {
    dark: dark,
    basemap: function () { return dark ? "dark-gray-vector" : "gray-vector"; },
    onChange: function (fn) { listeners.push(fn); }                              // maps register here to swap their basemap
  };
  apply();

  function build() {
    btn = document.createElement("button");
    btn.type = "button"; btn.className = "lang-toggle theme-toggle"; btn.id = "theme-toggle";
    btn.onclick = function () {
      dark = !dark;
      try { localStorage.setItem(KEY, dark ? "dark" : "light"); } catch (e) { /* ignore */ }
      apply();
      listeners.forEach(function (fn) { try { fn(THEME.basemap(), dark); } catch (e) { /* a listener must not break the switch */ } });
    };
    var host = document.querySelector(".tools") || document.querySelector(".topright") || document.querySelector("header.top");
    if (host) host.appendChild(btn); else { btn.classList.add("floating"); document.body.appendChild(btn); }
    apply();
  }
  // After i18n.js has added its language button, so the two sit together.
  var go = function () { setTimeout(build, 0); };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", go); else go();
})();
