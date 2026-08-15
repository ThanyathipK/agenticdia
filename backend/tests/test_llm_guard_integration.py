"""
End-to-end tests for Finding #39 guardrails over the real HTTP stack.

Verifies that LLM-facing endpoints actually apply their injected guards:
- ``POST /api/chat`` honours the sliding-window rate limit (HTTP 429)
- ``POST /api/chat`` and ``POST /api/workflow-router`` reject oversized
  payloads exceeding ``MAX_CONTEXT_TOKENS`` (HTTP 413)

The live LM Studio / database round-trips are swapped for fakes; only the
routing + dependency plumbing is exercised (which is exactly the layer this
finding was about).

Run from the ``backend`` directory::

    ../venv/bin/python -m pytest tests/test_llm_guard_integration.py -v
"""

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.rate_limit import limiter
from app.main import app

CHAT = "chat:testclient"
WORKFLOW = "workflow:testclient"


@pytest.fixture
def client(monkeypatch):
    async def _fake_lm(prompt_messages, response_format_schema=None):
        return {"text": "ok"}

    async def _fake_classify(message):
        return {"workflow": "CHAT", "confidence": 1.0, "reason": "fake"}

    import app.routes.chat as chat_route
    import app.semantic_service as semantic_service

    monkeypatch.setattr(chat_route, "call_lm_studio", _fake_lm)
    monkeypatch.setattr(semantic_service, "classify_workflow", _fake_classify)

    limiter.reset(CHAT)
    limiter.reset(WORKFLOW)

    # Note: no `with` block on purpose - lifespan (migrations/seeding) must not
    # run against the real database during unit-test HTTP round trips.
    return TestClient(app)


def test_chat_endpoint_returns_429_after_limit(client):
    body = {"messages": [{"role": "user", "content": "hello"}]}
    limit = settings.RATE_LIMIT_CHAT_LIMIT

    for _ in range(limit):
        response = client.post("/api/chat", json=body)
        assert response.status_code == 200, response.text

    response = client.post("/api/chat", json=body)
    assert response.status_code == 429
    assert "Retry-After" in response.headers


def test_chat_endpoint_rejects_oversized_history(client, monkeypatch):
    monkeypatch.setattr(settings, "MAX_CONTEXT_TOKENS", 10)
    body = {"messages": [{"role": "user", "content": "x" * 500}]}
    response = client.post("/api/chat", json=body)
    assert response.status_code == 413
    assert "context budget" in response.json()["detail"]


def test_workflow_router_endpoint_returns_429_after_limit(client):
    body = {"message": "classify me"}
    limit = settings.RATE_LIMIT_WORKFLOW_LIMIT

    for _ in range(limit):
        response = client.post("/api/workflow-router", json=body)
        assert response.status_code == 200, response.text

    response = client.post("/api/workflow-router", json=body)
    assert response.status_code == 429


def test_workflow_router_endpoint_rejects_oversized_message(client, monkeypatch):
    monkeypatch.setattr(settings, "MAX_CONTEXT_TOKENS", 10)
    response = client.post("/api/workflow-router", json={"message": "y" * 500})
    assert response.status_code == 413