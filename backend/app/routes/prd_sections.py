"""
PRD Section routes — part-level PRD editing, locking, and versioning.

A PRD is a collection of NINE editable parts (the same parts the preview
renders). Each part can be:
  - edited independently           -> PATCH  .../prd/sections/{section_key}
  - locked / unlocked individually -> POST   .../prd/sections/{section_key}/lock|unlock
  - inspected per-version          -> GET    .../prd/sections/{section_key}/versions
  - restored from history          -> POST   .../prd/sections/{section_key}/revert/{version}

Lock semantics (coarse -> fine):
  project lock  >  prd_document lock  >  prd_section lock
All three are enforced before any part mutation. Restores are APPEND-ONLY:
reverting copies old content into a NEW version, history is never rewritten.
"""
import logging
from typing import Dict
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.event_manager import event_manager
from app.prd_section_service import (
    VALID_REVIEW_STATUSES,
    assemble_document_markdown,
    ensure_sections_seeded,
    merge_edited_section,
)
from app.repositories import (
    ArtifactEventLogRepository,
    PRDDocumentRepository,
    PRDSectionRepository,
    PRDSectionVersionRepository,
    PRDVersionRepository,
    RequirementStateRepository,
)
from app.schemas import (
    ArtifactLockRequest,
    PrdSectionListResponse,
    PrdSectionRevertResponse,
    PrdSectionResponse,
    PrdSectionUpdate,
    PrdSectionUpdateResponse,
    PrdSectionVersionResponse,
)

logger = logging.getLogger("app.routes.prd_sections")

router = APIRouter()


async def _validate_project(project_id: str) -> None:
    try:
        UUID(project_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project_id format")


async def _raise_if_project_locked(project_id: str, session: AsyncSession) -> None:
    from app.lock_service import LockService, ArtifactLockError
    try:
        lock_info = await LockService.get_lock_status("project", project_id, session, project_id=project_id)
        LockService.raise_if_locked("project", project_id, lock_info)
    except ArtifactLockError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


async def _raise_if_document_locked(project_id: str, session: AsyncSession) -> None:
    """The PRD document lock is the coarse switch: a locked document freezes
    every part."""
    from app.lock_service import LockService, ArtifactLockError
    docs = await PRDDocumentRepository.get_by_project(project_id, session)
    if not docs:
        return
    try:
        lock_info = await LockService.get_lock_status(
            "prd_document", docs[0]["id"], session, project_id=project_id
        )
        LockService.raise_if_locked(
            "prd_document", docs[0]["id"], lock_info,
            message=f"The PRD document is locked by {lock_info.get('locked_by') or 'unknown'}. "
                    "Unlock the document before modifying any of its parts.",
        )
    except ArtifactLockError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError:
        return  # document row vanished between the two queries — nothing to enforce


async def _get_section_or_404(section_key: str, project_id: str, session: AsyncSession) -> Dict:
    section = await PRDSectionRepository.get_by_key(section_key, project_id, session)
    if not section:
        raise HTTPException(status_code=404, detail=f"PRD section '{section_key}' not found")
    return section


@router.get("/api/project/{project_id}/prd/sections", response_model=PrdSectionListResponse, status_code=status.HTTP_200_OK)
async def list_prd_sections(project_id: str, session: AsyncSession = Depends(get_db)) -> PrdSectionListResponse:
    """List all PRD parts (the nine preview parts) in document order.

    Seeds the parts on first access: from the project's current markdown PRD
    when one exists, otherwise from the official Krungsri template skeleton.
    """
    await _validate_project(project_id)
    state = await RequirementStateRepository.get_by_project_id(project_id, session)
    source = (state or {}).get("generated_prd") or ""
    sections = await ensure_sections_seeded(project_id, session, source_markdown=source)
    return {"project_id": project_id, "sections": sections}


@router.patch("/api/project/{project_id}/prd/sections/{section_key}", response_model=PrdSectionUpdateResponse, status_code=status.HTTP_200_OK)
async def update_prd_section(
    project_id: str,
    section_key: str,
    payload: PrdSectionUpdate,
    session: AsyncSession = Depends(get_db),
) -> PrdSectionUpdateResponse:
    """
    Edit ONE part of the PRD.

    Enforces project > document > section locks, appends an immutable version
    row for the part, then re-stitches and persists the full document.
    """
    await _validate_project(project_id)
    await _raise_if_project_locked(project_id, session)
    await _raise_if_document_locked(project_id, session)

    if payload.review_status and payload.review_status not in VALID_REVIEW_STATUSES:
        raise HTTPException(
            status_code=422,
            detail=f"review_status must be one of: {', '.join(sorted(VALID_REVIEW_STATUSES))}",
        )

    section = await _get_section_or_404(section_key, project_id, session)

    # MERGE-WITH-LAST-VERSION (three-way): the UI sends BOTH the full edited
    # text (``content``) AND the text it started editing from
    # (``base_content``). ``section.content`` is the CURRENT stored text —
    # possibly advanced by an AI regeneration while the user was editing.
    # ``merge_edited_section`` keeps the user's touched lines and preserves
    # concurrent changes outside the edit window, so a manual save always
    # produces "last version + this edit" instead of overwriting. Legacy
    # clients without ``base_content`` fall back to verbatim storage.
    edited_content = merge_edited_section(
        payload.base_content,
        section.get("content"),
        payload.content or "",
    )

    try:
        updated = await PRDSectionRepository.update_content(
            section["id"], project_id, edited_content, session,
            changed_by=payload.updated_by or "user",
            change_summary=payload.change_summary,
            review_status=payload.review_status,
        )
    except Exception as lock_err:
        # ArtifactLockError from the repository lock enforcement
        if type(lock_err).__name__ == "ArtifactLockError":
            raise HTTPException(status_code=409, detail=str(lock_err))
        raise

    if not updated:
        raise HTTPException(status_code=404, detail=f"PRD section '{section_key}' not found")

    try:
        await ArtifactEventLogRepository.log_event(
            artifact_type="prd_section",
            artifact_id=updated["id"],
            action="UPDATE",
            session=session,
            old_value={"content": section.get("content"), "section_key": section_key},
            new_value={"content": payload.content, "version_number": updated.get("version_number")},
            performed_by=payload.updated_by or "user",
        )
    except Exception as log_err:  # never block an edit on event logging
        logger.warning(f"[PRD SECTIONS] Failed to log update event: {log_err}")

    # Full-document snapshot flow: the parts table (with this edit applied) is
    # the single source of truth. Re-stitch ALL parts in canonical order.
    document_markdown = await assemble_document_markdown(project_id, session)

    # ORDER MATTERS: record the version FIRST so requirement_states
    # .version_number advances to N+1; the subsequent save_or_update then
    # propagates the merged document into a NEW prd_documents row for version
    # N+1 instead of overwriting the previous version's row in place. This is
    # what makes a manual edit "merge with the old one and save as a NEW
    # version" — the old version's document row is never touched.
    try:
        from app.version_service import record_prd_version
        await record_prd_version(
            project_id, session,
            generated_prd=document_markdown,
            generated_by=payload.updated_by or "user",
            change_type="manual",
            change_summary=payload.change_summary,
        )
    except Exception as ver_err:  # never block a valid edit on ledger bookkeeping
        logger.warning("[PRD SECTIONS] Failed to record manual PRD version: %s", ver_err)

    await RequirementStateRepository.save_or_update(project_id, {
        "generated_prd": document_markdown,
    }, session)

    await event_manager.publish(project_id, "prd_section_updated", {
        "project_id": project_id,
        "section_key": section_key,
        "version_number": updated.get("version_number"),
    })

    return {"section": updated, "document_markdown": document_markdown}


@router.get("/api/project/{project_id}/prd/sections/{section_key}/versions", response_model=list[PrdSectionVersionResponse], status_code=status.HTTP_200_OK)
async def list_prd_section_versions(
    project_id: str,
    section_key: str,
    session: AsyncSession = Depends(get_db),
) -> list[PrdSectionVersionResponse]:
    """Version history of one PRD part, newest first (append-only)."""
    await _validate_project(project_id)
    section = await _get_section_or_404(section_key, project_id, session)
    return await PRDSectionVersionRepository.get_by_section(section["id"], session)


@router.post("/api/project/{project_id}/prd/sections/{section_key}/revert/{version_number}", response_model=PrdSectionRevertResponse, status_code=status.HTTP_200_OK)
async def revert_prd_section(
    project_id: str,
    section_key: str,
    version_number: int,
    updated_by: str = "user",
    session: AsyncSession = Depends(get_db),
) -> PrdSectionRevertResponse:
    """
    Restore an old version of one PRD part.

    APPEND-ONLY: the old content becomes a NEW version row — history is never
    rewritten. Enforces project > document > section locks.
    """
    await _validate_project(project_id)
    await _raise_if_project_locked(project_id, session)
    await _raise_if_document_locked(project_id, session)

    section = await _get_section_or_404(section_key, project_id, session)
    version = await PRDSectionVersionRepository.get_by_version_number(
        section["id"], version_number, session
    )
    if not version:
        raise HTTPException(
            status_code=404,
            detail=f"Version {version_number} of PRD section '{section_key}' not found",
        )

    updated = await PRDSectionRepository.update_content(
        section["id"], project_id, version["content"], session,
        changed_by=updated_by or "user",
        change_summary=f"Reverted to version {version_number}.",
    )
    # Same single-source-of-truth flow as a manual edit: the parts table (with
    # the restored part applied) is re-stitched and persisted as both the
    # requirement-state document and the new immutable version.
    document_markdown = await assemble_document_markdown(project_id, session)

    # ORDER MATTERS: record the version first (advances requirement_states
    # .version_number) so the document propagation below creates a NEW
    # prd_documents row for the new version instead of overwriting the old
    # one. A revert must also preserve every previous version's document.
    try:
        from app.version_service import record_prd_version
        await record_prd_version(
            project_id, session,
            generated_prd=document_markdown,
            generated_by=updated_by or "user",
            change_type="manual",
            change_summary=f"Reverted '{section_key}' to version {version_number}.",
        )
    except Exception as ver_err:  # never block a valid revert on ledger bookkeeping
        logger.warning("[PRD SECTIONS] Failed to record revert PRD version: %s", ver_err)

    await RequirementStateRepository.save_or_update(project_id, {
        "generated_prd": document_markdown,
    }, session)

    await event_manager.publish(project_id, "prd_section_reverted", {
        "project_id": project_id,
        "section_key": section_key,
        "restored_from_version": version_number,
    })

    return {
        "section": updated,
        "document_markdown": document_markdown,
        "restored_from_version": version_number,
    }


@router.post("/api/project/{project_id}/prd/sections/{section_key}/lock", response_model=Dict, status_code=status.HTTP_200_OK)
async def lock_prd_section(
    project_id: str,
    section_key: str,
    payload: ArtifactLockRequest,
    session: AsyncSession = Depends(get_db),
) -> Dict:
    """Lock ONE PRD part: blocks edits AND excludes it from AI regeneration."""
    await _validate_project(project_id)
    from app.lock_service import LockService, ArtifactLockError

    section = await _get_section_or_404(section_key, project_id, session)
    try:
        lock_info = await LockService.lock_artifact(
            artifact_type="prd_section",
            artifact_id=section["id"],
            session=session,
            locked_by=payload.locked_by or "user",
            lock_reason=payload.lock_reason,
            project_id=project_id,
        )
    except ArtifactLockError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    await event_manager.publish(project_id, "artifact_locked", {
        "project_id": project_id,
        "artifact_type": "prd_section",
        "artifact_id": section["id"],
        "section_key": section_key,
    })
    return {"status": "locked", "artifact": lock_info}


@router.post("/api/project/{project_id}/prd/sections/{section_key}/unlock", response_model=Dict, status_code=status.HTTP_200_OK)
async def unlock_prd_section(
    project_id: str,
    section_key: str,
    payload: ArtifactLockRequest,
    session: AsyncSession = Depends(get_db),
) -> Dict:
    """Unlock ONE PRD part so it can be edited and AI-regenerated again."""
    await _validate_project(project_id)
    from app.lock_service import LockService

    section = await _get_section_or_404(section_key, project_id, session)
    try:
        lock_info = await LockService.unlock_artifact(
            artifact_type="prd_section",
            artifact_id=section["id"],
            session=session,
            unlocked_by=payload.locked_by or "user",
            project_id=project_id,
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    await event_manager.publish(project_id, "artifact_unlocked", {
        "project_id": project_id,
        "artifact_type": "prd_section",
        "artifact_id": section["id"],
        "section_key": section_key,
    })
    return {"status": "unlocked", "artifact": lock_info}


@router.get("/api/project/{project_id}/prd/sections/{section_key}", response_model=PrdSectionResponse, status_code=status.HTTP_200_OK)
async def get_prd_section(
    project_id: str,
    section_key: str,
    session: AsyncSession = Depends(get_db),
) -> PrdSectionResponse:
    """Fetch one PRD part (including its lock + review metadata)."""
    await _validate_project(project_id)
    return await _get_section_or_404(section_key, project_id, session)