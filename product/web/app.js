// tdoc landing — motion + live API demo.
// CSP: script-src 'self' only. No external JS. No inline handlers.
// Keep small: every byte ships on Cloudflare Pages free tier.

(() => {
  "use strict";

  const prefersReduced =
    window.matchMedia &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // ───────────────────────────────────────────────────────────────
  // 1. Hero entry — per-word stagger on the three title lines.
  //    Letter-spacing collapses from +0.04em → 0 while opacity 0 → 1.
  // ───────────────────────────────────────────────────────────────
  const heroLines = document.querySelectorAll(".hero__title .line > span");
  if (heroLines.length && !prefersReduced) {
    heroLines.forEach((el, i) => {
      el.style.opacity = "0";
      el.style.letterSpacing = "0.04em";
      el.style.transform = "translateY(120%)";
      el.style.transition =
        "opacity 1.1s cubic-bezier(0.2,0.9,0.2,1.1) " +
        i * 0.14 +
        "s, transform 1.1s cubic-bezier(0.2,0.9,0.2,1.1) " +
        i * 0.14 +
        "s, letter-spacing 1.4s ease " +
        i * 0.14 +
        "s";
    });
    requestAnimationFrame(() => {
      heroLines.forEach((el) => {
        el.style.opacity = "1";
        el.style.transform = "translateY(0)";
        el.style.letterSpacing = "0";
      });
    });
  }

  // ───────────────────────────────────────────────────────────────
  // 2. Scroll reveal — IntersectionObserver toggles .is-in on [data-reveal].
  // ───────────────────────────────────────────────────────────────
  const revealers = document.querySelectorAll("[data-reveal]");
  if (revealers.length) {
    if (prefersReduced || !("IntersectionObserver" in window)) {
      revealers.forEach((el) => el.classList.add("is-in"));
    } else {
      const io = new IntersectionObserver(
        (entries) => {
          entries.forEach((entry) => {
            if (entry.isIntersecting) {
              entry.target.classList.add("is-in");
              io.unobserve(entry.target);
            }
          });
        },
        { threshold: 0.12, rootMargin: "0px 0px -8% 0px" }
      );
      revealers.forEach((el) => io.observe(el));
    }
  }

  // ───────────────────────────────────────────────────────────────
  // 3. Live API demo — real GET to api.tdoc.xyz/v1/healthz.
  //    Measures latency, extracts edge PoP from cf-ray, typewrites
  //    the JSON response into the demo pane. Falls back gracefully
  //    if the network is down or the API is cold.
  // ───────────────────────────────────────────────────────────────
  const demoResp = document.getElementById("demo-response");
  const demoCursor = document.getElementById("demo-cursor");
  const demoStatus = document.getElementById("demo-status");
  const demoLatency = document.getElementById("demo-latency");
  const demoEdge = document.getElementById("demo-edge");

  const cfPops = {
    BOM: "Mumbai",
    SIN: "Singapore",
    HKG: "Hong Kong",
    NRT: "Tokyo",
    KIX: "Osaka",
    ICN: "Seoul",
    LHR: "London",
    CDG: "Paris",
    AMS: "Amsterdam",
    FRA: "Frankfurt",
    IAD: "Ashburn",
    EWR: "Newark",
    DFW: "Dallas",
    LAX: "Los Angeles",
    SFO: "San Francisco",
    SEA: "Seattle",
    ORD: "Chicago",
    ATL: "Atlanta",
    MIA: "Miami",
    GRU: "São Paulo",
    SYD: "Sydney",
    DXB: "Dubai",
    JNB: "Johannesburg",
  };

  const fallbackPayload = {
    service: "tdoc",
    version: "0.1.0",
    docs: "https://api.tdoc.xyz/docs",
    openapi: "https://api.tdoc.xyz/openapi.json",
    landing: "https://tdoc.xyz",
    source: "https://github.com/LuciferMors/tdoc",
  };

  function syntaxColor(json) {
    // Lightweight JSON colorizer — wraps tokens in <span class="k|s|n|p">.
    // The palette matches the request pane so request + response feel like
    // one specimen sheet.
    return json.replace(
      /("(\\u[a-fA-F0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(\.\d+)?([eE][+-]?\d+)?)/g,
      (m) => {
        let cls = "n";
        if (/^"/.test(m)) {
          cls = /:$/.test(m) ? "h" : "s";
          // strip trailing colon for key rendering
          if (cls === "h") {
            return `<span class="${cls}">${m.slice(0, -1)}</span><span class="p">:</span>`;
          }
        } else if (/true|false|null/.test(m)) {
          cls = "k";
        }
        return `<span class="${cls}">${m}</span>`;
      }
    );
  }

  async function typeInto(el, html, delayPerChar = 6) {
    // Types HTML into the element. Strips tags for pacing, then rewrites
    // the rich version once done. prefersReduced → paint all at once.
    if (prefersReduced) {
      el.innerHTML = html;
      return;
    }
    const plain = html.replace(/<[^>]+>/g, "");
    let i = 0;
    return new Promise((resolve) => {
      const step = () => {
        el.textContent = plain.slice(0, i);
        i++;
        if (i <= plain.length) {
          setTimeout(step, delayPerChar);
        } else {
          el.innerHTML = html; // swap in the colorized version at the end
          resolve();
        }
      };
      step();
    });
  }

  async function runDemo() {
    if (!demoResp) return;

    const t0 = performance.now();
    let status = "?";
    let payload = null;
    let edge = null;

    try {
      // ~2s hard cap — if the API is cold or the client is offline we
      // fall back rather than hold the page hostage.
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 2500);

      const resp = await fetch("https://api.tdoc.xyz/v1/healthz", {
        method: "GET",
        headers: { accept: "application/json" },
        cache: "no-store",
        signal: controller.signal,
      });
      clearTimeout(timeoutId);

      status = resp.status;
      const cfRay = resp.headers.get("cf-ray");
      if (cfRay) {
        const code = cfRay.split("-")[1];
        edge = cfPops[code] || code;
      }
      payload = await resp.json();
    } catch (err) {
      // Network refused / blocked / DNS failing on the client. The API
      // IS live (Cloudflare Worker at api.tdoc.xyz, Observatory A+ 130)
      // so this is almost always a client-side issue. Show the same
      // shape so the page still demonstrates the contract.
      status = "[offline]";
      payload = fallbackPayload;
      edge = "(cached)";
    }

    const dt = Math.round(performance.now() - t0);
    if (demoStatus) {
      demoStatus.textContent = status === 200 ? "200 OK" : String(status);
      demoStatus.style.color = status === 200 ? "var(--fire)" : "var(--paper-mute)";
    }
    if (demoLatency) demoLatency.textContent = `${dt} ms`;
    if (demoEdge) demoEdge.textContent = edge || "—";

    const pretty = JSON.stringify(payload, null, 2);
    const colored = syntaxColor(pretty);

    await typeInto(demoResp, colored, 4);

    if (demoCursor) demoCursor.style.display = "none";
  }

  // Kick the demo once the user is near the hero — saves bandwidth
  // on back-button visits or bot scrapes that never scroll.
  if ("IntersectionObserver" in window && demoResp) {
    const demoIo = new IntersectionObserver(
      (entries, obs) => {
        if (entries.some((e) => e.isIntersecting)) {
          obs.disconnect();
          runDemo();
        }
      },
      { threshold: 0.1 }
    );
    demoIo.observe(demoResp);
  } else if (demoResp) {
    // Environments without IntersectionObserver (ancient browsers) — just go.
    runDemo();
  }

  // ───────────────────────────────────────────────────────────────
  // 4. Magnetic pull on the primary CTA — subtle desktop delight.
  // ───────────────────────────────────────────────────────────────
  if (!prefersReduced && matchMedia("(pointer: fine)").matches) {
    document.querySelectorAll(".cta").forEach((btn) => {
      btn.addEventListener("mousemove", (e) => {
        const r = btn.getBoundingClientRect();
        const dx = ((e.clientX - r.left) / r.width - 0.5) * 8;
        const dy = ((e.clientY - r.top) / r.height - 0.5) * 6;
        btn.style.transform = `translate(${dx.toFixed(2)}px, ${dy.toFixed(2)}px)`;
      });
      btn.addEventListener("mouseleave", () => {
        btn.style.transform = "";
      });
    });
  }
})();
