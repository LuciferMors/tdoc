"""Plan storage backend — in-memory by default, Postgres when DATABASE_URL is set.

Why this exists: HF Spaces' filesystem is ephemeral. The previous in-memory
`_STORE = {}` in billing.py meant every Space restart wiped every API key —
unacceptable once a real customer exists. This module hides the storage
choice behind a single `Store` protocol so billing.py stays readable and the
test suite stays fast.

Production path:
    DATABASE_URL=postgres://...  (Supabase, Neon, Railway — any plain Postgres)
    HF Space rebuilds → first call to get_store() initialises the pool, runs
    the migration, and serves all subsequent reads/writes from Postgres.

Dev / CI path:
    DATABASE_URL unset → InMemoryStore (current behaviour, no new dep).

The psycopg import is intentionally lazy: production HF Spaces install it via
requirements.txt, but local dev / CI without DATABASE_URL never imports it.
"""

from __future__ import annotations

import os
import threading
from typing import Optional, Protocol

from product.service.billing import Plan, TIER_SPECS


class Store(Protocol):
    def get(self, api_key: str) -> Optional[Plan]: ...
    def put(self, plan: Plan) -> None: ...
    def update(self, plan: Plan) -> None: ...


class InMemoryStore:
    """Process-local dict. Wiped on restart. Fine for dev/tests, never for prod."""

    def __init__(self) -> None:
        self._d: dict[str, Plan] = {}
        self._lock = threading.Lock()

    def get(self, api_key: str) -> Optional[Plan]:
        with self._lock:
            return self._d.get(api_key)

    def put(self, plan: Plan) -> None:
        with self._lock:
            self._d[plan.api_key] = plan

    def update(self, plan: Plan) -> None:
        # Same object reference → already updated; lock is just for memory safety.
        with self._lock:
            self._d[plan.api_key] = plan


_PG_DDL = """
CREATE TABLE IF NOT EXISTS plans (
  api_key TEXT PRIMARY KEY,
  tier TEXT NOT NULL,
  units_included INTEGER NOT NULL,
  units_used INTEGER NOT NULL DEFAULT 0,
  overage_price_cents INTEGER NOT NULL DEFAULT 0,
  lemonsqueezy_customer_id TEXT,
  lemonsqueezy_subscription_id TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_plans_lsq_sub
  ON plans(lemonsqueezy_subscription_id);
"""


class PostgresStore:
    """Postgres-backed store. Compatible with Supabase, Neon, Railway, RDS.

    Connection strategy: a small psycopg ConnectionPool. Each request gets a
    short-lived connection from the pool. For HF Space free tier (1 vCPU,
    single worker) a pool size of 4 is more than enough — bumps to a separate
    PgBouncer once we cross meaningful traffic.
    """

    def __init__(self, dsn: str) -> None:
        # Lazy import — psycopg is only required when DATABASE_URL is set.
        try:
            from psycopg_pool import ConnectionPool  # type: ignore[import-not-found]
        except ImportError as e:  # pragma: no cover — import-time guard
            raise RuntimeError(
                "DATABASE_URL is set but psycopg[pool] is not installed. "
                "Add 'psycopg[binary,pool]>=3.2' to requirements.txt."
            ) from e

        self._pool = ConnectionPool(
            conninfo=dsn,
            min_size=1,
            max_size=4,
            timeout=10,
            kwargs={"autocommit": True},
        )
        self._migrated = False
        self._mig_lock = threading.Lock()

    def _migrate_once(self) -> None:
        if self._migrated:
            return
        with self._mig_lock:
            if self._migrated:
                return
            with self._pool.connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(_PG_DDL)
            self._migrated = True

    def get(self, api_key: str) -> Optional[Plan]:
        self._migrate_once()
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT api_key, tier, units_included, units_used, "
                    "overage_price_cents, lemonsqueezy_customer_id, "
                    "lemonsqueezy_subscription_id "
                    "FROM plans WHERE api_key = %s",
                    (api_key,),
                )
                row = cur.fetchone()
        if not row:
            return None
        return Plan(
            api_key=row[0],
            tier=row[1],
            units_included=row[2],
            units_used=row[3],
            overage_price_cents=row[4],
            lemonsqueezy_customer_id=row[5],
            lemonsqueezy_subscription_id=row[6],
        )

    def put(self, plan: Plan) -> None:
        self._migrate_once()
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO plans (api_key, tier, units_included, "
                    "units_used, overage_price_cents, "
                    "lemonsqueezy_customer_id, lemonsqueezy_subscription_id) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s) "
                    "ON CONFLICT (api_key) DO UPDATE SET "
                    "tier = EXCLUDED.tier, "
                    "units_included = EXCLUDED.units_included, "
                    "units_used = EXCLUDED.units_used, "
                    "overage_price_cents = EXCLUDED.overage_price_cents, "
                    "lemonsqueezy_customer_id = EXCLUDED.lemonsqueezy_customer_id, "
                    "lemonsqueezy_subscription_id = EXCLUDED.lemonsqueezy_subscription_id, "
                    "updated_at = NOW()",
                    (
                        plan.api_key,
                        plan.tier,
                        plan.units_included,
                        plan.units_used,
                        plan.overage_price_cents,
                        plan.lemonsqueezy_customer_id,
                        plan.lemonsqueezy_subscription_id,
                    ),
                )

    def update(self, plan: Plan) -> None:
        # Hot path — just bump usage / metadata; assume row exists.
        self._migrate_once()
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE plans SET units_used = %s, tier = %s, "
                    "units_included = %s, overage_price_cents = %s, "
                    "lemonsqueezy_customer_id = %s, "
                    "lemonsqueezy_subscription_id = %s, "
                    "updated_at = NOW() "
                    "WHERE api_key = %s",
                    (
                        plan.units_used,
                        plan.tier,
                        plan.units_included,
                        plan.overage_price_cents,
                        plan.lemonsqueezy_customer_id,
                        plan.lemonsqueezy_subscription_id,
                        plan.api_key,
                    ),
                )


_singleton: Optional[Store] = None
_singleton_lock = threading.Lock()


def get_store() -> Store:
    """Return the configured store. Postgres if DATABASE_URL is set, else memory."""
    global _singleton
    if _singleton is not None:
        return _singleton
    with _singleton_lock:
        if _singleton is not None:
            return _singleton
        dsn = os.environ.get("DATABASE_URL")
        if dsn:
            _singleton = PostgresStore(dsn)
        else:
            _singleton = InMemoryStore()
            _seed_dev_key(_singleton)
        return _singleton


def _seed_dev_key(store: Store) -> None:
    """Seed a stable dev API key for local testing.

    Mirrors the previous billing._seed_dev_key behaviour. Only runs in dev (no
    TDOC_ENV or TDOC_ENV=dev) so the well-known key never works against prod.
    """
    env = os.environ.get("TDOC_ENV", "dev")
    if env != "dev":
        return
    dev_key = os.environ.get("TDOC_DEV_KEY", "tdoc_dev_local")
    if store.get(dev_key) is None:
        store.put(
            Plan(
                api_key=dev_key,
                tier="team",
                units_included=TIER_SPECS["team"]["units_included"],
                overage_price_cents=TIER_SPECS["team"]["overage_price_cents"],
            )
        )


def reset_for_tests() -> None:
    """Drop the singleton — used by tests that toggle DATABASE_URL."""
    global _singleton
    with _singleton_lock:
        _singleton = None
