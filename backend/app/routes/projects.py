import logging
import uuid
from typing import Dict, Any, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.repository import (
    ProjectRepository,
    RequirementStateRepository,
    ConversationMessageRepository,
    PRDVersionRepository,
)
from app.schemas import (
    ProjectCreate,
    ProjectSummary,
    ProjectCreated,
    ProjectDeleteResponse,
    RequirementStateResponse,
    ConversationMessageResponse,
    PRDVersionResponse,
    PRDExportResponse,
)
from app.llm_client import call_lm_studio
from app.event_manager import event_manager

logger = logging.getLogger("app.routes.projects")

router = APIRouter()


@router.get("/api/projects", response_model=List[ProjectSummary], status_code=status.HTTP_200_OK)
async def get_projects(db: AsyncSession = Depends(get_db)) -> List[ProjectSummary]:
    """
    List all projects.

    Args:
        db: Active asynchronous database session.

    Returns:
        List[ProjectSummary]: All project summary records.
    """
    return await ProjectRepository.list_all(db)


@router.post("/api/projects", response_model=ProjectCreated, status_code=status.HTTP_201_CREATED)
async def create_project(payload: ProjectCreate, db: AsyncSession = Depends(get_db)) -> ProjectCreated:
    """
    Create a new project and initialize its requirement state.

    Args:
        payload: Project creation payload.
        db: Active asynchronous database session.

    Returns:
        ProjectCreated: The new project's UUID string and name.
    """
    project_data = payload.dict()
    project_data["id"] = str(uuid.uuid4())
    # Use system user UUID as default until proper auth is implemented
    project_data["user_id"] = "00000000-0000-0000-0000-000000000000"
    created_project = await ProjectRepository.create_project(project_data, db)
    await event_manager.publish(str(project_data["id"]), "project_created", {"project_id": project_data["id"]})
    return created_project


@router.put("/api/projects/{project_id}", response_model=ProjectSummary, status_code=status.HTTP_200_OK)
async def update_project(project_id: str, payload: ProjectCreate, db: AsyncSession = Depends(get_db)) -> ProjectSummary:
    """
    Update an existing project (rename).

    Args:
        project_id: Project UUID string.
        payload: Updated project fields.
        db: Active asynchronous database session.

    Returns:
        ProjectSummary: The updated project record.

    Raises:
        HTTPException: 400 if ``project_id`` is not a valid UUID; 404 if not found.
    """
    try:
        UUID(project_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project_id format")

    updates = payload.dict()
    updated = await ProjectRepository.update(project_id, updates, db)
    if not updated:
        raise HTTPException(status_code=404, detail="Project not found")
    await event_manager.publish(project_id, "project_updated", {
        "project_id": project_id,
        "name": updates.get("name")
    })
    return updated


@router.delete("/api/projects/{project_id}", response_model=ProjectDeleteResponse, status_code=status.HTTP_200_OK)
async def delete_project(project_id: str, db: AsyncSession = Depends(get_db)) -> ProjectDeleteResponse:
    """
    Delete an existing project.

    Args:
        project_id: Project UUID string.
        db: Active asynchronous database session.

    Returns:
        ProjectDeleteResponse: Confirmation containing the deleted project ID.

    Raises:
        HTTPException: 400 if ``project_id`` is not a valid UUID; 404 if not found.
    """
    try:
        UUID(project_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project_id format")

    deleted = await ProjectRepository.delete(project_id, db)
    if not deleted:
        raise HTTPException(status_code=404, detail="Project not found")
    await event_manager.publish(project_id, "project_deleted", {"project_id": project_id})
    return {"status": "deleted", "project_id": project_id}


@router.get("/api/project/{project_id}", response_model=RequirementStateResponse, status_code=status.HTTP_200_OK)
async def get_project_requirement_state(project_id: str, session: AsyncSession = Depends(get_db)) -> RequirementStateResponse:
    """
    Retrieves the centralized RequirementState for a project from Supabase.

    If it doesn't exist, returns default initialized values. Includes the
    persisted conversation history for the project.

    Args:
        project_id: Project UUID string.
        session: Active asynchronous database session.

    Returns:
        RequirementStateResponse: The flattened requirement state.

    Raises:
        HTTPException: 400 if ``project_id`` is not a valid UUID.
    """
    try:
        UUID(project_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project_id format")

    logger.info(f"[DB LOG] Loading RequirementState for project {project_id}")
    state = await RequirementStateRepository.get_by_project_id(project_id, session)
    logger.info(f"[DB LOG] Loading RequirementState for project {project_id} complete. Found: {state is not None}")
    if not state:
        state = {
            "project_id": project_id,
            "project_name": "PromptPay Settlement Engine",
            "requirements": [
                {
                    "requirement_code": "REQ-001",
                    "title": "PromptPay Real-Time Merchant Settlement Engine",
                    "description": "Main epic for PromptPay settlement",
                    "user_stories": []
                }
            ],
            "business_goals": [],
            "actors": [],
            "user_stories": [
                {
                    "ticket_code": "US-001",
                    "story_title": "Real-time Fund Settlement via QR Scan",
                    "as_a": "Corporate Merchant Retailer",
                    "i_want_to": "receive instant notifications and settlement when a customer scans my PromptPay QR code",
                    "so_that": "I can verify payment immediately and dispense goods without settlement delay",
                    "acceptance_criteria": [
                        "Given a customer has scanned a valid static PromptPay QR code, When the transaction is approved by the national switch, Then the funds are instantly credited to the corporate account.",
                        "Given the system detects a network timeout during national switch callback, When the transaction is retried, Then an explicit idempotency key must be checked to prevent double posting."
                    ]
                }
            ],
            "acceptance_criteria": [
                "Given a customer has scanned a valid static PromptPay QR code, When the transaction is approved by the national switch, Then the funds are instantly credited to the corporate account.",
                "Given the system detects a network timeout during national switch callback, When the transaction is retried, Then an explicit idempotency key must be checked to prevent double posting."
            ],
            "clarification_questions": [],
            "validation_status": "pending",
            "generated_prd": "",
            "generated_diagrams": "",
            "current_workflow_state": "gatherer_node",
            "version_number": 1,
            "updated_at": None
        }
        # Save default to database
        logger.info(f"[DB LOG] Saving default state for project {project_id}...")
        state = await RequirementStateRepository.save_or_update(project_id, state, session)
        logger.info(f"[DB LOG] Saving default state for project {project_id} complete.")
        await event_manager.publish(project_id, "state_initialized", {"project_id": project_id})

    conv_history = await ConversationMessageRepository.get_conversation_history(project_id)
    if isinstance(state, dict):
        state = dict(state)
        state["conversation_history"] = conv_history
    return state


@router.get("/api/project/{project_id}/conversations", response_model=List[ConversationMessageResponse], status_code=status.HTTP_200_OK)
async def get_project_conversations(project_id: str) -> List[ConversationMessageResponse]:
    """
    Retrieve the persisted conversation history for a project.

    Args:
        project_id: Project UUID string.

    Returns:
        List[ConversationMessageResponse]: All conversation messages, oldest first.

    Raises:
        HTTPException: 400 if ``project_id`` is not a valid UUID.
    """
    try:
        UUID(project_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project_id format")
    return await ConversationMessageRepository.get_conversation_history(project_id)


@router.put("/api/project/{project_id}", response_model=RequirementStateResponse, status_code=status.HTTP_200_OK)
async def update_project_requirement_state(project_id: str, updates: Dict[str, Any], session: AsyncSession = Depends(get_db)) -> RequirementStateResponse:
    """
    Directly updates the centralized RequirementState for a project in the database.

    Useful for saving manual PRD edits and synchronizing sections. Refuses to
    mutate a locked project.

    Args:
        project_id: Project UUID string.
        updates: Partial requirement-state payload to apply.
        session: Active asynchronous database session.

    Returns:
        RequirementStateResponse: The updated, flattened requirement state.

    Raises:
        HTTPException: 400 if ``project_id`` is not a valid UUID; 409 if the
            project is locked; 404 if the project cannot be resolved.
    """
    try:
        UUID(project_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project_id format")

    # LOCK ENFORCEMENT: Cannot update requirement state of a locked project
    from app.lock_service import LockService, ArtifactLockError
    try:
        lock_info = await LockService.get_lock_status("project", project_id, session, project_id=project_id)
        LockService.raise_if_locked("project", project_id, lock_info)
    except ArtifactLockError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    logger.info(f"[DB LOG] Updating RequirementState directly for project {project_id}")
    state = await RequirementStateRepository.save_or_update(project_id, updates, session)
    await event_manager.publish(project_id, "state_updated", {"project_id": project_id})
    return state


@router.post("/api/prd/export/{project_id}", response_model=PRDExportResponse, status_code=status.HTTP_200_OK)
async def post_prd_export_generation(project_id: UUID, db: AsyncSession = Depends(get_db)) -> PRDExportResponse:
    """
    Gathers linked user stories and acceptance criteria from the database,
    dispatches them to the local LLM, and returns a clean, finalized
    Production PRD document structured in markdown.

    A new immutable PRD version record is persisted on success.

    Args:
        project_id: Project UUID.
        db: Active asynchronous database session.

    Returns:
        PRDExportResponse: The generated PRD markdown, diagram, version and
            version record ID.

    Raises:
        HTTPException: 404 if the project or its requirement state is missing.
    """
    logger.info(f"Triggering automated compliance PRD synthesis for project {project_id}.")

    # Validate project existence
    project = await ProjectRepository.get_by_id(str(project_id), db)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

    # Fetch the real requirement state: requirements, user stories, and acceptance criteria
    req_state = await RequirementStateRepository.get_by_project_id(str(project_id), db)
    if not req_state:
        raise HTTPException(
            status_code=404,
            detail=f"No requirement state found for project {project_id}. Gather requirements before exporting a PRD."
        )

    requirements = req_state.get("requirements", []) or []
    user_stories = req_state.get("user_stories", []) or []
    acceptance_criteria = req_state.get("acceptance_criteria", []) or []
    business_goals = req_state.get("business_goals", []) or []
    actors = req_state.get("actors", []) or []
    version_number = req_state.get("version_number", 1)

    if not user_stories and not requirements:
        raise HTTPException(
            status_code=404,
            detail=f"No user stories or requirements found for project {project_id}. Gather requirements before exporting a PRD."
        )

    # Build a real context payload for the LLM from actual persisted artifacts
    payload_sections = []

    if business_goals:
        payload_sections.append("## Business Goals")
        for goal in business_goals:
            if isinstance(goal, dict):
                payload_sections.append(f"- {goal.get('description', goal)}")
            else:
                payload_sections.append(f"- {goal}")

    if actors:
        payload_sections.append("## Actors")
        for actor in actors:
            if isinstance(actor, dict):
                payload_sections.append(f"- {actor.get('name', actor)}")
            else:
                payload_sections.append(f"- {actor}")

    if requirements:
        payload_sections.append("## Requirements")
        for req in requirements:
            req_title = req.get("title") or req.get("requirement_code") or "Untitled Requirement"
            payload_sections.append(f"\n### {req.get('requirement_code', 'REQ')}: {req_title}")
            if req.get("description"):
                payload_sections.append(f"Description: {req['description']}")
            for story in req.get("user_stories", []):
                story_ac = story.get("acceptance_criteria", []) or []
                payload_sections.append(
                    f"- [{story.get('ticket_code', 'US-000')}] {story.get('story_title', 'Untitled Story')}\n"
                    f"  As a {story.get('as_a', '')}, I want to {story.get('i_want_to', '')} "
                    f"so that {story.get('so_that', '')}."
                )
                for ac in story_ac:
                    payload_sections.append(f"  - Acceptance Criteria: {ac}")
    else:
        payload_sections.append("## User Stories")
        for story in user_stories:
            payload_sections.append(
                f"- [{story.get('ticket_code', 'US-000')}] {story.get('story_title', 'Untitled Story')}\n"
                f"  As a {story.get('as_a', '')}, I want to {story.get('i_want_to', '')} "
                f"so that {story.get('so_that', '')}."
            )
        if acceptance_criteria:
            payload_sections.append("\n## Acceptance Criteria")
            for ac in acceptance_criteria:
                if isinstance(ac, dict):
                    payload_sections.append(f"- {ac.get('criteria_text', ac)}")
                else:
                    payload_sections.append(f"- {ac}")

    system_payload_description = "\n".join(payload_sections)

    prompt = [
        {
            "role": "system",
            "content": (
                "You are a senior system architect. Synthesize the provided project requirements "
                "into a formal, compliant Product Requirements Document (PRD) in markdown format. "
                "Include a mermaid sequence diagram when describing core system flows."
            )
        },
        {
            "role": "user",
            "content": (
                f"Synthesize a formal PRD for project {project_id} "
                f"(Project: {project.get('name', 'N/A')}, Version {version_number}).\n\n"
                f"Persisted Requirements Data:\n{system_payload_description}"
            )
        }
    ]

    prd_response = await call_lm_studio(prompt)
    markdown_content = prd_response.get("text", "# PRD\n\nFailed to synthesize PRD.")

    # Persist the newly generated PRD as an immutable version record
    version_record = None
    try:
        version_record = await PRDVersionRepository.create(str(project_id), {
            "generated_prd": markdown_content,
            "generated_diagram": "",
            "generated_by": "prd_export_endpoint"
        }, db)
        logger.info(f"[PRD EXPORT] Created PRD version {version_record['version_number']} for project {project_id}.")
    except Exception as version_err:
        logger.error(f"[PRD EXPORT] Failed to create PRD version: {str(version_err)}")

    await event_manager.publish(str(project_id), "prd_exported", {
        "project_id": str(project_id),
        "version": version_record["version_number"] if version_record else version_number,
    })

    return {
        "project_id": project_id,
        "version": version_record["version_number"] if version_record else version_number,
        "version_id": version_record["version_id"] if version_record else None,
        "prd_markdown": markdown_content,
        "mermaid_diagram": ""
    }


# ==========================================
# PRD VERSION HISTORY API
# ==========================================

@router.get("/api/project/{project_id}/prd-versions", response_model=List[PRDVersionResponse], status_code=status.HTTP_200_OK)
async def get_prd_versions(project_id: str, session: AsyncSession = Depends(get_db)) -> List[PRDVersionResponse]:
    """
    Retrieves all PRD versions for a project.

    Args:
        project_id: Project UUID string.
        session: Active asynchronous database session.

    Returns:
        List[PRDVersionResponse]: Immutable PRD version records, newest first.

    Raises:
        HTTPException: 400 if ``project_id`` is not a valid UUID.
    """
    try:
        UUID(project_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project_id format")

    versions = await PRDVersionRepository.get_by_project(project_id, session)
    return versions


@router.get("/api/project/{project_id}/prd-versions/latest", response_model=PRDVersionResponse, status_code=status.HTTP_200_OK)
async def get_latest_prd_version(project_id: str, session: AsyncSession = Depends(get_db)) -> PRDVersionResponse:
    """
    Retrieves the latest PRD version for a project.

    Args:
        project_id: Project UUID string.
        session: Active asynchronous database session.

    Returns:
        PRDVersionResponse: The most recent immutable PRD version record.

    Raises:
        HTTPException: 400 if ``project_id`` is not a valid UUID; 404 if no
            PRD versions exist for the project.
    """
    try:
        UUID(project_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project_id format")

    version = await PRDVersionRepository.get_latest(project_id, session)
    if not version:
        raise HTTPException(status_code=404, detail="No PRD versions found for this project")
    return version


@router.get("/api/project/{project_id}/prd-versions/{version_number}", response_model=PRDVersionResponse, status_code=status.HTTP_200_OK)
async def get_prd_version_by_number(project_id: str, version_number: int, session: AsyncSession = Depends(get_db)) -> PRDVersionResponse:
    """
    Retrieves a specific PRD version by version number.

    Args:
        project_id: Project UUID string.
        version_number: Monotonic PRD version number.
        session: Active asynchronous database session.

    Returns:
        PRDVersionResponse: The requested immutable PRD version record.

    Raises:
        HTTPException: 400 if ``project_id`` is not a valid UUID; 404 if the
            requested version does not exist for the project.
    """
    try:
        UUID(project_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project_id format")

    version = await PRDVersionRepository.get_by_version_number(project_id, version_number, session)
    if not version:
        raise HTTPException(status_code=404, detail=f"PRD version {version_number} not found for this project")
    return version