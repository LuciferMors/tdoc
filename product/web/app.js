// tdoc landing — minimal motion.
// Under 1 KB. No live API demo, no typewriter, no magnetic pulls,
// no "live" dots. A slow, subtle reveal on scroll — nothing else.
// CSP: script-src 'self'.

(() => {
  "use strict";

  const prefersReduced =
    window.matchMedia &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  const targets = document.querySelectorAll("[data-reveal]");
  if (!targets.length) return;

  if (prefersReduced || !("IntersectionObserver" in window)) {
    targets.forEach((el) => el.classList.add("is-in"));
    return;
  }

  // One observer. Reveals once, then stops watching. No cascading, no
  // stagger — each element reveals when it is ready to read.
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
})();
