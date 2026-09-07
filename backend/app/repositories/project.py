"""
Project-level repository operations.
"""
import logging
import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.lock_service import LockService
from app.models import ConversationMessageModel, ProjectModel, RequirementStateModel
from app.repositories.base import as_uuid, serialize_project
from app.repositories.event_log import ArtifactEventLogRepository

logger = logging.getLogger(__name__)

DEFAULT_SYSTEM_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000000")


def _make_snippet(message: str, query: str, window: int = 60) -> str:
    """Build a compact excerpt of a conversation message centered on the first
    case-insensitive occurrence of ``query``.

    The snippet is bounded so the sidebar row stays short; an ellipsis marks the
    trimmed edges. Returns an empty string when there is nothing meaningful to
    show (no message text or no occurrence), in which case callers skip the
    ``match_snippet`` field entirely.
    """
    text = (message or "").strip()
    needle = query.strip().lower()
    if not text or not needle:
        return ""
    lower = text.lower()
    idx = lower.find(needle)
    if idx == -1:
        return text[:160].rstrip() + ("…" if len(text) > 160 else "")
    start = max(0, idx - window)
    end = min(len(text), idx + len(needle) + window * 2)
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(text) else ""
    return f"{prefix}{text[start:end].strip()}{suffix}"


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
        :meth:`list_all`. When a project matched purely via message content, a
        ``match_snippet`` excerpt centered on ``query`` is attached so the UI can
        show *why* the project matched.

        Args:
            session: Active asynchronous database session.
            query: Non-empty search text (caller validates; stripped here).

        Returns:
            List[Dict[str, Any]]: Matching project summary records.
        """
        pattern = f"%{query.strip()}%"
        msg_col = ConversationMessageModel.message
        stmt = (
            select(ProjectModel, msg_col)
            .outerjoin(ConversationMessageModel, ConversationMessageModel.project_id == ProjectModel.id)
            .where(or_(
                ProjectModel.name.ilike(pattern),
                msg_col.ilike(pattern),
            ))
        )
        rows = (await session.execute(stmt)).all()

        # De-duplicate by project while capturing one snippet per project from
        # the first matching message (replaces the old ``.distinct()``).
        project_by_id: Dict[str, ProjectModel] = {}
        snippets: Dict[str, str] = {}
        for proj, message in rows:
            key = str(proj.id)
            if key not in project_by_id:
                project_by_id[key] = proj
            if message and key not in snippets:
                snippet = _make_snippet(message, query)
                if snippet:
                    snippets[key] = snippet

        projects = list(project_by_id.values())
        ProjectRepository._sort_projects(projects)
        return [
            serialize_project(p, match_snippet=snippets.get(str(p.id)))
            for p in projects
        ]

    @staticmethod
    async def name_exists(
        name: str,
        session: AsyncSession,
        exclude_project_id: Optional[str] = None,
    ) -> bool:
        """Return ``True`` when a project already uses ``name``.

        The comparison is case-insensitive and whitespace-trimmed on BOTH
        sides, so ``"Payment Hub"``, ``"payment hub "`` and legacy rows saved
        without trimming are all treated as the same name. Routes call this
        before create/rename and translate ``True`` into HTTP 409 Conflict.

        Args:
            name: Candidate project name (stripped + lower-cased here).
            session: Active asynchronous database session.
            exclude_project_id: Optional project UUID string to ignore — used
                by rename so a project keeps its own name.

        Returns:
            bool: ``True`` when the normalized name is already taken.
        """
        normalized = (name or "").strip().lower()
        if not normalized:
            return False
        stmt = (
            select(func.count())
            .select_from(ProjectModel)
            .where(func.trim(func.lower(ProjectModel.name)) == normalized)
        )
        if exclude_project_id is not None:
            stmt = stmt.where(ProjectModel.id != as_uuid(exclude_project_id))
        result = await session.execute(stmt)
        return bool((result.scalar_one() or 0) > 0)

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