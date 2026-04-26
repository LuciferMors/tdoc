# Postgres backend

The tdoc API stores API keys + per-plan usage in `product/service/store.py`.
By default this is an in-memory dict (fine for dev, useless for prod because
HF Spaces have ephemeral filesystems).

To turn on persistence, point the API at a Postgres database via the
`DATABASE_URL` environment variable. Any Postgres 14+ works — Supabase,
Neon, Railway, RDS — they all hand you a `postgres://...` connection string.

## Recommended: Supabase free tier

- No credit card.
- 500 MB storage, 50 K MAU on the free plan — far more than first launch needs.
- Daily backups, 7-day retention, included.

## Setup (~5 minutes, Rishi clicks)

1. Sign up: https://supabase.com (GitHub OAuth, no card).
2. **New project** → name `tdoc`, region `ap-south-1` (Mumbai),
   set a strong DB password, click **Create**. Wait ~2 min for provisioning.
3. **Project Settings → Database → Connection string → URI** — copy.
   It looks like `postgres://postgres:<pwd>@db.<ref>.supabase.co:5432/postgres`.
4. **Don't paste it in chat.** Add it as a Hugging Face Space secret instead:
   - https://huggingface.co/spaces/LuciferMors/tdoc/settings
   - **Variables and secrets** → **New secret**
   - Name: `DATABASE_URL`
   - Value: paste connection string
   - Save → Space restarts automatically (~30 s rebuild).
5. Verify the table got created: in Supabase **SQL Editor**, run
   `SELECT * FROM plans;` — should return zero rows, no error.

That's it. Existing `register()` / webhook flows now persist across
Space restarts. Lemon Squeezy webhook handler (next session) will
write rows here on every new subscription.

## Manual schema bootstrap (optional)

The application runs the DDL on first call. If you want to apply the schema
manually first — e.g. to inspect it before letting prod write — run the
SQL in `001_plans.sql` against your database. Idempotent; safe to re-run.

```bash
psql "$DATABASE_URL" -f 001_plans.sql
```

## Connection pool

`PostgresStore` keeps a `psycopg_pool.ConnectionPool` of 1–4 connections.
For HF Space free tier (1 vCPU, single uvicorn worker) that's overkill but
cheap. Bump `max_size` in `store.py` only after you've measured saturation.

## Why not the Supabase REST API?

Supabase ships a PostgREST front and a Python SDK, but plain `psycopg` over
`DATABASE_URL` keeps the code portable to *any* Postgres host. If we ever
move off Supabase, the only thing that changes is the connection string.
