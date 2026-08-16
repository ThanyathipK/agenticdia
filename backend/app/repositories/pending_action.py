"""
Pending Action repository operations.
"""
import logging
from datetime import datetime
from typing import Any, Dict, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PendingActionModel
from app.repositories.base import as_uuid, serialize_pending_action

logger = logging.getLogger(__name__)


class PendingActionRepository:
    """Handles Pending Actions for Human-in-the-Loop confirmation."""

    @staticmethod
    async def create(project_id: str, data: Dict[str, Any], expires_at: datetime, session: AsyncSession) -> Dict[str, Any]:
        pid = as_uuid(project_id)
        action = PendingActionModel(
            project_id=pid,
            action_type=data.get("action_type", "UPDATE"),
            target_requirement_id=data.get("target_requirement_id"),
            original_user_message=data.get("original_user_message", ""),
            proposed_changes=data.get("proposed_changes", {}),
            affected_user_story_ids=data.get("affected_user_story_ids", []),
            affected_acceptance_criteria_ids=data.get("affected_acceptance_criteria_ids", []),
            workflow_stage=data.get("workflow_stage", "gatherer_node"),
            expires_at=expires_at
        )
        session.add(action)
        await session.flush()
        await session.refresh(action)
        return serialize_pending_action(action)

    @staticmethod
    async def get_by_project(project_id: str, session: AsyncSession) -> List[Dict[str, Any]]:
        pid = as_uuid(project_id)
        stmt = select(PendingActionModel).where(PendingActionModel.project_id == pid, PendingActionModel.status == "WAITING_CONFIRMATION")
        result = await session.execute(stmt)
        actions = result.scalars().all()
        return [serialize_pending_action(a, full=True) for a in actions]

    @staticmethod
    async def delete(id_val: str, project_id: str, session: AsyncSession) -> bool:
        aid = as_uuid(id_val)
        pid = as_uuid(project_id)
        stmt = select(PendingActionModel).where(PendingActionModel.id == aid, PendingActionModel.project_id == pid)
        result = await session.execute(stmt)
        action = result.scalar_one_or_none()
        if action:
            await session.delete(action)
            await session.flush()
            return True
        return False