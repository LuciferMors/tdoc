"""Lemon Squeezy webhook handler tests.

Exercises the signature-verify, tier-mapping, and plan-mutation paths
with synthetic LS payloads. These tests do NOT hit the real LS API —
they construct a payload, HMAC-sign it with a known secret, POST it,
and assert what changed on the in-memory store afterwards.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402

from product.service.main import app  # noqa: E402
from product.service.billing import find_by_subscription_id  # noqa: E402
from product.service.store import get_store  # noqa: E402

client = TestClient(app)

WEBHOOK_PATH = "/v1/webhooks/lemonsqueezy"

SECRET = "test-ls-secret-do-not-use-in-prod"


@pytest.fixture(autouse=True)
def _ls_env(monkeypatch):
    monkeypatch.setenv("LEMONSQUEEZY_WEBHOOK_SECRET", SECRET)
    monkeypatch.setenv(
        "LS_VARIANT_MAP",
        json.dumps({"100": "pro", "101": "team", "102": "scale"}),
    )
    yield


def _sign(body: bytes) -> str:
    return hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()


def _payload(
    event: str, sub_id: str, variant_id: str = "100", customer_id: str = "9001"
):
    return {
        "meta": {"event_name": event, "test_mode": True},
        "data": {
            "type": "subscriptions",
            "id": sub_id,
            "attributes": {
                "variant_id": int(variant_id),
                "customer_id": int(customer_id),
                "user_email": "buyer@example.com",
                "status": "active",
            },
        },
    }


def _post(payload: dict, signature: str | None = None):
    body = json.dumps(payload).encode("utf-8")
    sig = signature if signature is not None else _sign(body)
    return client.post(
        WEBHOOK_PATH,
        content=body,
        headers={"Content-Type": "application/json", "X-Signature": sig},
    )


def test_webhook_rejects_missing_signature():
    body = json.dumps(_payload("subscription_created", "sub-1")).encode()
    r = client.post(
        WEBHOOK_PATH,
        content=body,
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 401


def test_webhook_rejects_wrong_signature():
    r = _post(_payload("subscription_created", "sub-2"), signature="deadbeef")
    assert r.status_code == 401


def test_webhook_503_when_secret_unset(monkeypatch):
    monkeypatch.delenv("LEMONSQUEEZY_WEBHOOK_SECRET", raising=False)
    r = _post(_payload("subscription_created", "sub-3"))
    assert r.status_code == 503


def test_subscription_created_provisions_key_at_correct_tier():
    r = _post(_payload("subscription_created", "sub-A", variant_id="101"))
    assert r.status_code == 200, r.text
    plan = find_by_subscription_id("sub-A")
    assert plan is not None
    assert plan.tier == "team"
    assert plan.lemonsqueezy_subscription_id == "sub-A"
    assert plan.lemonsqueezy_customer_id == "9001"


def test_subscription_created_falls_back_to_pro_when_variant_unmapped():
    r = _post(_payload("subscription_created", "sub-B", variant_id="9999"))
    assert r.status_code == 200, r.text
    plan = find_by_subscription_id("sub-B")
    assert plan is not None
    # Unknown variant → "pro" fallback so the customer isn't blocked.
    assert plan.tier == "pro"


def test_subscription_updated_changes_tier():
    _post(_payload("subscription_created", "sub-C", variant_id="100"))  # pro
    plan = find_by_subscription_id("sub-C")
    assert plan.tier == "pro"

    r = _post(_payload("subscription_updated", "sub-C", variant_id="102"))  # → scale
    assert r.status_code == 200, r.text
    plan = find_by_subscription_id("sub-C")
    assert plan.tier == "scale"
    # Tier-spec defaults must follow the new tier — units_included etc.
    from product.service.billing import TIER_SPECS

    assert plan.units_included == TIER_SPECS["scale"]["units_included"]


def test_subscription_updated_creates_if_unknown():
    # subscription_updated for a sub_id we've never seen → treat as create.
    r = _post(_payload("subscription_updated", "sub-D", variant_id="101"))
    assert r.status_code == 200, r.text
    plan = find_by_subscription_id("sub-D")
    assert plan is not None
    assert plan.tier == "team"


def test_subscription_cancelled_downgrades_to_free():
    _post(_payload("subscription_created", "sub-E", variant_id="102"))  # scale
    plan = find_by_subscription_id("sub-E")
    assert plan.tier == "scale"

    r = _post(_payload("subscription_cancelled", "sub-E"))
    assert r.status_code == 200, r.text
    plan = find_by_subscription_id("sub-E")
    assert plan.tier == "free"


def test_unknown_event_is_accepted_no_op():
    # LS sends events we don't yet handle (e.g. order_refunded). Don't 4xx
    # — that would make LS retry forever. Accept and no-op.
    r = _post(_payload("order_refunded", "ord-1"))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("action") == "ignored"


def test_webhook_does_not_leak_full_api_key():
    r = _post(_payload("subscription_created", "sub-F"))
    body = r.json()
    # Response should expose at most a short prefix, never the full key.
    if "key_prefix" in body:
        assert len(body["key_prefix"]) <= 16
    assert "api_key" not in body


def test_signature_with_constant_time_compare_only(monkeypatch):
    # Ensure the verifier uses hmac.compare_digest semantics — same-length
    # but-wrong digest is still rejected. (Smoke test for the helper.)
    from product.service.security import verify_lemonsqueezy_signature

    body = b"{}"
    good = _sign(body)
    bad = "0" * len(good)  # same length, different content
    assert verify_lemonsqueezy_signature(SECRET, body, good)
    assert not verify_lemonsqueezy_signature(SECRET, body, bad)


def test_store_refresh_persists_subscription_id():
    """Re-lookup after register should still find the same subscription_id."""
    _post(_payload("subscription_created", "sub-G"))
    plan = find_by_subscription_id("sub-G")
    assert plan is not None

    # The store is the source of truth — the lookup should return a plan
    # with the LS metadata populated.
    refetched = get_store().get(plan.api_key)
    assert refetched is not None
    assert refetched.lemonsqueezy_subscription_id == "sub-G"
