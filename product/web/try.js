// tdoc /try — public demo page.
// Drag-drop or click → POST to api.tdoc.xyz/v1/try-public → render typed AXC.
// CSP: script-src 'self', no eval, no inline. connect-src includes api.tdoc.xyz.

(() => {
  "use strict";

  const API = "https://api.tdoc.xyz/v1/try-public";
  const MAX_BYTES = 5 * 1024 * 1024;

  const $ = (id) => document.getElementById(id);
  const drop = $("drop");
  const file = $("file");
  const status = $("status");
  const results = $("results");

  // ─── Theme toggle (mirrors index.html / app.js) ──────────────
  function syncThemeButtons(theme) {
    document.querySelectorAll("[data-theme-set]").forEach((btn) => {
      btn.setAttribute(
        "aria-pressed",
        btn.dataset.themeSet === theme ? "true" : "false"
      );
    });
  }
  function setTheme(theme, persist) {
    if (theme !== "light" && theme !== "dark") return;
    document.documentElement.dataset.theme = theme;
    syncThemeButtons(theme);
    if (persist) {
      try { localStorage.setItem("tdoc-theme", theme); } catch (e) { /* ignore */ }
    }
  }
  syncThemeButtons(
    document.documentElement.dataset.theme === "dark" ? "dark" : "light"
  );
  document.querySelectorAll("[data-theme-set]").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.preventDefault(); e.stopPropagation();
      setTheme(btn.dataset.themeSet, true);
    });
  });

  // ─── Status helper ───────────────────────────────────────────
  function setStatus(msg, state) {
    status.textContent = "";
    status.dataset.state = state || "idle";
    if (state === "loading") {
      const sp = document.createElement("span");
      sp.className = "spinner";
      status.appendChild(sp);
    }
    status.appendChild(document.createTextNode(msg));
  }

  // ─── HTML-safe AXC highlighting ──────────────────────────────
  // First escape the entire string, THEN run regex replacements on the
  // already-escaped text. The regex never sees raw user content, so we
  // can't accidentally inject markup from a malicious document body.
  function escapeHtml(s) {
    return s
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }
  function highlight(axc) {
    const safe = escapeHtml(axc);
    return safe
      .replace(/(@[a-z][a-z0-9_-]*)/gi, '<span class="tag">$1</span>')
      .replace(/(\[[^\]\n]*\])/g, (m) => {
        // Highlight typed cells (data-type="…") more strongly.
        if (/data-type\s*=\s*"[^"]+"/.test(m)) {
          return '<span class="attr typed">' + m + "</span>";
        }
        return '<span class="attr">' + m + "</span>";
      });
  }

  // ─── Upload + render ─────────────────────────────────────────
  let busy = false;

  async function upload(f) {
    if (busy || !f) return;
    if (f.size > MAX_BYTES) {
      setStatus(
        "File is " + (f.size / 1024 / 1024).toFixed(1) +
          " MiB. Demo limit is 5 MiB.",
        "error"
      );
      return;
    }
    const name = (f.name || "").toLowerCase();
    if (!/\.(pdf|axc|txt|md)$/.test(name)) {
      setStatus("Unsupported file type. Use .pdf, .axc, .txt, or .md.", "error");
      return;
    }
    busy = true;
    results.dataset.shown = "false";
    setStatus("uploading " + f.name + "…", "loading");

    const fd = new FormData();
    fd.append("file", f);
    fd.append("title", f.name.replace(/\.[^.]+$/, "") || "Demo");
    fd.append("document_type", "article.research");

    try {
      const r = await fetch(API, { method: "POST", body: fd, mode: "cors" });
      if (!r.ok) {
        let detail = "";
        try { detail = (await r.json()).detail || ""; } catch (e) { /* ignore */ }
        setStatus(
          "server " + r.status + (detail ? " — " + detail : ""),
          "error"
        );
        busy = false;
        return;
      }
      const data = await r.json();
      render(data, f.name);
      setStatus(
        "done — typed " + data.nodes + " nodes from " + f.name,
        "ok"
      );
    } catch (err) {
      setStatus(
        "network error — " +
          (err && err.message ? err.message : String(err)),
        "error"
      );
    } finally {
      busy = false;
    }
  }

  function render(data, sourceName) {
    $("r-doc-id").textContent       = data.document_id || "—";
    $("r-content-hash").textContent = data.content_hash || "—";
    $("r-render-hash").textContent  = data.render_hash || "—";
    $("r-nodes").textContent        = String(data.nodes ?? "—");
    $("r-axc").innerHTML            = highlight(data.axc || "");

    const warnEl = $("r-warnings");
    const list = $("r-warnings-list");
    list.innerHTML = "";
    if (Array.isArray(data.warnings) && data.warnings.length) {
      data.warnings.forEach((w) => {
        const li = document.createElement("li");
        li.textContent = w;
        list.appendChild(li);
      });
      warnEl.hidden = false;
    } else {
      warnEl.hidden = true;
    }

    $("copy-btn").onclick = async () => {
      try {
        await navigator.clipboard.writeText(data.axc || "");
        $("copy-btn").textContent = "copied";
        setTimeout(() => ($("copy-btn").textContent = "Copy"), 1200);
      } catch (e) {
        setStatus("copy blocked by browser — select the text manually", "error");
      }
    };
    $("download-btn").onclick = () => {
      // application/octet-stream — opaque MIME — so the browser respects
      // the `download` attribute filename verbatim. With text/plain, Safari
      // and some Chromium variants append ".txt", producing "foo.axc.txt".
      const blob = new Blob([data.axc || ""], {
        type: "application/octet-stream",
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download =
        (sourceName.replace(/\.[^.]+$/, "") || "document") + ".axc";
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 0);
    };

    results.dataset.shown = "true";
  }

  // ─── Drag-and-drop wiring ────────────────────────────────────
  drop.addEventListener("click", (e) => {
    if (e.target.tagName !== "INPUT") file.click();
  });
  drop.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      file.click();
    }
  });
  file.addEventListener("change", () => upload(file.files[0]));

  ["dragenter", "dragover"].forEach((ev) => {
    drop.addEventListener(ev, (e) => {
      e.preventDefault(); e.stopPropagation();
      drop.dataset.drag = "true";
    });
  });
  ["dragleave", "drop"].forEach((ev) => {
    drop.addEventListener(ev, (e) => {
      e.preventDefault(); e.stopPropagation();
      drop.dataset.drag = "false";
    });
  });
  drop.addEventListener("drop", (e) => {
    const f =
      e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
    if (f) upload(f);
  });
})();
