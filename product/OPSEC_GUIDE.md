# Founder Operational Security — read this once, enable everything

**This is the private OpSec doc for the operator (you). Never commit it to a public repo.**

The biggest security risk to a solo-founder SaaS isn't the code — it's **you**.
One phished password, one SIM swap, one re-used credential, and a year of work
is a stranger's problem. These controls prevent ~95% of real attacks on founders.

Total time to set up: **2 hours**. One Saturday morning. Do it before you have
paying customers — the cost to migrate later is 10× higher.

---

## Tier 1 — do today, before anything else

### 1. Password manager (30 min)
- Install **Bitwarden** (free, open-source) — https://bitwarden.com
- Create a master password that is **(a) random (b) 20+ chars (c) you do not use anywhere else**. Write it on paper, store in a drawer at home. Memorise it.
- Enable the Bitwarden browser extension on your Mac + phone.
- From now on: **every password goes into Bitwarden**. No reuse. Ever.
- Generate strong random passwords for every account (Bitwarden generates 20-char strings by default).

### 2. Hardware 2FA key (one-time ₹2,500)
- Order one (or two — backup) of: **YubiKey 5C NFC** (works with USB-C Mac + iPhone NFC) or **Google Titan** (cheaper, similar).
- Why: SMS 2FA is *not secure* — SIM swap attacks are common in India, and criminals buy Aadhaar + phone number pairs on the dark web. Hardware keys cannot be phished.
- Register the key on: Gmail, GitHub, Cloudflare, Hostinger, Fly.io, Supabase, Lemon Squeezy, Bitwarden.

**If you cannot afford a hardware key today** — use TOTP via an authenticator app instead: **Aegis** (Android, open-source) or **2FAS** (iOS, open-source). DO NOT use Google Authenticator — it syncs to Google Cloud unencrypted, meaning a Google account compromise = all 2FA codes compromised.

### 3. Enable 2FA everywhere (20 min)
Walk through and enable 2FA on every account below. Use the hardware key where supported; TOTP otherwise:

- [ ] Gmail / Google (Security → 2-Step Verification → Security keys)
- [ ] GitHub (Settings → Password and authentication)
- [ ] Cloudflare (Profile → Authentication)
- [ ] Hostinger (Account → Security)
- [ ] Fly.io (Settings → Security)
- [ ] Supabase (Account Settings → Authenticator)
- [ ] Lemon Squeezy (Settings → Security)
- [ ] Bitwarden itself (Settings → Two-step Login)
- [ ] X / Twitter (Settings → Security → Two-factor authentication)
- [ ] Any bank / UPI / NEFT portal you use

### 4. Enable login alerts everywhere (5 min)
- Gmail: Activity page → enable "Unusual activity" alerts.
- GitHub: Settings → Emails → "Receive security notifications."
- Bank: SMS + email alert for every login and every transaction.

---

## Tier 2 — do this weekend

### 5. Separate emails (20 min)
- **Personal email** (Gmail): for friends, family, random services.
- **Business email** (`hello@tdoc.xyz` forwarded to a *dedicated* Gmail address, e.g. `tdoc.business@gmail.com`): for every work-related account.
- **Billing email** (a third address, e.g. `tdoc.billing@gmail.com`): ONLY for Stripe-class services — Lemon Squeezy, Fly.io, Supabase, Cloudflare, Hostinger.
- Why: when the billing email gets phished, it can't touch your personal email or your OAuth-connected dev accounts.

### 6. SSH keys (30 min)
- Generate a new **Ed25519** SSH key on your Mac specifically for GitHub:
  ```bash
  ssh-keygen -t ed25519 -C "tdoc-github" -f ~/.ssh/id_ed25519_github
  ```
  Enter a strong passphrase (Bitwarden-generated, stored in Bitwarden).
- Add it to GitHub: Settings → SSH and GPG keys → New SSH key. Copy the `.pub` file contents.
- Enable SSH-based git:
  ```bash
  git remote set-url origin git@github.com:YOUR_USERNAME/tdoc.git
  # Add to ~/.ssh/config:
  #   Host github.com
  #     IdentityFile ~/.ssh/id_ed25519_github
  #     IdentitiesOnly yes
  ```
- No more personal access tokens except for CI. SSH + passphrase is stronger.

### 7. Sign your git commits (15 min)
- Install GPG (`brew install gnupg`) or use sigstore's `gitsign` (simpler, recommended).
- Configure commit signing so every commit has a verified badge on GitHub:
  ```bash
  # gitsign approach:
  brew install sigstore/tap/gitsign
  git config --global gpg.x509.program gitsign
  git config --global gpg.format x509
  git config --global commit.gpgsign true
  ```
- Why: prevents an attacker who steals your GitHub PAT from pushing a malicious commit that looks like it's from you.

### 8. Full disk encryption (confirm, 2 min)
- macOS: System Settings → Privacy & Security → FileVault → **ensure it is ON**.
- Store the recovery key in Bitwarden.
- Why: if your Mac is lost/stolen, no one can read the files. This matters because your Mac has the private keys, env files, and source code.

### 9. Backup strategy (20 min)
- Enable **iCloud Drive** or **Google Drive** sync for your `/Users/rishi/Desktop/` folder OR use **Arq Backup** ($50 one-time) to an external drive + B2 cloud.
- Why: hardware dies. This is not a security question — it's a survival question.
- Test the restore path by recovering a file from the backup today.

---

## Tier 3 — weekly / monthly hygiene

### Weekly (Friday, 10 min)
- [ ] Review Bitwarden breach alerts (it scans HIBP for you). Rotate any credentials on breached services.
- [ ] Review Cloudflare Security Events dashboard for anomalies.
- [ ] Skim the tdoc audit log (Fly logs) for anything unusual.
- [ ] Check GitHub's **Security** tab on the repo for Dependabot alerts.

### Monthly
- [ ] Rotate the Ed25519 signing key (`TDOC_SIGNING_KEY` in Fly secrets). Document
      the rotation in a transparency log.
- [ ] Run `pip-audit` locally: `.venv/bin/pip-audit --strict`.
- [ ] Run `gitleaks detect --source . --verbose` to catch anything not in the hooks.
- [ ] Test the incident-response playbook — pretend there's a SEV-1 and walk through the steps.

### Quarterly
- [ ] Regenerate every API token: GitHub PAT, Fly.io token, Cloudflare API token.
- [ ] Audit which third-party apps have OAuth access to your Gmail / GitHub / Cloudflare. Revoke anything you don't recognise.

---

## What NOT to do — the anti-checklist

- ❌ **Don't reuse passwords** — one breach → all accounts compromised.
- ❌ **Don't use SMS 2FA for anything critical** — SIM swap is real, especially in India.
- ❌ **Don't put secrets in code**, `.env` files, Slack messages, or notes.
- ❌ **Don't paste code with real credentials into ChatGPT / Claude / Gemini** — they're trained on conversations in some contexts and even when not, your tokens are now sitting on someone else's disk.
- ❌ **Don't install random VS Code extensions or npm packages** without reading the source. This is the #1 vector for developer-targeted malware.
- ❌ **Don't click links in emails** that claim to be from Cloudflare / GitHub / your bank. Always navigate manually by typing the URL.
- ❌ **Don't share your screen in Zoom / Meet** with your password manager / Bitwarden extension visible.
- ❌ **Don't leave your Mac unlocked** in public cafés even for a second. Cmd+Ctrl+Q to lock instantly.
- ❌ **Don't store your master password or recovery phrases in iCloud Notes** — it's synced to a Google/Apple cloud that could be subpoenaed or breached.

---

## When things go wrong — who to call

| Scenario | Immediate action |
|---|---|
| Mac stolen / lost | iCloud.com → Find My → Erase (within 1 h) |
| Suspicious Gmail login | Gmail → Security → Review activity → sign out all devices + change password immediately |
| GitHub compromised | github.com/settings/security → review sessions, sign out, change password + regenerate PAT |
| Lost hardware key | Use backup key. Revoke lost key from every account. If you have no backup, use TOTP codes stored in Bitwarden |
| SIM-swap attempt | Call your carrier from another phone, ask for "port-out protection" on the account |
| Phishing email clicked + creds entered | Change that password + all accounts with the same password IMMEDIATELY; check for MFA reset; see INCIDENT_RESPONSE.md SEV-1 playbook |

---

## The "worst-case trusted" paper (read once, store in a drawer)

Write on a piece of paper, seal in an envelope, store in a safe at home:

1. Your Bitwarden master password
2. Your macOS FileVault recovery key
3. Your 2FA backup codes (download one set from each service — Bitwarden can store these too)
4. Location of the offsite backup drive (if you have one)
5. The phrase "If you are reading this, I am dead or incapacitated. Call [family member]. The business is at `github.com/YOUR_USERNAME/tdoc` and `tdoc.xyz` registrar is Hostinger."

Dramatic? Yes. But solo founders who don't plan for bus-factor catastrophes
leave their life's work stranded.

---

## Last word

Security is not a one-time project. It's a habit. But 90% of the protection comes
from the first hour of this doc (password manager + 2FA). Do that today. Everything
else is marginal gains.
