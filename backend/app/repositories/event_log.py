"""
Append-only immutable event log repository.

Stores historical records of CREATE, UPDATE, DELETE, ARCHIVE, LOCK, UNLOCK
events. Never overwrites or deletes existing records — purely historical
traceability.
"""
import logging
import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ArtifactEventLogModel
from app.repositories.base import serialize_event_log

logger = logging.getLogger(__name__)


class ArtifactEventLogRepository:
    """Append-only immutable event log for tracking all artifact modifications."""

    VALID_ACTIONS = {"CREATE", "UPDATE", "DELETE", "ARCHIVE", "LOCK", "UNLOCK"}

    @staticmethod
    async def log_event(
        artifact_type: str,
        artifact_id: str,
        action: str,
        session: AsyncSession,
        old_value: Optional[Dict[str, Any]] = None,
        new_value: Optional[Dict[str, Any]] = None,
        performed_by: str = "automated_agent"
    ) -> Dict[str, Any]:
        """
        Append a single event to the artifact event log.
        This is the ONLY write operation — logs are never updated or deleted.

        Args:
            artifact_type: Type of artifact (e.g. 'epic', 'requirement',
                'user_story', 'acceptance_criteria', 'prd')
            artifact_id: UUID string of the modified artifact
            action: One of CREATE, UPDATE, DELETE, ARCHIVE, LOCK, UNLOCK
            session: Active database session
            old_value: Snapshot of the artifact before the change (optional)
            new_value: Snapshot of the artifact after the change (optional)
            performed_by: Identifier of who performed the action

        Returns:
            The created event log entry
        """
        action_upper = action.upper()
        if action_upper not in ArtifactEventLogRepository.VALID_ACTIONS:
            raise ValueError(
                f"Invalid action '{action}'. Must be one of: "
                f"{', '.join(sorted(ArtifactEventLogRepository.VALID_ACTIONS))}"
            )

        log_entry = ArtifactEventLogModel(
            event_id=uuid.uuid4(),
            artifact_type=artifact_type,
            artifact_id=str(artifact_id),
            action=action_upper,
            old_value=old_value,
            new_value=new_value,
            performed_by=performed_by
        )
        session.add(log_entry)
        await session.flush()
        await session.refresh(log_entry)

        logger.info(f"[EVENT LOG] {action_upper} on {artifact_type} ({artifact_id}) by {performed_by}")

        return serialize_event_log(log_entry)

    @staticmethod
    async def get_by_artifact(
        artifact_type: str,
        artifact_id: str,
        session: AsyncSession,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Retrieve all events for a specific artifact, newest first."""
        stmt = (
            select(ArtifactEventLogModel)
            .where(
                ArtifactEventLogModel.artifact_type == artifact_type,
                ArtifactEventLogModel.artifact_id == str(artifact_id)
            )
            .order_by(ArtifactEventLogModel.timestamp.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await session.execute(stmt)
        events = result.scalars().all()
        return [serialize_event_log(e) for e in events]

    @staticmethod
    async def get_by_project(
        project_id: str,
        session: AsyncSession,
        artifact_type: Optional[str] = None,
        action: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Retrieve all events for a project, optionally filtered by artifact_type
        and/or action.

        Since artifact_event_logs has no project_id column, this queries by
        artifact_type and artifact_id patterns. For project-scoped queries, use
        the dedicated get_by_project_artifact_types method with known artifact IDs.

        This method is a convenience wrapper — for production use, consider
        querying by known artifact IDs from the project.
        """
        conditions = []
        if artifact_type:
            conditions.append(ArtifactEventLogModel.artifact_type == artifact_type)
        if action:
            conditions.append(ArtifactEventLogModel.action == action.upper())

        stmt = select(ArtifactEventLogModel)
        if conditions:
            stmt = stmt.where(*conditions)
        stmt = stmt.order_by(ArtifactEventLogModel.timestamp.desc()).limit(limit).offset(offset)

        result = await session.execute(stmt)
        events = result.scalars().all()
        return [serialize_event_log(e) for e in events]

    @staticmethod
    async def get_by_action(
        action: str,
        session: AsyncSession,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Retrieve all events for a specific action type (e.g. all CREATE events)."""
        action_upper = action.upper()
        stmt = (
            select(ArtifactEventLogModel)
            .where(ArtifactEventLogModel.action == action_upper)
            .order_by(ArtifactEventLogModel.timestamp.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await session.execute(stmt)
        events = result.scalars().all()
        return [serialize_event_log(e) for e in events]

    @staticmethod
    async def get_recent(
        session: AsyncSession,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Retrieve the most recent events across all artifacts."""
        stmt = (
            select(ArtifactEventLogModel)
            .order_by(ArtifactEventLogModel.timestamp.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await session.execute(stmt)
        events = result.scalars().all()
        return [serialize_event_log(e) for e in events]

    @staticmethod
    async def count_by_artifact(
        artifact_type: str,
        artifact_id: str,
        session: AsyncSession
    ) -> int:
        """Count total events for a specific artifact."""
        stmt = select(func.count()).select_from(ArtifactEventLogModel).where(
            ArtifactEventLogModel.artifact_type == artifact_type,
            ArtifactEventLogModel.artifact_id == str(artifact_id)
        )
        result = await session.execute(stmt)
        return result.scalar() or 0