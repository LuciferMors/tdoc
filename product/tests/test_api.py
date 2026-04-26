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
