"""Smoke tests for the axon-cloud API service.

Covers the happy path and auth rejection for each endpoint. A customer-shippable
API fails tests here, not in production."""

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

fastapi = pytest.importorskip("fastapi")
httpx = pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402

from product.service.main import app  # noqa: E402

AUTH = {"Authorization": "Bearer tdoc_dev_local"}
client = TestClient(app)


def test_healthz_open():
    r = client.get("/v1/healthz")
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_auth_required_on_me():
    assert client.get("/v1/me").status_code == 401
    assert (
        client.get("/v1/me", headers={"Authorization": "Bearer wrong"}).status_code
        == 401
    )
    ok = client.get("/v1/me", headers=AUTH)
    assert ok.status_code == 200
    body = ok.json()
    assert body["plan"] == "team"
    assert body["units_included"] > 0


def test_structure_axc_roundtrip():
    axc = b"""@section [id=\"hello\"]:\n  @paragraph:\n    Hi.\n"""
    files = {"file": ("in.axc", axc, "text/plain")}
    data = {"title": "Hello", "document_type": "article.test"}
    r = client.post("/v1/structure", headers=AUTH, files=files, data=data)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["nodes"] >= 3
    assert body["axc"].startswith("@document") or "@section" in body["axc"]


def test_structure_rejects_unknown_type():
    files = {"file": ("bad.zip", b"\x00\x00", "application/zip")}
    r = client.post("/v1/structure", headers=AUTH, files=files)
    assert r.status_code == 415


def test_query_aql():
    axc = """
@document:
  @section [id="s"]:
    @cell [data-type="pvalue" data-value="0.018"]: 0.018
    @cell [data-type="pvalue" data-value="0.5"]: 0.5
""".strip()
    payload = {
        "axc": axc,
        "aql": "QUERY q\nFROM @cell [data-type=pvalue]\nSELECT data-value\nWHERE data-value < 0.05\nRETURNS list",
    }
    r = client.post("/v1/query", headers=AUTH, json=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["count"] == 1


def test_sign_and_verify_roundtrip():
    pytest.importorskip("cryptography")
    axc = "@document:\n  @paragraph:\n    Signed.\n"
    manifest = {"title": "X", "document_id": "d", "axon_version": "1.0"}

    sign = client.post(
        "/v1/sign",
        headers=AUTH,
        json={"axc": axc, "render_axr": "", "manifest": manifest},
    )
    assert sign.status_code == 200, sign.text
    sig = sign.json()["signature"]

    verify = client.post(
        "/v1/verify",
        headers=AUTH,
        json={"axc": axc, "render_axr": "", "manifest": manifest, "signature": sig},
    )
    assert verify.status_code == 200, verify.text
    assert verify.json()["valid"] is True

    tampered = client.post(
        "/v1/verify",
        headers=AUTH,
        json={
            "axc": axc.replace("Signed", "Forged"),
            "render_axr": "",
            "manifest": manifest,
            "signature": sig,
        },
    )
    assert tampered.json()["valid"] is False


def test_free_tier_blocks_signing():
    from product.service.billing import register

    p = register("free")
    r = client.post(
        "/v1/sign",
        headers={"Authorization": f"Bearer {p.api_key}"},
        json={"axc": "@document:\n", "render_axr": "", "manifest": {}},
    )
    assert r.status_code == 402


def test_pro_tier_blocks_signing():
    from product.service.billing import register

    p = register("pro")
    r = client.post(
        "/v1/sign",
        headers={"Authorization": f"Bearer {p.api_key}"},
        json={"axc": "@document:\n", "render_axr": "", "manifest": {}},
    )
    assert r.status_code == 402


# --- /v1/try-public — public unauthenticated demo endpoint -----
# Powers the /try page on tdoc.xyz. Tighter caps than /v1/structure,
# no auth, no usage recording. IP rate limit handles abuse.


def test_try_public_no_auth_axc():
    axc = b'@section [id="hello"]:\n  @paragraph:\n    Hi.\n'
    files = {"file": ("in.axc", axc, "text/plain")}
    r = client.post("/v1/try-public", files=files)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["nodes"] >= 3
    assert "@section" in body["axc"] or body["axc"].startswith("@document")


def test_try_public_rejects_unknown_type():
    files = {"file": ("bad.zip", b"\x00\x00", "application/zip")}
    r = client.post("/v1/try-public", files=files)
    assert r.status_code == 415


def test_try_public_rejects_oversize():
    # 6 MiB exceeds the 5 MiB demo cap.
    big = b"x" * (6 * 1024 * 1024)
    files = {"file": ("huge.txt", big, "text/plain")}
    r = client.post("/v1/try-public", files=files)
    assert r.status_code == 413


def test_try_public_ignores_authorization_header():
    # Bogus Authorization must not gate the demo endpoint.
    axc = b"@paragraph:\n  hello\n"
    files = {"file": ("in.axc", axc, "text/plain")}
    r = client.post(
        "/v1/try-public",
        headers={"Authorization": "Bearer not-a-real-key"},
        files=files,
    )
    assert r.status_code == 200, r.text


def test_try_public_returns_real_hashes():
    # The demo response must carry actual content + render hashes — not
    # empty strings — so the UI shows real fingerprints, not "—".
    axc = b"@paragraph:\n  hi.\n"
    files = {"file": ("in.axc", axc, "text/plain")}
    r = client.post("/v1/try-public", files=files)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["content_hash"] and len(body["content_hash"]) >= 16
    assert body["render_hash"]


def test_try_public_default_doc_type_does_not_warn_about_sections():
    # Demo endpoint defaults to document_type=preprint so a 1-paragraph
    # input doesn't trigger spammy "Expected section X" warnings.
    axc = b"@paragraph:\n  short demo input.\n"
    files = {"file": ("in.axc", axc, "text/plain")}
    r = client.post("/v1/try-public", files=files)
    assert r.status_code == 200, r.text
    body = r.json()
    section_warnings = [w for w in body["warnings"] if "Expected section" in w]
    assert section_warnings == []


def test_structure_response_carries_real_hashes():
    # The authenticated path must also return non-empty hashes — the UI
    # treats them as fingerprints, not optional metadata.
    axc = b'@section [id="hello"]:\n  @paragraph:\n    Hi.\n'
    files = {"file": ("in.axc", axc, "text/plain")}
    data = {"title": "Hello", "document_type": "article.test"}
    r = client.post("/v1/structure", headers=AUTH, files=files, data=data)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["content_hash"] and len(body["content_hash"]) >= 16
    assert body["render_hash"]


# ─── Rich-response contract: html + tree + archive_b64 ──────────
# The /try page reads these; if any is missing or malformed, the
# Preview tab is blank, the JSON tab is empty, or .tdoc download fails.


def test_try_public_returns_html_preview():
    axc = b"@paragraph:\n  hello\n"
    files = {"file": ("in.axc", axc, "text/plain")}
    r = client.post("/v1/try-public", files=files)
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body["html"], str)
    # Some rendered HTML must come back — an empty string is a regression.
    assert len(body["html"]) > 0


def test_try_public_returns_json_tree():
    axc = b"@paragraph:\n  hello\n"
    files = {"file": ("in.axc", axc, "text/plain")}
    r = client.post("/v1/try-public", files=files)
    assert r.status_code == 200, r.text
    body = r.json()
    tree = body["tree"]
    assert isinstance(tree, dict)
    assert tree.get("type")  # at minimum a typed root node


def test_try_public_returns_downloadable_tdoc_archive():
    import base64
    import zipfile
    import io

    axc = b"@paragraph:\n  hello\n"
    files = {"file": ("in.axc", axc, "text/plain")}
    r = client.post("/v1/try-public", files=files)
    assert r.status_code == 200, r.text
    body = r.json()
    archive_b64 = body["archive_b64"]
    assert archive_b64, "archive_b64 must be non-empty"

    raw = base64.b64decode(archive_b64)
    # Must be a real ZIP we can open and that contains the manifest +
    # content entries the .tdoc layout requires.
    zf = zipfile.ZipFile(io.BytesIO(raw))
    names = set(zf.namelist())
    assert "manifest.json" in names
    assert "content/document.axc" in names


def test_try_public_accepts_tdoc_archive_roundtrip():
    """Upload .axc → get back .tdoc → re-upload .tdoc → see the same content."""
    import base64

    axc = (
        b'@section [id="intro"]:\n'
        b"  @heading [level=1]:\n"
        b"    Hello from a roundtrip\n"
        b"  @paragraph:\n"
        b"    Some paragraph body.\n"
    )
    r1 = client.post("/v1/try-public", files={"file": ("in.axc", axc, "text/plain")})
    assert r1.status_code == 200, r1.text
    archive_bytes = base64.b64decode(r1.json()["archive_b64"])
    assert archive_bytes.startswith(b"PK")  # ZIP magic

    # Re-upload as .tdoc and verify the same axc comes back.
    r2 = client.post(
        "/v1/try-public",
        files={"file": ("downloaded.tdoc", archive_bytes, "application/zip")},
    )
    assert r2.status_code == 200, r2.text
    assert "Hello from a roundtrip" in r2.json()["axc"]


def test_try_public_rejects_corrupt_tdoc():
    files = {"file": ("bad.tdoc", b"not a zip at all", "application/zip")}
    r = client.post("/v1/try-public", files=files)
    # Either 400 (AxonSecurityError caught) or 500 (unhandled) — must be a
    # 4xx so the client gets a clean error, never a stack trace.
    assert 400 <= r.status_code < 500, r.text


# ─── PDF-as-container — the universal-compat download ──────────


def test_try_public_returns_pdf_with_embedded_axon():
    """The response must include a real PDF containing an axon-content.axc
    embedded file. This is the universal download — opens in Preview /
    Acrobat / browser as a normal PDF, AI tools extract AXON via the
    embedded-files API."""
    import base64

    pytest.importorskip("pymupdf")
    import pymupdf as fitz

    axc = (
        b'@section [id="intro"]:\n'
        b"  @heading [level=1]:\n"
        b"    A short paper\n"
        b"  @paragraph:\n"
        b"    With a body.\n"
    )
    r = client.post("/v1/try-public", files={"file": ("in.axc", axc, "text/plain")})
    assert r.status_code == 200, r.text
    body = r.json()
    pdf_b64 = body.get("pdf_b64") or ""
    assert pdf_b64, "pdf_b64 must be non-empty"
    pdf_bytes = base64.b64decode(pdf_b64)
    assert pdf_bytes.startswith(b"%PDF"), "must begin with the PDF magic"

    pdf = fitz.open(stream=pdf_bytes, filetype="pdf")
    names = {pdf.embfile_info(i)["filename"] for i in range(pdf.embfile_count())}
    assert "axon-content.axc" in names
    assert "axon-manifest.json" in names


def test_try_public_pdf_roundtrip():
    """Upload .axc → server returns a PDF with embedded AXON → re-upload
    that PDF → server detects the embedded AXON and round-trips back to
    the same content. This is the full universal-container contract."""
    import base64

    pytest.importorskip("pymupdf")

    axc = b'@section [id="hi"]:\n' b"  @paragraph:\n" b"    Roundtrip via PDF.\n"
    r1 = client.post("/v1/try-public", files={"file": ("in.axc", axc, "text/plain")})
    assert r1.status_code == 200, r1.text
    pdf_bytes = base64.b64decode(r1.json()["pdf_b64"])
    assert pdf_bytes.startswith(b"%PDF")

    r2 = client.post(
        "/v1/try-public",
        files={"file": ("downloaded.pdf", pdf_bytes, "application/pdf")},
    )
    assert r2.status_code == 200, r2.text
    assert "Roundtrip via PDF" in r2.json()["axc"]


def test_try_public_pdf_has_visible_content():
    """PDF must render visible content in standard viewers — pixel-count
    check on the first page guards against the blank-page regression
    where the renderer produced a valid PDF skeleton with no painted
    text."""
    import base64

    pytest.importorskip("pymupdf")
    import pymupdf as fitz

    axc = (
        b"@section [id=intro]:\n"
        b"  @heading [level=1]:\n"
        b"    Visible content test\n"
        b"  @paragraph:\n"
        b"    The quick brown fox jumps over the lazy dog.\n"
    )
    r = client.post("/v1/try-public", files={"file": ("in.axc", axc, "text/plain")})
    assert r.status_code == 200, r.text
    pdf_bytes = base64.b64decode(r.json()["pdf_b64"])
    pdf = fitz.open(stream=pdf_bytes, filetype="pdf")
    assert len(pdf) >= 1
    page1 = pdf[0]
    pix = page1.get_pixmap(dpi=72)
    raw = pix.samples
    non_white = sum(
        1
        for k in range(0, len(raw), pix.n)
        if raw[k] < 250 or raw[k + 1] < 250 or raw[k + 2] < 250
    )
    # An A4 page with real text has tens of thousands of dark pixels;
    # a "blank" page has fewer than a hundred. Pick a generous floor.
    assert non_white > 1000, f"PDF page 1 looks blank — only {non_white} non-white px"
    text = page1.get_text()
    assert "Visible content test" in text
    assert "quick brown fox" in text


def test_try_public_pdf_strips_inline_markup():
    """Square-bracket inline-span markup must not leak into the visible
    PDF text — readers see clean prose, AI agents read the typed layer
    from the embedded axon-content.axc."""
    import base64

    pytest.importorskip("pymupdf")
    import pymupdf as fitz

    axc = (
        b"@paragraph:\n"
        b'  Across [data-type="numeric"]n=412[/data-type] adults the effect held.\n'
    )
    r = client.post("/v1/try-public", files={"file": ("in.axc", axc, "text/plain")})
    assert r.status_code == 200, r.text
    pdf_bytes = base64.b64decode(r.json()["pdf_b64"])
    pdf = fitz.open(stream=pdf_bytes, filetype="pdf")
    text = pdf[0].get_text()
    assert "[data-type=" not in text
    assert "[/data-type]" not in text
    assert "n=412" in text


def test_try_public_falls_back_for_vanilla_pdf():
    """A PDF without embedded AXON must still parse via the OCR-style
    convert_pdf path — never 4xx just because it's not tdoc-flavoured."""
    pytest.importorskip("pymupdf")
    import pymupdf as fitz
    import io as _io

    # Build a tiny PDF in-memory with no embedded files.
    pdf = fitz.open()
    page = pdf.new_page(width=595, height=842)  # A4
    page.insert_text((72, 72), "Vanilla paper, no AXON inside.", fontsize=12)
    buf = _io.BytesIO()
    pdf.save(buf)
    vanilla_pdf = buf.getvalue()

    r = client.post(
        "/v1/try-public",
        files={"file": ("vanilla.pdf", vanilla_pdf, "application/pdf")},
    )
    assert r.status_code == 200, r.text
    assert r.json()["nodes"] >= 1
