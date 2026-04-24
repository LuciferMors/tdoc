---
title: tdoc API
emoji: 📄
colorFrom: indigo
colorTo: purple
sdk: docker
app_port: 8080
pinned: false
license: apache-2.0
short_description: Typed, queryable, signable documents — as an API.
---

# tdoc — hosted API

This is the Docker Space that runs the tdoc FastAPI service.
The canonical repo lives at https://github.com/LuciferMors/tdoc and is
mirrored here on every push to `main` via a GitHub Action.

**Do not edit files in this Space directly.** Your edits will be
overwritten by the next sync from GitHub. Send PRs to the canonical
repo instead.

## Runtime

- Python 3.12-slim (see `/Dockerfile`)
- FastAPI on uvicorn, bound to `0.0.0.0:8080` (HF reads `app_port` above)
- Non-root UID 10001
- Healthcheck: `GET /v1/healthz` → `{"ok": true, ...}`

## Public endpoint

- `https://LuciferMors-tdoc.hf.space/v1/healthz`
- `api.tdoc.xyz/*` proxies here via a Cloudflare Worker (free tier) —
  that's the URL you should point clients at, not the hf.space URL
  directly.

## What this Space runs

Endpoints (all under `/v1`):
- `POST /structure` — PDF / DOCX / TXT / AXC → AXON tree + content/render hashes
- `POST /query` — AQL over an AXON document
- `POST /sign` — Ed25519-sign (Team+ tier only)
- `POST /verify` — verify an Ed25519-signed archive
- `GET  /healthz` — liveness
- `GET  /me` — caller identity + quota

Auth: `Authorization: Bearer <api_key>` on every endpoint except `/healthz`.

## Hardware

Running on **CPU basic** (2 vCPU, 16 GB RAM) — the HF free tier.
Sufficient for up to ~20 concurrent requests of moderate-size PDFs.
Will migrate to dedicated hosting once MRR clears $500/mo.
