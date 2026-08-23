"""
Project-level repository operations.
"""
import logging
import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.lock_service import LockService
from app.models import ConversationMessageModel, ProjectModel, RequirementStateModel
from app.repositories.base import as_uuid, serialize_project
from app.repositories.event_log import ArtifactEventLogRepository

logger = logging.getLogger(__name__)

DEFAULT_SYSTEM_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000000")


class ProjectRepository:
    """Handles project-level operations."""

    @staticmethod
    def _sort_projects(projects: List[ProjectModel]) -> None:
        """Sidebar ordering: pinned projects float to the top, then most recently updated first."""
        projects.sort(key=lambda p: (not (p.is_pinned or False), -(p.updated_at or p.created_at).timestamp() if (p.updated_at or p.created_at) else 0))

    @staticmethod
    async def list_all(session: AsyncSession) -> List[Dict[str, Any]]:
        stmt = select(ProjectModel)
        result = await session.execute(stmt)
        projects = list(result.scalars().all())
        ProjectRepository._sort_projects(projects)
        return [serialize_project(p) for p in projects]

    @staticmethod
    async def search(session: AsyncSession, query: str) -> List[Dict[str, Any]]:
        """Search projects by name OR by their persisted conversation messages.

        A project is returned when its name contains ``query`` (case-insensitive)
        or when at least one of its conversation messages contains ``query``
        (case-insensitive). Results use the same pinned-first ordering as
        :meth:`list_all`.

        Args:
            session: Active asynchronous database session.
            query: Non-empty search text (caller validates; stripped here).

        Returns:
            List[Dict[str, Any]]: Matching project summary records.
        """
        pattern = f"%{query.strip()}%"
        stmt = (
            select(ProjectModel)
            .outerjoin(ConversationMessageModel, ConversationMessageModel.project_id == ProjectModel.id)
            .where(or_(
                ProjectModel.name.ilike(pattern),
                ConversationMessageModel.message.ilike(pattern),
            ))
            .distinct()
        )
        result = await session.execute(stmt)
        projects = list(result.scalars().all())
        ProjectRepository._sort_projects(projects)
        return [serialize_project(p) for p in projects]

    @staticmethod
    async def create_project(project_data: Dict[str, Any], session: AsyncSession) -> Dict[str, Any]:
        user_id = project_data.get("user_id")
        if not user_id:
            # Resolve to standard seeded default system user
            user_id = DEFAULT_SYSTEM_USER_ID
        else:
            user_id = uuid.UUID(str(user_id))

        project = ProjectModel(
            id=uuid.UUID(str(project_data["id"])) if "id" in project_data else uuid.uuid4(),
            user_id=user_id,
            name=project_data["name"],
            description=project_data.get("description"),
            industry_standard=project_data.get("industry_standard", "Generic")
        )
        session.add(project)
        await session.flush()

        # Initialize requirement state
        req_state = RequirementStateModel(
            project_id=project.id,
            project_name=project.name
        )
        session.add(req_state)

        await session.flush()
        await session.refresh(project)
        return {"id": str(project.id), "name": project.name}

    @staticmethod
    async def get_by_id(project_id: str, session: AsyncSession) -> Optional[Dict[str, Any]]:
        pid = as_uuid(project_id)
        stmt = select(ProjectModel).where(ProjectModel.id == pid)
        result = await session.execute(stmt)
        p = result.scalar_one_or_none()
        if p:
            return serialize_project(p)
        return None

    @staticmethod
    async def update(project_id: str, updates: Dict[str, Any], session: AsyncSession) -> Optional[Dict[str, Any]]:
        pid = as_uuid(project_id)
        stmt = select(ProjectModel).where(ProjectModel.id == pid)
        result = await session.execute(stmt)
        p = result.scalar_one_or_none()
        if p:
            # LOCK ENFORCEMENT: Cannot update a locked project
            LockService.raise_if_locked_model(
                "project",
                p,
                message=f"Project '{p.name}' is locked by {p.locked_by or 'unknown'}. Unlock it before modifying."
            )
            if "name" in updates:
                p.name = updates["name"]
            if "description" in updates:
                p.description = updates["description"]
            if "industry_standard" in updates:
                p.industry_standard = updates["industry_standard"]
            if "is_pinned" in updates:
                p.is_pinned = bool(updates["is_pinned"])
            await session.flush()
            await session.refresh(p)
            return serialize_project(p)
        return None

    @staticmethod
    async def toggle_pinned(project_id: str, is_pinned: bool, session: AsyncSession) -> Optional[Dict[str, Any]]:
        """Pin or unpin a project (chat) so it floats to the top of the sidebar.

        Args:
            project_id: Project UUID string.
            is_pinned: New pinned state to apply.
            session: Active asynchronous database session.

        Returns:
            Optional[Dict[str, Any]]: The updated project record, or None if the
                project does not exist.
        """
        pid = as_uuid(project_id)
        stmt = select(ProjectModel).where(ProjectModel.id == pid)
        result = await session.execute(stmt)
        p = result.scalar_one_or_none()
        if not p:
            return None
        p.is_pinned = bool(is_pinned)
        await session.flush()
        await session.refresh(p)
        return serialize_project(p)

    @staticmethod
    async def delete(project_id: str, session: AsyncSession) -> bool:
        pid = as_uuid(project_id)
        stmt = select(ProjectModel).where(ProjectModel.id == pid)
        result = await session.execute(stmt)
        p = result.scalar_one_or_none()
        if p:
            # LOCK ENFORCEMENT: Cannot delete a locked project
            LockService.raise_if_locked_model(
                "project",
                p,
                message=f"Project '{p.name}' is locked by {p.locked_by or 'unknown'}. Unlock it before deleting."
            )
            await session.delete(p)
            await session.flush()
            # Log DELETE event
            try:
                await ArtifactEventLogRepository.log_event(
                    artifact_type="project",
                    artifact_id=str(project_id),
                    action="DELETE",
                    session=session,
                    old_value={"name": p.name, "description": p.description},
                    new_value=None,
                    performed_by="automated_agent"
                )
            except Exception as log_err:
                logger.warning(f"[EVENT LOG] Failed to log project delete: {log_err}")
            return True
        return False