"""
Version History repository operations.
"""
import logging
import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import RequirementModel, VersionHistoryModel
from app.repositories.base import as_uuid, serialize_version_history

logger = logging.getLogger(__name__)

SYSTEM_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000000")


class VersionHistoryRepository:
    """Handles Version History snapshot tracking of the project."""

    @staticmethod
    async def create(project_id: str, data: Dict[str, Any], session: AsyncSession) -> Dict[str, Any]:
        pid = as_uuid(project_id)

        stmt_req = select(RequirementModel).where(RequirementModel.project_id == pid)
        res_req = await session.execute(stmt_req)
        req = res_req.scalar_one_or_none()
        if not req:
            req = RequirementModel(
                project_id=pid,
                requirement_code="REQ-000",
                title="Untitled Requirement",
                status="active",
                is_locked=False,
                locked_by=None,
                locked_at=None
            )
            session.add(req)
            await session.flush()

        system_user_id = SYSTEM_USER_ID

        vh = VersionHistoryModel(
            project_id=pid,
            requirement_id=req.id,
            version=data.get("version", 1),
            changed_by_user_id=system_user_id,
            description=data.get("description", "Requirements updated."),
            requirements_snapshot=data.get("requirements_snapshot", {})
        )
        session.add(vh)
        await session.flush()
        return serialize_version_history(vh)

    @staticmethod
    async def get_by_id(id_val: str, project_id: str, session: AsyncSession) -> Optional[Dict[str, Any]]:
        vhid = as_uuid(id_val)
        pid = as_uuid(project_id)
        stmt = select(VersionHistoryModel).where(VersionHistoryModel.id == vhid, VersionHistoryModel.project_id == pid)
        result = await session.execute(stmt)
        vh = result.scalar_one_or_none()
        if vh:
            return serialize_version_history(vh)
        return None

    @staticmethod
    async def get_by_project(project_id: str, session: AsyncSession) -> List[Dict[str, Any]]:
        pid = as_uuid(project_id)
        stmt = select(VersionHistoryModel).where(VersionHistoryModel.project_id == pid).order_by(VersionHistoryModel.version.desc())
        result = await session.execute(stmt)
        records = result.scalars().all()
        return [serialize_version_history(vh) for vh in records]

    @staticmethod
    async def update(id_val: str, project_id: str, updates: Dict[str, Any], session: AsyncSession) -> Optional[Dict[str, Any]]:
        vhid = as_uuid(id_val)
        pid = as_uuid(project_id)
        stmt = select(VersionHistoryModel).where(VersionHistoryModel.id == vhid, VersionHistoryModel.project_id == pid)
        result = await session.execute(stmt)
        vh = result.scalar_one_or_none()
        if vh:
            if "version" in updates:
                vh.version = updates["version"]
            if "description" in updates:
                vh.description = updates["description"]
            if "requirements_snapshot" in updates:
                vh.requirements_snapshot = updates["requirements_snapshot"]
            await session.flush()
            return serialize_version_history(vh)
        return None

    @staticmethod
    async def delete(id_val: str, project_id: str, session: AsyncSession) -> bool:
        vhid = as_uuid(id_val)
        pid = as_uuid(project_id)
        stmt = select(VersionHistoryModel).where(VersionHistoryModel.id == vhid, VersionHistoryModel.project_id == pid)
        result = await session.execute(stmt)
        vh = result.scalar_one_or_none()
        if vh:
            await session.delete(vh)
            await session.flush()
            return True
        return False