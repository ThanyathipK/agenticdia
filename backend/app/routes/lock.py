import logging
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import AuthenticatedUser, require_project_owner
from app.database import get_db
from app.repositories import PendingActionRepository, RequirementStateRepository
from app.schemas import (
    ArtifactLockRequest,
    ArtifactLockResponse,
    LockStatusResponse,
    PendingActionResponse,
    ConfirmActionResponse,
    ActionStatusResponse,
    ImpactAnalysisResponse,
)
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

@router.post("/api/project/{project_id}/artifacts/{artifact_type}/{artifact_id}/lock", response_model=ArtifactLockResponse, status_code=status.HTTP_200_OK)
async def lock_artifact(
    project_id: str,
    artifact_type: str,
    artifact_id: str,
    payload: ArtifactLockRequest,
    current_user: AuthenticatedUser = Depends(require_project_owner),
    session: AsyncSession = Depends(get_db)
) -> ArtifactLockResponse:
    """
    Generic lock endpoint for any artifact type.

    Supported types: project, epic, requirement, user_story, acceptance_criteria,
    clarification_question, prd_document.

    Args:
        project_id: Owning project UUID string.
        artifact_type: One of the supported artifact types.
        artifact_id: Artifact UUID string.
        payload: Optional locking identity and reason.
        session: Active asynchronous database session.

    Returns:
        ArtifactLockResponse: Confirmation with the artifact's lock metadata.

    Raises:
        HTTPException: 400 on invalid IDs or unsupported artifact type; 409 if
            the artifact is already locked; 404 if the artifact is not found.
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


@router.post("/api/project/{project_id}/artifacts/{artifact_type}/{artifact_id}/unlock", response_model=ArtifactLockResponse, status_code=status.HTTP_200_OK)
async def unlock_artifact(
    project_id: str,
    artifact_type: str,
    artifact_id: str,
    payload: ArtifactLockRequest,
    current_user: AuthenticatedUser = Depends(require_project_owner),
    session: AsyncSession = Depends(get_db)
) -> ArtifactLockResponse:
    """
    Generic unlock endpoint for any artifact type.

    Args:
        project_id: Owning project UUID string.
        artifact_type: One of the supported artifact types.
        artifact_id: Artifact UUID string.
        payload: Optional unlocking identity.
        session: Active asynchronous database session.

    Returns:
        ArtifactLockResponse: Confirmation with the artifact's lock metadata.

    Raises:
        HTTPException: 400 on invalid IDs or unsupported artifact type; 409 if
            locked by a different user; 404 if the artifact is not found.
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


@router.get("/api/project/{project_id}/artifacts/{artifact_type}/{artifact_id}/lock-status", response_model=LockStatusResponse, status_code=status.HTTP_200_OK)
async def get_artifact_lock_status(
    project_id: str,
    artifact_type: str,
    artifact_id: str,
    current_user: AuthenticatedUser = Depends(require_project_owner),
    session: AsyncSession = Depends(get_db)
) -> LockStatusResponse:
    """
    Get the lock status of any artifact.

    Args:
        project_id: Owning project UUID string.
        artifact_type: One of the supported artifact types.
        artifact_id: Artifact UUID string.
        session: Active asynchronous database session.

    Returns:
        LockStatusResponse: The artifact's lock metadata.

    Raises:
        HTTPException: 400 on invalid IDs or unsupported artifact type; 404 if
            the artifact is not found.
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

# CONFIRM 3.1 — READ: staged actions (CONFIRM 2.1 / 1.7). Auth: AUTH 7.5 ownership.
#             Only rows still WAITING_CONFIRMATION are returned (repository 5.2); the
#             response carries `full=True` proposed_changes so the panel can render
#             the draft without a second call.
@router.get("/api/pending-actions/{project_id}", response_model=List[PendingActionResponse], status_code=status.HTTP_200_OK)
async def get_pending_actions(
    project_id: str,
    current_user: AuthenticatedUser = Depends(require_project_owner),
    session: AsyncSession = Depends(get_db),
) -> List[PendingActionResponse]:
    """
    Retrieve all pending (awaiting-confirmation) actions for a project.

    Args:
        project_id: Project UUID string.
        session: Active asynchronous database session.

    Returns:
        List[PendingActionResponse]: Pending actions for the project.
    """
    actions = await PendingActionRepository.get_by_project(project_id, session)
    return actions


# CONFIRM 3.2 — READ-ONLY impact preview for one staged action (CONFIRM 2.2 / 1.5).
#             Auth: AUTH 7.5. Branches: 400 invalid ids → 404 action not in this
#             project → ImpactService.analyze_pending_action (CONFIRM 4.x).
#             Writes nothing (note: the action is located via the project's pending
#             list, so an action id from another project is invisible → 404).
@router.get("/api/pending-actions/{action_id}/impact", response_model=ImpactAnalysisResponse, status_code=status.HTTP_200_OK)
async def get_action_impact(
    action_id: str,
    project_id: str,
    current_user: AuthenticatedUser = Depends(require_project_owner),
    session: AsyncSession = Depends(get_db),
) -> ImpactAnalysisResponse:
    """
    Requirement Impact Analysis for a pending merge action (READ-ONLY).

    Diffs the draft's proposed requirement state against the stored state and
    derives every downstream artifact impacted by the change — user stories,
    acceptance criteria, PRD sections and diagrams that reference the affected
    ``REQ-``/``US-`` codes — so the merge window can show the user what
    changes and what is impacted BEFORE they decide to Save or Cancel.

    Args:
        action_id: Pending-action UUID string.
        project_id: Project UUID string.
        session: Active asynchronous database session.

    Returns:
        ImpactAnalysisResponse: Change predictions + impacted artifacts.

    Raises:
        HTTPException: 400 on invalid IDs; 404 if the action does not exist.
    """
    from app.impact_service import ImpactService

    try:
        UUID(project_id)
        UUID(action_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project_id or action_id format")

    actions = await PendingActionRepository.get_by_project(project_id, session)
    action = next((a for a in actions if a["id"] == action_id), None)
    if not action:
        raise HTTPException(status_code=404, detail="Pending action not found")

    analysis = await ImpactService.analyze_pending_action(action, project_id, session)
    return analysis


# CONFIRM 3.3 — THE ONLY PATH THAT PERSISTS AI OUTPUT (CONFIRM 2.3 / 1.2). Everything
#             the agents produced before this point is a pending-action draft.
#             Branch map:
#               3.3.1 UUID format 400
#               3.3.2 project artifact lock gate → 409 (locked) / 404 (unresolvable)
#               3.3.3 action lookup within this project → 404
#               3.3.4 empty proposed_changes → action deleted + 400 (nothing to apply)
#               3.3.5 RequirementStateRepository.save_or_update ← THE WRITE
#                     (PROJECT 8.2.2: requirement_states + requirements / epics /
#                      user_stories / acceptance_criteria / audit_results /
#                      clarification_questions / prd_documents)
#               3.3.6 document-extraction bookkeeping (only INSERT_CHUNKED_REQUIREMENTS)
#               3.3.7 version ledger row (pinned version, fail-soft)
#               3.3.8 pending action deleted (the row IS the state; it is not "applied")
#               3.3.9 SSE "merge_confirmed" → clients refresh
#               3.3.10 response {status, requirement_state}
@router.post("/api/confirm-action/{action_id}", response_model=ConfirmActionResponse, status_code=status.HTTP_200_OK)
async def confirm_action(
    action_id: str,
    project_id: str,
    current_user: AuthenticatedUser = Depends(require_project_owner),
    session: AsyncSession = Depends(get_db),
) -> ConfirmActionResponse:
    """
    Confirm a pending merge action, applying its proposed changes to the database.

    Refuses to confirm when the project is locked.

    Args:
        action_id: Pending-action UUID string.
        project_id: Project UUID string.
        session: Active asynchronous database session.

    Returns:
        ConfirmActionResponse: The persisted, merged requirement state.

    Raises:
        HTTPException: 400 on invalid project ID or missing proposed changes;
            404 if the action does not exist; 409 if the project is locked.
    """
    from app.lock_service import LockService, ArtifactLockError
    try:
        UUID(project_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project_id format")
    # CONFIRM 3.3.2 — Lock gate (coarse, project-level): a locked project refuses the
    #               merge with 409; an unresolvable project id becomes 404. This is
    #               what stops an AI merge from overwriting a frozen baseline.
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
    # CONFIRM 3.3.5 — THE WRITE (the single point where a staged draft becomes real
    #               data). Reuses the PROJECT 8.2.2 repository step: create-if-missing,
    #               else partial update that rebuilds the child tables from the lists
    #               supplied in the draft. Committed by the request's get_db on success.
    persisted_state = await RequirementStateRepository.save_or_update(project_id, proposed_changes, session)

    # 3b. Document-extraction merges (INSERT_CHUNKED_REQUIREMENTS): flip the
    # source document's extraction flag and append the audit-log entry. The
    # draft was created by POST .../documents/{id}/process; THIS is the only
    # point at which document-derived requirements ever reach the DB.
    # CONFIRM 3.3.6 — Document-extraction bookkeeping (only for drafts staged by the
    #               DOCUMENT EXTRACTION flow, identified by `_document_ref` in the
    #               draft): flip uploaded_documents.extraction_status to
    #               "extraction_applied" and append an artifact_event_logs entry.
    #               Fail-soft: a logging failure never blocks the confirmed merge.
    document_ref = proposed_changes.get("_document_ref") or {}
    if action.get("action_type") == "INSERT_CHUNKED_REQUIREMENTS" and document_ref.get("document_id"):
        from app.repositories import ArtifactEventLogRepository, DocumentRepository

        await DocumentRepository.update_extraction_status(
            str(document_ref["document_id"]), project_id, "extraction_applied", session
        )
        try:
            await ArtifactEventLogRepository.log_event(
                artifact_type="uploaded_document",
                artifact_id=str(document_ref["document_id"]),
                action="CREATE",
                session=session,
                old_value=None,
                new_value={
                    "document_filename": document_ref.get("document_filename"),
                    "pending_action_id": action_id,
                    "applied_version": persisted_state.get("version_number"),
                },
                performed_by="user",
            )
        except Exception as log_err:  # never block a confirmed merge on logging
            logger.warning(f"[MERGE CONFIRM] Failed to log document merge event: {log_err}")

    # 3c. VERSION LEDGER — log EVERY confirmed merge as its own immutable
    # version row so the Version History records AI/chat merges too, not only
    # manual part edits / Generate PRD. A requirement merge does not change the
    # PRD document content itself; the row exists to log the merge event and
    # keep the version ledger in lock-step with the requirement version.
    try:
        from app.repositories.prd import PRDVersionRepository
        from app.version_service import record_prd_version

        latest_ledger = await PRDVersionRepository.get_latest(project_id, session)
        # Pin the ledger row to the requirement state's OWN version when it
        # already advanced exactly once (e.g. document-extraction drafts store
        # version_number + 1) — otherwise take the next free ledger number.
        # Never collides, never double-bumps.
        # CONFIRM 3.3.7 — Version ledger (VERSIONING flow): every confirmed merge gets
        #               its own immutable prd_versions row. `pinned_version` is the max
        #               of the draft's own version and the next free ledger number, so
        #               a draft that already bumped (document extraction) cannot
        #               double-bump. record_prd_version re-writes
        #               requirement_states.version_number, hence the re-read below.
        #               Fail-soft: a ledger failure is logged, the merge stays applied.
        pinned_version = max(
            int(persisted_state.get("version_number") or 1),
            int((latest_ledger or {}).get("version_number") or 0) + 1,
        )
        merge_note = (action.get("original_user_message") or "").strip()
        story_count = len(proposed_changes.get("user_stories") or []) if isinstance(proposed_changes, dict) else 0
        quoted = (merge_note[:180] + "…") if len(merge_note) > 180 else merge_note
        merge_summary = (
            f"Requirements merge confirmed (Save): \"{quoted or 'no message'}\""
            + (f" — {story_count} user stories" if story_count else "")
        )
        await record_prd_version(
            project_id, session,
            generated_prd=persisted_state.get("generated_prd") or "",
            generated_by="ai_merge",
            change_type="ai",
            change_summary=merge_summary,
            version_number=pinned_version,
        )
        # record_prd_version re-synced requirement_states.version_number to the
        # pinned ledger row; re-read so the response carries the final version.
        persisted_state = await RequirementStateRepository.get_by_project_id(project_id, session) or persisted_state
        logger.info(
            "[MERGE CONFIRM] Merge logged as version %d for project %s",
            pinned_version, project_id,
        )
    except Exception as ledger_err:  # NEVER block a confirmed merge on ledger logging
        logger.warning(f"[MERGE CONFIRM] Failed to log merge into the version ledger: {ledger_err}")

    # CONFIRM 3.3.8 — The action row is DELETED, never marked "applied": the pending
    #               action carries the only copy of the draft, and its absence is what
    #               tells the UI the gate is closed (3.4 does the same on Cancel).
    # 4. Delete the pending action
    await PendingActionRepository.delete(action_id, project_id, session)

    # CONFIRM 3.3.9 — Real-time fan-out: other clients (and this one, debounced)
    #               re-read the project state (EVENTS flow).
    await event_manager.publish(project_id, "merge_confirmed", {
        "project_id": project_id,
        "action_id": action_id,
    })

    logger.info(f"[MERGE CONFIRM] Merge confirmed and persisted for project {project_id}")
    return {
        "status": "confirmed",
        "requirement_state": persisted_state
    }


# CONFIRM 3.4 — Discard path (CONFIRM 2.4 / 1.4): delete the staged action and nothing
#             else — the persisted project is untouched, so no lock check is needed
#             (there is nothing to overwrite). SSE "action_cancelled" closes the gate
#             on every connected client.
@router.post("/api/cancel-action/{action_id}", response_model=ActionStatusResponse, status_code=status.HTTP_200_OK)
async def cancel_action(
    action_id: str,
    project_id: str,
    current_user: AuthenticatedUser = Depends(require_project_owner),
    session: AsyncSession = Depends(get_db),
) -> ActionStatusResponse:
    """
    Cancel (delete) a pending action without applying its proposed changes.

    Args:
        action_id: Pending-action UUID string.
        project_id: Project UUID string.
        session: Active asynchronous database session.

    Returns:
        ActionStatusResponse: Confirmation with status 'cancelled'.
    """
    await PendingActionRepository.delete(action_id, project_id, session)
    await event_manager.publish(project_id, "action_cancelled", {
        "project_id": project_id,
        "action_id": action_id,
    })
    return {"status": "cancelled"}