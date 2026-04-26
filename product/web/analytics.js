// tdoc analytics — anonymous, cookie-free, DNT-respecting.
// No-op until TDOC_PH_KEY is set on window (via a <script> tag in the HTML).
// Posts to PostHog's public /e endpoint. No PII. No cookies. No fingerprinting.
// CSP: script-src 'self' (this file), connect-src must include the host.

(() => {
  "use strict";

  // 1. Honour Do-Not-Track and the user's explicit opt-out.
  if (navigator.doNotTrack === "1" || window.doNotTrack === "1") return;
  try {
    if (localStorage.getItem("tdoc-analytics-opt-out") === "1") return;
  } catch (e) { /* private mode — keep going */ }

  // 2. Read project key from a global set in HTML. Until set: no-op.
  const KEY = (window && window.TDOC_PH_KEY) || "";
  const HOST = (window && window.TDOC_PH_HOST) || "https://eu.i.posthog.com";
  if (!KEY) return;

  // 3. Anonymous distinct id — random, cleared on browser-data wipe.
  //    Stored in localStorage only; never a cookie. Never sent to our API.
  let distinct_id = "";
  try {
    distinct_id = localStorage.getItem("tdoc-anon") || "";
    if (!distinct_id) {
      // 16 hex chars from crypto-random — collision negligible for our scale.
      const arr = new Uint8Array(8);
      (window.crypto || window.msCrypto).getRandomValues(arr);
      distinct_id = Array.from(arr).map((b) => b.toString(16).padStart(2, "0")).join("");
      localStorage.setItem("tdoc-anon", distinct_id);
    }
  } catch (e) {
    distinct_id = "anon-" + Math.random().toString(36).slice(2, 10);
  }

  function send(event, properties) {
    const payload = {
      api_key: KEY,
      event: event,
      distinct_id: distinct_id,
      properties: Object.assign(
        {
          $current_url: location.pathname,    // path only, never query / fragment
          $host: location.host,
          $referrer: document.referrer ? new URL(document.referrer, location.href).host : "",
          $screen_width: window.innerWidth || 0,
          $lib: "tdoc-anon",
          $lib_version: "1",
        },
        properties || {}
      ),
      timestamp: new Date().toISOString(),
    };
    const body = JSON.stringify(payload);
    const url = HOST.replace(/\/$/, "") + "/e/";
    try {
      // sendBeacon survives the page unload — best for click + nav events.
      if (navigator.sendBeacon) {
        navigator.sendBeacon(url, body);
        return;
      }
    } catch (e) { /* fall through */ }
    fetch(url, { method: "POST", body: body, keepalive: true, mode: "no-cors" }).catch(() => {});
  }

  // 4. Page-view (one per route, since this is a multi-page static site).
  send("pageview", { $pathname: location.pathname });

  // 5. Expose a tiny global so the page-specific scripts can record events.
  window.tdocTrack = function (event, props) {
    if (typeof event !== "string") return;
    send(event, props || {});
  };

  // 6. Generic outbound-link + download tracking (no per-page wiring needed).
  document.addEventListener("click", function (e) {
    const a = e.target && e.target.closest && e.target.closest("a[href]");
    if (!a) return;
    const href = a.getAttribute("href") || "";
    if (!href) return;
    if (a.hasAttribute("download")) {
      send("download_clicked", { href: href.split("?")[0] });
      return;
    }
    if (/^https?:/i.test(href) && a.host !== location.host) {
      send("outbound_clicked", { host: a.host });
    }
  }, { capture: true });
})();
