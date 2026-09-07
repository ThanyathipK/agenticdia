"""
Conversation message repository operations.
"""
import logging
import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models import ConversationMessageModel
from app.repositories.base import as_uuid, serialize_conversation_message

logger = logging.getLogger(__name__)


class ConversationMessageRepository:
    """
    Handles conversation message persistence in a dedicated table.
    Independent from requirement_states storage.
    """

    @staticmethod
    async def save_message(
        project_id: str,
        role: str,
        message: str,
        session: Optional[AsyncSession] = None,
        workflow_state: Optional[str] = None,
        intent: Optional[str] = None
    ) -> Dict[str, Any]:
        if not message or not message.strip():
            return {}

        pid = as_uuid(project_id)

        async def _save(s: AsyncSession):
            msg_obj = ConversationMessageModel(
                id=uuid.uuid4(),
                project_id=pid,
                role=role,
                message=message,
                workflow_state=workflow_state or "",
                intent=intent or ""
            )
            s.add(msg_obj)
            await s.flush()
            return serialize_conversation_message(msg_obj)

        if session:
            # Session is managed by the caller (e.g. get_db dependency) - just flush
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
    async def get_conversation_history(project_id: str, session: Optional[AsyncSession] = None) -> List[Dict[str, Any]]:
        pid = as_uuid(project_id)

        async def _fetch(s: AsyncSession):
            stmt = select(ConversationMessageModel).where(ConversationMessageModel.project_id == pid).order_by(ConversationMessageModel.created_at.asc())
            res = await s.execute(stmt)
            messages = res.scalars().all()
            return [serialize_conversation_message(m) for m in messages]

        if session:
            return await _fetch(session)
        async with AsyncSessionLocal() as db_session:
            return await _fetch(db_session)