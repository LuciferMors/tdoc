# Incident Response Runbook

**For the founder, alone, at 3 AM, when something breaks in production.**

## Severity classes

| Level | Definition | Response |
|---|---|---|
| **SEV-1** | Production down, customer data exposed, signing key leaked | Drop everything. Action inside 30 min. Public comm within 4 h. |
| **SEV-2** | Degraded performance, one feature broken, no data loss | Action inside 2 h. Customer notice if > 50% affected. |
| **SEV-3** | Minor bug, cosmetic issue, non-critical | Next business day. Fix in regular release. |

## SEV-1 response — the first 30 minutes

If you think it's SEV-1 and you're not sure — **treat it as SEV-1**. Apologise later.

### Step 1: Stop the bleeding (5 min)

Pick the smallest action that prevents more damage:

- **API returning customer data to wrong users?** Disable the affected endpoint.
  ```bash
  flyctl scale count 0 -a tdoc-api     # takes the API offline completely
  ```
- **Signing key leaked?** Rotate immediately.
  ```bash
  # Generate new key (Python one-liner):
  .venv/bin/python -c "
  from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
  from cryptography.hazmat.primitives import serialization
  sk = Ed25519PrivateKey.generate()
  print(sk.private_bytes(
      encoding=serialization.Encoding.Raw,
      format=serialization.PrivateFormat.Raw,
      encryption_algorithm=serialization.NoEncryption()
  ).hex())"
  # Push to Fly:
  flyctl secrets set TDOC_SIGNING_KEY=<new_hex> -a tdoc-api
  ```
- **Database compromised?** Rotate Supabase credentials + invalidate all API keys.
  ```sql
  -- From Supabase SQL editor:
  update plans set api_key = 'rotated_' || api_key where tier != 'free';
  ```
- **Landing page defaced or serving malware?** Take down.
  ```bash
  # Cloudflare dash → Pages → your project → Pause.
  ```

### Step 2: Preserve evidence (5 min)

- Snapshot logs: `flyctl logs -a tdoc-api > /tmp/incident-$(date +%s).log`
- Snapshot DB: Supabase → **Backups → Create backup**
- Screenshot anything anomalous in Cloudflare / Fly / Supabase dashboards.
- DO NOT `git push` fixes that reference the incident details publicly yet.

### Step 3: Assess blast radius (10 min)

Answer, in a scratch file:

- [ ] How long was the vulnerability exploitable?
- [ ] How many customer accounts could be affected?
- [ ] Any data confirmed exfiltrated? (Check audit logs for unusual read patterns.)
- [ ] Any downstream services to notify? (Lemon Squeezy, Supabase, Cloudflare.)
- [ ] Regulator notification threshold crossed? (GDPR: > 72 h for personal data
      breach affecting EU users.)

### Step 4: Communicate (10 min)

If any customer is affected, send an email from `security@tdoc.xyz` to each
affected customer within 4 hours, using this template:

```
Subject: Security incident affecting your tdoc account — action required

On [DATE] at [TIME] UTC, we detected [WHAT HAPPENED].

Impact to you: [SPECIFIC TO THIS CUSTOMER]
Actions we've taken: [WHAT YOU DID]
Actions you should take: [ROTATE KEY / NOTHING / WAIT]

We'll publish a full post-mortem within 14 days at tdoc.xyz/post-mortems.

— the tdoc team (solo founder, one person, so you're hearing this from me directly)
```

Status page update (even if you don't have one — post to `status.tdoc.xyz` once it's built, or to X/Twitter in the interim):

> [INVESTIGATING/IDENTIFIED/MONITORING/RESOLVED] — brief description, ETA next update.

---

## Common incident playbooks

### Playbook 1: Runaway bill from a bad actor

**Symptom**: Lemon Squeezy or Fly.io email says "usage spike, card declined."
**Root cause**: API quota bypass, leaked key, or runaway free-tier loop.

1. Identify which API key is consuming: `grep key_id= /tmp/incident.log | sort | uniq -c | sort -rn | head`
2. Disable that plan in billing: `UPDATE plans SET units_included = 0 WHERE api_key = 'tdoc_xxx';`
3. Refund the customer if they're legitimate. Block them if they're abusive.
4. Patch the bypass if there was one.

### Playbook 2: Signing key leaked

**Symptom**: Alert says "TDOC_SIGNING_KEY appears in public GitHub gist" or
similar; or you see Ed25519 signatures verifying from an unknown source.

1. **Rotate immediately** (commands above).
2. Re-sign every active document that customers rely on with the new key.
3. Publish a transparency log entry: "Key rotated on [DATE] due to [REASON].
   Old key fingerprint: X, new fingerprint: Y. All signatures after [TS] use
   the new key."
4. If the leak was via git history, force-push a cleaned history (rare — only
   do this after confirming no one has forked).
5. Post-mortem within 14 days.

### Playbook 3: Customer data exposure

**Symptom**: Bug report or support ticket: "I can see another user's document."

1. Reproduce in a private environment. Do NOT test on prod.
2. Take the affected endpoint offline: `flyctl scale count 0 -a tdoc-api`.
3. Fix the bug (usually an IDOR — missing authorization check).
4. Deploy fix. Re-scale.
5. Review audit logs for evidence the bug was exploited before you discovered it.
6. Notify every customer whose data could have been accessed, even if logs
   don't show evidence of actual access.

### Playbook 4: DDoS / traffic flood

**Symptom**: API latency > 5 s, error rate > 10 %, Cloudflare dashboard shows
traffic spike from a handful of IPs.

1. Cloudflare dashboard → **Security → WAF → Custom rules** → add a rule:
   `(http.request.uri.path contains "/v1/") and (cf.threat_score gt 20)` →
   action: Managed Challenge or Block.
2. Enable Cloudflare **Under Attack Mode** (left sidebar → Security →
   Settings → toggle) — this adds a 5-second JavaScript challenge to every
   visitor. Only enable during an active attack; disable as soon as traffic
   normalises.
3. If the attack is sustained > 1 h, upgrade to Cloudflare Pro ($20/mo) for
   better WAF rules and analytics.

---

## Post-mortem template

Fill this out within 14 days of every SEV-1. Publish it (with customer data
redacted) at `tdoc.xyz/post-mortems/YYYY-MM-DD-slug`.

```markdown
# Post-mortem: [Short title]

Date: YYYY-MM-DD
Severity: SEV-1/2/3
Duration: X hours Y minutes
Affected: [customer count / % of traffic]

## What happened
[Plain-language story of the incident, no blame.]

## Timeline (UTC)
- HH:MM — Detection (how did we find out)
- HH:MM — First response (what we did)
- HH:MM — Contained (bleeding stopped)
- HH:MM — Resolved (root cause fixed)
- HH:MM — Customers notified

## Root cause
[Technical explanation. 1–3 paragraphs.]

## Resolution
[What we did to fix it. Link to commits.]

## What went well
[Things that worked. Seriously — find at least two.]

## What went wrong
[Missing monitoring, slow response, wrong alert threshold, etc.]

## Action items
[Concrete, owner-assigned, with deadlines.]
- [ ] Ship fix for root cause (already done)
- [ ] Add alert for X (owner, deadline)
- [ ] Document runbook for Y (owner, deadline)
- [ ] Audit for similar issues (owner, deadline)

## Customer impact
[Which customers, what they experienced, what we gave them (refund, credit).]
```

---

## Who to contact (external)

| Service | Support URL | Typical response |
|---|---|---|
| Cloudflare | https://dash.cloudflare.com/?to=/:account/support | 4–24 h |
| Fly.io | https://community.fly.io (public) / billing@fly.io | 8–48 h |
| Supabase | https://supabase.com/dashboard/support | 12–48 h |
| Lemon Squeezy | support@lemonsqueezy.com | 4–24 h |
| Hostinger (domain) | 24×7 chat in hPanel | 1–4 h |
| GitHub (private repo breach) | https://support.github.com | 4–24 h |
| Cert Authority Authorisation abuse | (Cloudflare handles) | — |
| Indian CERT-In (for national-scale incidents) | incident@cert-in.org.in | — |

---

## Lessons from this runbook (so far)

*Empty — fill as incidents happen. Every incident should add one lesson here.*
