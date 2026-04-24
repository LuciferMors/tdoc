"""Security-header + CORS + rate-limit regression tests.

Every claim made in SECURITY.md and THREAT_MODEL.md must have a test here.
If these fail, the API has regressed on a published security guarantee.
"""

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from product.service.main import app  # noqa: E402

AUTH = {"Authorization": "Bearer tdoc_dev_local"}
client = TestClient(app)


# ──────────────────────────────────────────────────────────────────────
# Security headers
# ──────────────────────────────────────────────────────────────────────


def test_hsts_header_present():
    r = client.get("/v1/healthz")
    hsts = r.headers.get("strict-transport-security", "")
    assert "max-age=31536000" in hsts
    assert "includeSubDomains" in hsts
    assert "preload" in hsts


def test_frame_options_deny():
    r = client.get("/v1/healthz")
    assert r.headers.get("x-frame-options") == "DENY"


def test_content_type_options_nosniff():
    r = client.get("/v1/healthz")
    assert r.headers.get("x-content-type-options") == "nosniff"


def test_referrer_policy_strict():
    r = client.get("/v1/healthz")
    assert r.headers.get("referrer-policy") == "strict-origin-when-cross-origin"


def test_permissions_policy_locks_dangerous_apis():
    r = client.get("/v1/healthz")
    pp = r.headers.get("permissions-policy", "")
    for api in ["camera=()", "geolocation=()", "microphone=()", "payment=()", "usb=()"]:
        assert api in pp, f"missing lockdown for {api}"


def test_server_header_does_not_leak_framework():
    r = client.get("/v1/healthz")
    server = r.headers.get("server", "").lower()
    assert "uvicorn" not in server
    assert "starlette" not in server
    assert "python" not in server
    assert server == "tdoc"


def test_request_id_header_present():
    r = client.get("/v1/healthz")
    rid = r.headers.get("x-request-id")
    assert rid and len(rid) >= 16


# ──────────────────────────────────────────────────────────────────────
# CORS allowlist
# ──────────────────────────────────────────────────────────────────────


def test_cors_allows_tdoc_origin():
    r = client.options(
        "/v1/healthz",
        headers={
            "Origin": "https://tdoc.xyz",
            "Access-Control-Request-Method": "GET",
        },
    )
    # Either 200 (Starlette handled) or at minimum the ACAO header is present.
    assert r.headers.get("access-control-allow-origin") == "https://tdoc.xyz"


def test_cors_rejects_unknown_origin():
    r = client.options(
        "/v1/healthz",
        headers={
            "Origin": "https://evil.example.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    # Disallowed origin must NOT receive Access-Control-Allow-Origin header.
    assert r.headers.get("access-control-allow-origin") != "https://evil.example.com"


# ──────────────────────────────────────────────────────────────────────
# Auth + error-leak
# ──────────────────────────────────────────────────────────────────────


def test_invalid_api_key_rejected():
    r = client.get("/v1/me", headers={"Authorization": "Bearer tdoc_fake_" + "x" * 30})
    assert r.status_code == 401
    # Error response must NOT include stack trace fragments.
    body = r.text.lower()
    assert "traceback" not in body
    assert "file " not in body
    assert ".py" not in body


def test_missing_auth_returns_401():
    r = client.get("/v1/me")
    assert r.status_code == 401


def test_error_response_includes_request_id():
    """Even non-200 responses carry the request ID so customers can file tickets."""
    r = client.get("/v1/me", headers={"Authorization": "Bearer tdoc_fake"})
    assert r.status_code == 401
    assert r.headers.get("x-request-id")


# ──────────────────────────────────────────────────────────────────────
# Body size cap
# ──────────────────────────────────────────────────────────────────────


def test_oversized_content_length_rejected():
    """Requests with Content-Length > 32 MiB are rejected before body is read."""
    r = client.post(
        "/v1/query",
        headers={**AUTH, "Content-Length": str(50 * 1024 * 1024)},
        content=b"x",  # actual body doesn't need to be huge; header alone triggers reject
    )
    # The middleware should reject based on header alone.
    assert r.status_code in (413, 400)


# ──────────────────────────────────────────────────────────────────────
# Audit log — no raw API keys logged
# ──────────────────────────────────────────────────────────────────────


def test_audit_log_masks_api_key(caplog):
    """The audit log must never contain the full API key string."""
    import logging

    with caplog.at_level(logging.INFO, logger="tdoc.security"):
        client.get("/v1/me", headers=AUTH)
    full_key = "tdoc_dev_local"
    for record in caplog.records:
        assert (
            full_key not in record.getMessage()
        ), f"full API key leaked in audit log: {record.getMessage()}"
