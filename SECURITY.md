# Security Policy

## Supported versions

The current `main` branch is the only supported line. The AXON format library
follows [semantic versioning](https://semver.org/); security patches are
backported to the most recent minor release.

| Version | Supported |
|---------|-----------|
| 0.1.x   | ✅         |
| < 0.1   | ❌         |

## Reporting a vulnerability

**Please do NOT file a public GitHub issue for security bugs.**

Email: **security@tdoc.xyz** (PGP key fingerprint published below).
Response SLA:

- **Acknowledgement**: within 72 hours
- **Triage + severity**: within 7 days
- **Fix or mitigation**: within 30 days for HIGH/CRITICAL; 90 days for MEDIUM/LOW
- **Public disclosure**: coordinated with the reporter; default 90-day window
  per the [Project Zero disclosure policy](https://googleprojectzero.blogspot.com/p/vulnerability-disclosure-faq.html).

### What to include

- A proof-of-concept or reproduction steps
- The affected version / commit hash
- Your assessment of impact and severity
- Whether you've shared this with any third party

### What you'll receive

- Public credit in the security advisory (unless you request anonymity)
- Listing in `SECURITY_HALL_OF_FAME.md`
- (For severe findings in production services) a bug bounty — scaled with severity

### PGP key

```
(TODO: generate and paste the fingerprint + armored public key once
security@tdoc.xyz is provisioned via Cloudflare Email Routing →
Protonmail or similar.)
```

---

## Scope

### In scope
- `axon.py` — AXON format reference implementation
- `product/service/` — hosted API service (`api.tdoc.xyz`)
- `product/web/` — landing page (`tdoc.xyz`)
- Supply chain: any dependency listed in `pyproject.toml` or `requirements.txt`

### Out of scope
- Third-party services we depend on (Cloudflare, Fly.io, Supabase, Lemon Squeezy) — report to them directly
- Denial-of-service attacks that require > 10 req/sec of sustained traffic
  (we expect that volume to be handled at the Cloudflare edge)
- Social engineering of employees or customers
- Physical attacks on infrastructure

---

## Security controls currently in place

### Format / library layer (`axon.py`)
- ✅ Byte-deterministic archives (no hidden timestamps, no nonces)
- ✅ SHA3-256 content and render hashes
- ✅ Ed25519 cryptographic signatures (deterministic, tamper-proof)
- ✅ ZIP-bomb defense (per-member + total-size + ratio caps)
- ✅ Path-traversal defense (reject `..`, absolute paths, drive letters)
- ✅ Canonical JSON serialisation (sorted keys, UTF-8 bytes)
- ✅ Validation engine rejects malformed documents at decode time

### API layer (`product/service/`)
- ✅ Bearer API key auth with constant-time comparison (timing-attack safe)
- ✅ Per-IP and per-API-key rate limiting (token bucket)
- ✅ CORS allowlist (not `*`) — only `tdoc.xyz` subdomains
- ✅ Body-size cap at framework + endpoint level
- ✅ No stack-trace leakage to clients (opaque 500 response)
- ✅ Structured audit logging (JSON, no raw keys, no PII)
- ✅ Request-ID correlation for incident investigation
- ✅ Dev keys disabled in production via `TDOC_ENV=prod`

### Transport / edge layer
- ✅ HTTPS enforced via Cloudflare
- ✅ HSTS preload-ready (`max-age=31536000; includeSubDomains; preload`)
- ✅ Content-Security-Policy locked down on landing page
- ✅ X-Frame-Options: DENY
- ✅ X-Content-Type-Options: nosniff
- ✅ Referrer-Policy: strict-origin-when-cross-origin
- ✅ Permissions-Policy: all powerful APIs disabled
- ✅ Cloudflare WAF + DDoS protection (free tier)

### Supply chain
- ✅ pip-audit runs in CI on every PR
- ✅ CodeQL semantic analysis (security-extended queries)
- ✅ Bandit Python SAST
- ✅ gitleaks secret scan on every commit (pre-commit + CI)
- ✅ Dependabot enabled (alerts on vulnerable dependencies)

---

## What we DON'T have yet (roadmap)

- ❌ Bug bounty program (pending: fund it after $10K MRR)
- ❌ SOC 2 Type II (pending: first audit scheduled after first enterprise customer)
- ❌ WAF rules tuned to the API (currently using Cloudflare defaults)
- ❌ HSM-backed Ed25519 key (currently file-backed in Fly.io secret; migrate to
  AWS KMS / GCP KMS when revenue supports it)
- ❌ Customer-supplied encryption keys (CMK/BYOK) — enterprise feature

---

## See also

- [THREAT_MODEL.md](./THREAT_MODEL.md) — explicit attacker model and mitigations
- [INCIDENT_RESPONSE.md](./INCIDENT_RESPONSE.md) — runbook for security incidents
- [OPSEC_GUIDE.md](./OPSEC_GUIDE.md) — operator security (founder-internal)
