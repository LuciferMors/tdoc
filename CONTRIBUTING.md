# Contributing to tdoc

Thanks for looking. tdoc is a small, self-contained project:
one Python module (`axon.py`) + a FastAPI service (`product/service/`) +
a static landing page (`product/web/`). Most PRs touch a single file.

## Development setup

```bash
git clone https://github.com/LuciferMors/tdoc.git
cd tdoc
python3 -m venv .venv
.venv/bin/pip install -e ".[dev,crypto,pdf]"
.venv/bin/pre-commit install
.venv/bin/pytest tests/ product/tests/
```

Expected: `50 passed`. If tests fail on a clean checkout, that's a bug — please open an issue.

## Pre-commit hooks (mandatory)

Every commit runs:

- `gitleaks` — rejects accidental API-key commits
- `detect-private-key` — rejects SSH / PEM keys
- `bandit` — Python SAST (low + medium severity)
- `ruff` + `ruff-format` — Python linting and formatting
- `check-added-large-files` — 1 MB cap per file
- `trailing-whitespace`, `end-of-file-fixer`, `mixed-line-ending`, `check-yaml`, `check-toml`, `check-merge-conflict`

Do not bypass with `--no-verify`. If a hook fails, fix the root cause.
If you believe the hook is wrong (rare), open an issue first.

## Running the API locally

```bash
.venv/bin/uvicorn product.service.main:app --reload --port 8000
curl -H "Authorization: Bearer tdoc_dev_local" http://localhost:8000/v1/me
```

Interactive docs: `http://localhost:8000/docs`.

## How the codebase is organised

| Path | What |
|---|---|
| `axon.py` | Format reference: parser, serialiser, encoder, decoder, AQL engine, HTML/text renderers. ~2000 lines, stdlib-only core. |
| `AXON_Format_Specification.txt` | Normative spec for the format. Changes here imply a version bump. |
| `tests/` | Format-level tests — determinism, conformance, signatures, security. |
| `product/service/` | FastAPI service. `main.py` routes, `billing.py` tier logic, `security.py` middleware. |
| `product/tests/` | Service-level tests — auth, quotas, rate limits, headers. |
| `product/web/` | Static landing page. |
| `Dockerfile` | Runtime container (non-root, healthcheck, python:3.12-slim). |
| `deploy/` | Hosting-specific glue (Hugging Face Space config, Cloudflare Worker). |

## Contribution heuristics

- **Bug fixes**: always welcome. Add a test that fails before your fix and passes after.
- **New format features**: open an issue first. The AXON spec is the source of truth; PRs that deviate without spec changes will be declined.
- **New API endpoints**: open an issue first. Auth, rate limiting, and billing must be wired in.
- **Docs / README / spec clarifications**: ship directly; small PRs, fast reviews.
- **Refactors without functional change**: please open an issue first. The codebase is small by design.

## What to avoid

- New dependencies for the base library. AXON core stays stdlib-only. Crypto / PDF / fast-JSON / MathML live behind optional extras.
- Commented-out code. Delete it — git remembers.
- Wide tests that assert unrelated invariants. Narrow tests, one assertion idea each, are easier to keep green.

## Licence

Apache 2.0. By submitting a PR you agree to licence your contribution under the same terms.
