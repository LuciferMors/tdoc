# Threat Model — tdoc / AXON

Last updated: 2026-04-24

## Assets we protect

| Asset | Confidentiality | Integrity | Availability |
|---|---|---|---|
| Customer-uploaded documents (transient) | HIGH | HIGH | MEDIUM |
| Customer API keys | CRITICAL | HIGH | MEDIUM |
| Ed25519 signing key (server-side) | CRITICAL | CRITICAL | HIGH |
| Subscription / billing data (via Lemon Squeezy) | HIGH | HIGH | HIGH |
| Audit logs | MEDIUM | HIGH | MEDIUM |
| Source code (public repo, OSS) | LOW | HIGH | MEDIUM |
| Source code (private repo, commercial) | MEDIUM | HIGH | MEDIUM |
| Landing page content | LOW | MEDIUM | HIGH |

## Trust boundaries

```
 [public internet] ───▶ Cloudflare (edge) ───▶ Fly.io VM (API) ───▶ Supabase (DB)
                                                    │
                                                    └─▶ Lemon Squeezy (billing)
```

- **Trust edge**: Cloudflare. Assume anything before it is hostile.
- **Semi-trusted**: Fly.io. We control the code; the platform could in theory
  read secrets but the threat is considered low.
- **Trusted dependency**: Supabase, Lemon Squeezy. If they're breached, we're
  exposed to their blast radius — accepted risk.

## Attacker profiles

### Script kiddie (L1)
- *Capability*: off-the-shelf tools (sqlmap, nmap, Burp), no custom research.
- *Motivation*: bragging rights, website defacement, credential theft.
- *Mitigation*: Cloudflare WAF, generic security headers, rate limits. Our
  public attack surface should generate zero `curl -v` gotchas.

### Motivated attacker (L2)
- *Capability*: custom exploit dev, protocol-aware attacks, mid-tier OSINT.
- *Motivation*: API abuse for free compute, scraping customer documents,
  stealing private keys for resale.
- *Mitigation*: tier-aware rate limiting, constant-time key comparison, audit
  logs with immediate anomaly alerting, signing key rotation quarterly.

### Nation-state / APT (L3)
- *Capability*: supply-chain compromise, 0-days, insider threats.
- *Motivation*: specific target customer (pharma, finance, legal).
- *Mitigation (roadmap)*: hardware-key-backed signing, HSM for Ed25519,
  transparency log of signed documents, self-hostable SDK for air-gapped
  customers, SOC 2 Type II.

### Competitor (L2/L3)
- *Capability*: reverse-engineer our format, clone our API, poach customers.
- *Motivation*: market share.
- *Mitigation*: the AXON format is **deliberately open** — a competitor
  cloning the format helps normalize `.tdoc` as a standard. The moat is brand,
  distribution, and the proprietary API service code + tuning, not format
  secrecy. Proprietary code lives in a private repo.

## Top threats (STRIDE × likelihood × impact)

| # | Threat | Vector | Likelihood | Impact | Controls |
|---|---|---|---|---|---|
| 1 | API key theft | Log leakage, client-side exposure | MED | HIGH | Logs mask keys; no keys in URLs; rotation endpoint |
| 2 | ZIP bomb DoS | Crafted `.tdoc` upload | MED | MED | Size + ratio + member caps enforced in `decode_archive()` |
| 3 | Signing key exfiltration | Fly.io breach, env var leak, insider | LOW | CRITICAL | Key stored in `flyctl secrets`, rotation quarterly, audit trail of every sign |
| 4 | Quota farming / tier bypass | Multi-account abuse | MED | LOW | Per-IP rate limits, Lemon Squeezy fraud checks |
| 5 | Supply-chain compromise | Malicious PyPI dep | LOW | CRITICAL | pip-audit in CI, minimal deps (stdlib-only core), pinned versions |
| 6 | Cross-origin credential theft | Rogue JS hits our API with user's cookie | LOW | MED | CORS allowlist, `allow_credentials=False`, API keys in header not cookie |
| 7 | Timing attack key enumeration | Compare durations of key validation | LOW | MED | `constant_time_eq` on every auth path |
| 8 | Path-traversal in archive decode | `../../etc/passwd` entry | LOW | MED | `_safe_arcname` rejects `..`, absolute paths, drive letters |
| 9 | Invoice / subscription tampering | Modify Lemon Squeezy webhook | MED | MED | Signature verification on webhook (TODO: implement) |
| 10 | Social engineering of founder | Phishing, sim-swap, fake support | MED | HIGH | 2FA with hardware key (see OPSEC_GUIDE), password manager, no shared credentials |

## Mitigations tracked externally

- CVE vulns in deps → `pip-audit` in CI + Dependabot
- Secrets in commits → `gitleaks` in pre-commit + CI
- TLS config drift → Cloudflare handles cert rotation; SSLLabs scan monthly
- Session hijacking → N/A, we don't use sessions (stateless bearer tokens)

## Out-of-scope (accepted risks)

- We do not persist customer documents after processing (beyond transient
  in-memory). If a customer wants persistence, they store the `.tdoc` bytes
  themselves. This avoids being a target for data breaches.
- We do not offer customer-managed keys in v0.1 (CMK/BYOK is a future enterprise
  feature). All signatures use the server's key. Accepted until we have
  enterprise customers demanding otherwise.
- We do not currently have formal SOC 2 / ISO 27001 certification. Accepted
  until we have enterprise deal flow that requires it.
