# Lemon Squeezy webhook setup

The tdoc API auto-provisions an API key the moment Lemon Squeezy reports
a successful subscription. The handler lives at
`POST /v1/webhooks/lemonsqueezy` (see `product/service/main.py`).

## Environment variables

Set both as **HF Space secrets** (not in code, not in chat):

```
LEMONSQUEEZY_WEBHOOK_SECRET = <signing secret from LS dashboard>
LS_VARIANT_MAP              = {"100":"pro","101":"team","102":"scale"}
```

`LS_VARIANT_MAP` maps each Lemon Squeezy **variant id** to the
internal tdoc tier name (`free` / `pro` / `team` / `scale`). You can
find variant ids at https://app.lemonsqueezy.com/products under each
product's "Variants" section.

If a webhook arrives with a `variant_id` not in the map, the handler
falls back to `pro` — better to give the customer access than block
them — and logs the unmapped id so you can fix it.

## Wiring it up in Lemon Squeezy

1. Sign up at https://app.lemonsqueezy.com (PAN KYC for India ~24-48 h).
2. Create one product per tier (Pro $29, Team $99, Scale $499). Each
   product gets one or more **variants** (monthly / annual / etc).
3. **Settings → Webhooks → New webhook**:
   - URL: `https://api.tdoc.xyz/v1/webhooks/lemonsqueezy`
   - Signing secret: copy what LS shows; paste into the
     `LEMONSQUEEZY_WEBHOOK_SECRET` HF Space secret.
   - Events to send (tick all four):
     - `subscription_created`
     - `subscription_updated`
     - `subscription_cancelled`
     - `subscription_expired`
4. Copy the variant ids from each product into `LS_VARIANT_MAP`.
5. Save secrets in HF Space — Space restarts automatically (~30 s).
6. Run a `$1 test mode` checkout in Lemon Squeezy and confirm:
   - Webhook delivery shows 200 in the LS dashboard.
   - `find_by_subscription_id(<sub_id>)` returns the new plan via the
     API (or check Supabase: `SELECT * FROM plans WHERE
     lemonsqueezy_subscription_id = '...'`).

## Customer key delivery

Today the webhook **provisions** the key but does not **email** it. For
the first few customers, pull the key from Postgres + send manually
from `hello@tdoc.xyz`. Next iteration: integrate Resend
(free tier, 3 K emails/month) for an automatic delivery email.

## Idempotency + retries

LS retries on any non-2xx response. The handler:

- Verifies the HMAC-SHA256 signature → 401 on mismatch (LS retries).
- Returns 503 if `LEMONSQUEEZY_WEBHOOK_SECRET` is unset (LS retries
  until you fix the config).
- Returns 200 for every valid + verified event, even unknown ones, so
  LS doesn't accumulate retry backlog while we add new event types.

## Security notes

- Signature verified with `hmac.compare_digest` (constant time) —
  bad-signature timing oracle is blocked.
- The handler logs the **first 8 chars** of any provisioned API key,
  the LS subscription id, and the email **domain only** — never the
  full key, never the full email.
- The webhook respects the same security middleware as every other
  endpoint: rate limits, audit logging, body-size cap, request id.
