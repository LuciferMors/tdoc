# deploy/ — hosting glue

This folder holds per-host configuration files so the rest of the repo
stays host-agnostic.

## Contents

| Path | Target | What it does |
|---|---|---|
| `huggingface/README.md` | Hugging Face Space | Front-matter config (sdk=docker, app_port=8080). Overwrites the root README inside the Space only. |
| `cf-worker/` | Cloudflare Worker | Reverse-proxy `api.tdoc.xyz/*` → `LuciferMors-tdoc.hf.space/*`. |

## One-time setup (Rishi, ≈ 10 min total)

### 1. Hugging Face Space (3 min, no credit card)
1. Sign up at https://huggingface.co/join (email only).
2. Create a Space: https://huggingface.co/new-space
   - Name: `tdoc`
   - Type: **Docker**
   - Hardware: **CPU basic** (free)
   - Visibility: **Public**
3. Generate an HF API token: https://huggingface.co/settings/tokens
   → "Create new token" → Type: **Write** (fine-grained, scoped to your Spaces) → copy.
4. Add the token to GitHub repo secrets: https://github.com/LuciferMors/tdoc/settings/secrets/actions
   → **New repository secret** → Name: `HF_TOKEN` → Value: (paste) → save.
5. Re-run the GitHub Action: Actions tab → "Sync to Hugging Face Space" → Run workflow.
   First run builds the Docker image on HF (~5 min). Subsequent syncs take <60 sec.

Verify: `curl https://LuciferMors-tdoc.hf.space/v1/healthz` → `{"ok":true,"version":"0.1.0"}`.

### 2. Cloudflare Worker (5 min, no credit card)
See `cf-worker/README.md`. Uses `wrangler login` (browser OAuth, no token paste).

## Token safety

- `HF_TOKEN` lives in GitHub Actions secrets — encrypted at rest, never echoed to logs
  (the workflow uses `::add-mask::`-style redaction via `actions/checkout` + env injection).
- Never commit a token. The pre-commit `gitleaks` hook will reject it.
- Rotate any token you accidentally paste anywhere — transcripts, chat, Slack, Discord, anywhere.
  See `/Users/rishi/.claude/projects/-Users-rishi-Desktop-1/memory/feedback_secrets_in_chat.md`.
