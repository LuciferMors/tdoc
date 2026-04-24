# tdoc — zero-to-first-customer setup guide

Your domain: **`tdoc.xyz`** (acquired 🎉)

Written for a first-time founder operating from India with ≈₹100 already spent
(domain) and no other budget. Every step below is free-tier. Total out-of-pocket
to reach "customers can pay me and the money hits my bank account": **₹0 more**.

---

## The whole stack, one glance

| Need | Service | Cost | Why this one |
|---|---|---|---|
| Domain name | **Hostinger** (already done ✓) | ₹99 Y1 / ~₹900 Y2 | Already owned |
| DNS + email routing | **Cloudflare** | Free | Better than Hostinger's DNS, free TLS, free email forwarding |
| Landing page hosting | **Cloudflare Pages** | Free | Unlimited bandwidth, automatic HTTPS |
| API hosting | **Fly.io** | Free hobby tier | Deploys FastAPI in 3 commands |
| Database | **Supabase** | Free (< 500 MB) | Postgres for API keys + usage |
| Payments | **Lemon Squeezy** | Free signup, 5%+$0.50/sale | Merchant-of-record — handles global tax, NO US company needed |
| Code hosting | **GitHub** | Free | Public repo = marketing |
| Analytics | **PostHog Cloud** | Free (< 1M events/mo) | Self-serve, no credit card |
| Error monitoring | **Sentry** | Free (5K errors/mo) | Alerts when API breaks |

**Total day-1 spend remaining: ₹0.** Everything else activates with an email.

---

## What each thing actually does (plain English)

- **Domain** (`tdoc.xyz`): The word people type to reach you. You rent it yearly. **You own this already.**
- **Cloudflare**: A free layer between your domain and the rest of the world. Handles DNS (which server answers for `tdoc.xyz`), SSL certificate (the lock icon in the browser), and email forwarding (`hello@tdoc.xyz` → your Gmail).
- **Cloudflare Pages**: Free web host. Your `product/web/index.html` becomes `https://tdoc.xyz`.
- **Fly.io**: Free server. Runs the Python API (`product/service/main.py`). Customers hit `api.tdoc.xyz/v1/structure` → routes here.
- **Supabase**: Free Postgres database. Stores who bought what plan and how many API calls they've made.
- **Lemon Squeezy**: Handles "customer clicks Buy → pays → money in your Indian bank account." They collect payments, handle GST/VAT for 180+ countries, and deposit INR to your bank. **No Delaware C-Corp. No Stripe Atlas. Just your PAN + Indian bank account.** This is the single most important piece of your stack.
- **GitHub**: Where your code lives publicly. The open-source AXON library → marketing attention.
- **PostHog**: Tells you which landing pages people visit and what they click.
- **Sentry**: Emails you when the API throws an exception.

---

## Week 1 — day by day

### Day 1 (today if possible): connect your domain to Cloudflare

You already own `tdoc.xyz` through Hostinger. Hostinger's DNS works, but Cloudflare's is faster, gives you free email forwarding, and is what we'll need anyway for Pages hosting. **15 minutes of work, all free.**

1. Go to https://dash.cloudflare.com/sign-up → sign up with your Gmail. Free Cloudflare account.
2. In Cloudflare dashboard: click **Add a site** → enter `tdoc.xyz` → choose the **Free** plan (always free).
3. Cloudflare shows you **two nameservers** (something like `abby.ns.cloudflare.com` and `bob.ns.cloudflare.com`). **Copy both exactly.**
4. Open a new tab, log into Hostinger: https://hpanel.hostinger.com
5. In Hostinger: **Domains** → click `tdoc.xyz` → look for **"Change nameservers"** or **"DNS / Nameservers"**.
6. Switch from "Hostinger nameservers" to "Custom" / "External nameservers". Paste the two Cloudflare nameservers. Save.
7. Go back to the Cloudflare tab → click **Done, check nameservers**.
8. Wait 10–60 minutes. Cloudflare will email you "Site is active".

**Set up free custom email** (so `hello@tdoc.xyz` works):

9. In Cloudflare → left sidebar → **Email** → **Email Routing** → **Get Started**. The wizard adds MX records automatically.
10. Create a catch-all rule: anything `@tdoc.xyz` → forward to `your.personal.email@gmail.com`. Verify when Cloudflare emails your Gmail.
11. Test: email `hello@tdoc.xyz` from your phone. Should land in your Gmail within 2 minutes.
12. **Optional but recommended** — enable "Send as" in Gmail:
    - Gmail → Settings (gear icon) → **See all settings** → **Accounts and Import** → "Send mail as" → **Add another email address**
    - Name: `tdoc`
    - Email: `hello@tdoc.xyz`
    - Uncheck "Treat as an alias"
    - SMTP server: `smtp.gmail.com`, port 587, your Gmail address, app password (generate at https://myaccount.google.com/apppasswords)
    - Gmail sends a verification code to `hello@tdoc.xyz` (arrives in your inbox). Enter it. Done.

✅ **End of Day 1**: `tdoc.xyz` runs on Cloudflare DNS. `hello@tdoc.xyz` works. You can reply *from* that address in Gmail.

---

### Day 2: push code to GitHub + deploy landing page

**Morning (30 min)**
1. GitHub account if you don't have one: https://github.com/signup.
2. Create a **public** repo: name it `tdoc`. Leave it empty (don't initialise with README).
3. In your terminal, inside `/path/to/tdoc/`:
   ```bash
   git init
   git add .
   git commit -m "Initial tdoc commit — AXON format + API + landing"
   git branch -M main
   git remote add origin https://github.com/YOUR_USERNAME/tdoc.git
   git push -u origin main
   ```
   If git asks for credentials: username = your GitHub username, password = a Personal Access Token (not your login password). Create one at https://github.com/settings/tokens → "Generate new token (classic)" → tick `repo` → copy the token and use *that* as the password.

**Afternoon (20 min) — deploy the landing page**
4. https://dash.cloudflare.com → **Workers & Pages** → **Create** → **Pages** → **Connect to Git** → pick your `tdoc` repo.
5. Build settings:
   - **Framework preset**: None
   - **Build command**: (leave empty)
   - **Build output directory**: `product/web`
6. Click **Save and Deploy**. Cloudflare builds in ~60 seconds. You'll get a URL like `tdoc-xyz.pages.dev`.
7. Visit that URL — your landing page should be live.
8. Back in Cloudflare Pages → your project → **Custom domains** → **Set up a custom domain** → enter `tdoc.xyz`. Cloudflare auto-configures DNS.
9. Visit https://tdoc.xyz in your browser. Live. HTTPS. Done.

✅ **End of Day 2**: `https://tdoc.xyz` shows your landing page.

---

### Day 3: deploy the API

1. Sign up at https://fly.io/app/sign-up (no credit card required for hobby tier).
2. Install `flyctl` on your Mac:
   ```bash
   brew install flyctl
   # or: curl -L https://fly.io/install.sh | sh
   flyctl auth login
   ```
3. Create `/path/to/tdoc/Dockerfile` (I'll write this for you — just tell me when you're at this step and I'll produce the exact file).

   Starter content:
   ```dockerfile
   FROM python:3.12-slim
   WORKDIR /app
   COPY . /app
   RUN pip install --no-cache-dir fastapi "uvicorn[standard]" python-multipart cryptography
   EXPOSE 8080
   CMD ["uvicorn", "product.service.main:app", "--host", "0.0.0.0", "--port", "8080"]
   ```
4. Launch:
   ```bash
   flyctl launch --name tdoc-api --region sin
   # Region 'sin' = Singapore, nearest to India for low latency.
   # When asked: Postgres? → No (we use Supabase).
   # Deploy now? → Yes.
   ```
5. Fly prints a URL like `tdoc-api.fly.dev`. Test:
   ```bash
   curl https://tdoc-api.fly.dev/v1/healthz
   # Expected: {"ok":true,"version":"0.1.0"}
   ```
6. Attach your custom subdomain:
   ```bash
   flyctl certs add api.tdoc.xyz
   ```
   Fly shows you a DNS record to add. Back in Cloudflare → DNS → **Add record** → paste what Fly told you → save. Wait 5 minutes.
7. `curl https://api.tdoc.xyz/v1/healthz` → should work.

✅ **End of Day 3**: `https://api.tdoc.xyz` is live.

---

### Day 4: payments (Lemon Squeezy)

The one that feels scary. It isn't — it's just a form.

1. https://www.lemonsqueezy.com → Sign up (free). Enter:
   - Full name (must match your PAN)
   - Email (use `hello@tdoc.xyz` if you want)
   - Phone number
2. Create your **Store**: name it `tdoc`.
   - **Country**: India
   - **Currency**: USD (you price in USD; LS auto-converts payouts to INR)
   - **Legal business name**: your own name (sole proprietorship) — **no need to incorporate yet**
3. **Tax info**: upload your PAN card. For year-end reporting.
4. **Payout method**: Indian bank account (IFSC + account number). LS deposits every 30 days.
5. **Identity verification**: selfie + PAN photo. Usually approved in 24–48 hours.
6. Once approved, **create products**:
   - "tdoc Pro" — $29/mo subscription, recurring monthly
   - "tdoc Team" — $99/mo subscription, recurring monthly
   - "tdoc Scale" — $499/mo subscription, recurring monthly
7. Each product gets a **checkout URL** like `tdoc.lemonsqueezy.com/buy/abc-123`. **Copy all three.**
8. Update `product/web/index.html` (I'll handle this in one edit once you send me the URLs) — replace `#checkout-pro`, `#checkout-team`, and the `mailto:` Scale link with the real LS checkout URLs. Commit, push. Cloudflare Pages auto-redeploys in 60 seconds.
9. Webhooks: LS → **Settings → Webhooks** → Add webhook. URL: `https://api.tdoc.xyz/v1/webhooks/lemonsqueezy`. Events: `subscription_created`, `subscription_updated`, `subscription_cancelled`. Copy the signing secret. (I'll write the webhook handler once you're at this step.)

✅ **End of Day 4**: Strangers on the internet can pay you and the money will land in your Indian bank account. No US entity required.

---

### Day 5: database + the launch post

**Morning (30 min) — Supabase**
1. https://supabase.com/dashboard → sign up with GitHub.
2. Create a project: name `tdoc`, region Singapore, strong DB password (save it).
3. In Supabase SQL editor:
   ```sql
   create table plans (
     id serial primary key,
     api_key text unique not null,
     tier text not null,
     units_included int not null,
     units_used int default 0,
     lemonsqueezy_subscription_id text,
     lemonsqueezy_customer_id text,
     email text,
     created_at timestamptz default now()
   );
   create index on plans (api_key);
   ```
4. Copy the **connection string** from Supabase → **Settings → Database**. Format: `postgresql://postgres:PASSWORD@db.xxx.supabase.co:5432/postgres`.
5. Store it as a Fly secret:
   ```bash
   flyctl secrets set DATABASE_URL="postgresql://..."
   ```
   (I'll swap `_STORE` in `billing.py` for real Postgres queries when you're ready.)

**Afternoon — write your launch post**

Title: **"Why PDFs are killing your RAG pipeline"**

Structure (1,500 words):
1. **The pain** — screenshot GPT-4 mangling a p-value read from a table.
2. **Why it happens** — PDFs are visual, not semantic. Tables are coordinates, not cells.
3. **What you tried** — pdfplumber (breaks on complex tables), Unstructured (close but no typing), LlamaParse (closer but no signatures).
4. **What you built** — the AXON format + the `.tdoc` file type + the tdoc API. One paragraph, one code sample.
5. **Benchmarks** — 3 real PDFs (a scientific paper, an SEC 10-K filing, a clinical trial protocol) — show before/after with numbers.
6. **Free tier + CTA** — "100 `.tdoc` files/month free. No credit card. https://tdoc.xyz"

Publish Friday night IST = Saturday morning Americas = highest HN weekend attention.

✅ **End of Week 1**: Live site, live API, working payments, one technical post ready.

---

## Week 2 — the launch

### Monday
- Post the blog to Hacker News. Title: **"Show HN: tdoc – typed documents as an API"**.
  - Submit at 8:30 AM PT Tuesday = **9:00 PM IST Tuesday**.
  - First comment (yours): 4 sentences — the problem, what you built, a link to the free-tier API (no signup required for 5 calls), "I'll read every comment."
  - Stay on HN for the first 6 hours, respond to every comment inside 15 minutes.
  - Realistic outcome if post is good: 5K–50K visits → 100–1000 free-tier signups → 5–30 paying customers in the next 30 days from this one post.

### Tuesday–Friday
Cross-post the article (different framing each time — NEVER the same link twice):
- r/MachineLearning (educational framing, not promo)
- r/LocalLLaMA (audience has this exact pain daily)
- r/LangChain
- dev.to (technical deep-dive version)
- LinkedIn (post as text, not link)
- X/Twitter (8-post thread)

### Saturday
First weekly review: signups, paying customers, #1 objection in customer emails. Write it in a Google Sheet.

---

## Week 3 — outbound + content engine

### Outbound (zero cost)
10 AI startups from https://aistartupjobs.com or YC W24/W25/S25 batches. Find head of engineering on LinkedIn. Manually (not bulk-tool — that gets you flagged as spam):

```
Subject: structured PDFs for {their product}

Hi {Name} —

Noticed {company} ingests {10-Ks / contracts / trial protocols / whatever}.
Just shipped tdoc — turns PDFs into typed .tdoc files (p-values are typed as
pvalues, currency as currency, etc.). Free tier at tdoc.xyz — 100 files/mo,
no credit card.

Would love your thoughts. Happy to run your 5 hardest PDFs through it live if
you want to see it.

— Rishi
tdoc.xyz · github.com/{you}/tdoc
```

10 emails, each personalized in the first 2 lines. Expect 2–3 replies. Book 1 demo.

### Content engine
- Blog post #2: **"A semantic type system for documents"** — explain AXON's type registry (`pvalue`, `measure`, `currency`, etc.). 1200 words.
- 2-min screen-capture: "From PDF to `.tdoc` in 30 seconds." Post to YouTube, X, LinkedIn.
- Open source more prominently: add `CONTRIBUTING.md`, pin issues labeled `good first issue`. Contributors become advocates.

---

## Week 4 — measure, decide, commit

| Metric | Red (pivot) | Yellow (push) | Green (scale) |
|---|---|---|---|
| Sign-ups | < 100 | 100–500 | 500+ |
| Paying customers | 0–1 | 2–4 | 5+ |
| MRR | < $30 | $30–$200 | $200+ |
| HN launch rank | didn't land | top 30 | top 10 |
| Inbound demos booked | 0 | 1–2 | 3+ |

**Decision tree**:
- **Green** → keep shipping. Month 2: LangChain plugin, LlamaIndex loader, Docs site, Discord community.
- **Yellow** → fix top-1 objection from support emails. Re-launch revised version on Product Hunt in week 5.
- **Red** → do 20 discovery calls in week 5. Wedge is wrong. Probable pivots: go deep on one vertical (legal contracts, clinical protocols), or make `.tdoc` a standalone desktop app instead of API, or reframe as a LangChain/LlamaIndex plugin first.

---

## What you never spend money on in Year 1

- Paid ads — Meta/Google/LinkedIn burn money fast without ICP certainty.
- SEO tools (Ahrefs, Semrush) — Use free Google Search Console + Reddit research.
- Email outbound tools — Do 10 hand-typed emails/week. Bulk = spam complaints = domain blacklist.
- Stripe Atlas ($500) — Lemon Squeezy replaces this until you want to raise.
- Delaware C-Corp (~$800/yr franchise tax + CPA) — Only when an investor demands it.
- Design agency — Canva free + a clean font. Your landing already works.
- Conferences — Until you have a booth worth manning, a blog post + HN thread reach more people for $0.

---

## When to spend money (trigger-based, not time-based)

| Trigger | Spend |
|---|---|
| First $500 MRR | Incorporate Indian Pvt Ltd (~₹15K via VakilSearch/IndiaFilings). Saves tax headaches. |
| First $2K MRR | Upgrade Fly.io paid ($30–50/mo) for reliability + dedicated IPs. |
| First $5K MRR | Hire a freelance writer for 2 blog posts/month (~$500–1000/mo). |
| First $20K MRR | Stripe Atlas + Delaware C-Corp → raise seed OR keep bootstrapping. |
| First $50K MRR | First full-time hire: DevRel engineer or content lead. |

---

## What I (Claude) do vs. what only you can do

**I can**:
- Write and update code — API endpoints, billing, Lemon Squeezy webhook, tests, docs.
- Write blog posts and marketing copy.
- Draft the HN post, outbound emails, onboarding emails.
- Design the pricing page, feature comparison, FAQ.
- Build the Docusaurus docs site at `docs.tdoc.xyz`.
- Write investor updates (when you have any).

**Only you can**:
- Sign up for each service (Cloudflare, Fly.io, Supabase, Lemon Squeezy, Sentry, PostHog) — they need your identity.
- Submit your PAN/KYC to Lemon Squeezy.
- Answer customer support emails in your voice.
- Do 10 outbound conversations per week — founder-led sales has no substitute.
- Decide whether to pivot.

**When you sit down with any of these services, tell me which one — I'll walk you through the exact fields you type into each box.**

---

## The `.tdoc` file extension — your brand moat

Your product outputs `.tdoc` files. These are AXON archives (valid against the open format spec), but the extension is *yours*. Every time a user:
- Opens `report.tdoc` in their file explorer → sees your brand
- Googles "what is a .tdoc file" → lands on your docs
- Shares `paper.tdoc` with a colleague → that colleague asks "what is tdoc"

Make this real on day 1:
- Add to README: `tdoc files are AXON archives with the .tdoc extension`
- Ensure your API defaults to saving with `.tdoc` extension (not `.axon`)
- Register the MIME type `application/x-tdoc` in your docs
- Submit `.tdoc` to the IANA media types registry once you have 1,000 users (free, takes ~2 weeks)

This is a compounding brand asset. Nobody can take it from you without forking the format.
