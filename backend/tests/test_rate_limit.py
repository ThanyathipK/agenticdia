"""
Unit tests for :mod:`app.rate_limit`.

Exercises the sliding-window limiter, the FastAPI ``Depends`` factory that
guards LLM-facing endpoints (Finding #39), the proxy-aware client-key
resolution, the pluggable store factory, and the fail-loud single-worker
deployment guard (so 429 protection can never silently disappear in a
multi-process run).

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


# ==========================================
# Proxy-aware client-key resolution
# ==========================================
class _FakeRequestWithHeaders:
    def __init__(self, host="203.0.113.9", headers=None):
        self.client = _FakeClient()
        self.client.host = host
        self.headers = headers or {}


def test_client_key_ignores_proxy_headers_by_default(monkeypatch):
    # Headers are never trusted unless the operator opted into trusting them.
    monkeypatch.setattr(rate_limit.settings, "TRUST_PROXY_HEADERS", False)
    req = _FakeRequestWithHeaders(
        host="10.0.0.5",
        headers={"x-forwarded-for": "198.51.100.7, 10.0.0.5"},
    )
    assert rate_limit.make_client_key(req, "chat") == "chat:10.0.0.5"


def test_client_key_uses_xff_from_trusted_proxy(monkeypatch):
    # Trusted proxy appends the client IP it saw: chain is just the client.
    monkeypatch.setattr(rate_limit.settings, "TRUST_PROXY_HEADERS", True)
    monkeypatch.setattr(rate_limit.settings, "TRUSTED_PROXY_IPS", "10.0.0.5")
    req = _FakeRequestWithHeaders(
        host="10.0.0.5",
        headers={"x-forwarded-for": "203.0.113.9"},
    )
    assert rate_limit.make_client_key(req, "chat") == "chat:203.0.113.9"


def test_client_key_ignores_spoofed_leftmost_xff(monkeypatch):
    # Client sent a forged XFF, but the trusted proxy appended the real client
    # on the right; the forged entry must never win.
    monkeypatch.setattr(rate_limit.settings, "TRUST_PROXY_HEADERS", True)
    monkeypatch.setattr(rate_limit.settings, "TRUSTED_PROXY_IPS", "10.0.0.5")
    req = _FakeRequestWithHeaders(
        host="10.0.0.5",
        headers={"x-forwarded-for": "198.51.100.66, 203.0.113.9"},
    )
    assert rate_limit.make_client_key(req, "chat") == "chat:203.0.113.9"


def test_client_key_skips_trusted_chain_members(monkeypatch):
    # client -> 10.0.0.6 (trusted) -> 10.0.0.5 (trusted peer): chain is
    # "203.0.113.9, 10.0.0.6" and the walk skips 10.0.0.6 to find the client.
    monkeypatch.setattr(rate_limit.settings, "TRUST_PROXY_HEADERS", True)
    monkeypatch.setattr(rate_limit.settings, "TRUSTED_PROXY_IPS", "10.0.0.5, 10.0.0.6")
    req = _FakeRequestWithHeaders(
        host="10.0.0.5",
        headers={"x-forwarded-for": "203.0.113.9, 10.0.0.6"},
    )
    assert rate_limit.make_client_key(req, "chat") == "chat:203.0.113.9"


def test_client_key_all_trusted_chain_falls_back_to_peer(monkeypatch):
    # Only trusted proxies in the chain (e.g. NAT'd backend traffic): fall back
    # to the socket peer rather than fabricating a client IP.
    monkeypatch.setattr(rate_limit.settings, "TRUST_PROXY_HEADERS", True)
    monkeypatch.setattr(rate_limit.settings, "TRUSTED_PROXY_IPS", "10.0.0.5, 10.0.0.6")
    req = _FakeRequestWithHeaders(
        host="10.0.0.5",
        headers={"x-forwarded-for": "10.0.0.6, 10.0.0.5"},
    )
    assert rate_limit.make_client_key(req, "chat") == "chat:10.0.0.5"


def test_client_key_ignores_headers_from_untrusted_peer(monkeypatch):
    # A peer that is NOT on the trusted list cannot smuggle a wider bucket.
    monkeypatch.setattr(rate_limit.settings, "TRUST_PROXY_HEADERS", True)
    monkeypatch.setattr(rate_limit.settings, "TRUSTED_PROXY_IPS", "10.0.0.5")
    req = _FakeRequestWithHeaders(
        host="198.51.100.7",
        headers={"x-forwarded-for": "1.1.1.1"},
    )
    assert rate_limit.make_client_key(req, "chat") == "chat:198.51.100.7"


def test_client_key_falls_back_to_peer_without_xff(monkeypatch):
    monkeypatch.setattr(rate_limit.settings, "TRUST_PROXY_HEADERS", True)
    monkeypatch.setattr(rate_limit.settings, "TRUSTED_PROXY_IPS", "10.0.0.5")
    req = _FakeRequestWithHeaders(host="10.0.0.5", headers={})
    assert rate_limit.make_client_key(req, "chat") == "chat:10.0.0.5"


def test_forwarded_header_parsing(monkeypatch):
    monkeypatch.setattr(rate_limit.settings, "TRUST_PROXY_HEADERS", True)
    monkeypatch.setattr(rate_limit.settings, "TRUSTED_PROXY_IPS", "10.0.0.5")
    req = _FakeRequestWithHeaders(
        host="10.0.0.5",
        headers={"forwarded": 'for=203.0.113.9;proto=https;host=example.com'},
    )
    assert rate_limit.make_client_key(req, "chat") == "chat:203.0.113.9"


# ==========================================
# Store factory + deployment guardrail
# ==========================================
def test_get_rate_limit_store_returns_in_process_by_default():
    assert rate_limit.get_rate_limit_store() is limiter


def test_get_rate_limit_store_rejects_unsupported_mode(monkeypatch):
    monkeypatch.setattr(rate_limit.settings, "RATE_LIMIT_STORE", "redis")
    with pytest.raises(ValueError, match="Unsupported RATE_LIMIT_STORE"):
        rate_limit.get_rate_limit_store()


def test_detect_worker_count_parses_argv(monkeypatch):
    monkeypatch.setattr(
        rate_limit.sys, "argv", ["uvicorn", "app.main:app", "--workers", "4"]
    )
    assert rate_limit.detect_worker_count() == 4
    monkeypatch.setattr(
        rate_limit.sys, "argv", ["uvicorn", "app.main:app", "-w", "3"]
    )
    assert rate_limit.detect_worker_count() == 3
    monkeypatch.setattr(
        rate_limit.sys, "argv", ["uvicorn", "app.main:app", "--workers=8"]
    )
    assert rate_limit.detect_worker_count() == 8
    monkeypatch.setattr(rate_limit.sys, "argv", ["uvicorn", "app.main:app"])
    assert rate_limit.detect_worker_count() == 1


def test_verify_guard_refuses_multiple_workers(monkeypatch, caplog):
    monkeypatch.setattr(
        rate_limit.sys, "argv", ["uvicorn", "app.main:app", "--workers", "2"]
    )
    monkeypatch.setattr(rate_limit.settings, "RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(
        rate_limit.settings, "RATE_LIMIT_ALLOW_MULTI_PROCESS_IN_PROCESS", False
    )
    with pytest.raises(RuntimeError, match="Refusing to start for 429-protection"):
        rate_limit.verify_single_worker_guarantee()


def test_verify_guard_passes_for_single_worker(monkeypatch):
    monkeypatch.setattr(rate_limit.sys, "argv", ["uvicorn", "app.main:app"])
    monkeypatch.setattr(rate_limit.settings, "RATE_LIMIT_ENABLED", True)
    # Must not raise.
    rate_limit.verify_single_worker_guarantee()


def test_verify_guard_warns_when_override_set(monkeypatch, caplog):
    monkeypatch.setattr(
        rate_limit.sys, "argv", ["uvicorn", "app.main:app", "--workers", "2"]
    )
    monkeypatch.setattr(rate_limit.settings, "RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(
        rate_limit.settings, "RATE_LIMIT_ALLOW_MULTI_PROCESS_IN_PROCESS", True
    )
    # Must NOT raise even though 2 workers are detected.
    rate_limit.verify_single_worker_guarantee()
    assert any("RATE_LIMIT:" in rec.message for rec in caplog.records)


def test_verify_guard_is_noop_when_disabled(monkeypatch):
    monkeypatch.setattr(
        rate_limit.sys, "argv", ["uvicorn", "app.main:app", "--workers", "2"]
    )
    monkeypatch.setattr(rate_limit.settings, "RATE_LIMIT_ENABLED", False)
    monkeypatch.setattr(
        rate_limit.settings, "RATE_LIMIT_ALLOW_MULTI_PROCESS_IN_PROCESS", False
    )
    rate_limit.verify_single_worker_guarantee()  # must not raise
