"""
In-process sliding-window rate limiter for LLM-facing endpoints.

Security context
----------------
Finding #39 flagged that ``/api/chat`` and the workflow endpoints accept
arbitrary input with no rate limiting or token-budget enforcement, leaving the
local LLM gateway open to abuse (cost spikes, service degradation, or memory
exhaustion on the MacBook Air M4 runtime).

This module provides a lightweight, dependency-injectable sliding-window
limiter keyed by *scope + client IP*. A ``Depends`` factory lets individual
routes opt in with their own limits while keeping the throttling logic in one
place. Because the backend currently has no shared cache/Redis dependency, the
limiter is intentionally in-process (single uvicorn worker is the documented
deployment model); swap the ``SlidingWindowRateLimiter`` internals for a
distributed store (e.g. Redis) when running multiple workers.
"""

import logging
import threading
import time
from collections import defaultdict, deque
from typing import Deque, Dict

from fastapi import HTTPException, Request, status

from app.config import settings

logger = logging.getLogger("app.rate_limit")


class SlidingWindowRateLimiter:
    """Thread-safe fixed-window-with-sliding-arrival algorithm.

    Each key tracks the arrival timestamps of accepted requests inside a moving
    window. A request is allowed only if the number of accepted arrivals inside
    the current window is below ``limit``.
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


# Shared singleton used across all routes.
limiter = SlidingWindowRateLimiter()


def make_client_key(request: Request, scope: str) -> str:
    """Build a stable rate-limit key from the client IP and the route scope."""
    client_ip = request.client.host if request.client else "unknown"
    return f"{scope}:{client_ip}"


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
        if not limiter.allow(key, limit, window_seconds):
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
