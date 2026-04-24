# Repo split strategy — public OSS + private commercial

## Current state (now)

**ONE PRIVATE repo on GitHub**, containing everything:

```
github.com/YOUR_USERNAME/tdoc   (PRIVATE ← set this when you create the repo)
├── axon.py                      ← the open format (will open-source later)
├── AXON_Format_Specification.txt
├── tests/                       ← format tests
├── demo.py, paper*.axc, *.axon  ← demo + samples
├── product/                     ← COMMERCIAL: API service, billing, landing page
│   ├── service/                 ← API code (PROPRIETARY)
│   ├── web/                     ← landing page (will be public via Cloudflare Pages)
│   ├── tests/                   ← API tests (PROPRIETARY)
│   ├── SETUP_ZERO_CAPITAL.md    ← founder strategy (PROPRIETARY)
│   ├── OPSEC_GUIDE.md           ← personal operational security (PROPRIETARY)
│   └── README.md
├── SECURITY.md
├── THREAT_MODEL.md
├── INCIDENT_RESPONSE.md
├── LICENSE                      ← Apache-2.0
├── pyproject.toml
├── requirements.txt
├── README.md                    ← top-level
└── .github/workflows/ci.yml     ← security + test pipeline
```

**Why private, not public, right now**:

1. **Proprietary code protection** — `product/service/*.py` contains your billing
   logic, rate-limit tuning, quota math. Competitors copying this is worse than
   competitors copying the format.
2. **Founder strategy docs** — `SETUP_ZERO_CAPITAL.md`, `OPSEC_GUIDE.md` are
   internal. They stay in the private repo.
3. **Cloudflare Pages works with private repos** — you don't need public
   visibility to deploy the landing page.
4. **OSS as a marketing moment** — save the "we open-sourced AXON!" moment for
   the HN launch in Week 3. It's a one-time attention spike; don't spend it prematurely.

---

## Split it later, at HN launch (~Week 3)

When you're ready to launch on Hacker News, extract the format into a second,
public repo. This gives you:

- Marketing credibility: "Built on the open AXON format — see [github.com/YOUR_USERNAME/axon](https://github.com/YOUR_USERNAME/axon)"
- Community contributions: people can submit format bug fixes without access to your commercial code
- Credibility with enterprise buyers: "the format is open; no lock-in"

### Step-by-step split (do this once you have a working product + traffic)

```bash
# 1. Create a new PUBLIC repo on GitHub named `axon` (or `axon-format`, if `axon` is taken).
#    Do this via GitHub UI: https://github.com/new

# 2. Clone your private tdoc repo to a new folder:
cd ~
git clone --mirror git@github.com:YOUR_USERNAME/tdoc.git axon-split
cd axon-split

# 3. Use git-filter-repo to keep ONLY the format files in the public split.
#    (Install with: pip install git-filter-repo)
git filter-repo \
  --path axon.py \
  --path AXON_Format_Specification.txt \
  --path demo.py \
  --path LICENSE \
  --path pyproject.toml \
  --path requirements.txt \
  --path tests/ \
  --path-glob 'paper*.axc' \
  --path-glob '*.axon'

# 4. Rewrite the remote + push to the new public repo:
git remote set-url origin git@github.com:YOUR_USERNAME/axon.git
git push --mirror

# 5. In the PRIVATE tdoc repo, convert axon.py into a pip dependency:
#    (Stop committing axon.py; reference it via pyproject.toml)
echo "axon-document>=0.1.0" >> pyproject.toml   # published from the public repo to PyPI
git rm axon.py AXON_Format_Specification.txt tests/test_*.py
git commit -m "Extract AXON format to public repo; depend on axon-document package"

# 6. Publish axon-document to PyPI from the public repo:
cd ~/axon-split   # (the public axon repo clone)
python -m build
python -m twine upload dist/*
```

After this, you have two repos:
- **Public** `github.com/YOUR_USERNAME/axon` — the open-source AXON format, on PyPI
- **Private** `github.com/YOUR_USERNAME/tdoc` — the commercial product, depends on `axon-document`

---

## Until then: the "one private repo" rules

While everything is in one private repo, follow these rules:

1. **Repo visibility**: PRIVATE. Triple-check this when you create the repo —
   the toggle is at `github.com/new`, right under the repository name.
2. **Collaborators**: just you, until you hire someone. No free-tier employees,
   no freelancers with read access, no "just for a weekend" consultants.
3. **Deploy keys, not personal PATs**: when Fly.io or Cloudflare Pages needs to
   read the repo, give it a **deploy key** (read-only, repo-scoped) rather than
   your personal PAT (full-account access).
4. **CI secrets**: any secret used in `.github/workflows/ci.yml` goes in
   GitHub Settings → Secrets, not in the YAML file.
5. **Branch protection on main**: even solo, turn this on. Require PR + passing
   CI even for your own pushes. Prevents a tired 3 AM force-push from destroying
   history. Settings → Branches → Branch protection rule → `main` → Require
   status checks to pass + Include administrators.

---

## Making the landing page deploy from a private repo

Cloudflare Pages supports private repos natively — no special config needed.
When you connect the Git repo in Cloudflare Pages, authorise the Cloudflare
GitHub App on your `tdoc` repo specifically (not all repos). Cloudflare then
uses a scoped OAuth token to read only that repo for deploys. Your other
private projects are untouched.
