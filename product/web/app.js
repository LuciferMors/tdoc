// tdoc landing — motion + theme + mobile drawer.
// Under 2 KB. No live API demo, no typewriter, no magnetic pulls.
// CSP: script-src 'self'.

(() => {
  "use strict";

  const prefersReduced =
    window.matchMedia &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // ─── Scroll reveal ──────────────────────────────────────────
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
  const metaColors = { light: "#fafaf7", dark: "#141310" };

  function syncThemeButtons(theme) {
    document.querySelectorAll("[data-theme-set]").forEach((btn) => {
      btn.setAttribute(
        "aria-pressed",
        btn.dataset.themeSet === theme ? "true" : "false"
      );
    });
  }
  function applyMetaColor(theme) {
    const head = document.head;
    head.querySelectorAll('meta[name="theme-color"]').forEach((el) => el.remove());
    const meta = document.createElement("meta");
    meta.name = "theme-color";
    meta.content = metaColors[theme] || metaColors.light;
    head.appendChild(meta);
  }
  function setTheme(theme, persist) {
    if (theme !== "light" && theme !== "dark") return;
    document.documentElement.dataset.theme = theme;
    syncThemeButtons(theme);
    applyMetaColor(theme);
    if (persist) {
      try { localStorage.setItem("tdoc-theme", theme); } catch (e) { /* ignore */ }
    }
  }

  const initialTheme =
    document.documentElement.dataset.theme === "dark" ? "dark" : "light";
  syncThemeButtons(initialTheme);

  document.querySelectorAll("[data-theme-set]").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation(); // don't let click bubble to drawer-close
      setTheme(btn.dataset.themeSet, true);
    });
  });

  if (window.matchMedia) {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const listener = (ev) => {
      let hasExplicit = false;
      try { hasExplicit = !!localStorage.getItem("tdoc-theme"); } catch (e) { /* ignore */ }
      if (!hasExplicit) setTheme(ev.matches ? "dark" : "light", false);
    };
    if (mq.addEventListener) mq.addEventListener("change", listener);
    else if (mq.addListener) mq.addListener(listener);
  }

  // ─── Mobile drawer (hamburger) ──────────────────────────────
  const masthead = document.querySelector(".masthead");
  const burger = document.querySelector(".burger");
  const drawer = document.getElementById("masthead-drawer");

  function setDrawer(open) {
    if (!masthead || !burger) return;
    masthead.dataset.open = open ? "true" : "false";
    burger.setAttribute("aria-expanded", open ? "true" : "false");
  }

  if (burger && masthead) {
    burger.addEventListener("click", (e) => {
      e.stopPropagation();
      const isOpen = masthead.dataset.open === "true";
      setDrawer(!isOpen);
    });

    // Close when a nav link inside the drawer is clicked — user is navigating.
    if (drawer) {
      drawer.addEventListener("click", (e) => {
        const t = e.target;
        if (t.tagName === "A") setDrawer(false);
      });
    }

    // Close on outside click.
    document.addEventListener("click", (e) => {
      if (masthead.dataset.open !== "true") return;
      if (!masthead.contains(e.target)) setDrawer(false);
    });

    // Close on Escape.
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && masthead.dataset.open === "true") {
        setDrawer(false);
        burger.focus();
      }
    });

    // If the viewport grows past the mobile breakpoint while the drawer
    // is open, close it — otherwise it looks stuck on desktop.
    if (window.matchMedia) {
      const desktopMq = window.matchMedia("(min-width: 721px)");
      const onChange = () => {
        if (desktopMq.matches && masthead.dataset.open === "true") setDrawer(false);
      };
      if (desktopMq.addEventListener) desktopMq.addEventListener("change", onChange);
      else if (desktopMq.addListener) desktopMq.addListener(onChange);
    }
  }
})();
