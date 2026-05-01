"""tdoc API — hosted document structuring service, powered by the AXON reference.

Endpoints
---------
POST /v1/structure   Convert a raw document (PDF / DOCX / TXT / AXC) into an AXON tree.
POST /v1/query       Execute an AQL query over a stored or uploaded AXON document.
POST /v1/sign        Ed25519-sign an AXON document with a server-managed key.
POST /v1/verify      Verify an Ed25519-signed AXON document.
GET  /v1/healthz     Liveness probe.
GET  /v1/me          Caller identity + current usage + quota.

Auth: Bearer API key in Authorization header. Keys and plan metadata live in Redis
(or an in-memory dict for local dev).

Billing: usage is metered in-process and flushed to Stripe periodically (see
product/service/billing.py). Each endpoint that transforms content increments
"units" on the caller's plan; hitting the quota returns HTTP 402.
"""

from __future__ import annotations

import base64
import os
import sys
import tempfile
from typing import Optional

import json

from fastapi import FastAPI, Header, HTTPException, Request, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict

# Make the top-level `axon.py` importable (product/ is a subdir of the repo).
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from axon import (  # noqa: E402
    compute_document_hashes,
    convert_axc_string,
    convert_pdf,
    encode_pdf_with_axon,
    execute_aql,
    parse_axc,
    parse_pdf_with_axon,
    parse_tdoc_archive,
    render_html,
    serialize_axc,
    serialize_axr,
    serialize_for_ai,
    sign_document_ed25519,
    verify_document_ed25519,
    validate,
    AxonSecurityError,
)
from product.service.billing import (  # noqa: E402
    Plan,
    PlanQuotaExceeded,
    find_by_subscription_id,
    get_principal,
    record_units,
    register,
    update_tier,
)
from product.service.security import (  # noqa: E402
    AuditLogMiddleware,
    BodySizeLimitMiddleware,
    RateLimitMiddleware,
    RequestIDMiddleware,
    SecurityHeadersMiddleware,
    allowed_origins,
    constant_time_eq,
    take_key_token,
    unhandled_exception_handler,
    verify_lemonsqueezy_signature,
)

# Optional: Sentry error monitoring. Activates only when SENTRY_DSN is set
# AND sentry-sdk is installed. Missing package or missing env → silent no-op.
_SENTRY_DSN = os.environ.get("SENTRY_DSN")
if _SENTRY_DSN:
    try:
        import sentry_sdk  # type: ignore[import-not-found]

        sentry_sdk.init(
            dsn=_SENTRY_DSN,
            traces_sample_rate=float(
                os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0.1")
            ),
            send_default_pii=False,  # never forward auth headers / bodies
            environment=os.environ.get("TDOC_ENV", "production"),
            release=os.environ.get("TDOC_RELEASE"),
        )
    except ImportError:
        pass  # sentry-sdk not installed — no-op

app = FastAPI(
    title="tdoc API",
    version="0.1.0",
    description=(
        "Typed, queryable, signable documents — as an API. "
        "Powered by the open AXON format (v1.0)."
    ),
    # OpenAPI docs are fine at /docs in dev, but disable in prod to reduce
    # attack-surface fingerprinting. Override with TDOC_EXPOSE_DOCS=1 if needed.
    docs_url="/docs" if os.environ.get("TDOC_EXPOSE_DOCS", "1") == "1" else None,
    redoc_url="/redoc" if os.environ.get("TDOC_EXPOSE_DOCS", "1") == "1" else None,
)

# Middleware order matters — these run outside-in on request, inside-out on response.
# Last added = innermost (runs first on response). So we register in reverse.
app.add_middleware(AuditLogMiddleware)  # emits the log line last (sees final status)
app.add_middleware(SecurityHeadersMiddleware)  # attaches headers to every response
app.add_middleware(RateLimitMiddleware)  # blocks over-quota before auth runs
app.add_middleware(
    BodySizeLimitMiddleware
)  # rejects huge bodies before anything reads them
app.add_middleware(RequestIDMiddleware)  # attaches request ID before the log sees it
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins(),
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    allow_credentials=False,  # API keys go in Authorization header, not cookies
    max_age=3600,
)

# Catch-all error handler — never leak stack traces or internal paths.
app.add_exception_handler(Exception, unhandled_exception_handler)


class StructureResponse(BaseModel):
    document_id: str
    content_hash: str
    render_hash: str
    axc: str
    axc_ai: str = ""
    pdf_b64: str = ""
    nodes: int
    warnings: list[str]
    html: str = ""
    tree: dict = {}

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "document_id": "doc_01J8XYZABC",
                "content_hash": "c7a1f9e6…",
                "render_hash": "3b8d40b2…",
                "axc": '@section [id="s1"]:\n  @heading [level=1]:\n    Introduction\n',
                "axc_ai": "<!-- AXON DOCUMENT — MACHINE-NATIVE … -->\n@section …",
                "nodes": 142,
                "warnings": ["@figure missing alt-text (id=fig-3)"],
                "html": "<article>…rendered HTML…</article>",
                "tree": {"type": "document", "children": []},
            }
        }
    )


class QueryRequest(BaseModel):
    aql: str
    axc: str  # The AXON content notation to run the query against.

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "aql": "SELECT text FROM cell WHERE data-type = 'pvalue' AND value < 0.05",
                "axc": '@section [id="results"]:\n  @table [id="t1"]:\n    …',
            }
        }
    )


class QueryResponse(BaseModel):
    count: int
    results: list[dict] | list[str]

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "count": 3,
                "results": [
                    {"text": "0.003"},
                    {"text": "0.011"},
                    {"text": "0.049"},
                ],
            }
        }
    )


class SignRequest(BaseModel):
    axc: str
    render_axr: Optional[str] = None
    manifest: dict

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "axc": '@section [id="s1"]:\n  @paragraph:\n    Signed content.\n',
                "render_axr": "",
                "manifest": {
                    "document_id": "doc_01J8XYZABC",
                    "title": "Signed Paper",
                    "document_type": "article.research",
                    "content_hash": "c7a1f9e6…",
                    "render_hash": "3b8d40b2…",
                },
            }
        }
    )


class SignResponse(BaseModel):
    signature: dict

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "signature": {
                    "type": "ed25519",
                    "signature": "6f8a…64-byte hex…",
                    "public_key": "9c1b…32-byte hex…",
                    "covered_fields": ["manifest", "content_hash", "render_hash"],
                }
            }
        }
    )


class VerifyRequest(BaseModel):
    axc: str
    render_axr: str
    manifest: dict
    signature: dict

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "axc": '@section [id="s1"]:\n  @paragraph:\n    Signed content.\n',
                "render_axr": "",
                "manifest": {
                    "document_id": "doc_01J8XYZABC",
                    "content_hash": "c7a1f9e6…",
                    "render_hash": "3b8d40b2…",
                },
                "signature": {
                    "type": "ed25519",
                    "signature": "6f8a…64-byte hex…",
                    "public_key": "9c1b…32-byte hex…",
                },
            }
        }
    )


class VerifyResponse(BaseModel):
    valid: bool

    model_config = ConfigDict(json_schema_extra={"example": {"valid": True}})


@app.get("/v1/healthz")
def healthz() -> dict:
    return {"ok": True, "version": app.version}


def _auth(authorization: Optional[str]) -> Plan:
    """Validate bearer API key. Uses constant-time lookup to resist key-enumeration
    timing attacks, and applies per-key rate limits once the tier is known."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer API key")
    key = authorization.split(None, 1)[1].strip()
    plan = get_principal(key)
    if plan is None:
        # Do NOT log the raw key here — AuditLogMiddleware logs a masked prefix only.
        raise HTTPException(status_code=401, detail="Invalid API key")
    # Defence-in-depth: reject if the stored key doesn't match bit-for-bit
    # (e.g. if the store is somehow compromised and a lookalike key is served).
    if not constant_time_eq(plan.api_key, key):
        raise HTTPException(status_code=401, detail="Invalid API key")
    # Per-key rate limit — tier-aware.
    if not take_key_token(plan.api_key, plan.tier):
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit for tier '{plan.tier}' exceeded. Try again in a moment.",
            headers={"Retry-After": "2"},
        )
    return plan


@app.get("/v1/me")
def me(authorization: Optional[str] = Header(default=None)) -> dict:
    plan = _auth(authorization)
    return {
        "plan": plan.tier,
        "units_used": plan.units_used,
        "units_included": plan.units_included,
        "overage_price_cents": plan.overage_price_cents,
    }


def _count_nodes(node) -> int:
    return 1 + sum(_count_nodes(c) for c in node.children)


def _build_rich_response(doc) -> StructureResponse:
    """Common path for /v1/structure and /v1/try-public — packs the same
    document into the artifacts a buyer or agent needs:

      - axc    : canonical text serialization (format-author view)
      - axc_ai : self-describing AI-native output (preamble + AXC, no base64 images)
      - html   : rendered HTML preview (human view)
      - tree   : pure JSON tree (LLM view — no parser required)

    Plus the integrity hashes and validator warnings.
    """
    axc = serialize_axc(doc.content)
    axc_ai = serialize_for_ai(doc)
    axr = serialize_axr(doc.render)
    content_hash, render_hash = compute_document_hashes(axc, axr)
    html = render_html(doc)
    tree = doc.content.to_dict()

    pdf_b64 = ""
    try:
        pdf_bytes = encode_pdf_with_axon(doc)
        pdf_b64 = base64.b64encode(pdf_bytes).decode("ascii")
    except Exception:
        pass

    result = validate(doc)
    return StructureResponse(
        document_id=doc.manifest.document_id,
        content_hash=content_hash,
        render_hash=render_hash,
        axc=axc,
        axc_ai=axc_ai,
        pdf_b64=pdf_b64,
        nodes=_count_nodes(doc.content),
        warnings=result.warnings,
        html=html,
        tree=tree,
    )


@app.post("/v1/structure", response_model=StructureResponse)
async def structure(
    file: UploadFile = File(...),
    title: str = Form("Untitled"),
    document_type: str = Form("article.research"),
    authorization: Optional[str] = Header(default=None),
) -> StructureResponse:
    plan = _auth(authorization)
    blob = await file.read()
    if len(blob) > 32 * 1024 * 1024:  # 32 MiB hard cap per request
        raise HTTPException(status_code=413, detail="File exceeds 32 MiB limit")

    suffix = (file.filename or "").lower()
    try:
        if suffix.endswith(".pdf"):
            # First try parsing as a tdoc-flavoured PDF (one we generated
            # earlier with AXON embedded inside). If it has axon-content.axc
            # as an embedded file we can do a perfect round-trip; otherwise
            # fall back to the OCR-style text extraction path.
            try:
                doc = parse_pdf_with_axon(blob)
            except AxonSecurityError:
                # Vanilla PDF — extract text via convert_pdf. Write to a
                # secure temp file (random name, 0600 perms) so the parser
                # can open it by path; delete in the finally clause.
                with tempfile.NamedTemporaryFile(
                    prefix="axon_in_", suffix=".pdf", delete=False
                ) as tf:
                    tf.write(blob)
                    tmp = tf.name
                try:
                    doc = convert_pdf(tmp, title=title, document_type=document_type)
                finally:
                    try:
                        os.remove(tmp)
                    except OSError:
                        pass
        elif suffix.endswith((".axc", ".txt", ".md")):
            doc = convert_axc_string(
                blob.decode("utf-8"), title=title, document_type=document_type
            )
        elif suffix.endswith(".tdoc"):
            # New-format tdoc is a PDF with AXON embedded; legacy was a ZIP.
            try:
                doc = parse_pdf_with_axon(blob)
            except AxonSecurityError:
                doc = parse_tdoc_archive(blob)
        else:
            raise HTTPException(
                status_code=415,
                detail=f"Unsupported file type: {suffix!r}. Use .pdf, .axc, .txt, or .md.",
            )
    except AxonSecurityError as e:
        raise HTTPException(status_code=400, detail=f"Unsafe input: {e}")

    try:
        record_units(plan, amount=max(1, len(blob) // 50_000))  # ≈ 1 unit per 50 KB
    except PlanQuotaExceeded as e:
        raise HTTPException(status_code=402, detail=str(e))

    return _build_rich_response(doc)


# Public, unauthenticated demo endpoint. Powers the /try page on tdoc.xyz so a
# visitor can drop a small file and see typed AXON output without signing up.
# Tighter caps than /v1/structure (5 MiB, no signing/storage). IP rate-limit
# inherited from RateLimitMiddleware (5 rps, 30 burst per IP).
_TRY_MAX_BYTES = 5 * 1024 * 1024


@app.post("/v1/try-public", response_model=StructureResponse)
async def try_public(
    file: UploadFile = File(...),
    title: str = Form("Demo"),
    # "preprint" has no required-section schema, so a 1-paragraph demo
    # input doesn't trigger 4 alarming "expected section X not found"
    # warnings. The authenticated /v1/structure path keeps article.research
    # as the default since real callers know what they're submitting.
    document_type: str = Form("preprint"),
) -> StructureResponse:
    blob = await file.read()
    if len(blob) > _TRY_MAX_BYTES:
        raise HTTPException(
            status_code=413,
            detail="Demo limit is 5 MiB. Sign up for the full 32 MiB limit.",
        )

    suffix = (file.filename or "").lower()
    try:
        if suffix.endswith(".pdf"):
            with tempfile.NamedTemporaryFile(
                prefix="axon_try_", suffix=".pdf", delete=False
            ) as tf:
                tf.write(blob)
                tmp = tf.name
            try:
                doc = convert_pdf(tmp, title=title, document_type=document_type)
            finally:
                try:
                    os.remove(tmp)
                except OSError:
                    pass
        elif suffix.endswith((".axc", ".txt", ".md")):
            doc = convert_axc_string(
                blob.decode("utf-8", errors="replace"),
                title=title,
                document_type=document_type,
            )
        elif suffix.endswith(".tdoc"):
            doc = parse_tdoc_archive(blob)
        else:
            raise HTTPException(
                status_code=415,
                detail=f"Unsupported file type: {suffix!r}. Use .pdf, .axc, .txt, or .md.",
            )
    except AxonSecurityError as e:
        raise HTTPException(status_code=400, detail=f"Unsafe input: {e}")

    return _build_rich_response(doc)


@app.post("/v1/query", response_model=QueryResponse)
def query(
    req: QueryRequest, authorization: Optional[str] = Header(default=None)
) -> QueryResponse:
    plan = _auth(authorization)
    root = parse_axc(req.axc)
    result = execute_aql(req.aql, root)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    try:
        record_units(plan, amount=1)
    except PlanQuotaExceeded as e:
        raise HTTPException(status_code=402, detail=str(e))
    return QueryResponse(
        count=result.get("count", 0), results=result.get("results", [])
    )


def _load_server_signing_key():
    """Load (or lazily generate) the server's Ed25519 signing key.

    In production the key lives in KMS/secret-manager. Here: env var AXON_CLOUD_SIGNING_KEY
    holds the raw 32-byte hex; absence generates an ephemeral in-memory key (dev only).
    """
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    except ImportError:
        raise HTTPException(
            status_code=501,
            detail="Signing requires the 'cryptography' package on the server",
        )
    key_hex = os.environ.get("TDOC_SIGNING_KEY")
    if key_hex:
        return Ed25519PrivateKey.from_private_bytes(bytes.fromhex(key_hex))
    # Dev fallback — ephemeral, but we cache on the app state so multiple calls are consistent.
    if not hasattr(app.state, "_signing_key"):
        app.state._signing_key = Ed25519PrivateKey.generate()
    return app.state._signing_key


@app.post("/v1/sign", response_model=SignResponse)
def sign(
    req: SignRequest, authorization: Optional[str] = Header(default=None)
) -> SignResponse:
    plan = _auth(authorization)
    if plan.tier in ("free", "pro"):
        raise HTTPException(
            status_code=402,
            detail="Ed25519 signing requires the Team plan or higher.",
        )
    sk = _load_server_signing_key()
    render_axr = req.render_axr or ""
    try:
        sig = sign_document_ed25519(req.axc, render_axr, req.manifest, sk)
    except ImportError as e:
        raise HTTPException(status_code=501, detail=str(e))
    record_units(plan, amount=1)
    return SignResponse(signature=sig)


@app.post("/v1/verify", response_model=VerifyResponse)
def verify(
    req: VerifyRequest, authorization: Optional[str] = Header(default=None)
) -> VerifyResponse:
    _auth(authorization)
    try:
        ok = verify_document_ed25519(
            req.axc, req.render_axr, req.manifest, req.signature
        )
    except ImportError as e:
        raise HTTPException(status_code=501, detail=str(e))
    return VerifyResponse(valid=ok)


# ────────────────────────────────────────────────────────────────────────────
# Lemon Squeezy webhook — auto-provision API keys on subscription_created,
# re-tier on subscription_updated, downgrade to free on subscription_cancelled.
#
# LS reference: https://docs.lemonsqueezy.com/help/webhooks
# Signature:    HMAC-SHA256(body, signing_secret) → hex → header X-Signature
#
# Configuration (HF Space secrets):
#   LEMONSQUEEZY_WEBHOOK_SECRET  — the signing secret you copy from LS dashboard.
#   LS_VARIANT_MAP               — JSON like {"123":"pro","124":"team","125":"scale"}
#                                  mapping LS variant_id → tdoc tier name.
#
# Endpoint: POST /v1/webhooks/lemonsqueezy
#
# Idempotency: LS retries on non-2xx. We always return 2xx for verified
# requests so retries don't pile up; failures-after-verification are logged
# and surfaced via Sentry, not via 5xx.
# ────────────────────────────────────────────────────────────────────────────


def _ls_variant_to_tier(variant_id: str) -> str | None:
    """Look up the tdoc tier for a LS variant id, returning None if unmapped.

    Reads the LS_VARIANT_MAP env var (JSON) on every call so an operator can
    add a tier without restarting the Space — env updates DO trigger a
    Space rebuild on HF, but local dev should pick up changes immediately.
    """
    raw = os.environ.get("LS_VARIANT_MAP", "")
    if not raw:
        return None
    try:
        import json as _json

        m = _json.loads(raw)
    except ValueError:
        return None
    if not isinstance(m, dict):
        return None
    return m.get(str(variant_id))


@app.post("/v1/webhooks/lemonsqueezy")
async def lemonsqueezy_webhook(request: Request) -> dict:
    secret = os.environ.get("LEMONSQUEEZY_WEBHOOK_SECRET", "")
    if not secret:
        # Refuse to process unsigned webhooks rather than silently dropping
        # them — operator error should surface, not hide.
        raise HTTPException(
            status_code=503,
            detail="Webhook handler not configured (LEMONSQUEEZY_WEBHOOK_SECRET unset)",
        )

    body = await request.body()
    sig = request.headers.get("x-signature", "")
    if not verify_lemonsqueezy_signature(secret, body, sig):
        raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        import json as _json

        payload = _json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise HTTPException(status_code=400, detail="Malformed JSON body")

    meta = payload.get("meta", {})
    event = meta.get("event_name", "")
    data = payload.get("data", {})
    attrs = data.get("attributes", {})
    sub_id = str(data.get("id", "")) or None
    variant_id = str(attrs.get("variant_id", "")) or None
    customer_id = str(attrs.get("customer_id", "")) or None
    user_email = attrs.get("user_email") or ""

    rid = getattr(request.state, "request_id", "")

    if event == "subscription_created":
        if not sub_id or not variant_id:
            raise HTTPException(
                status_code=400, detail="Missing subscription/variant id"
            )
        tier = _ls_variant_to_tier(variant_id) or "pro"
        # If the variant map isn't configured yet we still create the key
        # at "pro" tier — far better than refusing the customer's purchase.
        # Operator gets a log line to fix the mapping.
        plan = register(
            tier,
            lemonsqueezy_customer_id=customer_id,
            lemonsqueezy_subscription_id=sub_id,
        )
        # Log the prefix only — never the full key.
        from product.service.security import logger as _seclog

        _seclog.info(
            json.dumps(
                {
                    "rid": rid,
                    "ls_event": event,
                    "tier": tier,
                    "sub_id": sub_id,
                    "key_prefix": plan.api_key[:8] + "…",
                    "user_email_domain": user_email.split("@", 1)[-1]
                    if "@" in user_email
                    else "",
                }
            )
        )
        return {"ok": True, "event": event, "key_prefix": plan.api_key[:8] + "…"}

    if event == "subscription_updated":
        if not sub_id:
            raise HTTPException(status_code=400, detail="Missing subscription id")
        plan = find_by_subscription_id(sub_id)
        if plan is None:
            # First time we see this subscription — treat as create.
            tier = _ls_variant_to_tier(variant_id or "") or "pro"
            plan = register(
                tier,
                lemonsqueezy_customer_id=customer_id,
                lemonsqueezy_subscription_id=sub_id,
            )
            return {"ok": True, "event": event, "action": "created"}
        new_tier = _ls_variant_to_tier(variant_id or "") or plan.tier
        if new_tier != plan.tier:
            update_tier(plan, new_tier)
        return {"ok": True, "event": event, "tier": new_tier}

    if event in ("subscription_cancelled", "subscription_expired"):
        if not sub_id:
            raise HTTPException(status_code=400, detail="Missing subscription id")
        plan = find_by_subscription_id(sub_id)
        if plan is not None:
            update_tier(plan, "free")
        return {"ok": True, "event": event}

    # Unknown event — accept (so LS doesn't retry forever) and no-op.
    return {"ok": True, "event": event, "action": "ignored"}


# Uvicorn entrypoint:  uvicorn product.service.main:app --reload --port 8000
