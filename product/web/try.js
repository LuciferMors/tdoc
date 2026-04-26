// tdoc /try — public demo page.
// Drag-drop or click → POST to api.tdoc.xyz/v1/try-public → render typed
// document in three views (Preview / JSON / Raw .axc) + download .tdoc archive.
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

  // ─── HTML escape (always run before any regex-based highlighting) ──
  function escapeHtml(s) {
    return s
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  // ─── AXC syntax highlighter ──────────────────────────────────
  function highlightAxc(axc) {
    const safe = escapeHtml(axc);
    return safe
      .replace(/(@[a-z][a-z0-9_-]*)/gi, '<span class="tag">$1</span>')
      .replace(/(\[[^\]\n]*\])/g, (m) => {
        if (/data-type\s*=\s*"[^"]+"/.test(m)) {
          return '<span class="attr typed">' + m + "</span>";
        }
        return '<span class="attr">' + m + "</span>";
      });
  }

  // ─── JSON pretty-printer with HTML-safe highlighting ─────────
  function highlightJson(value) {
    const pretty = JSON.stringify(value, null, 2);
    if (pretty == null) return "";
    return escapeHtml(pretty).replace(
      /("(\\.|[^"\\])*")(\s*:)?|\b(true|false|null)\b|(-?\d+(\.\d+)?([eE][+-]?\d+)?)/g,
      (m, str, _esc, colon, kw, num) => {
        if (str) {
          // If a colon follows, this string is a key; otherwise a value.
          return colon
            ? '<span class="key">' + str + "</span>" + colon
            : '<span class="str">' + str + "</span>";
        }
        if (kw) {
          const cls = kw === "null" ? "null" : "bool";
          return '<span class="' + cls + '">' + kw + "</span>";
        }
        if (num) return '<span class="num">' + num + "</span>";
        return m;
      }
    );
  }

  // ─── Tab switching ───────────────────────────────────────────
  const TABS = ["preview", "json", "axc"];
  let activeTab = "preview";

  function setTab(name) {
    if (!TABS.includes(name)) return;
    activeTab = name;
    TABS.forEach((t) => {
      const btn = $("tab-btn-" + t);
      const panel = $("tab-" + t);
      if (btn) btn.setAttribute("aria-selected", t === name ? "true" : "false");
      if (panel) panel.dataset.active = t === name ? "true" : "false";
    });
  }
  TABS.forEach((t) => {
    const btn = $("tab-btn-" + t);
    if (btn) btn.addEventListener("click", () => setTab(t));
  });

  // ─── base64 → Uint8Array (for .tdoc download) ────────────────
  function b64ToBytes(b64) {
    const bin = atob(b64);
    const out = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
    return out;
  }

  // ─── Upload + render ─────────────────────────────────────────
  let busy = false;
  let lastData = null;
  let lastSourceName = "document";

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
    // Default document_type is set on the server (preprint for the demo
    // endpoint), so we don't send one and let the API pick.

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
      lastData = data;
      lastSourceName = f.name;
      render(data);
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

  function render(data) {
    $("r-doc-id").textContent       = data.document_id || "—";
    $("r-content-hash").textContent = data.content_hash || "—";
    $("r-render-hash").textContent  = data.render_hash || "—";
    $("r-nodes").textContent        = String(data.nodes ?? "—");

    // Preview — sandboxed iframe via srcdoc. The sandbox="" attribute (in
    // try.html) revokes every capability, so even if data.html contained
    // a malicious <script>, it could not run, fetch, or read cookies.
    const iframe = $("r-preview");
    iframe.srcdoc = data.html || "<p style=\"font-family:sans-serif;color:#888;padding:2rem\">no rendered HTML</p>";

    // JSON tree
    $("r-json").innerHTML = highlightJson(data.tree || {});

    // Raw .axc
    $("r-axc").innerHTML = highlightAxc(data.axc || "");

    // Warnings
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

    setTab("preview");
    results.dataset.shown = "true";
  }

  // ─── Toolbar: Copy current tab + Download .tdoc ──────────────
  // Defensive null-guards: if a future deploy renames or removes a
  // toolbar button, the page must NOT crash at module load. Without this
  // a stale browser cache (e.g. user on old try.js, fresh try.html) would
  // throw "Cannot set properties of null (setting 'onclick')" and break
  // every other feature on the page including upload itself.
  function on(id, handler) {
    const el = $(id);
    if (el) el.onclick = handler;
  }

  on("copy-btn", async () => {
    if (!lastData) return;
    let text = "";
    if (activeTab === "axc")  text = lastData.axc || "";
    else if (activeTab === "json") text = JSON.stringify(lastData.tree || {}, null, 2);
    else text = lastData.html || "";
    try {
      await navigator.clipboard.writeText(text);
      const btn = $("copy-btn");
      if (btn) {
        btn.textContent = "copied";
        setTimeout(() => { if (btn) btn.textContent = "Copy current"; }, 1200);
      }
    } catch (e) {
      setStatus("copy blocked by browser — select the text manually", "error");
    }
  });

  on("download-tdoc-btn", () => {
    if (!lastData || !lastData.archive_b64) {
      setStatus("no archive on this response — try again", "error");
      return;
    }
    const bytes = b64ToBytes(lastData.archive_b64);
    // application/zip is the underlying container; .tdoc filename is the
    // brand. application/octet-stream would also work; zip is more honest
    // because the archive really is a deterministic ZIP.
    const blob = new Blob([bytes], { type: "application/zip" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download =
      (lastSourceName.replace(/\.[^.]+$/, "") || "document") + ".tdoc";
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 0);
  });

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
