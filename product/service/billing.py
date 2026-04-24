"""Plan / quota / billing primitives.

For local dev, keys and usage live in an in-memory dict. For production, swap
_STORE for Supabase (Postgres) behind the same interface.

Payments flow via Lemon Squeezy (merchant-of-record) — chosen over Stripe because:
  - Lemon Squeezy handles global VAT/GST/tax compliance on your behalf.
  - Works from an Indian sole proprietorship — NO Delaware C-Corp needed on day 1.
  - No upfront incorporation cost; they deposit net earnings in INR to your bank.
  - Free until first sale; ~5% + $0.50 per transaction thereafter.

Webhook handler (to be added in production):
  POST /webhooks/lemonsqueezy:
    - on subscription_created → billing.register(tier=...)
    - on subscription_updated → update tier
    - on subscription_cancelled → downgrade to free
"""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass


class PlanQuotaExceeded(Exception):
    """Raised when the plan's included-units cap is reached on a hard-block tier."""


@dataclass
class Plan:
    api_key: str
    tier: str  # "free" | "pro" | "team" | "scale"
    units_included: int
    units_used: int = 0
    overage_price_cents: int = 0  # price per unit beyond the cap (0 = hard block)
    lemonsqueezy_customer_id: str | None = None
    lemonsqueezy_subscription_id: str | None = None


# ── Tier definitions (editable, mirrored on landing page pricing table) ─────────
# 1 unit ≈ 50 KB of input content.
TIER_SPECS = {
    # Free forever — gets users past the "is this real" barrier without a credit card.
    "free": {"units_included": 100, "overage_price_cents": 0, "price_usd": 0},
    # Indie / hobbyist — credit-card self-serve.
    "pro": {"units_included": 2_000, "overage_price_cents": 0, "price_usd": 29},
    # Small team / startup — adds Ed25519 signing + verify.
    "team": {"units_included": 10_000, "overage_price_cents": 2, "price_usd": 99},
    # Production workloads.
    "scale": {"units_included": 100_000, "overage_price_cents": 1, "price_usd": 499},
}


def make_plan(tier: str, api_key: str | None = None) -> Plan:
    spec = TIER_SPECS[tier]
    return Plan(
        api_key=api_key or ("tdoc_" + secrets.token_urlsafe(24)),
        tier=tier,
        units_included=spec["units_included"],
        overage_price_cents=spec["overage_price_cents"],
    )


# ── In-memory store (dev only) ──────────────────────────────────────────────────
_STORE: dict[str, Plan] = {}


def _seed_dev_key() -> None:
    """Seed a stable dev API key for local testing.

    SECURITY: only runs when TDOC_ENV is unset ('dev' default) or 'dev'. In
    production (TDOC_ENV=prod) no default keys exist — every key must come from
    a Lemon Squeezy webhook creating a real subscription. This prevents the
    known-key 'tdoc_dev_local' from accidentally working against a prod deploy
    if the env var is misconfigured.
    """
    env = os.environ.get("TDOC_ENV", "dev")
    if env != "dev":
        return
    dev_key = os.environ.get("TDOC_DEV_KEY", "tdoc_dev_local")
    if dev_key not in _STORE:
        _STORE[dev_key] = Plan(
            api_key=dev_key,
            tier="team",
            units_included=TIER_SPECS["team"]["units_included"],
            overage_price_cents=TIER_SPECS["team"]["overage_price_cents"],
        )


_seed_dev_key()


def get_principal(api_key: str) -> Plan | None:
    return _STORE.get(api_key)


def register(tier: str) -> Plan:
    """Provision a new API key on the given tier. Production: called by Stripe webhook."""
    plan = make_plan(tier)
    _STORE[plan.api_key] = plan
    return plan


def record_units(plan: Plan, amount: int) -> None:
    plan.units_used += amount
    if plan.units_used > plan.units_included:
        if plan.overage_price_cents == 0:
            # Roll back + hard-block.
            plan.units_used -= amount
            raise PlanQuotaExceeded(
                f"Plan '{plan.tier}' quota exceeded "
                f"({plan.units_included} units). Upgrade at /pricing."
            )
        # Else: overage charged off-band — in production this would post to Stripe.
