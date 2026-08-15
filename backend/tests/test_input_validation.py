"""
Unit tests for :mod:`app.input_validation`.

Exercises the token-budget enforcement that backs Finding #39 (guard
LLM-facing endpoints against oversized payloads):

- ``count_tokens`` (tiktoken with chars/4 heuristic fallback)
- ``validate_text_budget``
- ``validate_messages_budget``
- ``validate_body_budget``

Run from the ``backend`` directory::

    ../venv/bin/python -m pytest tests/test_input_validation.py -v
"""

import pytest
from types import SimpleNamespace

from fastapi import HTTPException

from app.config import settings
from app.input_validation import (
    count_tokens,
    validate_body_budget,
    validate_messages_budget,
    validate_text_budget,
)


class TestCountTokens:
    def test_empty_returns_zero(self):
        assert count_tokens("") == 0
        assert count_tokens(None) == 0

    def test_non_empty_returns_positive(self):
        assert count_tokens("hello world, this is a moderately long sentence that should be more than just a couple of tokens" * 10) > 0

    def test_short_text_returns_at_least_one(self):
        assert count_tokens("a") >= 1


class TestValidateTextBudget:
    def test_small_text_passes(self, monkeypatch):
        monkeypatch.setattr(settings, "MAX_CONTEXT_TOKENS", 1000)
        result = validate_text_budget("hi there")
        assert isinstance(result, int)
        assert result >= 0

    def test_large_text_raises_413(self, monkeypatch):
        monkeypatch.setattr(settings, "MAX_CONTEXT_TOKENS", 10)
        with pytest.raises(HTTPException) as exc:
            validate_text_budget("x" * 500, label="input")
        assert exc.value.status_code == 413
        assert "input" in exc.value.detail


class TestValidateMessagesBudget:
    def test_combined_history_passes(self, monkeypatch):
        monkeypatch.setattr(settings, "MAX_CONTEXT_TOKENS", 1000)
        messages = [
            SimpleNamespace(content="Hello"),
            SimpleNamespace(content="I need a new requirement for transfers"),
        ]
        result = validate_messages_budget(messages)
        assert result >= 0

    def test_combined_history_raises_413(self, monkeypatch):
        monkeypatch.setattr(settings, "MAX_CONTEXT_TOKENS", 10)
        messages = [SimpleNamespace(content="z" * 400), SimpleNamespace(content="y" * 400)]
        with pytest.raises(HTTPException) as exc:
            validate_messages_budget(messages)
        assert exc.value.status_code == 413

    def test_empty_history_passes(self, monkeypatch):
        monkeypatch.setattr(settings, "MAX_CONTEXT_TOKENS", 10)
        assert validate_messages_budget([]) == 0


class TestValidateBodyBudget:
    def test_small_body_passes(self, monkeypatch):
        monkeypatch.setattr(settings, "MAX_CONTEXT_TOKENS", 1000)
        assert isinstance(validate_body_budget({"project_id": "abc", "raw_input": "hi"}), int)

    def test_large_body_raises_413(self, monkeypatch):
        monkeypatch.setattr(settings, "MAX_CONTEXT_TOKENS", 10)
        with pytest.raises(HTTPException) as exc:
            validate_body_budget({"data": "q" * 500}, label="Process-requirements request")
        assert exc.value.status_code == 413
        assert "Process-requirements request" in exc.value.detail
