"""Unit tests for :mod:`app.llm_client` domain-exception contract.

Verifies that ``call_lm_studio`` raises framework-agnostic domain exceptions
(``LMStudioGatewayError`` / ``LMStudioUnavailableError`` /
``LMStudioOutputParsingError``) instead of Web-framework-specific
``fastapi.HTTPException`` objects, so the service stays decoupled from the
HTTP layer and can be consumed by route and non-route callers alike.

Run from the ``backend`` directory::

    ../venv/bin/python -m pytest tests/test_llm_client.py -v
"""
import httpx
import pytest

import app.llm_client as llm_client
from app.llm_client import (
    LMStudioError,
    LMStudioGatewayError,
    LMStudioOutputParsingError,
    LMStudioUnavailableError,
)


class _FakeResponse:
    def __init__(self, payload=None, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = str(payload)

    def raise_for_status(self):
        if self.status_code >= 400:
            request = httpx.Request("POST", "http://localhost:1234/v1/chat/completions")
            response = httpx.Response(self.status_code, text=self.text)
            raise httpx.HTTPStatusError("HTTP error", request=request, response=response)
        return None

    def json(self):
        return self._payload


class _FakeAsyncClient:
    """Emulates the subset of :class:`httpx.AsyncClient` used by ``call_lm_studio``."""

    def __init__(self, *, result=None, post_error=None, post_wants_status=False, **kwargs):
        self._result = result
        self._post_error = post_error
        self._post_wants_status = post_wants_status

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, headers=None, json=None):
        if self._post_error is not None:
            raise self._post_error
        return self._result


@pytest.mark.asyncio
async def test_call_lm_studio_success_text(monkeypatch):
    calls = []
    text = "hello from the local model"

    def _factory(**kwargs):
        calls.append(kwargs.get("timeout"))
        return _FakeAsyncClient(result=_FakeResponse(
            {"choices": [{"message": {"content": text}}]}
        ))

    monkeypatch.setattr(llm_client.httpx, "AsyncClient", _factory)
    result = await llm_client.call_lm_studio([{"role": "user", "content": "hi"}])

    assert result["text"] == text
    assert calls and calls[0] == 60.0


@pytest.mark.asyncio
async def test_call_lm_studio_raises_gateway_error(monkeypatch):
    def _factory(**kwargs):
        return _FakeAsyncClient(result=_FakeResponse(status_code=500, payload="boom"))

    monkeypatch.setattr(llm_client.httpx, "AsyncClient", _factory)
    with pytest.raises(LMStudioGatewayError):
        await llm_client.call_lm_studio([{"role": "user", "content": "hi"}])


@pytest.mark.asyncio
async def test_call_lm_studio_raises_unavailable_error(monkeypatch):
    def _factory(**kwargs):
        return _FakeAsyncClient(post_error=httpx.ConnectError("refused"))

    monkeypatch.setattr(llm_client.httpx, "AsyncClient", _factory)
    with pytest.raises(LMStudioUnavailableError):
        await llm_client.call_lm_studio([{"role": "user", "content": "hi"}])


@pytest.mark.asyncio
async def test_call_lm_studio_raises_parsing_error(monkeypatch):
    def _factory(**kwargs):
        return _FakeAsyncClient(result=_FakeResponse(
            {"choices": [{"message": {"content": "{not valid json"}}]}
        ))

    # Force the structured-output branch so the content must be parseable JSON.
    monkeypatch.setattr(llm_client.httpx, "AsyncClient", _factory)

    class _FakeSchema:
        def model_json_schema(self):
            return {"type": "object"}

    with pytest.raises(LMStudioOutputParsingError):
        await llm_client.call_lm_studio(
            [{"role": "user", "content": "hi"}],
            response_format_schema=_FakeSchema(),
        )


@pytest.mark.asyncio
async def test_call_lm_studio_never_raises_fastapi_http_exception(monkeypatch):
    """The service must stay decoupled from the HTTP/web framework."""
    from fastapi import HTTPException

    def _factory(**kwargs):
        return _FakeAsyncClient(result=_FakeResponse(status_code=500, payload="boom"))

    monkeypatch.setattr(llm_client.httpx, "AsyncClient", _factory)
    try:
        await llm_client.call_lm_studio([{"role": "user", "content": "hi"}])
    except HTTPException:  # pragma: no cover - failing case
        pytest.fail("call_lm_studio must raise domain exceptions, not fastapi.HTTPException")
    except LMStudioError:
        pass