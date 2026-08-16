"""
Audit Result repository operations.
"""
import logging
import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditResultModel, RequirementModel
from app.repositories.base import as_uuid, serialize_audit_result

logger = logging.getLogger(__name__)


class AuditResultRepository:
    """Handles Audit Results of the project."""

    @staticmethod
    async def create(project_id: str, data: Dict[str, Any], session: AsyncSession, requirement_id: Optional[uuid.UUID] = None) -> Dict[str, Any]:
        pid = as_uuid(project_id)

        if requirement_id is None:
            stmt = select(RequirementModel).where(RequirementModel.project_id == pid).order_by(RequirementModel.version.desc())
            res = await session.execute(stmt)
            req = res.scalars().first()
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
            requirement_id = req.id

        ar = AuditResultModel(
            requirement_id=requirement_id,
            is_valid=data.get("is_valid", False),
            audit_version_reviewed=data.get("audit_version_reviewed", 1),
            passed_checks=data.get("passed_checks", []),
            failed_checks=data.get("failed_checks", [])
        )
        session.add(ar)
        await session.flush()
        await session.refresh(ar)
        return serialize_audit_result(ar, pid)

    @staticmethod
    async def get_by_id(id_val: str, project_id: str, session: AsyncSession) -> Optional[Dict[str, Any]]:
        arid = as_uuid(id_val)
        pid = as_uuid(project_id)
        stmt = select(AuditResultModel).join(RequirementModel).where(
            AuditResultModel.id == arid,
            RequirementModel.project_id == pid
        )
        result = await session.execute(stmt)
        ar = result.scalar_one_or_none()
        if ar:
            return serialize_audit_result(ar, pid)
        return None

    @staticmethod
    async def get_by_project(project_id: str, session: AsyncSession, requirement_id: Optional[uuid.UUID] = None) -> List[Dict[str, Any]]:
        pid = as_uuid(project_id)
        if requirement_id is None:
            stmt_req = select(RequirementModel).where(RequirementModel.project_id == pid).order_by(RequirementModel.version.desc())
            res_req = await session.execute(stmt_req)
            req = res_req.scalars().first()
            if req:
                requirement_id = req.id

        if requirement_id:
            stmt = select(AuditResultModel).where(AuditResultModel.requirement_id == requirement_id)
        else:
            stmt = select(AuditResultModel).join(RequirementModel).where(RequirementModel.project_id == pid)

        result = await session.execute(stmt)
        records = result.scalars().all()
        return [serialize_audit_result(ar, pid) for ar in records]

    @staticmethod
    async def update(id_val: str, project_id: str, updates: Dict[str, Any], session: AsyncSession) -> Optional[Dict[str, Any]]:
        arid = as_uuid(id_val)
        pid = as_uuid(project_id)
        stmt = select(AuditResultModel).join(RequirementModel).where(
            AuditResultModel.id == arid,
            RequirementModel.project_id == pid
        )
        result = await session.execute(stmt)
        ar = result.scalar_one_or_none()
        if ar:
            if "is_valid" in updates:
                ar.is_valid = updates["is_valid"]
            if "audit_version_reviewed" in updates:
                ar.audit_version_reviewed = updates["audit_version_reviewed"]
            if "passed_checks" in updates:
                ar.passed_checks = updates["passed_checks"]
            if "failed_checks" in updates:
                ar.failed_checks = updates["failed_checks"]
            await session.flush()
            await session.refresh(ar)
            return serialize_audit_result(ar, pid)
        return None

    @staticmethod
    async def delete(id_val: str, project_id: str, session: AsyncSession) -> bool:
        arid = as_uuid(id_val)
        pid = as_uuid(project_id)
        stmt = select(AuditResultModel).join(RequirementModel).where(
            AuditResultModel.id == arid,
            RequirementModel.project_id == pid
        )
        result = await session.execute(stmt)
        ar = result.scalar_one_or_none()
        if ar:
            await session.delete(ar)
            await session.flush()
            return True
        return False