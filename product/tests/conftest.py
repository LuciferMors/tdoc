"""Shared test fixtures for product/tests/.

Most fixtures here exist to keep stateful in-process middleware from
leaking across tests:

  - The rate-limit middleware uses an in-memory token bucket keyed by
    client IP. Every test POSTs from 127.0.0.1, so once the bucket runs
    dry mid-suite, unrelated downstream tests start seeing 429s.

  - The plan store is a process-singleton that may have been switched to
    Postgres by a stray DATABASE_URL in the developer's shell. We force
    it back to in-memory and seed the dev key for tests that expect it.
"""

from __future__ import annotations

import os
import sys

import pytest


ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


@pytest.fixture(autouse=True)
def _reset_middleware_state(monkeypatch):
    # Force in-memory store, regardless of any DATABASE_URL the developer
    # has in their shell, and drop the singleton so seed runs cleanly.
    monkeypatch.delenv("DATABASE_URL", raising=False)
    from product.service import store as _store

    _store.reset_for_tests()

    # Empty the rate-limit token-bucket dict so each test starts on a
    # full bucket and the order tests execute in does not affect outcomes.
    from product.service import security as _sec

    _sec._BUCKETS.clear()

    yield

    _store.reset_for_tests()
    _sec._BUCKETS.clear()
