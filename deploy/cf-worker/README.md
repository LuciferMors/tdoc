# Cloudflare Worker — api.tdoc.xyz proxy

Reverse-proxies `api.tdoc.xyz/*` to the Hugging Face Space running the
tdoc FastAPI backend. Free tier Cloudflare Workers give us 100,000
requests/day with no credit card required.

## One-time deploy (~5 min, no credit card)

### Prerequisite

You need `wrangler` (the Cloudflare Workers CLI) and a logged-in
Cloudflare account. The Cloudflare account you already use for
tdoc.xyz DNS + Pages is fine — same account.

```bash
# From /Users/rishi/Desktop/1/deploy/cf-worker:
npx wrangler@latest login
```

`wrangler login` opens a browser window for OAuth. No tokens are
pasted anywhere — credentials live in `~/.config/.wrangler/config/`.

### Deploy

```bash
npx wrangler@latest deploy
```

Expected output ends with:
```
Uploaded tdoc-api-proxy (x.xx sec)
Published tdoc-api-proxy (x.xx sec)
  api.tdoc.xyz/* (CNAME + route)
```

Wrangler handles the DNS `CNAME` and route binding automatically —
no manual Cloudflare dashboard click needed for this step.

### Verify

```bash
curl -sS https://api.tdoc.xyz/v1/healthz
# Expected: {"ok":true,"version":"0.1.0"}
```

If this 502s, the HF Space hasn't built yet. Wait 2–5 min after the first
GitHub Actions sync completes, then retry.

## What the Worker does

1. Accepts requests on `api.tdoc.xyz/*`.
2. Rejects anything not under `/v1/*`, `/docs`, `/redoc`, `/openapi.json`, or `/` — 404 at the edge.
3. Rewrites URL to `https://LuciferMors-tdoc.hf.space/<path>` with the same method, body, and most headers.
4. Strips hop-by-hop + origin-provided CORS headers, then re-applies our own CORS + HSTS + security header stack.
5. Returns the response to the caller.

Stateless, no caching, ~15 ms added latency.

## Updating the upstream origin

If the HF Space URL changes (renamed, transferred owner, or migrated
off HF), update the `ORIGIN` constant in `src/worker.js` and run
`npx wrangler deploy` again. Deploy takes ~10 sec.

## Free-tier limits

| Limit | Value |
|---|---|
| Requests/day | 100,000 |
| CPU time/request | 10 ms (more than enough for a pass-through) |
| Worker size | 1 MB (our worker.js is ~3 KB) |
| Custom domain | included free |

If we outgrow the free tier, Workers Paid is $5/mo — but by then revenue
should cover it.

## Rollback

If something breaks after a deploy, revert to the previous version
directly in the Cloudflare dashboard: Workers & Pages →
`tdoc-api-proxy` → Deployments → previous version → **Rollback**.
No code change needed.
