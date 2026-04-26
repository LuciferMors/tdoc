-- tdoc — plans table.
--
-- Schema for product/service/store.py PostgresStore. Run once on a fresh
-- database. Idempotent — safe to re-run during deploys.
--
-- Compatible with Supabase, Neon, Railway, RDS — anywhere that speaks
-- standard Postgres 14+.
--
-- The application also runs this DDL on first call (via
-- PostgresStore._migrate_once) so manual execution is a belt-and-suspenders
-- step, not strictly required.

CREATE TABLE IF NOT EXISTS plans (
  api_key                       TEXT PRIMARY KEY,
  tier                          TEXT NOT NULL,
  units_included                INTEGER NOT NULL,
  units_used                    INTEGER NOT NULL DEFAULT 0,
  overage_price_cents           INTEGER NOT NULL DEFAULT 0,
  lemonsqueezy_customer_id      TEXT,
  lemonsqueezy_subscription_id  TEXT,
  created_at                    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at                    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Webhook lookups go by Lemon Squeezy subscription id, not api_key.
CREATE INDEX IF NOT EXISTS idx_plans_lsq_sub
  ON plans(lemonsqueezy_subscription_id);
