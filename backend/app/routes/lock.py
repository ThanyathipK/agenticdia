import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.repository import PendingActionRepository, RequirementStateRepository
from app.schemas import ArtifactLockRequest
from app.event_manager import event_manager

logger = logging.getLogger("app.routes.lock")

router = APIRouter()

# Valid artifact types for the generic lock/unlock endpoints
VALID_ARTIFACT_TYPES = [
    "project",
    "epic",
    "requirement",
    "user_story",
    "acceptance_criteria",
    "clarification_question",
    "prd_document",
]


# ==========================================
# GENERIC ARTIFACT LOCK / UNLOCK API
# ==========================================

@router.post("/api/project/{project_id}/artifacts/{artifact_type}/{artifact_id}/lock", status_code=status.HTTP_200_OK)
async def lock_artifact(
    project_id: str,
    artifact_type: str,
    artifact_id: str,
    payload: ArtifactLockRequest,
    session: AsyncSession = Depends(get_db)
):
    """
    Generic lock endpoint for any artifact type.
    Supported types: project, epic, requirement, user_story, acceptance_criteria, clarification_question, prd_document
    """
    from app.lock_service import LockService, ArtifactLockError

    try:
        UUID(project_id)
        UUID(artifact_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project_id or artifact_id format")

    # Validate artifact type
    if artifact_type not in VALID_ARTIFACT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid artifact_type. Must be one of: {', '.join(VALID_ARTIFACT_TYPES)}"
        )

    try:
        lock_info = await LockService.lock_artifact(
            artifact_type=artifact_type,
            artifact_id=artifact_id,
            session=session,
            locked_by=payload.locked_by or "user",
            lock_reason=payload.lock_reason,
            project_id=project_id
        )
        await event_manager.publish(project_id, "artifact_locked", {
            "project_id": project_id,
            "artifact_type": artifact_type,
            "artifact_id": artifact_id,
        })
        return {
            "status": "locked",
            "artifact": lock_info
        }
    except ArtifactLockError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/api/project/{project_id}/artifacts/{artifact_type}/{artifact_id}/unlock", status_code=status.HTTP_200_OK)
async def unlock_artifact(
    project_id: str,
    artifact_type: str,
    artifact_id: str,
    payload: ArtifactLockRequest,
    session: AsyncSession = Depends(get_db)
):
    """
    Generic unlock endpoint for any artifact type.
    """
    from app.lock_service import LockService

    try:
        UUID(project_id)
        UUID(artifact_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project_id or artifact_id format")

    # Validate artifact type
    if artifact_type not in VALID_ARTIFACT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid artifact_type. Must be one of: {', '.join(VALID_ARTIFACT_TYPES)}"
        )

    try:
        lock_info = await LockService.unlock_artifact(
            artifact_type=artifact_type,
            artifact_id=artifact_id,
            session=session,
            unlocked_by=payload.locked_by or "user",
            project_id=project_id
        )
        await event_manager.publish(project_id, "artifact_unlocked", {
            "project_id": project_id,
            "artifact_type": artifact_type,
            "artifact_id": artifact_id,
        })
        return {
            "status": "unlocked",
            "artifact": lock_info
        }
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/api/project/{project_id}/artifacts/{artifact_type}/{artifact_id}/lock-status", status_code=status.HTTP_200_OK)
async def get_artifact_lock_status(
    project_id: str,
    artifact_type: str,
    artifact_id: str,
    session: AsyncSession = Depends(get_db)
):
    """
    Get the lock status of any artifact.
    """
    from app.lock_service import LockService

    try:
        UUID(project_id)
        UUID(artifact_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project_id or artifact_id format")

    # Validate artifact type
    if artifact_type not in VALID_ARTIFACT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid artifact_type. Must be one of: {', '.join(VALID_ARTIFACT_TYPES)}"
        )

    try:
        lock_info = await LockService.get_lock_status(artifact_type, artifact_id, session, project_id=project_id)
        return lock_info
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ==========================================
# PENDING ACTIONS API
# ==========================================

@router.get("/api/pending-actions/{project_id}")
async def get_pending_actions(project_id: str, session: AsyncSession = Depends(get_db)):
    actions = await PendingActionRepository.get_by_project(project_id, session)
    return actions


@router.post("/api/confirm-action/{action_id}")
async def confirm_action(action_id: str, project_id: str, session: AsyncSession = Depends(get_db)):
    # 0. LOCK ENFORCEMENT: Cannot confirm an action on a locked project
    from app.lock_service import LockService, ArtifactLockError
    try:
        UUID(project_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project_id format")
    try:
        lock_info = await LockService.get_lock_status("project", project_id, session, project_id=project_id)
        LockService.raise_if_locked("project", project_id, lock_info)
    except ArtifactLockError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    # 1. Get the action
    actions = await PendingActionRepository.get_by_project(project_id, session)
    action = next((a for a in actions if a["id"] == action_id), None)

    if not action:
        raise HTTPException(status_code=404, detail="Pending action not found")

    # 2. Extract the proposed changes (the full merged requirement state)
    proposed_changes = action.get("proposed_changes", {})
    if not proposed_changes:
        await PendingActionRepository.delete(action_id, project_id, session)
        raise HTTPException(status_code=400, detail="No proposed changes found in pending action")

    # 3. Apply proposed changes to the database
    logger.info(f"[MERGE CONFIRM] Persisting merged state for project {project_id}...")
    persisted_state = await RequirementStateRepository.save_or_update(project_id, proposed_changes, session)

    # 4. Delete the pending action
    await PendingActionRepository.delete(action_id, project_id, session)

    await event_manager.publish(project_id, "merge_confirmed", {
        "project_id": project_id,
        "action_id": action_id,
    })

    logger.info(f"[MERGE CONFIRM] Merge confirmed and persisted for project {project_id}")
    return {
        "status": "confirmed",
        "requirement_state": persisted_state
    }


@router.post("/api/cancel-action/{action_id}")
async def cancel_action(action_id: str, project_id: str, session: AsyncSession = Depends(get_db)):
    await PendingActionRepository.delete(action_id, project_id, session)
    await event_manager.publish(project_id, "action_cancelled", {
        "project_id": project_id,
        "action_id": action_id,
    })
    return {"status": "cancelled"}