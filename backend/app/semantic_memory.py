"""
Semantic memory service (Option A memory layer).

Improves AI understanding of a project across sessions by:

1. **Semantic memory** — a small LLM pass distils DURABLE facts/decisions
   from each chat turn ("project requires SSO", "user rejected option B"),
   embeds them with the local LM Studio embedding model and stores them in
   ``semantic_memories`` (via :class:`SemanticMemoryRepository`).
2. **Recall at prompt-build time** — the current user message is embedded,
   scored against recent memories (blended cosine relevance + recency decay)
   and the top-k results are injected as a hard-capped "Relevant project
   memory" block into the system prompt.

Design rules (mirroring the guardrails introduced by Findings #39/#40):

* **Fail-open**: every entrypoint catches its own failures and degrades to
  the pre-memory behaviour (empty recall / no stored facts) instead of
  breaking the chat turn. Memory must never take chat down.
* **Token-budget hygiene**: the injected block is capped at
  ``MEMORY_CONTEXT_MAX_TOKENS`` via :func:`app.input_validation.count_tokens`
  so recall cannot silently blow the 8192-token context window.
* **Local-only**: embeddings and fact extraction both go through LM Studio —
  no data leaves the machine, consistent with the rest of the backend.
"""
import json
import logging
import math
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from pydantic import BaseModel, Field

from app.config import settings
from app.input_validation import count_tokens
from app.llm_client import call_lm_studio
from app.repositories import SemanticMemoryRepository

logger = logging.getLogger("app.semantic_memory")


class SemanticMemoryError(Exception):
    """Base class for semantic-memory failures (service/domain layer)."""


class MemoryEmbeddingUnavailableError(SemanticMemoryError):
    """LM Studio could not produce embeddings (offline / gateway error)."""


# ==========================================
# EMBEDDING CLIENT (LM Studio /v1/embeddings)
# ==========================================


async def embed_texts(
    texts: List[str],
    client_factory: Optional[type] = None,
) -> List[List[float]]:
    """
    Embed ``texts`` via LM Studio's OpenAI-compatible embeddings endpoint.

    Vectors are unit-normalised so cosine similarity is stable across models
    and the relevance/recency blend behaves predictably.

    Args:
        texts: Non-empty strings to embed (empty strings are rejected).
        client_factory: DI seam for tests (defaults to httpx.AsyncClient).

    Returns:
        List of unit-normalised float vectors, one per input text.

    Raises:
        MemoryEmbeddingUnavailableError: LM Studio is unreachable, returned a
            non-2xx status, or a malformed payload.
        SemanticMemoryError: an input text is empty.
    """
    if not texts:
        return []

    cleaned = [t.strip() if isinstance(t, str) else "" for t in texts]
    if any(not c for c in cleaned):
        raise SemanticMemoryError("embed_texts received an empty text.")

    headers = {
        "Authorization": f"Bearer {settings.LM_STUDIO_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": settings.LM_STUDIO_EMBEDDING_MODEL,
        "input": cleaned,
    }
    url = f"{settings.LM_STUDIO_URL.rstrip('/')}/embeddings"
    factory = client_factory or httpx.AsyncClient

    try:
        async with factory(timeout=settings.MEMORY_EMBEDDING_TIMEOUT_SECONDS) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPStatusError as http_err:
        logger.warning(
            "Embedding gateway error (HTTP %s) — memory write/recall degraded.",
            http_err.response.status_code,
        )
        raise MemoryEmbeddingUnavailableError(
            f"Embedding gateway error: {http_err.response.status_code}"
        ) from http_err
    except httpx.RequestError as req_err:
        logger.warning("LM Studio embeddings unreachable (%s) — memory degraded.", req_err)
        raise MemoryEmbeddingUnavailableError(
            "LM Studio embeddings endpoint is offline or unreachable."
        ) from req_err
    except json.JSONDecodeError as json_err:
        raise MemoryEmbeddingUnavailableError(
            f"Malformed embedding payload: {json_err}"
        ) from json_err

    try:
        items = sorted(data["data"], key=lambda item: item["index"])
        vectors = [list(map(float, item["embedding"])) for item in items]
    except (KeyError, TypeError, ValueError) as shape_err:
        raise MemoryEmbeddingUnavailableError(
            f"Malformed embedding payload: {shape_err}"
        ) from shape_err

    if len(vectors) != len(cleaned):
        raise MemoryEmbeddingUnavailableError(
            f"Embedding count mismatch: sent {len(cleaned)}, got {len(vectors)}."
        )

    return [_normalize(vec) for vec in vectors]


def _normalize(vec: List[float]) -> List[float]:
    """Return ``vec`` scaled to unit length (zero vector passes through)."""
    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0.0:
        return list(vec)
    return [v / norm for v in vec]


def cosine_similarity(a: List[float], b: List[float]) -> float:
    """
    Cosine similarity between two vectors (pure function).

    Returns 0.0 for zero vectors or a length mismatch (e.g. an embedding-model
    change mid-project) so the blend degrades to pure recency rather than
    producing a bogus score.
    """
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


# ==========================================
# FACT EXTRACTION (LLM pass per chat turn)
# ==========================================


class ExtractedFacts(BaseModel):
    """Structured output schema for the per-turn fact extraction pass."""

    facts: List[str] = Field(
        default_factory=list,
        description="Durable project facts/decisions worth remembering. Empty list if none.",
    )


_FACT_EXTRACTION_SYSTEM_PROMPT = (
    "You extract durable project knowledge from a requirements-analysis chat turn. "
    "Return ONLY facts that a business analyst would need in FUTURE conversations "
    "(decisions, constraints, preferences, domain rules, rejected options). "
    "Never include transient small talk, question phrasing, or anything already "
    "implied by the requirements documents. Each fact: one short declarative "
    "sentence (max 200 chars). Return {\"facts\": []} when nothing qualifies."
)


def _clean_facts(raw: Any) -> List[str]:
    """Normalise the parsed extraction payload into clean, bounded fact strings."""
    if not isinstance(raw, list):
        return []
    facts: List[str] = []
    seen_normalized = set()
    for item in raw:
        if not isinstance(item, str):
            continue
        fact = re.sub(r"\s+", " ", item).strip()
        if not fact or len(fact) > 300:
            continue
        key = fact.lower()
        if key in seen_normalized:
            continue
        seen_normalized.add(key)
        facts.append(fact)
        if len(facts) >= settings.MEMORY_MAX_FACTS_PER_TURN:
            break
    return facts


async def extract_facts(
    user_message: str,
    assistant_reply: str,
    max_tokens: int = 300,
) -> List[str]:
    """
    Distil durable facts from one chat turn via the local LLM.

    Raises whatever :func:`call_lm_studio` raises; the public
    :func:`extract_and_remember` wrapper treats every failure as fail-open.
    """
    prompt = (
        f"USER MESSAGE:\n{user_message[:4000]}\n\n"
        f"ASSISTANT REPLY:\n{assistant_reply[:4000]}\n\n"
        "Extract the durable project facts/decisions as JSON per the schema."
    )
    parsed = await call_lm_studio(
        [
            {"role": "system", "content": _FACT_EXTRACTION_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        response_format_schema=ExtractedFacts,
        max_tokens=max_tokens,
    )
    raw_facts = parsed.get("facts") if isinstance(parsed, dict) else None
    return _clean_facts(raw_facts)



# ==========================================
# REMEMBER (write path)
# ==========================================


async def remember_facts(
    project_id: str,
    facts: List[str],
    source_message_id: Optional[str] = None,
    kind: str = "semantic",
    session: Optional[Any] = None,
) -> List[Dict[str, Any]]:
    """
    Embed and persist ``facts`` for a project, skipping near-duplicates.

    A fact is skipped when its cosine similarity against ANY existing memory
    of the project is >= ``MEMORY_DEDUPE_SIMILARITY`` (same meaning, reworded)
    — keeps memory from bloating across sessions. Dedupe also applies within
    the same batch.

    Raises:
        MemoryEmbeddingUnavailableError: embeddings could not be produced
            (the caller's fail-open wrapper handles it).
        ValueError: a fact is empty after stripping.
    """
    facts = _clean_facts(facts)
    if not facts:
        return []

    vectors = await embed_texts(facts)
    existing = await SemanticMemoryRepository.get_recent(
        project_id, limit=settings.MEMORY_CANDIDATE_LIMIT, session=session
    )
    existing_vectors = [m.get("embedding") or [] for m in existing]

    saved: List[Dict[str, Any]] = []
    for fact, vec in zip(facts, vectors):
        is_duplicate = any(
            cosine_similarity(vec, ev) >= settings.MEMORY_DEDUPE_SIMILARITY
            for ev in existing_vectors
            if ev
        )
        if is_duplicate:
            logger.info("Semantic memory skipped (duplicate): %s", fact[:80])
            continue
        saved.append(
            await SemanticMemoryRepository.save_memory(
                project_id=project_id,
                content=fact,
                embedding=vec,
                embedding_model=settings.LM_STUDIO_EMBEDDING_MODEL,
                kind=kind,
                source_message_id=source_message_id,
                session=session,
            )
        )
        existing_vectors.append(vec)  # dedupe within the same batch too
    if saved:
        logger.info(
            "Semantic memory: stored %d new fact(s) for project %s.", len(saved), project_id
        )
    return saved


async def extract_and_remember(
    project_id: str,
    user_message: str,
    assistant_reply: str,
    source_message_id: Optional[str] = None,
) -> int:
    """
    Full fail-open write path: extract facts from a finished chat turn and
    store them. Returns the number of NEW facts stored (0 on any failure —
    failures are logged, never raised).
    """
    if not settings.MEMORY_ENABLED or not settings.MEMORY_FACT_EXTRACTION_ENABLED:
        return 0
    try:
        facts = await extract_facts(user_message, assistant_reply)
        if not facts:
            return 0
        saved = await remember_facts(project_id, facts, source_message_id=source_message_id)
        return len(saved)
    except SemanticMemoryError as err:
        logger.warning("Semantic memory write degraded (%s).", err)
        return 0
    except Exception as err:  # never break the chat turn on memory failures
        logger.warning("Semantic memory write failed unexpectedly (%s).", err, exc_info=True)
        return 0



# ==========================================
# RECALL (read path)
# ==========================================


def _recency_factor(created_at_iso: str, now: Optional[datetime] = None) -> float:
    """Exponential recency decay: 1.0 now -> 0.5 after one half-life."""
    try:
        created = datetime.fromisoformat(created_at_iso)
    except (TypeError, ValueError):
        return 0.0
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    now = now or datetime.now(timezone.utc)
    age_days = max(0.0, (now - created).total_seconds() / 86400.0)
    return 0.5 ** (age_days / max(settings.MEMORY_RECENCY_HALF_LIFE_DAYS, 0.001))


def score_memory(
    query_vector: List[float],
    memory: Dict[str, Any],
    now: Optional[datetime] = None,
) -> float:
    """
    Blended relevance+recency score for one candidate memory (pure function).

    score = MEMORY_RELEVANCE_WEIGHT * cosine(query, memory)
          + (1 - MEMORY_RELEVANCE_WEIGHT) * recency_factor
    """
    relevance = cosine_similarity(query_vector, memory.get("embedding") or [])
    recency = _recency_factor(memory.get("created_at") or "", now=now)
    return (
        settings.MEMORY_RELEVANCE_WEIGHT * relevance
        + (1.0 - settings.MEMORY_RELEVANCE_WEIGHT) * recency
    )


async def recall(
    project_id: str,
    query: str,
    k: Optional[int] = None,
    session: Optional[Any] = None,
) -> List[Dict[str, Any]]:
    """
    Retrieve the top-k most relevant memories for ``query``.

    Scoring runs over the ``MEMORY_CANDIDATE_LIMIT`` most recent memories of
    the project. Fail-open: returns ``[]`` when embeddings are unavailable,
    the DB read fails, or nothing is stored, so prompt assembly proceeds
    without memory instead of erroring the chat turn.
    """
    if not settings.MEMORY_ENABLED or not query or not query.strip():
        return []
    top_k = k or settings.MEMORY_TOP_K
    try:
        query_vector = (await embed_texts([query]))[0]
        candidates = await SemanticMemoryRepository.get_recent(
            project_id, limit=settings.MEMORY_CANDIDATE_LIMIT, session=session
        )
        scored = [
            (score_memory(query_vector, memory), memory)
            for memory in candidates
        ]
        # Require actual semantic relevance: a memory with ZERO cosine
        # similarity to the query would otherwise slip in on recency alone
        # (score = (1-weight) * recency > 0) and inject unrelated content.
        # An unrelated query therefore yields no memory block at all.
        scored = [
            (s, m) for s, m in scored
            if s > 0.0
            and cosine_similarity(query_vector, m.get("embedding") or []) > 0.0
        ]
        scored.sort(key=lambda pair: pair[0], reverse=True)
        top = scored[:top_k]
        if top:
            # Best-effort usage telemetry; must never break recall.
            try:
                await SemanticMemoryRepository.mark_recalled(
                    [m["id"] for _, m in top], session=session
                )
            except Exception:
                logger.debug("mark_recalled failed (non-fatal).", exc_info=True)
        return [dict(m, score=round(s, 4)) for s, m in top]
    except MemoryEmbeddingUnavailableError as err:
        logger.warning("Semantic memory recall degraded (%s).", err)
        return []
    except Exception as err:
        logger.warning("Semantic memory recall failed unexpectedly (%s).", err, exc_info=True)
        return []


def build_memory_block(memories: List[Dict[str, Any]]) -> str:
    """
    Render recalled memories as a compact prompt block, hard-capped at
    ``MEMORY_CONTEXT_MAX_TOKENS`` (budget hygiene, Finding #39 discipline).

    Returns an empty string when there is nothing to inject, so callers can
    append the block unconditionally.
    """
    if not memories:
        return ""
    max_tokens = settings.MEMORY_CONTEXT_MAX_TOKENS
    lines: List[str] = []
    used = count_tokens("Relevant project memory (from previous conversations):\n")
    for memory in memories:
        content = str(memory.get("content") or "").strip()
        if not content:
            continue
        line = f"- {content}"
        line_tokens = count_tokens(line + "\n")
        if used + line_tokens > max_tokens:
            break
        lines.append(line)
        used += line_tokens
    if not lines:
        return ""
    return "Relevant project memory (from previous conversations):\n" + "\n".join(lines)

