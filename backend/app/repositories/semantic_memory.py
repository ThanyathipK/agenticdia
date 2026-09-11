"""
Semantic memory repository operations.

Backs :mod:`app.semantic_memory` (Option A memory layer): distilled facts
extracted from conversations, embedded and stored per project so later
prompt builds can recall them. Pure persistence — all embedding / scoring /
LLM logic lives in the service layer.
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models import SemanticMemoryModel
from app.repositories.base import as_uuid, serialize_semantic_memory

logger = logging.getLogger(__name__)


class SemanticMemoryRepository:
    """
    Persistence for project-scoped semantic memories.

    Mirrors the ConversationMessageRepository pattern: static methods, an
    optional externally-managed ``session`` (caller-owned transaction, e.g.
    the get_db dependency), falling back to a dedicated AsyncSessionLocal
    session with commit/rollback.
    """

    @staticmethod
    async def save_memory(
        project_id: str,
        content: str,
        embedding: List[float],
        embedding_model: str = "",
        kind: str = "semantic",
        source_message_id: Optional[str] = None,
        session: Optional[AsyncSession] = None,
    ) -> Dict[str, Any]:
        """Insert one distilled fact with its embedding; returns its dict repr."""
        if not content or not content.strip():
            raise ValueError("Semantic memory content cannot be empty.")
        pid = as_uuid(project_id)
        src = as_uuid(source_message_id) if source_message_id else None

        async def _save(s: AsyncSession):
            mem = SemanticMemoryModel(
                id=uuid.uuid4(),
                project_id=pid,
                kind=kind,
                content=content.strip(),
                embedding=list(embedding),
                embedding_model=embedding_model,
                source_message_id=src,
            )
            s.add(mem)
            await s.flush()
            return serialize_semantic_memory(mem)

        if session:
            return await _save(session)
        async with AsyncSessionLocal() as db_session:
            try:
                result = await _save(db_session)
                await db_session.commit()
                return result
            except Exception:
                await db_session.rollback()
                raise

    @staticmethod
    async def get_recent(
        project_id: str,
        limit: int = 400,
        session: Optional[AsyncSession] = None,
    ) -> List[Dict[str, Any]]:
        """Most recent ``limit`` memories for a project (newest first)."""
        pid = as_uuid(project_id)

        async def _fetch(s: AsyncSession):
            stmt = (
                select(SemanticMemoryModel)
                .where(SemanticMemoryModel.project_id == pid)
                .order_by(SemanticMemoryModel.created_at.desc())
                .limit(limit)
            )
            res = await s.execute(stmt)
            return [serialize_semantic_memory(m) for m in res.scalars().all()]

        if session:
            return await _fetch(session)
        async with AsyncSessionLocal() as db_session:
            return await _fetch(db_session)

    @staticmethod
    async def mark_recalled(
        memory_ids: List[str],
        session: Optional[AsyncSession] = None,
    ) -> None:
        """Increment recall_count and touch last_recalled_at (best-effort usage telemetry)."""
        if not memory_ids:
            return
        now = datetime.now(timezone.utc)
        ids = [as_uuid(mid) for mid in memory_ids]

        async def _mark(s: AsyncSession):
            await s.execute(
                update(SemanticMemoryModel)
                .where(SemanticMemoryModel.id.in_(ids))
                .values(
                    recall_count=SemanticMemoryModel.recall_count + 1,
                    last_recalled_at=now,
                )
            )

        if session:
            await _mark(session)
            return
        async with AsyncSessionLocal() as db_session:
            try:
                await _mark(db_session)
                await db_session.commit()
            except Exception:
                await db_session.rollback()
                logger.warning("mark_recalled failed (non-fatal).", exc_info=True)

    @staticmethod
    async def delete_for_project(
        project_id: str,
        session: Optional[AsyncSession] = None,
    ) -> int:
        """Delete every memory for a project (used when a project is removed)."""
        from sqlalchemy import delete
        pid = as_uuid(project_id)

        async def _delete(s: AsyncSession):
            res = await s.execute(
                delete(SemanticMemoryModel).where(SemanticMemoryModel.project_id == pid)
            )
            return res.rowcount or 0

        if session:
            return await _delete(session)
        async with AsyncSessionLocal() as db_session:
            try:
                count = await _delete(db_session)
                await db_session.commit()
                return count
            except Exception:
                await db_session.rollback()
                raise