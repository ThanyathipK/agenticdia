"""
Uploaded-document repository operations.

The ``uploaded_documents`` table is the project's immutable knowledge /
document store. Uploading a document ONLY adds source material — nothing here
ever mutates requirements, user stories, or acceptance criteria (that happens
exclusively through the explicit, user-confirmed extraction flow in
``app/routes/documents.py``).
"""
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import DocumentModel
from app.repositories.base import as_uuid, serialize_document

logger = logging.getLogger(__name__)


class DocumentRepository:
    """CRUD operations for uploaded project documents."""

    @staticmethod
    async def create(project_id: str, data: Dict[str, Any], session: AsyncSession) -> Dict[str, Any]:
        """Persist a new document record with its full canonical markdown."""
        doc = DocumentModel(
            project_id=as_uuid(project_id),
            original_filename=data["original_filename"],
            original_format=data["original_format"],
            mime_type=data.get("mime_type"),
            content_markdown=data.get("content_markdown", ""),
            file_size_bytes=data.get("file_size_bytes", 0),
            token_count=data.get("token_count", 0),
            status=data.get("status", "processed"),
            uploaded_by=data.get("uploaded_by", "user"),
            extraction_status=data.get("extraction_status", "not_extracted"),
        )
        session.add(doc)
        await session.flush()
        await session.refresh(doc)
        return serialize_document(doc)

    @staticmethod
    async def get_by_project(project_id: str, session: AsyncSession) -> List[Dict[str, Any]]:
        """List every uploaded document for a project, newest first."""
        pid = as_uuid(project_id)
        stmt = (
            select(DocumentModel)
            .where(DocumentModel.project_id == pid)
            .order_by(DocumentModel.created_at.desc())
        )
        result = await session.execute(stmt)
        docs = result.scalars().all()
        return [serialize_document(d) for d in docs]

    @staticmethod
    async def get_by_id(document_id: str, project_id: str, session: AsyncSession) -> Optional[Dict[str, Any]]:
        """Fetch a single document by id, scoped to the project."""
        did = as_uuid(document_id)
        pid = as_uuid(project_id)
        stmt = select(DocumentModel).where(
            DocumentModel.id == did,
            DocumentModel.project_id == pid,
        )
        result = await session.execute(stmt)
        doc = result.scalar_one_or_none()
        if not doc:
            return None
        return serialize_document(doc, include_markdown=True)

    @staticmethod
    async def update_extraction_status(
        document_id: str,
        project_id: str,
        extraction_status: str,
        session: AsyncSession,
    ) -> Optional[Dict[str, Any]]:
        """Update a document's extraction-status tracking flag."""
        did = as_uuid(document_id)
        pid = as_uuid(project_id)
        stmt = select(DocumentModel).where(
            DocumentModel.id == did,
            DocumentModel.project_id == pid,
        )
        result = await session.execute(stmt)
        doc = result.scalar_one_or_none()
        if not doc:
            return None
        doc.extraction_status = extraction_status
        await session.flush()
        await session.refresh(doc)
        return serialize_document(doc)

    @staticmethod
    async def delete(document_id: str, project_id: str, session: AsyncSession) -> Optional[Dict[str, Any]]:
        """Hard-delete an uploaded document, scoped to the owning project.

        Returns the removed record (for logging/audit) or ``None`` when the
        document does not exist. Watch out: any DRAFT merge preview already
        staged from this document (a pending_action whose
        ``proposed_changes._document_ref.document_id`` matches) is handled by
        the DELETE route, not here.
        """
        did = as_uuid(document_id)
        pid = as_uuid(project_id)
        stmt = select(DocumentModel).where(
            DocumentModel.id == did,
            DocumentModel.project_id == pid,
        )
        result = await session.execute(stmt)
        doc = result.scalar_one_or_none()
        if not doc:
            return None
        await session.delete(doc)
        await session.flush()
        return serialize_document(doc)