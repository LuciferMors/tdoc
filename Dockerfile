# syntax=docker/dockerfile:1.7
# tdoc API — production Dockerfile for Fly.io (Singapore region).
# Image target: python:3.12-slim (stable, small, well-maintained).

FROM python:3.12-slim AS base

# Security defaults: non-root user, no pip cache, no pyc writes, unbuffered stdout.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Minimal OS deps. PyMuPDF wheels ship binaries for glibc so we stay on -slim.
# curl is used only by the HEALTHCHECK instruction.
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# Non-root runtime user.
RUN useradd --create-home --shell /usr/sbin/nologin --uid 10001 tdoc
WORKDIR /app

# Install Python deps first so the layer caches across code edits.
# Only the runtime-required extras (pdf + fastjson + crypto). No dev deps.
COPY requirements.txt ./
RUN pip install --no-cache-dir \
      fastapi \
      "uvicorn[standard]" \
      python-multipart \
      PyMuPDF \
      orjson \
      cryptography \
      "psycopg[binary,pool]>=3.2"

# Copy application source.
COPY axon.py ./
COPY product ./product

# Flip ownership then drop to the non-root user.
RUN chown -R tdoc:tdoc /app
USER tdoc

EXPOSE 8080

# HEALTHCHECK hits the public /v1/healthz endpoint that already exists.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl --fail --silent --show-error http://127.0.0.1:8080/v1/healthz || exit 1

# Run uvicorn directly — Fly.io attaches its proxy to $PORT, so we bind 0.0.0.0:8080.
# Single worker is fine for free-tier; bump `--workers` when paid plan lands.
CMD ["uvicorn", "product.service.main:app", "--host", "0.0.0.0", "--port", "8080"]
