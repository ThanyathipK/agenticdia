import logging
from typing import Dict, Any, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.rate_limit import rate_limit_dependency
from app.input_validation import validate_text_budget, validate_body_budget
from app.repositories import (
    RequirementRepository,
    RequirementStateRepository,
    ConversationMessageRepository,
    PendingActionRepository,
)
from app.schemas import (
    ProcessRequirementsRequest,
    RequirementLockRequest,
    UserAnswerSubmit,
    WorkflowRouterRequest,
    IntentDetectorRequest,
    RequirementMatcherRequest,
    RequirementDetail,
    RequirementLockResponse,
    AuditRespondResponse,
    RequirementStateResponse,
    ProcessRequirementsResponse,
    WorkflowRoutingResult,
    RequirementIntentDetectionResult,
    RequirementMatcherResult,
)
from app.agents import prd_workflow
from app.event_manager import event_manager

logger = logging.getLogger("app.routes.requirements")

router = APIRouter()


# ==========================================
# REQUIREMENT CRUD API
# ==========================================

@router.get("/api/project/{project_id}/requirements", response_model=List[RequirementDetail], status_code=status.HTTP_200_OK)
async def get_project_requirements(project_id: str, session: AsyncSession = Depends(get_db)) -> List[RequirementDetail]:
    """
    Retrieve all requirements for a project, including lock status.

    Args:
        project_id: Project UUID string.
        session: Active asynchronous database session.

    Returns:
        List[RequirementDetail]: All requirement records for the project.

    Raises:
        HTTPException: 400 if ``project_id`` is not a valid UUID.
    """
    try:
        UUID(project_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project_id format")

    requirements = await RequirementRepository.get_by_project(project_id, session)
    return requirements


@router.get("/api/project/{project_id}/requirements/{requirement_id}", response_model=RequirementDetail, status_code=status.HTTP_200_OK)
async def get_requirement(project_id: str, requirement_id: str, session: AsyncSession = Depends(get_db)) -> RequirementDetail:
    """
    Retrieve a single requirement by ID, including lock status.

    Args:
        project_id: Project UUID string.
        requirement_id: Requirement UUID string.
        session: Active asynchronous database session.

    Returns:
        RequirementDetail: The requested requirement record.

    Raises:
        HTTPException: 400 if either ID is not a valid UUID; 404 if not found.
    """
    try:
        UUID(project_id)
        UUID(requirement_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project_id or requirement_id format")

    requirement = await RequirementRepository.get_by_id(requirement_id, project_id, session)
    if not requirement:
        raise HTTPException(status_code=404, detail="Requirement not found")
    return requirement


# ==========================================
# REQUIREMENT LOCK / UNLOCK API
# ==========================================

@router.post("/api/project/{project_id}/requirements/{requirement_id}/lock", response_model=RequirementLockResponse, status_code=status.HTTP_200_OK)
async def lock_requirement(
    project_id: str,
    requirement_id: str,
    payload: RequirementLockRequest,
    session: AsyncSession = Depends(get_db)
) -> RequirementLockResponse:
    """
    Lock a requirement so it cannot be updated, deleted, merged, or modified by AI.

    Args:
        project_id: Project UUID string.
        requirement_id: Requirement UUID string.
        payload: Optional locking identity and reason.
        session: Active asynchronous database session.

    Returns:
        RequirementLockResponse: Confirmation with the locked requirement record.

    Raises:
        HTTPException: 400 if either ID is not a valid UUID; 404 if the
            requirement does not exist.
    """
    try:
        UUID(project_id)
        UUID(requirement_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project_id or requirement_id format")

    locked = await RequirementRepository.lock(
        requirement_id, project_id, session, locked_by=payload.locked_by or "user"
    )
    if not locked:
        raise HTTPException(status_code=404, detail="Requirement not found")
    await event_manager.publish(project_id, "requirement_locked", {
        "project_id": project_id,
        "requirement_id": requirement_id,
        "locked_by": payload.locked_by or "user",
    })
    return {
        "status": "locked",
        "requirement": locked
    }


@router.post("/api/project/{project_id}/requirements/{requirement_id}/unlock", response_model=RequirementLockResponse, status_code=status.HTTP_200_OK)
async def unlock_requirement(
    project_id: str,
    requirement_id: str,
    payload: RequirementLockRequest,
    session: AsyncSession = Depends(get_db)
) -> RequirementLockResponse:
    """
    Unlock a requirement so it can be modified again.

    Args:
        project_id: Project UUID string.
        requirement_id: Requirement UUID string.
        payload: Optional unlocking identity.
        session: Active asynchronous database session.

    Returns:
        RequirementLockResponse: Confirmation with the unlocked requirement record.

    Raises:
        HTTPException: 400 if either ID is not a valid UUID; 403 if locked by a
            different user; 404 if the requirement does not exist.
    """
    try:
        UUID(project_id)
        UUID(requirement_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project_id or requirement_id format")

    try:
        unlocked = await RequirementRepository.unlock(
            requirement_id, project_id, session, unlocked_by=payload.locked_by or "user"
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    if not unlocked:
        raise HTTPException(status_code=404, detail="Requirement not found")
    await event_manager.publish(project_id, "requirement_unlocked", {
        "project_id": project_id,
        "requirement_id": requirement_id,
        "unlocked_by": payload.locked_by or "user",
    })
    return {
        "status": "unlocked",
        "requirement": unlocked
    }


# ==========================================
# AUDIT / CLARIFICATION API
# ==========================================

@router.post("/api/audit/respond/{question_id}", response_model=AuditRespondResponse, status_code=status.HTTP_200_OK)
async def post_audit_resolution_reply(question_id: UUID, payload: UserAnswerSubmit, db: AsyncSession = Depends(get_db)) -> AuditRespondResponse:
    """
    Submits official BA/PO answer to close an active compliance query roadblock.

    Persists the resolution answer and marks the clarification question as resolved.

    Args:
        question_id: Clarification-question UUID.
        payload: The official stakeholder resolution text.
        db: Active asynchronous database session.

    Returns:
        AuditRespondResponse: Confirmation with the resolution timestamp.

    Raises:
        HTTPException: 404 if the clarification question does not exist.
    """
    from sqlalchemy import select
    from app.models import ClarificationQuestionModel
    from datetime import datetime

    logger.info(f"Updating clarification question {question_id} state with resolution.")

    db_query = select(ClarificationQuestionModel).where(ClarificationQuestionModel.id == question_id)
    result = await db.execute(db_query)
    question = result.scalar_one_or_none()
    if not question:
        raise HTTPException(status_code=404, detail=f"Clarification question {question_id} not found")

    question.user_answer = payload.answer_text
    question.is_resolved = True
    await db.commit()
    await db.refresh(question)

    logger.info(f"Clarification question {question_id} resolved successfully.")

    return {
        "status": "success",
        "message": f"Answer to clarification question {question_id} has been logged and registered.",
        "resolved_at": question.updated_at.isoformat() if question.updated_at else datetime.utcnow().isoformat(),
        "is_resolved": question.is_resolved
    }


@router.post("/api/clarification/submit", response_model=RequirementStateResponse, status_code=status.HTTP_200_OK)
async def post_clarification_submit(payload: Dict[str, Any], session: AsyncSession = Depends(get_db)) -> RequirementStateResponse:
    """
    Submits answers to clarification questions, runs Auditor compliance check,
    and updates workflow state.

    Args:
        payload: Dict containing ``project_id`` and a mapping of answers
            (``answers[`q-<idx>`]``).
        session: Active asynchronous database session.

    Returns:
        RequirementStateResponse: The updated requirement state.

    Raises:
        HTTPException: 400 if ``project_id`` is not a valid UUID; 409 if the
            project is locked; 404 if the project does not exist.
    """
    project_id = payload.get("project_id")
    answers = payload.get("answers", {})

    # LOCK ENFORCEMENT: Cannot submit clarification answers on a locked project
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

    req_state = await RequirementStateRepository.get_by_project_id(project_id, session)
    if not req_state:
        raise HTTPException(status_code=404, detail="Project not found")

    questions = req_state.get("clarification_questions", [])
    for idx, q in enumerate(questions):
        ans_key = f"q-{idx}"
        if ans_key in answers:
            q["user_answer"] = answers[ans_key]
            q["is_resolved"] = True

    req_state["clarification_questions"] = questions

    unresolved = [q for q in questions if not q.get("is_resolved", False)]
    is_valid = len(unresolved) == 0
    req_state["validation_status"] = "valid" if is_valid else "invalid"
    req_state["current_workflow_state"] = "REVIEWING" if is_valid else "WAITING_CLARIFICATION"

    saved_state = await RequirementStateRepository.save_or_update(project_id, req_state, session)
    await event_manager.publish(project_id, "clarification_submitted", {
        "project_id": project_id,
        "validation_status": req_state.get("validation_status"),
        "current_workflow_state": req_state.get("current_workflow_state"),
    })
    return saved_state


# ==========================================
# MULTI-AGENT PROCESS REQUIREMENTS API
# ==========================================

@router.post("/api/process-requirements", response_model=ProcessRequirementsResponse, status_code=status.HTTP_200_OK)
async def post_process_requirements(
    request: ProcessRequirementsRequest,
    session: AsyncSession = Depends(get_db),
    _rate_limit: None = Depends(
        rate_limit_dependency(
            "workflow", settings.RATE_LIMIT_WORKFLOW_LIMIT, settings.RATE_LIMIT_WORKFLOW_WINDOW
        )
    ),
) -> ProcessRequirementsResponse:
    """
    Asynchronously invokes the LangGraph multi-agent workflow (prd_workflow)
    to process raw requirements, audit compliance, or build PRD & architectural diagrams.
    Loads and updates the shared RequirementState from Supabase (as single source of truth).

    Pipeline:
    1. Persist every user message before intent detection
    2. Detect intent (GENERAL_CHAT, REQUIREMENT_REQUEST)
    3. If GENERAL_CHAT: generate response with project context, persist, return (no LangGraph)
    4. If REQUIREMENT_REQUEST: proceed to LangGraph workflow
    5. Persist every assistant response

    Args:
        request: Processing payload (project ID, raw input, target agent,
            structured requirements, version context).
        session: Active asynchronous database session.

    Returns:
        ProcessRequirementsResponse: The workflow outcome, structured
            requirements, audit result, PRD/diagram content, and pending merge
            metadata.

    Raises:
        HTTPException: 413 if the request payload (raw input + structured
            requirements) exceeds ``MAX_CONTEXT_TOKENS``; 500 if the
            multi-agent workflow execution fails.
    """
    from datetime import datetime, timedelta

    logger.info(f"Triggering on-demand {request.target_agent} agent for project {request.project_id}")

    # Finding #39: enforce MAX_CONTEXT_TOKENS on the incoming processing payload
    # (raw_input + structured_requirements) before spending any LLM budget.
    validate_body_budget(request.model_dump(), "Process-requirements request")

    # ==========================================
    # STEP 1: Persist every user message before any intent detection or agent routing
    # ==========================================
    if request.project_id and request.raw_input and request.raw_input.strip():
        await ConversationMessageRepository.save_message(
            project_id=str(request.project_id),
            role="user",
            message=request.raw_input.strip(),
            workflow_state=request.target_agent or "gatherer",
            intent="PENDING_DETECTION"
        )

    # ==========================================
    # STEP 2: Intent Detection (before LangGraph)
    # ==========================================
    from app.semantic_service import detect_requirement_intent, generate_general_chat_response

    # Load the centralized RequirementState from Supabase (single source of truth)
    logger.info(f"[DB LOG] Loading RequirementState for processing project {request.project_id}")
    req_state = await RequirementStateRepository.get_by_project_id(request.project_id, session)
    logger.info(f"[DB LOG] Loading RequirementState for processing project {request.project_id} complete. Found: {req_state is not None}")

    # Detect intent on the raw input
    detected_intent_result = await detect_requirement_intent(
        request.raw_input or "",
        req_state.get("user_stories", []) if req_state else []
    )
    detected_intent = detected_intent_result.get("intent", "GENERAL_CHAT")
    logger.info(f"[INTENT DETECTION] Detected intent: {detected_intent} (confidence: {detected_intent_result.get('confidence', 0.0)})")

    # ==========================================
    # STEP 3: GENERAL_CHAT handling (bypass LangGraph entirely)
    # ==========================================
    # If the intent is GENERAL_CHAT (greeting, question, explanation request, concept query),
    # generate an LLM response directly without entering any agent workflow.
    # REQUIREMENT_REQUEST intents fall through to the LangGraph workflow below.
    #
    # IMPORTANT: Explicit on-demand agent requests (e.g. "Generate PRD" button sends
    # target_agent="architect" with empty raw_input) MUST bypass the GENERAL_CHAT
    # short-circuit. Otherwise the empty raw_input defaults to GENERAL_CHAT and the
    # architect/auditor workflow never runs.
    on_demand_agents = ("architect", "auditor", "delete_requirement")
    if detected_intent == "GENERAL_CHAT" and request.target_agent not in on_demand_agents:
        logger.info("[GENERAL_CHAT] Handling as general chat. Generating conversational response with project context.")

        # Load conversation history for context (with error handling for DB failures)
        conv_history = []
        if request.project_id:
            try:
                conv_history = await ConversationMessageRepository.get_conversation_history(request.project_id)
            except Exception as db_err:
                logger.warning(f"[GENERAL_CHAT] Failed to load conversation history from DB: {str(db_err)}. Proceeding without history.")

        # Generate response with full project context
        try:
            response_text = await generate_general_chat_response(
                raw_input=request.raw_input or "",
                project_context=req_state or {},
                conversation_history=conv_history
            )
        except Exception as llm_err:
            logger.error(f"[GENERAL_CHAT] Failed to generate LLM response: {str(llm_err)}")
            response_text = "I understand your question, but I'm currently experiencing some technical difficulties. Please try again in a moment."

        # Persist assistant response (with error handling for DB failures)
        if request.project_id and response_text:
            try:
                await ConversationMessageRepository.save_message(
                    project_id=str(request.project_id),
                    role="assistant",
                    message=response_text,
                    workflow_state="general_chat",
                    intent="GENERAL_CHAT"
                )
            except Exception as db_err:
                logger.warning(f"[GENERAL_CHAT] Failed to save assistant response to DB: {str(db_err)}. Response generated but not persisted.")
            else:
                # Notify SSE subscribers so other connected clients refresh their conversation view.
                await event_manager.publish(str(request.project_id), "chat_reply", {
                    "project_id": str(request.project_id),
                    "intent": "GENERAL_CHAT",
                })

        # Return response (no project artifacts modified)
        return {
            "status": "general_chat",
            "detected_intent": "GENERAL_CHAT",
            "message": response_text,
            "structured_requirements": {
                "epic_name": (
                    req_state.get("requirements", [])[0].get("title", "")
                    if req_state and req_state.get("requirements")
                    else ""
                ),
                "version": req_state.get("version_number", 1) if req_state else 1,
                "user_stories": req_state.get("user_stories", []) if req_state else []
            } if req_state else {},
            "audit_result": {
                "is_valid": req_state.get("validation_status") == "valid" if req_state else False,
                "audit_version_reviewed": req_state.get("version_number", 1) if req_state else 1,
                "clarification_questions": req_state.get("clarification_questions", []) if req_state else [],
                "passed_checks": [],
                "failed_checks": []
            },
            "prd_markdown": req_state.get("generated_prd", "") if req_state else "",
            "mermaid_diagram": req_state.get("generated_diagrams", "") if req_state else "",
            "workflow_routing": {"workflow": "CHAT", "confidence": 1.0, "reason": "Routed as GENERAL_CHAT via intent detection."}
        }

    # ==========================================
    # STEP 4: Route based on detected intent
    # ==========================================
    # Map detected intent to target_agent for LangGraph workflow routing
    intent_to_target = {
        "CREATE_REQUIREMENT": "gatherer",
        "UPDATE_REQUIREMENT": "gatherer",
        "DELETE_REQUIREMENT": "delete_requirement",
        "CLARIFY_REQUIREMENT": "auditor",
    }
    if detected_intent in intent_to_target:
        request.target_agent = intent_to_target[detected_intent]
        logger.info(f"[INTENT ROUTING] Intent {detected_intent} -> target_agent={request.target_agent}")

    current_state = req_state.get("current_workflow_state", "IDLE") if req_state else "IDLE"
    logger.info(f"[WORKFLOW STATE MACHINE] Current workflow state: {current_state}")

    # Routing rules based on current_workflow_state
    if current_state == "IDLE":
        current_state = "GATHERING"
    elif current_state == "GATHERING":
        pass
    elif current_state == "REVIEWING":
        if request.target_agent == "gatherer" or (request.raw_input and ("update" in request.raw_input.lower() or "create" in request.raw_input.lower() or "add" in request.raw_input.lower())):
            current_state = "GATHERING"
        else:
            # Wait for user edits / normal chat, do not run gatherer automatically
            pass
    elif current_state == "AUDITING":
        if request.target_agent != "auditor":
            # Wait until user explicitly clicks Run Auditor
            pass
    elif current_state == "WAITING_CLARIFICATION":
        # User messages treated as clarification answers
        request.target_agent = "auditor"
    elif current_state == "ARCHITECTING":
        if request.target_agent != "architect":
            # Wait until user explicitly clicks Generate PRD / Diagram
            pass
    elif current_state == "COMPLETED":
        if request.target_agent == "gatherer" or (request.raw_input and ("update" in request.raw_input.lower() or "create" in request.raw_input.lower())):
            current_state = "GATHERING"
        else:
            pass

    if not req_state:
        reqs = request.structured_requirements or {}
        all_ac = []
        for us in reqs.get("user_stories", []):
            all_ac.extend(us.get("acceptance_criteria", []))

        req_state = {
            "project_id": request.project_id,
            "project_name": "PromptPay Settlement Engine",
            "requirements": [
                {
                    "requirement_code": "REQ-001",
                    "title": reqs.get("epic_name", ""),
                    "description": "",
                    "user_stories": reqs.get("user_stories", [])
                }
            ] if reqs else [],
            "business_goals": [],
            "actors": [],
            "user_stories": reqs.get("user_stories", []),
            "acceptance_criteria": all_ac,
            "clarification_questions": [],
            "validation_status": "pending",
            "generated_prd": "",
            "generated_diagrams": "",
            "current_workflow_state": current_state,
            "version_number": request.current_version if request.current_version is not None else 1,
            "updated_at": None
        }
    else:
        req_state["current_workflow_state"] = current_state
        # If frontend sent newer structured_requirements (e.g. user manually updated them), sync in memory before workflow run
        if request.structured_requirements:
            reqs = request.structured_requirements
            all_ac = []
            for us in reqs.get("user_stories", []):
                all_ac.extend(us.get("acceptance_criteria", []))

            reqs_list = reqs.get("requirements", [])
            if isinstance(reqs_list, list) and reqs_list:
                # Use the requirements list from frontend
                req_state["requirements"] = reqs_list
            else:
                # Convert legacy epic_name to requirement format
                req_state["requirements"] = [
                    {
                        "requirement_code": "REQ-001",
                        "title": reqs.get("epic_name", ""),
                        "description": "",
                        "user_stories": reqs.get("user_stories", [])
                    }
                ]
            req_state["user_stories"] = reqs.get("user_stories", [])
            req_state["acceptance_criteria"] = all_ac
            if "version" in reqs:
                req_state["version_number"] = reqs["version"]

    # Formulate initial state corresponding to AgentState TypedDict
    initial_state = {
        "project_id": request.project_id,
        "raw_input": request.raw_input or "",
        "structured_requirements": {
            "epic_name": (
                req_state.get("requirements", [])[0].get("title", "")
                if req_state and req_state.get("requirements")
                else ""
            ),
            "version": req_state.get("version_number", 1),
            "user_stories": req_state.get("user_stories", [])
        },
        "audit_result": {},
        "prd_markdown": req_state.get("generated_prd", ""),
        "mermaid_diagram": req_state.get("generated_diagrams", ""),
        "current_version": req_state.get("version_number", 1),
        "version_history_summaries": request.version_history_summaries if request.version_history_summaries is not None else "No previous history.",
        "target_agent": request.target_agent or "gatherer",
        "requirement_state": req_state,
        "detected_intent": detected_intent,
        "db_session": session  # Pass the active session to workflow nodes
    }

    try:
        # Run state graph asynchronously (merges and generates in memory)
        final_state = await prd_workflow.ainvoke(initial_state)

        # Read updated centralized RequirementState from final graph output
        req_state = final_state.get("requirement_state", req_state)

        # Update workflow state after run
        if request.target_agent == "gatherer" or current_state == "GATHERING":
            req_state["current_workflow_state"] = "REVIEWING"
        elif request.target_agent == "auditor":
            is_valid = req_state.get("validation_status") == "valid"
            req_state["current_workflow_state"] = "REVIEWING" if is_valid else "WAITING_CLARIFICATION"
        elif request.target_agent == "architect":
            req_state["current_workflow_state"] = "COMPLETED"

        workflow_routing = final_state.get("workflow_routing") or {}
        wf_type = str(workflow_routing.get("workflow", "REQUIREMENT")).upper()

        # ==========================================
        # IN-MEMORY MERGE: Store merged state as a pending action instead of directly persisting to DB.
        # The user must confirm before changes are committed to the database.
        # ==========================================
        import uuid

        logger.info(f"[IN-MEMORY MERGE] Storing merged state as pending action for project {request.project_id}...")

        # Create a pending action with the full merged state as proposed changes
        pending_action = await PendingActionRepository.create(
            project_id=request.project_id,
            data={
                "action_type": "MERGE",
                "target_requirement_id": None,
                "original_user_message": request.raw_input or "",
                "proposed_changes": req_state,
                "affected_user_story_ids": [],
                "affected_acceptance_criteria_ids": [],
                "workflow_stage": req_state.get("current_workflow_state", "gatherer_node")
            },
            expires_at=datetime.utcnow() + timedelta(hours=1),
            session=session
        )

        pending_action_id = pending_action.get("id")
        logger.info(f"[IN-MEMORY MERGE] Pending action {pending_action_id} created. Awaiting user confirmation.")

        # ==========================================
        # STEP 5: Persist assistant response for non-GENERAL_CHAT intents
        # ==========================================
        agent_message = final_state.get("agent_message", "")
        if request.project_id and agent_message:
            await ConversationMessageRepository.save_message(
                project_id=str(request.project_id),
                role="assistant",
                message=agent_message,
                workflow_state=req_state.get("current_workflow_state", request.target_agent or "gatherer"),
                intent=detected_intent
            )

        # Determine status dynamically based on centralized validation status
        is_valid = req_state.get("validation_status") == "valid"
        status_str = "completed" if is_valid else "audit_pending"

        # Format structures back to preserve frontend compatibility
        reqs_data = req_state.get("requirements", [])
        if isinstance(reqs_data, list):
            # Multi-requirement format
            epic_name = reqs_data[0].get("title", "") if reqs_data else ""
            structured_out = {
                "epic_name": epic_name,
                "version": req_state.get("version_number", 1),
                "user_stories": req_state.get("user_stories", []),
                "requirements": reqs_data
            }
        elif isinstance(reqs_data, dict):
            # Legacy dict format
            structured_out = {
                "epic_name": reqs_data.get("epic_name", ""),
                "version": req_state.get("version_number", 1),
                "user_stories": req_state.get("user_stories", [])
            }
        else:
            # Fallback for None or unexpected types
            structured_out = {
                "epic_name": "",
                "version": req_state.get("version_number", 1),
                "user_stories": req_state.get("user_stories", [])
            }

        # Ensure audit result fields are cleanly populated
        audit_out = {
            "is_valid": is_valid,
            "audit_version_reviewed": req_state.get("version_number", 1),
            "clarification_questions": req_state.get("clarification_questions", []),
            "passed_checks": final_state.get("audit_result", {}).get("passed_checks", []),
            "failed_checks": final_state.get("audit_result", {}).get("failed_checks", [])
        }

        # Notify SSE subscribers that the workflow produced new state / a pending merge.
        await event_manager.publish(str(request.project_id), "workflow_update", {
            "project_id": str(request.project_id),
            "workflow_state": req_state.get("current_workflow_state"),
            "validation_status": req_state.get("validation_status"),
            "pending_action_id": pending_action_id,
            "target_agent": request.target_agent,
        })

        return {
            "status": status_str,
            "workflow_routing": workflow_routing,
            "detected_intent": final_state.get("detected_intent") or req_state.get("detected_intent", detected_intent),
            "structured_requirements": structured_out,
            "audit_result": audit_out,
            "prd_markdown": req_state.get("generated_prd", ""),
            "mermaid_diagram": req_state.get("generated_diagrams", ""),
            "message": agent_message,
            "pending_merge": True,
            "pending_action_id": pending_action_id
        }
    except Exception as e:
        logger.error(f"Multi-agent workflow execution failed for project {request.project_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"LangGraph multi-agent workflow execution failed: {str(e)}"
        )


# ==========================================
# WORKFLOW ROUTER / INTENT DETECTOR / MATCHER API
# ==========================================

@router.post("/api/workflow-router", response_model=WorkflowRoutingResult, status_code=status.HTTP_200_OK)
async def post_workflow_router(
    payload: WorkflowRouterRequest,
    _rate_limit: None = Depends(
        rate_limit_dependency(
            "workflow", settings.RATE_LIMIT_WORKFLOW_LIMIT, settings.RATE_LIMIT_WORKFLOW_WINDOW
        )
    ),
) -> WorkflowRoutingResult:
    """
    Direct endpoint for testing and executing the Workflow Router.

    Classifies incoming message into CHAT, QUESTION, COMMAND, or REQUIREMENT.

    Args:
        payload: Contains the user ``message`` to classify.
        _rate_limit: Injected rate limiter (Finding #39).

    Returns:
        WorkflowRoutingResult: The classified workflow type with confidence and reason.

    Raises:
        HTTPException: 413 if ``message`` exceeds ``MAX_CONTEXT_TOKENS``.
    """
    from app.semantic_service import classify_workflow

    # Finding #39: enforce MAX_CONTEXT_TOKENS on the incoming message.
    validate_text_budget(payload.message, "Workflow-router message")
    return await classify_workflow(payload.message)


@router.post("/api/intent-detector", response_model=RequirementIntentDetectionResult, status_code=status.HTTP_200_OK)
async def post_intent_detector(
    payload: IntentDetectorRequest,
    db: AsyncSession = Depends(get_db),
    _rate_limit: None = Depends(
        rate_limit_dependency(
            "workflow", settings.RATE_LIMIT_WORKFLOW_LIMIT, settings.RATE_LIMIT_WORKFLOW_WINDOW
        )
    ),
) -> RequirementIntentDetectionResult:
    """
    Direct endpoint for testing and executing Requirement Intent Detection
    (GENERAL_CHAT, REQUIREMENT_REQUEST).

    Args:
        payload: Contains the user ``message`` and optional project context.
        db: Active asynchronous database session.
        _rate_limit: Injected rate limiter (Finding #39).

    Returns:
        RequirementIntentDetectionResult: The detected intent with confidence and reason.

    Raises:
        HTTPException: 413 if ``message`` exceeds ``MAX_CONTEXT_TOKENS``.
    """
    from app.semantic_service import detect_requirement_intent

    # Finding #39: enforce MAX_CONTEXT_TOKENS on the incoming message.
    validate_text_budget(payload.message, "Intent-detector message")

    current_stories = []
    if payload.project_id:
        try:
            req_state = await RequirementStateRepository.get_by_project_id(payload.project_id, db)
            current_stories = req_state.get("user_stories", []) if req_state else []
        except Exception:
            pass

    result = await detect_requirement_intent(payload.message, current_stories)
    return result


@router.post("/api/requirement-matcher", response_model=RequirementMatcherResult, status_code=status.HTTP_200_OK)
async def post_requirement_matcher(
    payload: RequirementMatcherRequest,
    db: AsyncSession = Depends(get_db),
    _rate_limit: None = Depends(
        rate_limit_dependency(
            "workflow", settings.RATE_LIMIT_WORKFLOW_LIMIT, settings.RATE_LIMIT_WORKFLOW_WINDOW
        )
    ),
) -> RequirementMatcherResult:
    """
    Direct endpoint for testing and executing the Requirement Matcher Agent.

    Determines which existing requirement(s) the user's message refers to
    before any modification occurs.

    Args:
        payload: Contains the user ``message``, optional project context and
            pre-detected intent.
        db: Active asynchronous database session.
        _rate_limit: Injected rate limiter (Finding #39).

    Returns:
        RequirementMatcherResult: The matched requirement, action recommendation
            and any ambiguous candidates.

    Raises:
        HTTPException: 413 if ``message`` exceeds ``MAX_CONTEXT_TOKENS``.
    """
    from app.semantic_service import match_requirement, detect_requirement_intent

    # Finding #39: enforce MAX_CONTEXT_TOKENS on the incoming message.
    validate_text_budget(payload.message, "Requirement-matcher message")

    current_stories = []
    if payload.project_id:
        try:
            req_state = await RequirementStateRepository.get_by_project_id(payload.project_id, db)
            current_stories = req_state.get("user_stories", []) if req_state else []
        except Exception:
            pass

    intent = payload.detected_intent
    if not intent:
        intent_res = await detect_requirement_intent(payload.message, current_stories)
        intent = intent_res.get("intent", "UPDATE")

    result = await match_requirement(payload.message, intent, current_stories)
    return result