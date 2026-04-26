"""Production security middleware for the tdoc API.

Implements (in order of request flow):
  1. Request-ID attach (for audit log correlation)
  2. Body-size cap (DoS defense beyond per-endpoint caps)
  3. Rate limiting (per IP + per API key, token-bucket)
  4. Security headers (HSTS, CSP, frame-options, referrer, permissions)
  5. Structured audit logging (JSON, no PII)
  6. Error sanitization (no stack traces, no internal paths)

Design choices + rationale (CyberTeam threat model):

  - CORS is an allowlist, not "*". Threat: CSRF and API-key theft via rogue
    JS on attacker-controlled site.
  - Rate limit is in-memory token bucket. For a single Fly.io instance that's
    correct; for a multi-region deploy, swap _BUCKETS for Redis. Threat:
    credential stuffing + API-key brute force + quota farming.
  - Security headers target a Mozilla Observatory "A" rating baseline.
  - Audit logs never include the raw API key — only the first 8 chars as an
    identifier (plus the plan tier). Threat: log leakage revealing credentials.
  - Error handler returns a stable shape: {error: "...", request_id: "..."}
    so clients can file incident tickets, but no internals leak.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import secrets as _secrets
import time
import uuid
from typing import Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware


logger = logging.getLogger("tdoc.security")
logger.setLevel(logging.INFO)
if not logger.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(_h)


# ──────────────────────────────────────────────────────────────────────────
# 1. Body size cap (global DoS defense)
# ──────────────────────────────────────────────────────────────────────────
MAX_REQUEST_BYTES = 32 * 1024 * 1024  # 32 MiB — matches /v1/structure per-endpoint cap


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    """Reject requests with Content-Length > cap before the body is read.

    Prevents an attacker from tying up server memory with an attacker-declared
    but stream-trickled body. Note: chunked transfer encoding has no header
    cap — uvicorn's own limits still apply there.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        cl = request.headers.get("content-length")
        if cl is not None:
            try:
                if int(cl) > MAX_REQUEST_BYTES:
                    return JSONResponse(
                        status_code=413,
                        content={"error": "Request body exceeds server maximum"},
                    )
            except ValueError:
                return JSONResponse(
                    status_code=400,
                    content={"error": "Invalid Content-Length header"},
                )
        return await call_next(request)


# ──────────────────────────────────────────────────────────────────────────
# 2. Rate limiter (token bucket, per-IP and per-API-key)
# ──────────────────────────────────────────────────────────────────────────
#
# Token bucket with configurable burst + sustained rate. In-memory for a single
# instance. Replace _BUCKETS with Redis for multi-region.

# Sustained rate (tokens per second) and bucket capacity (burst).
_RATE_SPECS = {
    # IP-level: block anonymous floods / naive DDoS.
    "ip": {"refill_per_sec": 5.0, "capacity": 30},
    # Key-level: different tiers get different caps — overridden per tier below.
    "key:free": {"refill_per_sec": 1.0, "capacity": 10},
    "key:pro": {"refill_per_sec": 2.0, "capacity": 30},
    "key:team": {"refill_per_sec": 5.0, "capacity": 60},
    "key:scale": {"refill_per_sec": 20.0, "capacity": 200},
}

_BUCKETS: dict[str, tuple[float, float]] = {}  # bucket_id -> (tokens, last_refill_ts)


def _take_token(bucket_id: str, spec_key: str) -> bool:
    spec = _RATE_SPECS.get(spec_key) or _RATE_SPECS["ip"]
    now = time.monotonic()
    tokens, last = _BUCKETS.get(bucket_id, (float(spec["capacity"]), now))
    # Refill based on elapsed time.
    tokens = min(spec["capacity"], tokens + (now - last) * spec["refill_per_sec"])
    if tokens >= 1:
        _BUCKETS[bucket_id] = (tokens - 1, now)
        return True
    _BUCKETS[bucket_id] = (tokens, now)
    return False


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Enforce per-IP rate limits; per-key limits apply once auth happens."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Skip non-API routes so healthz/docs don't count.
        if not request.url.path.startswith("/v1/"):
            return await call_next(request)

        # Trust X-Forwarded-For from Cloudflare/Fly, fall back to client.host.
        ip = (
            request.headers.get("cf-connecting-ip")
            or request.headers.get("x-forwarded-for", "").split(",")[0].strip()
            or (request.client.host if request.client else "unknown")
        )
        if not _take_token(f"ip:{ip}", "ip"):
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit exceeded (IP). Try again in a few seconds."
                },
                headers={"Retry-After": "5"},
            )

        # Per-key rate limit happens in main.py after auth resolves the tier.
        return await call_next(request)


def take_key_token(api_key: str, tier: str) -> bool:
    """Per-API-key rate limit. Called from main.py after auth identifies the tier."""
    return _take_token(f"key:{api_key}", f"key:{tier}")


# ──────────────────────────────────────────────────────────────────────────
# 3. Security headers
# ──────────────────────────────────────────────────────────────────────────
#
# Targets Mozilla Observatory "A+" for API surfaces. CSP is restrictive because
# this is an API, not a browser-facing UI. `Server` header is blanked to avoid
# leaking framework/version fingerprints to attackers.

_SECURITY_HEADERS: dict[str, str] = {
    # Transport security — force HTTPS for 1 year, include subdomains, preload-ready.
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains; preload",
    # Don't let the API be embedded in an iframe anywhere.
    "X-Frame-Options": "DENY",
    # MIME sniffing defense.
    "X-Content-Type-Options": "nosniff",
    # Leak less info in Referer when following links.
    "Referrer-Policy": "strict-origin-when-cross-origin",
    # Disable every powerful browser API by default — API clients never need them.
    "Permissions-Policy": (
        "accelerometer=(), camera=(), geolocation=(), gyroscope=(), "
        "magnetometer=(), microphone=(), payment=(), usb=()"
    ),
    # Cross-origin isolation for any HTML surfaces we might serve alongside.
    "Cross-Origin-Resource-Policy": "same-origin",
    "Cross-Origin-Opener-Policy": "same-origin",
    # Obscure the server banner (defense-in-depth; fingerprinting still possible
    # via response shape, but we don't volunteer it).
    "Server": "tdoc",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response: Response = await call_next(request)
        # Remove any upstream-set Server header (e.g. uvicorn's default) so we
        # don't leak framework fingerprints, then set ours.
        if "server" in response.headers:
            del response.headers["server"]
        for h, v in _SECURITY_HEADERS.items():
            response.headers[h] = v
        return response


# ──────────────────────────────────────────────────────────────────────────
# 4. Request-ID + structured audit logging
# ──────────────────────────────────────────────────────────────────────────


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Attach a request ID for log correlation and surface it to clients."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex
        request.state.request_id = rid
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        return response


class AuditLogMiddleware(BaseHTTPMiddleware):
    """Emit one JSON log line per request. No PII, no API keys, no bodies."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - start) * 1000, 2)

        # First 8 chars of API key (if any) for log correlation w/o credential leak.
        auth = request.headers.get("authorization", "")
        key_id = ""
        if auth.lower().startswith("bearer "):
            raw = auth.split(None, 1)[1].strip()
            # Masked: only a short prefix so logs can be grepped but keys can't be reconstructed.
            key_id = raw[:8] + "…" if len(raw) > 8 else "?"

        logger.info(
            json.dumps(
                {
                    "ts": int(time.time()),
                    "rid": getattr(request.state, "request_id", ""),
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "duration_ms": duration_ms,
                    "key_id": key_id,
                    "ua": (request.headers.get("user-agent", "")[:80] or ""),
                    "ip": (
                        request.headers.get("cf-connecting-ip")
                        or (request.client.host if request.client else "")
                    ),
                }
            )
        )
        return response


# ──────────────────────────────────────────────────────────────────────────
# 5. Constant-time API key comparison
# ──────────────────────────────────────────────────────────────────────────


def constant_time_eq(a: str, b: str) -> bool:
    """Timing-attack-resistant comparison — used in auth paths."""
    return _secrets.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def verify_lemonsqueezy_signature(secret: str, body: bytes, signature_hex: str) -> bool:
    """Verify the X-Signature header on a Lemon Squeezy webhook.

    LS signs the raw request body with HMAC-SHA256 using the per-store
    signing secret you set in the LS dashboard. The header is the lowercase
    hex digest. We compare in constant time so bad-signature attempts can't
    be used as a timing oracle.

    Returns False on any malformed input rather than raising — webhook
    handlers want a clean boolean, not a try/except.
    """
    if not secret or not signature_hex:
        return False
    try:
        expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    except (TypeError, ValueError):
        return False
    return hmac.compare_digest(expected, signature_hex.strip())


# ──────────────────────────────────────────────────────────────────────────
# 6. CORS allowlist (exported for main.py)
# ──────────────────────────────────────────────────────────────────────────
#
# Keep this tight. Every origin here is a potential footgun if compromised.


def allowed_origins() -> list[str]:
    env = os.environ.get("TDOC_ENV", "dev")
    if env == "prod":
        return [
            "https://tdoc.xyz",
            "https://www.tdoc.xyz",
            "https://docs.tdoc.xyz",
        ]
    # Dev: add localhost for local testing. Never in prod.
    return [
        "https://tdoc.xyz",
        "https://www.tdoc.xyz",
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
    ]


# ──────────────────────────────────────────────────────────────────────────
# 7. Global error handler
# ──────────────────────────────────────────────────────────────────────────


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Never leak a stack trace to the client. Log server-side, return opaque error."""
    rid = getattr(request.state, "request_id", "")
    logger.error(
        json.dumps(
            {
                "ts": int(time.time()),
                "rid": rid,
                "path": request.url.path,
                "exc_type": type(exc).__name__,
                "exc_msg": str(exc)[:500],  # capped so log lines stay bounded
            }
        )
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "request_id": rid,
            "support": "hello@tdoc.xyz",
        },
        headers={"X-Request-ID": rid} if rid else None,
    )
