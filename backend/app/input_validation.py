"""
Token-budget / input-size validation for LLM-facing endpoints.

Security context
----------------
Finding #39: ``/api/chat`` and the workflow endpoints accept arbitrary input
with no token-budget enforcement. This module enforces ``MAX_CONTEXT_TOKENS``
on incoming request payloads so a single oversized request cannot exceed the
local LLM's context window (config default 8192 tokens on the MacBook Air M4).

Token counting uses ``tiktoken`` (OpenAI's BPE tokenizer, already available in
this backend) with a transparent ``chars / 4`` heuristic fallback so the
validation never hard-crashes when the tokenizer library is unavailable.

Every enforcement helper raises an ``HTTPException`` (413) with a clear detail
message and the measured token count so callers can surface it to users.
"""

import json
import logging
from typing import Any, List

import tiktoken
from fastapi import HTTPException, status

from app.config import settings

logger = logging.getLogger("app.input_validation")

# Lazily initialized BPE encoder. ``_encoder`` is None until first resolved;
# ``_encoder_unavailable`` is set once tiktoken proves unavailable so we do not
# retry the (potentially expensive) import on every request.
_encoder = None
_encoder_unavailable = False


def _get_encoder():
    """Return a lazily-initialised tiktoken encoder (or None if unavailable)."""
    global _encoder, _encoder_unavailable
    if _encoder is None and not _encoder_unavailable:
        try:
            _encoder = tiktoken.get_encoding("cl100k_base")
        except Exception as exc:  # pragma: no cover - tiktoken is installed here
            logger.warning(
                "tiktoken unavailable (%s); falling back to chars/4 heuristic.",
                exc,
            )
            _encoder_unavailable = True
            return None
    return _encoder


def count_tokens(text: str) -> int:
    """Estimate the token count of ``text``.

    Prefers tiktoken; falls back to a ``chars / 4`` heuristic (a widely used
    approximation for English text) when the tokenizer is unavailable. Returns
    at least 1 for any non-empty string so zero-length inputs are not treated
    as causing overflow.
    """
    if not text:
        return 0
    encoder = _get_encoder()
    if encoder is not None:
        try:
            return len(encoder.encode(text))
        except Exception:  # pragma: no cover - defensive
            logger.warning("tiktoken encode failed; using heuristic.")
    return max(1, len(text) // 4)


def count_body_tokens(payload: Any) -> int:
    """Count tokens across a whole payload (dict/list/model) by JSON-encoding it."""
    if payload is None:
        return 0
    try:
        encoded = json.dumps(payload, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        encoded = str(payload)
    return count_tokens(encoded)


def validate_text_budget(text: str, label: str = "input") -> int:
    """Raise HTTP 413 if ``text`` exceeds ``MAX_CONTEXT_TOKENS``; else return count."""
    token_count = count_tokens(text)
    if token_count > settings.MAX_CONTEXT_TOKENS:
        logger.warning(
            "%s rejected: %s tokens exceeds budget of %s tokens",
            label,
            token_count,
            settings.MAX_CONTEXT_TOKENS,
        )
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=(
                f"{label} is too large: ~{token_count} tokens exceeds the "
                f"configured context budget of {settings.MAX_CONTEXT_TOKENS} tokens."
            ),
        )
    return token_count


def validate_body_budget(payload: Any, label: str = "request") -> int:
    """Raise HTTP 413 if the whole ``payload`` exceeds ``MAX_CONTEXT_TOKENS``."""
    total = count_body_tokens(payload)
    if total > settings.MAX_CONTEXT_TOKENS:
        logger.warning(
            "%s body rejected: %s tokens exceeds budget of %s tokens",
            label,
            total,
            settings.MAX_CONTEXT_TOKENS,
        )
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=(
                f"{label} is too large: ~{total} tokens exceeds the configured "
                f"context budget of {settings.MAX_CONTEXT_TOKENS} tokens."
            ),
        )
    return total


def validate_messages_budget(messages: List[Any]) -> int:
    """Raise HTTP 413 if the combined chat messages exceed the context budget."""
    total = sum(count_tokens(getattr(m, "content", "") or "") for m in messages)
    if total > settings.MAX_CONTEXT_TOKENS:
        logger.warning(
            "Chat message history rejected: %s tokens exceeds budget of %s tokens",
            total,
            settings.MAX_CONTEXT_TOKENS,
        )
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=(
                f"Conversation is too large: ~{total} tokens exceeds the "
                f"configured context budget of {settings.MAX_CONTEXT_TOKENS} tokens."
            ),
        )
    return total
