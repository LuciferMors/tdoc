#!/usr/bin/env python3
"""Build the rendered /spec page from AXON_Format_Specification.txt.

Run from the repo root:

    python tools/build_spec.py

Reads `AXON_Format_Specification.txt`, emits `product/web/spec.html`
in the Printed-Matter aesthetic of the rest of the site. Idempotent;
safe to run on every commit. No external dependencies."""

from __future__ import annotations

import html
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPEC = ROOT / "AXON_Format_Specification.txt"
OUT = ROOT / "product/web/spec.html"


PART = re.compile(r"^PART\s+([A-Z\-]+):\s*(.+)$")
NODE_HEADING = re.compile(r"^─{3,}\s+(@\w+)\s+─{3,}\s*$")
SUBSEP = re.compile(r"^─{3,}\s+(.+?)\s+─{3,}\s*$")
SEPARATOR = re.compile(r"^═{3,}\s*$")


def slug(text: str) -> str:
    s = re.sub(r"[^\w]+", "-", text.lower()).strip("-")
    return s or "section"


def build() -> str:
    raw = SPEC.read_text(encoding="utf-8")
    lines = raw.splitlines()

    # First non-empty line is the title; subsequent until first blank are subtitle.
    title = lines[0].strip() if lines else "AXON"
    head_meta = []
    j = 1
    while j < len(lines) and lines[j].strip():
        head_meta.append(lines[j].strip())
        j += 1

    # Two-pass: first pass collects TOC entries; second pass builds body.
    toc: list[tuple[int, str, str]] = []  # (level, slug, label)
    body: list[str] = []
    in_pre = False

    def flush_pre() -> None:
        nonlocal in_pre
        if in_pre:
            body.append("</pre>")
            in_pre = False

    i = j
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if SEPARATOR.match(stripped):
            flush_pre()
            i += 1
            continue

        m = PART.match(stripped)
        if m:
            flush_pre()
            label = stripped
            sl = slug(label)
            toc.append((2, sl, label))
            body.append(
                f'<h2 id="{sl}"><a class="anchor" href="#{sl}">¶</a> {html.escape(label)}</h2>'
            )
            i += 1
            continue

        m = NODE_HEADING.match(stripped)
        if m:
            flush_pre()
            tag = m.group(1)
            label = tag
            sl = slug("node-" + tag.lstrip("@"))
            toc.append((3, sl, label))
            body.append(
                f'<h3 id="{sl}"><a class="anchor" href="#{sl}">¶</a> '
                f"<code>{html.escape(label)}</code></h3>"
            )
            i += 1
            continue

        m = SUBSEP.match(stripped)
        if m:
            flush_pre()
            label = m.group(1)
            sl = slug(label)
            body.append(
                f'<h3 id="{sl}"><a class="anchor" href="#{sl}">¶</a> {html.escape(label)}</h3>'
            )
            i += 1
            continue

        # Indented blocks (4+ spaces, or starting with 2 spaces and an "@" or "REQUIRED:"):
        if line.startswith("  ") and stripped:
            if not in_pre:
                body.append("<pre>")
                in_pre = True
            body.append(html.escape(line))
            i += 1
            continue

        if not stripped:
            flush_pre()
            i += 1
            continue

        # Plain paragraph — wrap whatever runs of non-blank, non-special lines.
        flush_pre()
        para_lines = [stripped]
        i += 1
        while (
            i < len(lines)
            and lines[i].strip()
            and not SEPARATOR.match(lines[i].strip())
            and not PART.match(lines[i].strip())
            and not NODE_HEADING.match(lines[i].strip())
            and not SUBSEP.match(lines[i].strip())
            and not lines[i].startswith("  ")
        ):
            para_lines.append(lines[i].strip())
            i += 1
        joined = " ".join(para_lines)
        body.append(f"<p>{html.escape(joined)}</p>")

    flush_pre()

    # ─── TOC HTML ─────────────────────────────────────────────
    toc_items = []
    for lvl, sl, label in toc:
        cls = "toc__h2" if lvl == 2 else "toc__h3"
        toc_items.append(
            f'<li class="{cls}"><a href="#{sl}">{html.escape(label)}</a></li>'
        )
    toc_html = "\n".join(toc_items)

    head_meta_html = "<br>".join(html.escape(m) for m in head_meta)

    return _page_template(title, head_meta_html, toc_html, "\n".join(body))


def _page_template(
    title: str, head_meta_html: str, toc_html: str, body_html: str
) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>tdoc · spec</title>
<meta name="description" content="The AXON document format specification — v1.0 core plus v1.1 semantic research blocks.">
<link rel="canonical" href="https://tdoc.xyz/spec">
<link rel="icon" type="image/svg+xml" href="/favicon.svg">
<meta property="og:title" content="AXON specification">
<meta property="og:description" content="A typed, queryable, signable document format. v1.0 core + v1.1 semantic research blocks.">
<meta property="og:type" content="article">
<meta property="og:url" content="https://tdoc.xyz/spec">
<meta name="twitter:card" content="summary">
<meta name="theme-color" content="#fafaf7" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#141310" media="(prefers-color-scheme: dark)">

<script src="./theme.js?v=3"></script>

<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Newsreader:ital,opsz,wght@0,6..72,200..800;1,6..72,200..800&family=JetBrains+Mono:ital,wght@0,400..600;1,400..600&display=swap">

<style>
:root{{--serif:"Newsreader","Iowan Old Style",Baskerville,Georgia,serif;--mono:"JetBrains Mono",ui-monospace,"SF Mono",Menlo,monospace;--col-max:1180px;--gutter:clamp(1.5rem,4vw,4rem)}}
:root,[data-theme="light"]{{--paper:#fafaf7;--paper-2:#f2eee4;--ink:#0c0c0c;--ink-2:#2b2a27;--ink-3:#55524d;--rule:#c8c3b7;--rule-soft:#e6e1d4;--oxblood:#7a0c1a}}
[data-theme="dark"]{{--paper:#141310;--paper-2:#1c1a15;--ink:#efe9d9;--ink-2:#c6c0b1;--ink-3:#8a8577;--rule:#2c2a24;--rule-soft:#221f1a;--oxblood:#d85565}}
*,*::before,*::after{{box-sizing:border-box;min-width:0}}
html{{-webkit-text-size-adjust:100%;overflow-x:hidden;scroll-behavior:smooth}}
body{{margin:0;background:var(--paper);color:var(--ink);font-family:var(--serif);font-size:clamp(1rem,.9rem + .45vw,1.15rem);line-height:1.6;font-variation-settings:"opsz" 17;-webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility;overflow-wrap:break-word}}
a{{color:var(--ink);text-decoration-thickness:1px;text-underline-offset:3px;text-decoration-color:var(--rule)}}
a:hover{{color:var(--oxblood);text-decoration-color:var(--oxblood)}}
::selection{{background:var(--oxblood);color:var(--paper)}}
.column{{max-width:var(--col-max);margin:0 auto;padding:0 var(--gutter)}}

.masthead{{border-bottom:1px solid var(--rule);padding:1.4rem 0}}
.masthead__grid{{display:flex;justify-content:space-between;align-items:baseline;gap:1rem;flex-wrap:wrap}}
.masthead__title{{font-family:var(--serif);font-style:italic;font-weight:500;font-size:1.4rem;margin:0;letter-spacing:-0.01em}}
.masthead__title a{{text-decoration:none}}
.masthead__title em{{font-style:italic;color:var(--oxblood)}}
.masthead__meta{{font-family:var(--mono);font-size:.78rem;color:var(--ink-3);letter-spacing:.04em;text-transform:uppercase}}
.masthead__meta a{{color:var(--ink-3);text-decoration:none}}
.masthead__meta a:hover{{color:var(--oxblood);text-decoration:underline}}
.theme-toggle button{{background:none;border:0;font:inherit;color:inherit;cursor:pointer;padding:0;letter-spacing:inherit;text-transform:inherit}}
.theme-toggle button[aria-pressed="true"]{{color:var(--oxblood)}}
.theme-toggle .sep{{margin:0 .4em;color:var(--ink-3)}}

.spec-shell{{display:grid;grid-template-columns:18rem minmax(0,1fr);gap:clamp(2rem,6vw,5rem);padding:clamp(2rem,5vw,3rem) 0}}
@media (max-width:920px){{.spec-shell{{grid-template-columns:1fr}}}}

.toc{{position:sticky;top:1rem;align-self:start;max-height:calc(100vh - 2rem);overflow-y:auto;font-family:var(--mono);font-size:.76rem;color:var(--ink-2);padding-right:.6rem}}
.toc h2{{font-family:var(--mono);font-size:.7rem;letter-spacing:.18em;text-transform:uppercase;color:var(--ink-3);margin:0 0 .8rem;padding-bottom:.4rem;border-bottom:1px solid var(--rule)}}
.toc ul{{list-style:none;padding:0;margin:0}}
.toc li{{padding:.12rem 0}}
.toc__h2{{margin-top:.6rem;color:var(--ink)}}
.toc__h3{{padding-left:1.1rem;color:var(--ink-3)}}
.toc a{{text-decoration:none;color:inherit}}
.toc a:hover{{color:var(--oxblood)}}

.spec article{{max-width:42rem;font-feature-settings:"onum","kern","liga"}}
.spec h1{{font-family:var(--serif);font-weight:400;font-size:clamp(2rem,1.6rem + 2vw,3rem);line-height:1.05;letter-spacing:-.02em;margin:0 0 1.2rem;font-variation-settings:"opsz" 60}}
.spec h1 em{{color:var(--oxblood)}}
.spec h2{{font-family:var(--serif);font-weight:600;font-size:1.4rem;margin:2.6rem 0 .6rem;padding-bottom:.4rem;border-bottom:1px solid var(--rule-soft);scroll-margin-top:1rem}}
.spec h3{{font-family:var(--serif);font-weight:600;font-size:1.1rem;margin:2.2rem 0 .4rem;color:var(--ink);scroll-margin-top:1rem}}
.spec h3 code{{font-family:var(--mono);font-size:.95em;background:transparent;padding:0;color:var(--oxblood)}}
.spec h2 .anchor,.spec h3 .anchor{{color:var(--ink-4);text-decoration:none;font-size:.7em;margin-right:.3em;opacity:0;transition:opacity 100ms}}
.spec h2:hover .anchor,.spec h3:hover .anchor{{opacity:1;color:var(--oxblood)}}
.spec p{{margin:0 0 1rem;color:var(--ink-2)}}
.spec pre{{font-family:var(--mono);font-size:.84rem;line-height:1.55;background:var(--rule-soft);border-left:3px solid var(--rule);padding:.9rem 1.1rem;overflow-x:auto;margin:.8rem 0 1.4rem;color:var(--ink-2)}}
.spec code{{font-family:var(--mono);font-size:.92em;background:var(--rule-soft);padding:.05em .35em;border:1px solid var(--rule)}}

.eyebrow{{font-family:var(--mono);font-size:.75rem;letter-spacing:.18em;text-transform:uppercase;color:var(--ink-3);margin:0 0 .8rem}}

.colophon{{margin-top:clamp(3rem,8vw,6rem);padding:2rem 0;border-top:1px solid var(--rule);font-family:var(--mono);font-size:.78rem;color:var(--ink-3);text-align:center}}
.colophon a{{color:var(--ink-3)}}
</style>
</head>
<body>

<header class="masthead">
  <div class="column masthead__grid">
    <h1 class="masthead__title"><a href="/">tdoc<em>.</em></a></h1>
    <div class="masthead__meta">
      <a href="/">Home</a> · <a href="/try">Try</a> · <a href="/view">View</a> · <a href="https://github.com/LuciferMors/tdoc" rel="noopener">Source</a>
      &nbsp;&nbsp;
      <span class="theme-toggle" role="group" aria-label="Theme">
        <button type="button" data-theme-set="light" aria-pressed="true">Day</button><span class="sep" aria-hidden="true">·</span><button type="button" data-theme-set="dark" aria-pressed="false">Night</button>
      </span>
    </div>
  </div>
</header>

<main class="column spec-shell spec">

<aside class="toc" aria-label="Table of contents">
  <h2>Contents</h2>
  <ul>
{toc_html}
  </ul>
</aside>

<article>
<p class="eyebrow">Version 1.1 · normative</p>
<h1>The <em>{html.escape(title.split()[0].lower())}</em> spec.</h1>
<p>{head_meta_html}</p>

{body_html}
</article>

</main>

<script src="./analytics-config.js?v=3"></script>
<script src="./analytics.js?v=3"></script>

<footer class="colophon">
  <div class="column">
    <p>tdoc · <a href="/">home</a> · <a href="/try">try</a> · <a href="/view">view</a> · <a href="/terms">terms</a> · <a href="/privacy">privacy</a> · <a href="/security">security</a> · <a href="https://github.com/LuciferMors/tdoc/blob/main/AXON_Format_Specification.txt" rel="noopener">spec source</a></p>
  </div>
</footer>

</body>
</html>
"""


def main() -> int:
    out = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(out, encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)} ({len(out)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
