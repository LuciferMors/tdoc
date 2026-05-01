// tdoc /view — universal .tdoc viewer.
// Drop a .tdoc, paste a URL, or pick the example. Renders inside a sandboxed
// iframe; "Print / Save as PDF" opens a fresh window with the same HTML so
// the browser's native print pipeline works without weakening the sandbox.
// CSP: script-src 'self', no eval, no inline. connect-src includes api.tdoc.xyz.

(() => {
  "use strict";

  const API = "https://api.tdoc.xyz/v1/try-public";
  const MAX_BYTES = 5 * 1024 * 1024;

  const $ = (id) => document.getElementById(id);
  const track = (e, p) => {
    try { if (typeof window.tdocTrack === "function") window.tdocTrack(e, p); } catch (e) { /* swallow */ }
  };
  const dropCard = $("drop-card");
  const fileInput = $("file-input");
  const fileBtn = $("file-btn");
  const urlInput = $("url-input");
  const urlBtn = $("url-btn");
  const status = $("status");
  const wrap = $("frame-wrap");
  const preview = $("preview");
  const exampleSample = $("example-sample");

  // ─── Theme toggle ────────────────────────────────────────────
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

  // ─── Status + state ──────────────────────────────────────────
  let busy = false;
  let lastData = null;
  let lastSourceName = "document";

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

  // ─── Render the API response ─────────────────────────────────
  function render(data, sourceName) {
    lastData = data;
    lastSourceName = sourceName || "document";
    $("frame-title").textContent = data.document_id || "Document";
    $("r-doc-id").textContent       = data.document_id || "—";
    $("r-content-hash").textContent = data.content_hash || "—";
    $("r-render-hash").textContent  = data.render_hash || "—";
    $("r-nodes").textContent        = String(data.nodes ?? "—");
    preview.srcdoc = data.html || "<p style='font-family:sans-serif;color:#888;padding:2rem'>no rendered HTML</p>";
    wrap.dataset.shown = "true";
  }

  // ─── Common upload pipeline (file or fetched bytes) ──────────
  async function pumpToApi(blob, name, mime) {
    if (blob.size > MAX_BYTES) {
      setStatus(
        "File is " + (blob.size / 1024 / 1024).toFixed(1) +
          " MiB. Demo limit is 5 MiB.",
        "error"
      );
      return;
    }
    busy = true;
    wrap.dataset.shown = "false";
    setStatus("rendering " + name + "…", "loading");
    track("view_uploaded", {
      ext: (name.match(/\.([a-z0-9]+)$/i) || ["", ""])[1].toLowerCase(),
      size_kb: Math.round(blob.size / 1024),
    });

    const fd = new FormData();
    fd.append("file", blob, name);
    fd.append("title", name.replace(/\.[^.]+$/, "") || "Document");

    try {
      const r = await fetch(API, { method: "POST", body: fd, mode: "cors" });
      if (!r.ok) {
        let detail = "";
        try { detail = (await r.json()).detail || ""; } catch (e) { /* ignore */ }
        setStatus(
          "server " + r.status + (detail ? " — " + detail : ""),
          "error"
        );
        return;
      }
      const data = await r.json();
      render(data, name);
      setStatus(
        "rendered " + data.nodes + " nodes from " + name,
        "ok"
      );
    } catch (err) {
      setStatus(
        "error — " + (err && err.message ? err.message : String(err)),
        "error"
      );
    } finally {
      busy = false;
    }
  }

  // ─── File-drop wiring ────────────────────────────────────────
  function acceptFile(f) {
    if (busy || !f) return;
    const lname = (f.name || "").toLowerCase();
    if (!/\.(axc|pdf|txt|md)$/.test(lname)) {
      setStatus(
        "Unsupported file type — use .axc, .pdf, .txt, or .md.",
        "error"
      );
      return;
    }
    pumpToApi(f, f.name, f.type || "application/octet-stream");
  }

  dropCard.addEventListener("click", (e) => {
    if (e.target.tagName === "INPUT") return;
    fileInput.click();
  });
  fileBtn.addEventListener("click", (e) => { e.stopPropagation(); fileInput.click(); });
  fileInput.addEventListener("change", () => acceptFile(fileInput.files[0]));

  ["dragenter", "dragover"].forEach((ev) => {
    dropCard.addEventListener(ev, (e) => {
      e.preventDefault(); e.stopPropagation();
      dropCard.dataset.drag = "true";
    });
  });
  ["dragleave", "drop"].forEach((ev) => {
    dropCard.addEventListener(ev, (e) => {
      e.preventDefault(); e.stopPropagation();
      dropCard.dataset.drag = "false";
    });
  });
  dropCard.addEventListener("drop", (e) => {
    const f =
      e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
    if (f) acceptFile(f);
  });

  // ─── URL fetch ───────────────────────────────────────────────
  async function openFromUrl(rawUrl) {
    if (busy) return;
    let url;
    try {
      url = new URL(rawUrl, window.location.href);
    } catch (e) {
      setStatus("not a valid URL", "error");
      return;
    }
    if (!/^https?:$/.test(url.protocol)) {
      setStatus("URL must use http or https", "error");
      return;
    }
    setStatus("fetching " + url.href + "…", "loading");
    try {
      const r = await fetch(url.href, { mode: "cors" });
      if (!r.ok) {
        setStatus("could not fetch (HTTP " + r.status + ")", "error");
        return;
      }
      const blob = await r.blob();
      // Infer the file name from the URL path; fall back to "remote.tdoc".
      const tail = url.pathname.split("/").filter(Boolean).pop() || "remote.axc";
      const name = /\.(axc|pdf|txt|md)$/i.test(tail) ? tail : tail + ".axc";
      acceptFile(new File([blob], name, { type: blob.type || "application/zip" }));
    } catch (err) {
      setStatus(
        "fetch failed — " + (err && err.message ? err.message : String(err)) +
          ". The remote server may not allow CORS to api.tdoc.xyz.",
        "error"
      );
    }
  }

  urlBtn.addEventListener("click", () => {
    const v = urlInput.value.trim();
    if (v) openFromUrl(v);
  });
  urlInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      urlBtn.click();
    }
  });

  // ─── Example loader (sample.axc → upload as .axc) ─────────────
  if (exampleSample) {
    exampleSample.addEventListener("click", async (e) => {
      e.preventDefault();
      if (busy) return;
      setStatus("loading sample…", "loading");
      try {
        const r = await fetch("/sample.axc", { cache: "force-cache" });
        if (!r.ok) {
          setStatus("could not load sample (HTTP " + r.status + ")", "error");
          return;
        }
        const text = await r.text();
        const f = new File([text], "sample.axc", { type: "text/plain" });
        acceptFile(f);
      } catch (err) {
        setStatus(
          "could not load sample — " +
            (err && err.message ? err.message : String(err)),
          "error"
        );
      }
    });
  }

  // ─── Print / Save as PDF ─────────────────────────────────────
  // Cross-origin-iframe printing is a maze. Cleanest path: open a fresh tab
  // via Blob URL with the rendered HTML, let the browser handle print +
  // "Save as PDF" natively. The user is on tdoc.xyz; the new tab is at a
  // blob: URL, fully isolated. Closes itself after printing.
  function printDocument() {
    if (!lastData || !lastData.html) {
      setStatus("nothing to print yet — open a document first", "error");
      return;
    }
    // Inject a tiny script that prints and closes after the user dismisses.
    const printedHtml =
      lastData.html.replace(
        "</body>",
        '<script>window.addEventListener("load",function(){setTimeout(function(){window.print();},120);window.addEventListener("afterprint",function(){window.close();});});<\/script></body>'
      );
    const blob = new Blob([printedHtml], { type: "text/html;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const w = window.open(url, "_blank", "noopener");
    if (!w) {
      setStatus(
        "your browser blocked the print window — allow popups for tdoc.xyz",
        "error"
      );
      URL.revokeObjectURL(url);
      return;
    }
    setTimeout(() => URL.revokeObjectURL(url), 60_000);
  }

  function downloadAxc() {
    if (!lastData) {
      setStatus("nothing to download yet — open a document first", "error");
      return;
    }
    const text = lastData.axc_ai || lastData.axc || "";
    if (!text) {
      setStatus("nothing to download", "error");
      return;
    }
    const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download =
      (lastSourceName.replace(/\.[^.]+$/, "") || "document") + ".axc";
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 0);
  }

  $("download-pdf-btn").addEventListener("click", () => { track("view_downloaded", { format: "axc" }); downloadAxc(); });
  $("print-btn").addEventListener("click", () => { track("view_printed"); printDocument(); });
  $("reload-btn").addEventListener("click", () => {
    if (lastData) render(lastData, lastSourceName);
  });
})();
