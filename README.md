# AXON — Document Format · powers **tdoc** (https://tdoc.xyz)

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/LuciferMors/tdoc/blob/main/examples/quickstart.ipynb)
[![PyPI](https://img.shields.io/pypi/v/axon-document.svg)](https://pypi.org/project/axon-document/)
[![Observatory](https://img.shields.io/badge/Observatory-A%2B%20125-7a0c1a)](https://developer.mozilla.org/en-US/observatory/analyze?host=tdoc.xyz)

Deterministic, semantic, signable documents. A `.pdf` you can open in every viewer on the planet — with the typed AXON tree embedded inside so AI tools extract structure without rendering.

- **Try in 5 seconds**: https://tdoc.xyz/try — drop a PDF, get a typed PDF back.
- **View any tdoc-flavoured PDF**: https://tdoc.xyz/view
- **Spec**: [`AXON_Format_Specification.txt`](AXON_Format_Specification.txt) — v1.0 core + v1.1 semantic research blocks. Rendered: https://tdoc.xyz/spec
- **Reference impl**: `axon.py` — single-file Python reference (~2000 lines).
- **Quickstart**: `examples/quickstart.ipynb` — install → typed paper → query → render → sign, in 30 seconds. [Open in Colab](https://colab.research.google.com/github/LuciferMors/tdoc/blob/main/examples/quickstart.ipynb).
- **Product** (hosted API): `product/` — see `product/README.md`.

## A tdoc is a PDF

> A **tdoc** is a normal PDF file with the **AXON** tree embedded inside as
> PDF/A-3 attachments. It opens in Preview, Acrobat, Chrome, Safari, email,
> LMS — anywhere PDF works. AI agents extract the structured AXON layer
> with one call, never rendering the visual page.

- **File extension**: `.pdf` — so it just works.
- **Format on the wire**: PDF + embedded `axon-content.axc`, `axon-manifest.json`, `axon-render.axr`, `axon-signature.json`.
- **AXON** is the open format inside. Apache-2.0 spec + reference. Anyone can author, render, sign, or verify a tdoc without our service.
- Legacy `.tdoc` ZIP archives from earlier builds still upload-roundtrip via the API for backwards compatibility, but every tool in the tdoc surface (`/try`, `/view`, the SDK) now produces and consumes the PDF form.

## Status

Public beta. AXON v1.0 core + v1.1 semantic research blocks. Reference implementation ships with **103 passing tests** covering parse, render, archive, sign/verify, validator, and the v1.1 schema. Landing is live at https://tdoc.xyz with Mozilla Observatory **A+ · 125/125** on the apex and **A+ · 130** on the API surface.

## Install

From PyPI (once published):

```bash
pip install axon-document           # → import axon
pip install axon-document[crypto]   # + Ed25519 signatures
pip install axon-document[pdf]      # + PyMuPDF PDF ingest
pip install axon-document[all]      # everything
```

From source (editable):

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev,crypto]"
.venv/bin/pytest tests/ product/tests/
```

Optional extras: `[pdf]`, `[fastjson]`, `[crypto]`, `[mathml]`, `[all]`.

## Quick start

```python
from axon import convert_axc_string, encode_archive, decode_archive, render_html

doc = convert_axc_string("""
@section [id="hello"]:
  @heading [level=1]:
    Hello
  @paragraph:
    A deterministic document.
""", title="Hello", document_type="article.research")

encode_archive(doc, "hello.tdoc")  # .tdoc extension is the convention

loaded = decode_archive("hello.tdoc", verify=True)
print(render_html(loaded))
```

## What's verified

As of the current test suite (`pytest tests/`):

| Invariant | Status |
|---|---|
| AXC parse ↔ serialise round-trip (Unicode, nested, attributes) | ✅ |
| Archive byte-determinism — two encodes produce identical bytes | ✅ |
| ZIP entries stamped with fixed epoch (not wall-clock) | ✅ |
| `encode_archive` does not mutate `manifest.modified` | ✅ |
| Content-hash tamper detection via `validate()` | ✅ |
| `verify_document` rejects zeroed manifest hash | ✅ |
| **Ed25519 cryptographic signing + verification** | ✅ |
| **ZIP-bomb + path-traversal defenses on decode** | ✅ |
| **Spec conformance (accessibility warnings, dup-ids, hash mismatch)** | ✅ |

**32 tests, 0 xfail** for the format. **18 additional tests** for the `tdoc` API service (auth, quotas, security headers, rate limits). **50 total, all green**.

## License

Apache-2.0. See `LICENSE`.

## Commercial

Hosted API, paid plans, and signing-as-a-service live at **[tdoc.xyz](https://tdoc.xyz)**.
