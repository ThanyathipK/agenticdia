"""Unit tests for the semantic memory layer (:mod:`app.semantic_memory`).

Covers the Option A memory contracts without touching a live database or LM
Studio:

- ``embed_texts``: success (index ordering + unit normalisation) and the
  domain-exception contract (``MemoryEmbeddingUnavailableError`` for gateway
  and connectivity failures — mirroring ``test_llm_client.py``).
- Pure scoring helpers: ``cosine_similarity`` and the blended
  relevance+recency ``score_memory``.
- Fact extraction: cleaning/caps (``_clean_facts``), the LLM pass
  (``extract_facts``) and the fail-open wrapper (``extract_and_remember``).
- Dedupe on the write path (``remember_facts``) and the fail-open, ranked
  read path (``recall``) with an in-memory fake repository.
- Token-budget hygiene of ``build_memory_block``.

Run from the ``backend`` directory::

    ../venv/bin/python -m pytest tests/test_semantic_memory.py -v
"""
from datetime import datetime, timedelta, timezone

import httpx
import pytest

import app.semantic_memory as sm
from app.semantic_memory import (
    MemoryEmbeddingUnavailableError,
    SemanticMemoryError,
    build_memory_block,
    cosine_similarity,
    extract_and_remember,
    extract_facts,
    recall,
    remember_facts,
    score_memory,
    _clean_facts,
)


class _FakeResponse:
    def __init__(self, payload=None, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = str(payload)

    def raise_for_status(self):
        if self.status_code >= 400:
            request = httpx.Request("POST", "http://localhost:1234/v1/embeddings")
            response = httpx.Response(self.status_code, text=self.text)
            raise httpx.HTTPStatusError("HTTP error", request=request, response=response)
        return None

    def json(self):
        return self._payload


class _FakeAsyncClient:
    """Emulates the subset of httpx.AsyncClient used by ``embed_texts``."""

    def __init__(self, *, result=None, post_error=None, **kwargs):
        self._result = result
        self._post_error = post_error

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, headers=None, json=None):
        self.last_url = url
        self.last_json = json
        if self._post_error is not None:
            raise self._post_error
        return self._result


def _embedding_payload(vectors):
    """Build an LM Studio-shaped embeddings payload."""
    return {
        "data": [
            {"index": i, "embedding": vec} for i, vec in enumerate(vectors)
        ]
    }


# =====================================================================
# embed_texts
# =====================================================================


@pytest.mark.asyncio
async def test_embed_texts_success_orders_and_normalizes(monkeypatch):
    captured = {}

    def _factory(**kwargs):
        client = _FakeAsyncClient(result=_FakeResponse(
            _embedding_payload([[3.0, 0.0], [0.0, 4.0]])  # sent out of order via index
        ))
        captured["client"] = client
        return client

    vectors = await sm.embed_texts(["second", "first"], client_factory=_factory)

    assert vectors[0] == pytest.approx([1.0, 0.0])
    assert vectors[1] == pytest.approx([0.0, 1.0])
    assert captured["client"].last_url.endswith("/embeddings")
    assert captured["client"].last_json["model"] == sm.settings.LM_STUDIO_EMBEDDING_MODEL


@pytest.mark.asyncio
async def test_embed_texts_empty_input_short_circuits():
    assert await sm.embed_texts([]) == []


@pytest.mark.asyncio
async def test_embed_texts_rejects_blank_text():
    with pytest.raises(SemanticMemoryError):
        await sm.embed_texts(["   "])


@pytest.mark.asyncio
async def test_embed_texts_raises_gateway_error(monkeypatch):
    def _factory(**kwargs):
        return _FakeAsyncClient(result=_FakeResponse(status_code=500, payload="boom"))

    with pytest.raises(MemoryEmbeddingUnavailableError):
        await sm.embed_texts(["hi"], client_factory=_factory)


@pytest.mark.asyncio
async def test_embed_texts_raises_unavailable_error(monkeypatch):
    def _factory(**kwargs):
        return _FakeAsyncClient(post_error=httpx.ConnectError("refused"))

    with pytest.raises(MemoryEmbeddingUnavailableError):
        await sm.embed_texts(["hi"], client_factory=_factory)


# =====================================================================
# Scoring helpers
# =====================================================================


def test_cosine_similarity_pure_math():
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)
    assert cosine_similarity([1.0, 0.0], [-1.0, 0.0]) == pytest.approx(-1.0)


def test_cosine_similarity_handles_mismatch_and_zero_vectors():
    assert cosine_similarity([1.0], [1.0, 2.0]) == 0.0
    assert cosine_similarity([], [1.0]) == 0.0
    assert cosine_similarity([0.0, 0.0], [1.0, 0.0]) == 0.0


def test_score_memory_blends_relevance_and_recency():
    now = datetime.now(timezone.utc)
    fresh = {"embedding": [1.0, 0.0], "created_at": now.isoformat()}
    old = {
        "embedding": [1.0, 0.0],
        "created_at": (now - timedelta(days=90)).isoformat(),  # ~3 half-lives
    }
    fresh_score = score_memory([1.0, 0.0], fresh, now=now)
    old_score = score_memory([1.0, 0.0], old, now=now)
    # Fresh memory: relevance 1.0 + recency 1.0 -> max score. Old memory:
    # expected = 0.7 * 1.0 + 0.3 * (0.5 ** 3) ≈ 0.7375.
    assert fresh_score == pytest.approx(1.0)
    assert old_score == pytest.approx(0.7 + 0.3 * (0.5 ** 3), rel=1e-3)
    assert old_score < fresh_score


# =====================================================================
# Fact extraction
# =====================================================================


def test_clean_facts_normalizes_dedupes_and_caps():
    raw = [
        "The  project   requires SSO.",
        "the project requires sso.",  # case-insensitive duplicate
        42,                            # non-string ignored
        "",                            # empty ignored
        "x" * 301,                     # over-length ignored
        "Valid fact.",
    ]
    facts = _clean_facts(raw)
    assert facts == ["The project requires SSO.", "Valid fact."]


def test_clean_facts_caps_at_max_facts_per_turn(monkeypatch):
    monkeypatch.setattr(sm.settings, "MEMORY_MAX_FACTS_PER_TURN", 2)
    facts = _clean_facts(["a", "b", "c", "d"])
    assert facts == ["a", "b"]


@pytest.mark.asyncio
async def test_extract_facts_parses_llm_payload(monkeypatch):
    async def _fake_call(messages, response_format_schema=None, max_tokens=300):
        return {"facts": ["User prefers OAuth2 over SAML.", "  "]}

    monkeypatch.setattr(sm, "call_lm_studio", _fake_call)
    facts = await extract_facts("u", "a")
    assert facts == ["User prefers OAuth2 over SAML."]


@pytest.mark.asyncio
async def test_extract_and_remember_is_fail_open(monkeypatch):
    async def _boom(*args, **kwargs):
        raise MemoryEmbeddingUnavailableError("LM Studio offline")

    monkeypatch.setattr(sm, "extract_facts", _boom)
    assert await extract_and_remember("p1", "u", "a") == 0


@pytest.mark.asyncio
async def test_extract_and_remember_returns_count(monkeypatch):
    async def _facts(*args, **kwargs):
        return ["Fact one.", "Fact two."]

    async def _remember(project_id, facts, source_message_id=None, session=None):
        return [{"content": f} for f in facts]

    monkeypatch.setattr(sm, "extract_facts", _facts)
    monkeypatch.setattr(sm, "remember_facts", _remember)
    assert await extract_and_remember("p1", "u", "a") == 2


# =====================================================================
# Write path: remember_facts (dedupe)
# =====================================================================


class _FakeRepo:
    """In-memory stand-in for SemanticMemoryRepository."""

    def __init__(self, existing=None):
        self.existing = list(existing or [])
        self.saved = []
        self.recalled = []

    async def get_recent(self, project_id, limit=400, session=None):
        return list(self.existing)

    async def save_memory(self, project_id, content, embedding, embedding_model="",
                          kind="semantic", source_message_id=None, session=None):
        record = {
            "id": f"m{len(self.saved)}", "project_id": project_id,
            "kind": kind, "content": content, "embedding": list(embedding),
            "embedding_model": embedding_model,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "source_message_id": source_message_id,
        }
        self.saved.append(record)
        return record

    async def mark_recalled(self, memory_ids, session=None):
        self.recalled = list(memory_ids)


@pytest.mark.asyncio
async def test_remember_facts_dedupes_against_existing(monkeypatch):
    repo = _FakeRepo(existing=[
        {"embedding": [1.0, 0.0], "content": "Project requires SSO.",
         "created_at": datetime.now(timezone.utc).isoformat(), "id": "old"},
    ])
    monkeypatch.setattr(sm, "SemanticMemoryRepository", repo)

    async def _fake_embed(texts):
        # "Project requires SSO." ~ duplicate; "Uses Postgres" ~ orthogonal.
        return [[1.0, 0.0], [0.0, 1.0]]

    monkeypatch.setattr(sm, "embed_texts", _fake_embed)
    saved = await remember_facts("p1", ["Project requires SSO.", "Uses Postgres"])

    assert [m["content"] for m in saved] == ["Uses Postgres"]
    assert len(repo.saved) == 1


@pytest.mark.asyncio
async def test_remember_facts_empty_facts_is_noop(monkeypatch):
    repo = _FakeRepo()
    monkeypatch.setattr(sm, "SemanticMemoryRepository", repo)
    assert await remember_facts("p1", []) == []
    assert await remember_facts("p1", ["   "]) == []
    assert repo.saved == []


# =====================================================================
# Read path: recall + build_memory_block
# =====================================================================


@pytest.mark.asyncio
async def test_recall_ranks_and_marks_recalled(monkeypatch):
    now = datetime.now(timezone.utc)
    repo = _FakeRepo(existing=[
        {"id": "relevant", "content": "Project requires SSO.",
         "embedding": [1.0, 0.0], "created_at": now.isoformat()},
        {"id": "irrelevant", "content": "Uses Postgres.",
         "embedding": [0.0, 1.0], "created_at": now.isoformat()},
    ])
    monkeypatch.setattr(sm, "SemanticMemoryRepository", repo)

    async def _fake_embed(texts):
        return [[1.0, 0.0]]

    monkeypatch.setattr(sm, "embed_texts", _fake_embed)
    memories = await recall("p1", "Do we need single sign-on?")

    assert [m["id"] for m in memories] == ["relevant"]
    assert memories[0]["score"] > 0
    assert repo.recalled == ["relevant"]


@pytest.mark.asyncio
async def test_recall_fail_open_on_embedding_failure(monkeypatch):
    repo = _FakeRepo(existing=[{"id": "m", "content": "x", "embedding": [1.0],
                                "created_at": datetime.now(timezone.utc).isoformat()}])
    monkeypatch.setattr(sm, "SemanticMemoryRepository", repo)

    async def _boom(texts, client_factory=None):
        raise MemoryEmbeddingUnavailableError("offline")

    monkeypatch.setattr(sm, "embed_texts", _boom)
    assert await recall("p1", "anything") == []


@pytest.mark.asyncio
async def test_recall_empty_query_short_circuits(monkeypatch):
    assert await recall("p1", "   ") == []


def test_build_memory_block_caps_tokens(monkeypatch):
    monkeypatch.setattr(sm.settings, "MEMORY_CONTEXT_MAX_TOKENS", 30)
    memories = [
        {"content": f"Fact number {i} with a bit of padding text."} for i in range(20)
    ]
    block = build_memory_block(memories)
    assert block.startswith("Relevant project memory")
    assert sm.count_tokens(block) <= 30


def test_build_memory_block_empty():
    assert build_memory_block([]) == ""
    assert build_memory_block([{"content": ""}]) == ""
