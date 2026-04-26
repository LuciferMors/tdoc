"""Store interface tests — exercises the in-memory backend.

The Postgres path is not exercised in CI (no live DB); the same code path
is exercised in production by the live `/v1/me` endpoint and the
Lemon Squeezy webhook (next session). Both stores share the same `Store`
protocol, so the in-memory tests pin down the contract that PostgresStore
must also honour."""

from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from product.service.billing import (  # noqa: E402
    Plan,
    PlanQuotaExceeded,
    TIER_SPECS,
    get_principal,
    record_units,
    register,
)
from product.service.store import (  # noqa: E402
    InMemoryStore,
    get_store,
    reset_for_tests,
)


@pytest.fixture(autouse=True)
def _fresh_store(monkeypatch):
    # Force the in-memory backend regardless of any DATABASE_URL leaked
    # from the developer's shell, then drop the singleton so each test
    # starts on a clean slate.
    monkeypatch.delenv("DATABASE_URL", raising=False)
    reset_for_tests()
    yield
    reset_for_tests()


def test_in_memory_store_get_returns_none_for_unknown_key():
    s = InMemoryStore()
    assert s.get("nope") is None


def test_in_memory_store_put_then_get_roundtrip():
    s = InMemoryStore()
    p = Plan(api_key="k", tier="pro", units_included=10, units_used=0)
    s.put(p)
    got = s.get("k")
    assert got is not None
    assert got.api_key == "k"
    assert got.tier == "pro"
    assert got.units_included == 10


def test_in_memory_store_update_persists_usage_change():
    s = InMemoryStore()
    p = Plan(api_key="k", tier="pro", units_included=10, units_used=0)
    s.put(p)
    p.units_used = 5
    s.update(p)
    assert s.get("k").units_used == 5


def test_get_store_returns_in_memory_when_no_database_url():
    s = get_store()
    assert isinstance(s, InMemoryStore)


def test_register_provisions_unique_keys():
    a = register("free")
    b = register("free")
    assert a.api_key != b.api_key
    assert get_principal(a.api_key) is a or get_principal(a.api_key).tier == "free"
    assert get_principal(b.api_key) is not None


def test_record_units_persists_across_lookups():
    p = register("pro")
    record_units(p, 3)
    record_units(p, 7)
    refetched = get_principal(p.api_key)
    assert refetched is not None
    assert refetched.units_used == 10


def test_record_units_blocks_at_quota_on_hard_block_tier():
    # Free tier has overage_price_cents=0 → hard block at units_included.
    p = register("free")
    cap = TIER_SPECS["free"]["units_included"]
    record_units(p, cap)  # exactly at the cap is allowed
    with pytest.raises(PlanQuotaExceeded):
        record_units(p, 1)
    # Rollback persisted: refetched plan still at cap, not over.
    refetched = get_principal(p.api_key)
    assert refetched.units_used == cap


def test_record_units_allows_overage_on_metered_tier():
    # Team tier has overage_price_cents=2 → no hard block, charged off-band.
    p = register("team")
    cap = TIER_SPECS["team"]["units_included"]
    record_units(p, cap + 5)  # exceeds cap, no exception
    refetched = get_principal(p.api_key)
    assert refetched.units_used == cap + 5


def test_dev_seed_only_runs_when_env_is_dev(monkeypatch):
    # Default env is 'dev' → seed key exists.
    reset_for_tests()
    s = get_store()
    assert s.get("tdoc_dev_local") is not None

    # With TDOC_ENV=prod the seed key must NOT be present (security: a
    # known key MUST NOT work against a prod-flagged store).
    monkeypatch.setenv("TDOC_ENV", "prod")
    reset_for_tests()
    s = get_store()
    assert s.get("tdoc_dev_local") is None
