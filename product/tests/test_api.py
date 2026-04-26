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
