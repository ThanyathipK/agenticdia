"""
Unit tests for :mod:`app.rate_limit`.

Exercises the sliding-window limiter and the FastAPI ``Depends`` factory that
guard LLM-facing endpoints (Finding #39) from inbound abuse.

Run from the ``backend`` directory::

    ../venv/bin/python -m pytest tests/test_rate_limit.py -v
"""

import pytest

from fastapi import HTTPException

import app.rate_limit as rate_limit
from app.rate_limit import limiter, rate_limit_dependency


# ==========================================
# SlidingWindowRateLimiter
# ==========================================
class TestRateLimiter:
    def test_allows_up_to_limit_then_blocks(self, monkeypatch):
        limiter.reset("k")
        assert limiter.allow("k", 2, 60) is True
        assert limiter.allow("k", 2, 60) is True
        assert limiter.allow("k", 2, 60) is False

    def test_key_scope_is_isolated(self, monkeypatch):
        limiter.reset("a")
        limiter.reset("b")
        assert limiter.allow("a", 1, 60) is True
        assert limiter.allow("a", 1, 60) is False
        assert limiter.allow("b", 1, 60) is True

    def test_window_slides_after_expiry(self, monkeypatch):
        limiter.reset("k")
        fake_time = [100.0]
        monkeypatch.setattr(rate_limit.time, "monotonic", lambda: fake_time[0])
        assert limiter.allow("k", 1, 60) is True
        assert limiter.allow("k", 1, 60) is False
        # Move past the 60s window.
        fake_time[0] = 161.0
        assert limiter.allow("k", 1, 60) is True

    def test_current_count_reflects_records(self, monkeypatch):
        limiter.reset("k")
        fake_time = [100.0]
        monkeypatch.setattr(rate_limit.time, "monotonic", lambda: fake_time[0])
        assert limiter.allow("k", 10, 60) is True
        assert limiter.allow("k", 10, 60) is True
        assert limiter.current_count("k", 60) == 2

    def test_reset_clears(self, monkeypatch):
        limiter.reset("k")
        assert limiter.allow("k", 1, 60) is True
        assert limiter.allow("k", 1, 60) is False
        limiter.reset("k")
        assert limiter.allow("k", 1, 60) is True


# ==========================================
# rate_limit_dependency factory
# ==========================================
class _FakeClient:
    host = "203.0.113.9"


class _FakeRequest:
    def __init__(self, host="203.0.113.9"):
        self.client = _FakeClient()
        self.client.host = host


@pytest.mark.asyncio
async def test_dependency_allows_below_limit():
    dep = rate_limit_dependency("test-chat", 2, 60)
    limiter.reset("test-chat:203.0.113.9")
    await dep(_FakeRequest())  # should not raise
    await dep(_FakeRequest())  # should not raise


@pytest.mark.asyncio
async def test_dependency_raises_429_when_exceeded():
    dep = rate_limit_dependency("test-chat", 2, 60)
    limiter.reset("test-chat:203.0.113.9")
    await dep(_FakeRequest())
    await dep(_FakeRequest())
    with pytest.raises(HTTPException) as exc:
        await dep(_FakeRequest())
    assert exc.value.status_code == 429
    assert "Retry-After" in exc.value.headers


@pytest.mark.asyncio
async def test_dependency_disabled_is_noop(monkeypatch):
    monkeypatch.setattr(rate_limit.settings, "RATE_LIMIT_ENABLED", False)
    dep = rate_limit_dependency("test-chat", 1, 60)
    limiter.reset("test-chat:203.0.113.9")
    await dep(_FakeRequest())
    await dep(_FakeRequest())  # would exceed limit if enabled
    await dep(_FakeRequest())
