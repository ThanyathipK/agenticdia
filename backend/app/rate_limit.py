"""Sliding-window rate limiter for LLM-facing endpoints, with fail-loud guards.

Security context
----------------
Finding #39 flagged that ``/api/chat`` and the workflow endpoints accept
arbitrary input with no rate limiting or token-budget enforcement, leaving the
local LLM gateway open to abuse (cost inflation, service degradation, or memory
exhaustion on the MacBook Air M4 runtime).

Design
------
A lightweight, dependency-injectable sliding-window limiter keyed by *scope +
client IP*. A ``Depends`` factory lets individual routes opt in with their own
limits while keeping the throttling logic in one place.

The shipped store is **in-process** (a RAM ``defaultdict`` guarded by a
``threading.Lock``). That is only safe for exactly one uvicorn process. If the
app were started with multiple workers (``--workers N``) while still using an
in-process store, each OS process would keep an independent counter and the
effective 429 budget would silently scale by the worker count — i.e. protection
quietly disappears.

To make that failure impossible to miss, this module exposes
:func:`verify_single_worker_guarantee`, which the application invokes at
startup. It **refuses to boot** (or, with an explicit operator opt-in, emits a
loud warning) whenever an in-process store is combined with more than one
worker process. A pluggable :class:`RateLimitStore` interface is provided so a
distributed backend (Redis / SQLite) can be dropped in later and relax that
constraint the correct way (shared counters) rather than swallowing it.

Key resolution is also proxy-aware: the client IP is taken from the immediate
socket peer unless that peer is a configured *trusted* proxy, in which case the
``X-Forwarded-For``/``Forwarded for`` chain is walked from the right (nearest
hop) skipping trusted addresses until an untrusted one is found. This prevents
a reverse proxy / load-balancer deployment from collapsing every caller into
one bucket, and stops a client from widening its own bucket by spoofing headers.
"""

import logging
import sys
import threading
import time
from collections import defaultdict, deque
from typing import Deque, Dict, List, Optional, Protocol

from fastapi import HTTPException, Request, status

from app.config import settings

logger = logging.getLogger("app.rate_limit")

#: Normalised store modes that the factory knows how to instantiate today.
_SUPPORTED_STORE_MODES = {"in_process", "memory"}


class RateLimitStore(Protocol):
    """Minimal contract a distributed limiter backend must satisfy.

    Both the in-process implementation and any future shared store (Redis /
    SQLite) implement this so route code never depends on *how* a limit is
    enforced, only that it is.
    """

    def allow(self, key: str, limit: int, window_seconds: int) -> bool:
        """Return True if a request for ``key`` may proceed, else record it."""
        ...

    def current_count(self, key: str, window_seconds: int = 60) -> int:
        """Return the number of recorded arrivals inside the window."""
        ...

    def reset(self, key: str) -> None:
        """Clear recorded arrivals for ``key`` (used by tests/operators)."""
        ...


class SlidingWindowRateLimiter:
    """Thread-safe fixed-window-with-sliding-arrival algorithm (in-process).

    Each key tracks the arrival timestamps of accepted requests inside a moving
    window. A request is allowed only if the number of accepted arrivals inside
    the current window is below ``limit``. Suitable for exactly one OS process;
    the startup guard enforces that constraint when this store is selected.
    """

    def __init__(self) -> None:
        self._hits: Dict[str, Deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str, limit: int, window_seconds: int) -> bool:
        """Return True if a request for ``key`` may proceed, else record it.

        When True is returned, the request is recorded so it counts toward the
        window. When the caller aborts early we still count it (a safe,
        conservative choice for abuse protection).
        """
        current_time = time.monotonic()
        with self._lock:
            timestamps = self._hits[key]
            cutoff = current_time - window_seconds
            # Drop arrivals that have fallen out of the window.
            while timestamps and timestamps[0] <= cutoff:
                timestamps.popleft()
            if len(timestamps) >= limit:
                return False
            timestamps.append(current_time)
            return True

    def current_count(self, key: str, window_seconds: int = 60) -> int:
        """Return the number of recorded arrivals for ``key`` in the window."""
        current_time = time.monotonic()
        cutoff = current_time - window_seconds
        with self._lock:
            timestamps = self._hits[key]
            while timestamps and timestamps[0] <= cutoff:
                timestamps.popleft()
            return len(timestamps)

    def reset(self, key: str) -> None:
        """Clear recorded arrivals for ``key`` (used by tests)."""
        with self._lock:
            self._hits.pop(key, None)


# Shared singleton used across all routes (backed by an in-process store).
limiter = SlidingWindowRateLimiter()


# ==========================================================
# Client-IP resolution (proxy-aware, safe by default)
# ==========================================================
def _is_trusted_proxy(peer: str) -> bool:
    """True when header-borne client IPs may be trusted from ``peer``."""
    if not settings.TRUST_PROXY_HEADERS:
        return False
    return peer in settings.trusted_proxy_ip_list


def _forwarded_for_header(value: str) -> Optional[str]:
    """Extract the ``for`` token from an RFC 7239 ``Forwarded`` header."""
    for part in value.split(";"):
        part = part.strip()
        if part.lower().startswith("for="):
            token = part.split("=", 1)[1].strip().strip('"')
            return token or None
    return None


def _resolve_client_ip(request: Request) -> str:
    """Return the real client IP, honoring proxy headers only from a trusted hop.

    When the immediate socket peer is a configured trusted proxy, the chain is
    walked from the right (nearest hop) skipping trusted addresses until an
    untrusted one is found — the true client. Spoofable left-hand entries are
    ignored. Otherwise the raw socket peer is returned so a spoofed header can
    never widen a bucket.
    """
    peer = request.client.host if request.client else "unknown"
    if not _is_trusted_proxy(peer):
        return peer

    xff = request.headers.get("x-forwarded-for")
    chain: List[str] = [e.strip() for e in xff.split(",") if e.strip()] if xff else []
    if not chain:
        forwarded = request.headers.get("forwarded")
        if forwarded:
            token = _forwarded_for_header(forwarded)
            if token:
                chain = [token]
    # Walk the chain from the right (most trustworthy: each proxy appends the
    # hop it received the request from, so the rightmost part was written last
    # by the trusted peer's nearest hop). Skip addresses that are also trusted
    # proxies; the first untrusted address is the real client. Spoofed left-hand
    # entries are never reached. If everything is trusted (or the chain is
    # empty), fall back to the peer.
    for entry in reversed(chain):
        if entry not in settings.trusted_proxy_ip_list:
            return entry
    return peer


def make_client_key(request: Request, scope: str) -> str:
    """Build a stable rate-limit key from the client IP and the route scope.

    Honors proxy headers only when the immediate socket peer is a configured
    trusted proxy (``TRUST_PROXY_HEADERS`` / ``TRUSTED_PROXY_IPS``); otherwise
    the raw peer is used.
    """
    client_ip = _resolve_client_ip(request)
    return f"{scope}:{client_ip}"


# ==========================================================================
# Store factory + deployment guardrail
# ==========================================================================
def _store_mode() -> str:
    """Normalise ``RATE_LIMIT_STORE`` or raise on an unsupported value.

    Raising (rather than silently falling back to the in-process store) is
    deliberate: an unimplemented distributed store must never quietly degrade
    to process-local behaviour and recreate the exact bug this module guards
    against.
    """
    raw = (settings.RATE_LIMIT_STORE or "").strip().lower().replace("-", "_")
    if not raw:
        return "in_process"
    if raw in _SUPPORTED_STORE_MODES:
        return raw
    raise ValueError(
        f"Unsupported RATE_LIMIT_STORE={settings.RATE_LIMIT_STORE!r}. Only "
        "'in-process' is implemented today. Add a distributed store backend "
        "before selecting another value; the app refuses to start rather than "
        "silently degrade to a weaker in-process limiter."
    )


def get_rate_limit_store() -> RateLimitStore:
    """Return the configured rate-limit backend.

    Today this always returns the in-process singleton. The indirection exists
    so a distributed store can be added later without touching every route, and
    so the startup guard can reason about the store type. Raises for an
    unsupported ``RATE_LIMIT_STORE`` value.
    """
    _store_mode()  # validate; raises on unimplemented modes.
    return limiter


def detect_worker_count() -> int:
    """Best-effort uvicorn worker count, sourced from the live process argv.

    Returns the larger of 1 and the ``--workers`` / ``-w`` value. Detection is
    best-effort: when the argv cannot determine it, it returns 1 (the safe
    single-worker default). If a multi-worker deployment is genuinely intended,
    a distributed store must be configured (or the operator must explicitly
    opt into the reduced in-process posture).
    """
    args = sys.argv[1:]
    for idx, arg in enumerate(args):
        if arg in ("--workers", "-w") and idx + 1 < len(args):
            try:
                return max(1, int(args[idx + 1]))
            except ValueError:
                continue
        if arg.startswith("--workers="):
            try:
                return max(1, int(arg.split("=", 1)[1]))
            except ValueError:
                continue
    return 1


def verify_single_worker_guarantee() -> None:
    """Fail loud instead of silently weakening 429 protection across processes.

    Call once at application startup. An in-process limiter is correct only for
    a single OS process; if more workers are detected the app refuses to boot
    unless the operator has explicitly set
    ``RATE_LIMIT_ALLOW_MULTI_PROCESS_IN_PROCESS=true`` (which still logs a loud
    warning). A (future) distributed store relaxes this because its counters
    are genuinely shared.
    """
    if not settings.RATE_LIMIT_ENABLED:
        return
    try:
        mode = _store_mode()
    except ValueError:
        raise  # reuse the loud message from the factory for unknown stores.
    if mode != "in_process":
        return  # a shared store is multi-process-safe by construction.
    workers = detect_worker_count()
    if workers <= 1:
        return

    message = (
        f"backend started with {workers} uvicorn worker process(es) while "
        "RATE_LIMIT_STORE='in_process' (process-local). Each worker keeps an "
        "independent counter, so the 429 budget silently scales up by the worker "
        f"count ({workers}x) and inbound abuse protection is weaker than intended. "
        "Run a single uvicorn worker (the default), or set "
        "RATE_LIMIT_ALLOW_MULTI_PROCESS_IN_PROCESS=true to explicitly accept "
        "this reduced posture (not recommended), or add a distributed store."
    )
    if settings.RATE_LIMIT_ALLOW_MULTI_PROCESS_IN_PROCESS:
        logger.warning("RATE_LIMIT: %s", message)
        return
    logger.error("RATE_LIMIT: %s", message)
    raise RuntimeError("Refusing to start for 429-protection safety. " + message)


# ==========================================================================
# FastAPI dependency
# ==========================================================================
def rate_limit_dependency(scope: str, limit: int, window_seconds: int):
    """Return a FastAPI dependency enforcing ``limit`` per window per client.

    Usage::

        @router.post("/api/chat", ...)
        async def post_chat_query(
            request: ChatSessionRequest,
            _rate: None = Depends(rate_limit_dependency("chat", 30, 60)),
        ) -> ChatResponse: ...

    Raises ``HTTPException`` 429 when the limit is exceeded. The dependency is
    a no-op when rate limiting is disabled via ``RATE_LIMIT_ENABLED``.
    """

    async def dependency(request: Request) -> None:
        if not settings.RATE_LIMIT_ENABLED:
            return
        key = make_client_key(request, scope)
        store = get_rate_limit_store()
        if not store.allow(key, limit, window_seconds):
            logger.warning(
                "Rate limit exceeded for scope=%s key=%s (limit=%s per %ss)",
                scope,
                key,
                limit,
                window_seconds,
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f"Rate limit exceeded for {scope}. Please retry after "
                    f"{window_seconds} second(s)."
                ),
                headers={"Retry-After": str(window_seconds)},
            )

    return dependency