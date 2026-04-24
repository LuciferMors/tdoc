# AXON — Document Format · powers **tdoc** (https://tdoc.xyz)

Deterministic, semantic, signable document archives. A clean break from PDF / DOCX / HTML.

- **Spec**: `AXON_Format_Specification.txt` — v1.0 design draft.
- **Reference impl**: `axon.py` — single-file Python reference (~1800 lines).
- **Demo**: `demo.py` — runs the full pipeline end-to-end.
- **Product** (commercial API on top): `product/` — see `product/README.md`.

## The AXON format vs the `.tdoc` file extension

- **AXON** is the open format. Open spec, Apache-2.0 reference implementation. Anyone can build tools on it.
- **`.tdoc`** is the standard file extension for AXON archives. A `.tdoc` file *is* an AXON archive.
- Readers that support AXON also accept `.axon` for backwards compatibility.

Think of it like `.png` vs PNG: one is the file extension users see, the other is the open standard.

## Status

Early-alpha reference. Spec is complete; implementation covers most of it and ships with 27 tests covering the load-bearing invariants.

## Install (editable)

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev,crypto]"
.venv/bin/pytest
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

**27 tests, 0 xfail** for the format. **8 additional tests** for the `tdoc` API service.

## License

Apache-2.0. See `LICENSE`.

## Commercial

Hosted API, paid plans, and signing-as-a-service live at **[tdoc.xyz](https://tdoc.xyz)**.
