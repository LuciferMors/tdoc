// tdoc landing — minimal motion + theme toggle.
// Under 1.5 KB. No live API demo, no typewriter, no magnetic pulls.
// CSP: script-src 'self'.

(() => {
  "use strict";

  const prefersReduced =
    window.matchMedia &&
    window.matchMedia("(prefers-color-scheme: dark)") && // presence check
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // ─── Scroll reveal ──────────────────────────────────────────
  // One observer, reveals once, then unobserves. Slow + subtle.
  const targets = document.querySelectorAll("[data-reveal]");
  if (targets.length) {
    if (prefersReduced || !("IntersectionObserver" in window)) {
      targets.forEach((el) => el.classList.add("is-in"));
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
        { threshold: 0.08, rootMargin: "0px 0px -6% 0px" }
      );
      targets.forEach((el) => io.observe(el));
    }
  }

  // ─── Theme toggle ───────────────────────────────────────────
  // theme.js in <head> set document.documentElement.dataset.theme
  // before first paint. Here we:
  //   1. Sync the Day/Night button aria-pressed state with the
  //      current theme (handles system-pref initial state).
  //   2. Wire click handlers that persist choice to localStorage.
  //   3. Keep the meta[name="theme-color"] consistent so mobile
  //      browsers repaint their chrome on toggle.
  const metaColors = {
    light: "#fafaf7",
    dark: "#141310",
  };

  function syncButtons(theme) {
    document
      .querySelectorAll("[data-theme-set]")
      .forEach((btn) => {
        btn.setAttribute(
          "aria-pressed",
          btn.dataset.themeSet === theme ? "true" : "false"
        );
      });
  }

  function applyMetaColor(theme) {
    // Replace all existing <meta name="theme-color"> with a single,
    // unconditional one reflecting the active theme. This beats the
    // media-query variants once the user has an explicit choice.
    const head = document.head;
    const existing = head.querySelectorAll('meta[name="theme-color"]');
    existing.forEach((el) => el.remove());
    const meta = document.createElement("meta");
    meta.name = "theme-color";
    meta.content = metaColors[theme] || metaColors.light;
    head.appendChild(meta);
  }

  function setTheme(theme, persist) {
    if (theme !== "light" && theme !== "dark") return;
    document.documentElement.dataset.theme = theme;
    syncButtons(theme);
    applyMetaColor(theme);
    if (persist) {
      try {
        localStorage.setItem("tdoc-theme", theme);
      } catch (e) {
        // localStorage blocked — stay in-session only.
      }
    }
  }

  // Initial sync — whatever theme.js decided, reflect it in the UI.
  const initial =
    document.documentElement.dataset.theme === "dark" ? "dark" : "light";
  syncButtons(initial);

  // Toggle clicks.
  document.querySelectorAll("[data-theme-set]").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.preventDefault();
      setTheme(btn.dataset.themeSet, true);
    });
  });

  // Live-update if system preference changes AND the user hasn't made
  // an explicit choice yet. Polite: doesn't fight a user decision.
  if (window.matchMedia) {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const listener = (ev) => {
      let hasExplicit = false;
      try {
        hasExplicit = !!localStorage.getItem("tdoc-theme");
      } catch (e) {
        // ignore
      }
      if (!hasExplicit) setTheme(ev.matches ? "dark" : "light", false);
    };
    if (mq.addEventListener) mq.addEventListener("change", listener);
    else if (mq.addListener) mq.addListener(listener); // old Safari
  }
})();
