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


# CHAT 7.x — Shared conversation transcript persistence (conversation_messages).
# Call sites across flows:
#   7.1 save_message             ← CHAT 2.3.3 (pipeline assistant turn),
#                                  CHAT 5.3 / 5.5 (/api/chat turns), and every
#                                  agent node in the GATHERING/AUDITOR flows
#   7.2 get_conversation_history ← CHAT 2.3.1 (chat context), PROJECT 2.3.4
#                                  (state response), CHAT 5.2 and the agent prompts
# Session ownership: callers may pass the request-scoped session (participating in
# the caller's transaction) or omit it, in which case the repository opens its own
# AsyncSessionLocal with commit/rollback.
class ConversationMessageRepository:
    """
    Handles conversation message persistence in a dedicated table.
    Independent from requirement_states storage.
    """

    # CHAT 7.1 — INSERT one turn; returns {} for a blank message (no row, no error).
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

    # CHAT 7.2 — SELECT the full transcript oldest-first (the ORDER BY created_at
    # asc is what keeps prompt context and the restored UI timeline consistent).
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