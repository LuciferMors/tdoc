// Theme boot — MUST run before first paint to avoid FOUC.
// Loaded synchronously in <head>. Under 500 bytes.
// CSP: script-src 'self'.
(function () {
  "use strict";
  try {
    var saved = localStorage.getItem("tdoc-theme");
    var sysDark =
      window.matchMedia &&
      window.matchMedia("(prefers-color-scheme: dark)").matches;
    var theme = saved || (sysDark ? "dark" : "light");
    document.documentElement.dataset.theme = theme;
  } catch (e) {
    // localStorage blocked (Safari private, etc.) — fall back to system.
    var sysDark2 =
      window.matchMedia &&
      window.matchMedia("(prefers-color-scheme: dark)").matches;
    document.documentElement.dataset.theme = sysDark2 ? "dark" : "light";
  }
})();
