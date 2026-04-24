# tdoc — product workspace

tdoc is the commercial API on top of the open-source **AXON** document format.
This folder contains everything product-related. The spec and reference impl are
at the repo root.

## Layout

```
product/
├── service/
│   ├── main.py         FastAPI app — /v1/structure /query /sign /verify /me /healthz
│   └── billing.py      Plans, quotas, Lemon-Squeezy-ready metered usage
├── tests/
│   └── test_api.py     8 smoke tests for every endpoint + auth + tier gating
├── web/
│   └── index.html      Landing + pricing — deploys to Cloudflare Pages
├── SETUP_ZERO_CAPITAL.md   ← **START HERE** — day-by-day founder setup guide
└── README.md           (this file)
```

## Pricing — as shipped

| Tier | Price / mo | Documents / mo | Signing | Overage |
|---|---|---|---|---|
| Free | $0 | 100 | ❌ | hard-block |
| Pro | $29 | 2,000 | ❌ | upgrade |
| Team | $99 | 10,000 | ✅ | $0.02 / doc |
| Scale | $499 | 100,000 | ✅ + self-host | $0.01 / doc |

1 "document" unit ≈ 50 KB of input. Defined in `service/billing.py:TIER_SPECS`.

## Run locally

```bash
cd /path/to/tdoc
.venv/bin/pip install -q fastapi "uvicorn[standard]" httpx python-multipart cryptography
.venv/bin/uvicorn product.service.main:app --reload --port 8000
```

Smoke it:

```bash
curl -H "Authorization: Bearer tdoc_dev_local" http://localhost:8000/v1/me
curl http://localhost:8000/v1/healthz
```

Interactive API docs at [http://localhost:8000/docs](http://localhost:8000/docs).

## Tests

```bash
.venv/bin/pytest product/tests/ -v
```

## Revenue math — $1M ARR year 1

| Mix | Free signups / mo | Pro $29 | Team $99 | Scale $499 | MRR end of Y1 | ARR |
|---|---|---|---|---|---|---|
| Dev-led | 10,000 | 300 | 150 | 8 | $27.5K | $330K |
| Strong | 30,000 | 600 | 300 | 25 | $59.5K | $714K |
| Breakout | 50,000 | 1,000 | 500 | 50 | $103K | $1.24M |

**Honest probability**, zero-capital first-time founder from India:

- 5–10% → $1M ARR (requires viral launch + fast pivots + AI tailwind holding)
- 25% → $200K – $1M ARR (realistic upside)
- 40% → $20K – $200K ARR (most likely)
- 25% → < $20K (pivot needed)

The controllable variable is **distribution velocity**, not product quality. The
product is good enough right now. What's left is getting 10,000 developers to try it.
