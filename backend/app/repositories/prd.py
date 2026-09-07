"""
PRD Document and PRD Version repository operations.
"""
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.lock_service import LockService
from app.models import PRDDocumentModel, PRDVersionModel
from app.repositories.base import as_uuid, serialize_prd_document, serialize_prd_version

logger = logging.getLogger(__name__)


class PRDDocumentRepository:
    """Handles generated PRD Documents of the project."""

    @staticmethod
    async def create(project_id: str, data: Dict[str, Any], session: AsyncSession) -> Dict[str, Any]:
        pid = as_uuid(project_id)
        prd = PRDDocumentModel(
            project_id=pid,
            version=data.get("version", 1),
            prd_markdown=data.get("prd_markdown", ""),
            mermaid_diagram=data.get("mermaid_diagram", "")
        )
        session.add(prd)
        await session.flush()
        await session.refresh(prd)
        return serialize_prd_document(prd)

    @staticmethod
    async def get_by_id(id_val: str, project_id: str, session: AsyncSession) -> Optional[Dict[str, Any]]:
        prdid = as_uuid(id_val)
        pid = as_uuid(project_id)
        stmt = select(PRDDocumentModel).where(PRDDocumentModel.id == prdid, PRDDocumentModel.project_id == pid)
        result = await session.execute(stmt)
        prd = result.scalar_one_or_none()
        if prd:
            return serialize_prd_document(prd)
        return None

    @staticmethod
    async def get_by_project(project_id: str, session: AsyncSession, version: Optional[int] = None) -> List[Dict[str, Any]]:
        pid = as_uuid(project_id)
        if version is not None:
            stmt = select(PRDDocumentModel).where(PRDDocumentModel.project_id == pid, PRDDocumentModel.version == version)
        else:
            stmt = select(PRDDocumentModel).where(PRDDocumentModel.project_id == pid).order_by(PRDDocumentModel.version.desc())
        result = await session.execute(stmt)
        records = result.scalars().all()
        return [serialize_prd_document(prd) for prd in records]

    @staticmethod
    async def update(id_val: str, project_id: str, updates: Dict[str, Any], session: AsyncSession) -> Optional[Dict[str, Any]]:
        prdid = as_uuid(id_val)
        pid = as_uuid(project_id)
        stmt = select(PRDDocumentModel).where(PRDDocumentModel.id == prdid, PRDDocumentModel.project_id == pid)
        result = await session.execute(stmt)
        prd = result.scalar_one_or_none()
        if prd:
            # LOCK ENFORCEMENT: Cannot update a locked PRD document
            LockService.raise_if_locked_model(
                "prd_document",
                prd,
                message=f"PRD Document is locked by {prd.locked_by or 'unknown'}. Unlock it before modifying."
            )
            if "version" in updates:
                prd.version = updates["version"]
            if "prd_markdown" in updates:
                prd.prd_markdown = updates["prd_markdown"]
            if "mermaid_diagram" in updates:
                prd.mermaid_diagram = updates["mermaid_diagram"]
            await session.flush()
            await session.refresh(prd)
            return serialize_prd_document(prd)
        return None

    @staticmethod
    async def delete(id_val: str, project_id: str, session: AsyncSession) -> bool:
        prdid = as_uuid(id_val)
        pid = as_uuid(project_id)
        stmt = select(PRDDocumentModel).where(PRDDocumentModel.id == prdid, PRDDocumentModel.project_id == pid)
        result = await session.execute(stmt)
        prd = result.scalar_one_or_none()
        if prd:
            # LOCK ENFORCEMENT: Cannot delete a locked PRD document
            LockService.raise_if_locked_model(
                "prd_document",
                prd,
                message=f"PRD Document is locked by {prd.locked_by or 'unknown'}. Unlock it before deleting."
            )
            await session.delete(prd)
            await session.flush()
            return True
        return False


class PRDVersionRepository:
    """
    Dedicated immutable PRD version repository.
    Each PRD generation creates a new version record.
    Never overwrites previous versions.
    Does NOT store version history inside requirement_states.
    """

    @staticmethod
    async def create(project_id: str, data: Dict[str, Any], session: AsyncSession) -> Dict[str, Any]:
        pid = as_uuid(project_id)

        # Determine the next version number for this project
        stmt = select(func.max(PRDVersionModel.version_number)).where(PRDVersionModel.project_id == pid)
        result = await session.execute(stmt)
        max_version = result.scalar() or 0
        next_version = max_version + 1

        version = PRDVersionModel(
            project_id=pid,
            version_number=next_version,
            generated_prd=data.get("generated_prd", ""),
            generated_by=data.get("generated_by", "automated_agent")
        )
        session.add(version)
        await session.flush()
        await session.refresh(version)
        return serialize_prd_version(version)

    @staticmethod
    async def get_by_project(project_id: str, session: AsyncSession) -> List[Dict[str, Any]]:
        pid = as_uuid(project_id)
        stmt = select(PRDVersionModel).where(PRDVersionModel.project_id == pid).order_by(PRDVersionModel.version_number.desc())
        result = await session.execute(stmt)
        records = result.scalars().all()
        return [serialize_prd_version(v) for v in records]

    @staticmethod
    async def get_by_version_number(project_id: str, version_number: int, session: AsyncSession) -> Optional[Dict[str, Any]]:
        pid = as_uuid(project_id)
        stmt = select(PRDVersionModel).where(
            PRDVersionModel.project_id == pid,
            PRDVersionModel.version_number == version_number
        )
        result = await session.execute(stmt)
        v = result.scalar_one_or_none()
        if v:
            return serialize_prd_version(v)
        return None

    @staticmethod
    async def get_latest(project_id: str, session: AsyncSession) -> Optional[Dict[str, Any]]:
        pid = as_uuid(project_id)
        stmt = select(PRDVersionModel).where(PRDVersionModel.project_id == pid).order_by(PRDVersionModel.version_number.desc()).limit(1)
        result = await session.execute(stmt)
        v = result.scalar_one_or_none()
        if v:
            return serialize_prd_version(v)
        return None