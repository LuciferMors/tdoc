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


# ── Storage backend ─────────────────────────────────────────────────────────────
# Swappable: in-memory by default; Postgres (Supabase / Neon / Railway / RDS)
# when DATABASE_URL is set. See product/service/store.py for the full rationale
# — short version: HF Spaces have ephemeral filesystems, so a real customer's
# API key cannot live in process memory.


def get_principal(api_key: str) -> Plan | None:
    from product.service.store import get_store

    return get_store().get(api_key)


def register(
    tier: str,
    *,
    lemonsqueezy_customer_id: str | None = None,
    lemonsqueezy_subscription_id: str | None = None,
) -> Plan:
    """Provision a new API key on the given tier. Production: called by Lemon Squeezy webhook."""
    from product.service.store import get_store

    plan = make_plan(tier)
    plan.lemonsqueezy_customer_id = lemonsqueezy_customer_id
    plan.lemonsqueezy_subscription_id = lemonsqueezy_subscription_id
    get_store().put(plan)
    return plan


def find_by_subscription_id(sub_id: str) -> Plan | None:
    """Webhook handlers use this to find the existing plan when LS sends
    subscription_updated / subscription_cancelled events."""
    from product.service.store import get_store

    return get_store().find_by_subscription_id(sub_id)


def update_tier(plan: Plan, tier: str) -> Plan:
    """Re-tier a live plan. Used by subscription_updated handler."""
    from product.service.store import get_store

    spec = TIER_SPECS[tier]
    plan.tier = tier
    plan.units_included = spec["units_included"]
    plan.overage_price_cents = spec["overage_price_cents"]
    get_store().update(plan)
    return plan


def record_units(plan: Plan, amount: int) -> None:
    from product.service.store import get_store

    plan.units_used += amount
    if plan.units_used > plan.units_included:
        if plan.overage_price_cents == 0:
            # Roll back + hard-block.
            plan.units_used -= amount
            # Persist the rollback so retries don't double-count.
            get_store().update(plan)
            raise PlanQuotaExceeded(
                f"Plan '{plan.tier}' quota exceeded "
                f"({plan.units_included} units). Upgrade at /pricing."
            )
        # Else: overage charged off-band — in production this would post to Lemon Squeezy.
    get_store().update(plan)
