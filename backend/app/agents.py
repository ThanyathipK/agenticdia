import logging
import json
from typing import TypedDict, Dict, Any, List, Optional
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
try:
    from langchain.output_parsers import OutputFixingParser
except ImportError:
    OutputFixingParser = None
from langgraph.graph import StateGraph, START, END
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories import RequirementStateRepository, ConversationMessageRepository, PRDVersionRepository
from app.schemas import GatheredRequirements
from app.prompt_loader import load_prompt, _PromptProxy
from app.llm_factory import llm, parser
from app.llm_utils import invoke_llm_structured
from app.merge_service import collect_acceptance_criteria, filter_active_stories, merge_user_stories, normalize_ticket_code
from app.semantic_service import (
    classify_workflow,
    detect_requirement_intent,
    detect_semantic_changes,
    match_requirement,
)


# Set up logging configuration for the multi-agent framework
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app.agents")

# ==========================================
# SYSTEM PROMPTS (LOADED DYNAMICALLY VIA PROMPT LOADER)
# ==========================================
GATHERER_PROMPT = _PromptProxy("gatherer")
AUDITOR_PROMPT = _PromptProxy("auditor")
ARCHITECT_PROMPT = _PromptProxy("architect")

# ==========================================
# STATE MANAGEMENT
# ==========================================
class RequirementState(TypedDict):
    """
    Centralized requirement state containing all project-specific
    specifications, metadata, security status, and technical outputs.
    """
    project_id: str
    project_name: str
    requirements: dict
    business_goals: list
    actors: list
    user_stories: list
    acceptance_criteria: list
    clarification_questions: list
    validation_status: str
    generated_prd: str
    generated_diagrams: str
    current_workflow_state: str
    version_number: int
    updated_at: Optional[str]
    detected_intent: Optional[str]

class AgentState(TypedDict, total=False):
    """
    Context safety state tracking dictionary.
    Maintains historic attributes across multi-agent graph workflows.
    """
    project_id: str
    raw_input: str
    structured_requirements: dict
    audit_result: dict
    prd_markdown: str
    mermaid_diagram: str
    current_version: int
    version_history_summaries: str
    target_agent: str # Supports on-demand agent execution flow
    requirement_state: RequirementState
    detected_intent: Optional[str]
    workflow_routing: Optional[dict]
    agent_message: Optional[str]

async def get_or_init_requirement_state(project_id: str, session: Optional[AsyncSession] = None, current_version: int = 1) -> RequirementState:
    """
    Retrieves or initializes the centralized RequirementState object from Supabase.
    """
    logger.info(f"[DB LOG] [AGENTS] Loading project state for {project_id}...")
    
    # Use provided session or create a new one as fallback
    if session is None:
        from app.database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            db_state = await RequirementStateRepository.get_by_project_id(project_id, session)
    else:
        db_state = await RequirementStateRepository.get_by_project_id(project_id, session)
    
    logger.info(f"[DB LOG] [AGENTS] Loading project state for {project_id} complete. Found: {db_state is not None}")
    if not db_state:
        db_state = {
            "project_id": project_id,
            # The authoritative project name lives in the projects table /
            # frontend; leave this denormalized copy blank instead of seeding a
            # fabricated demo label ("PromptPay Settlement Engine").
            "project_name": "",
            "requirements": [],
            "business_goals": [],
            "actors": [],
            "user_stories": [],
            "acceptance_criteria": [],
            "clarification_questions": [],
            "validation_status": "pending",
            "generated_prd": "",
            "generated_diagrams": "",
            "current_workflow_state": "gatherer_node",
            "version_number": current_version,
            "updated_at": None
        }
    return db_state

# ==========================================
# GRAPH NODES (THE AGENTS)
# ==========================================

def _llm_content_length(raw) -> int:
    """Return the character length of a likely LLM payload without rendering it."""
    if isinstance(raw, str):
        return len(raw)
    if raw is None:
        return 0
    try:
        return len(list(raw))
    except TypeError:
        return 0


def extract_content_from_response(response) -> str:
    """Robustly extracts content from ChatOpenAI response.

    Logging is intentionally conservative here: the full response object
    (repr, content, additional_kwargs and response_metadata) is never written
    to the logs because it is noisy and may leak sensitive data such as PII or
    project details embedded in LLM output. Only a short, non-sensitive summary
    is emitted, and only at DEBUG level.
    """
    # 1. Log a concise, redacted summary of the response (no payload data).
    logger.debug(
        "Received LLM response of type '%s' (top-level content: %d chars).",
        type(response).__name__,
        _llm_content_length(getattr(response, "content", None)),
    )

    # 2. Extract content
    content = ""
    if hasattr(response, "content") and isinstance(response.content, str) and response.content.strip():
        content = response.content
    elif hasattr(response, "additional_kwargs"):
        if "content" in response.additional_kwargs:
            content = response.additional_kwargs["content"]
        # Handle reasoning models (if reasoning_content is present, look for the final answer)
        if "reasoning_content" in response.additional_kwargs:
            logger.debug("Reasoning mode detected.")
            # If main content is empty, check if final answer is in another field or mixed in
            if not content:
                content = response.additional_kwargs.get("final_answer", "")
    elif hasattr(response, "response_metadata") and "content" in response.response_metadata:
         content = response.response_metadata["content"]

    # Log only the length of the extracted content, never the content itself.
    logger.debug("Extracted LLM content of %d chars.", _llm_content_length(content))
    return content


async def workflow_router_node(state: AgentState) -> Dict[str, Any]:
    """
    Workflow Router Node:
    Intercepts user input BEFORE the Gatherer Agent.
    Classifies incoming user messages into:
    - CHAT
    - QUESTION
    - COMMAND
    - REQUIREMENT
    """
    raw_input = state.get("raw_input", "")

    target_agent = state.get("target_agent", "gatherer")

    logger.info(f"[WORKFLOW ROUTER] Intercepted raw_input: '{raw_input[:100]}'")

    # Run classification
    router_result = await classify_workflow(raw_input)
    workflow_type = str(router_result.get("workflow", "REQUIREMENT")).upper()
    logger.info(f"[WORKFLOW ROUTER] Classification: {router_result}")

    project_id = state.get("project_id", "PROJ-UNKNOWN")
    
    # Use session from state if available, otherwise let function create one
    db_session = state.get("db_session")
    req_state = await get_or_init_requirement_state(project_id, session=db_session, current_version=state.get("current_version", 1))

    if workflow_type == "CHAT":
        logger.info("[WORKFLOW ROUTER] Handling as CHAT. Generating conversational response.")
        chat_sys = load_prompt("chat")
        try:
            resp = await llm.ainvoke([SystemMessage(content=chat_sys), HumanMessage(content=raw_input)])
            msg_content = resp.content if hasattr(resp, "content") else str(resp)
        except Exception as e:
            # Intentional graceful degradation: when the LLM is unreachable during a
            # plain CHAT turn we return a canned greeting instead of raising. The
            # failure is logged as an error with traceback so it is not masked, and
            # no state is corrupted by this fallback.
            logger.error(f"Failed LLM chat invocation: {str(e)}", exc_info=True)
            msg_content = "Hello! How can I assist you with your core banking requirements today?"

        return {
            "workflow_routing": router_result,
            "agent_message": msg_content,
            "requirement_state": req_state
        }

    elif workflow_type == "QUESTION":
        logger.info("[WORKFLOW ROUTER] Handling as QUESTION. Answering direct question.")
        requirements = req_state.get("requirements", [])
        existing_epic = requirements[0].get("title", "") if requirements else ""
        stories = req_state.get("user_stories", [])
        stories_summary = "\n".join([f"- {s.get('ticket_code', 'US')}: {s.get('story_title', '')}" for s in stories[:10]])

        q_sys = load_prompt("question").format(existing_epic=existing_epic, stories_summary=stories_summary)
        try:
            resp = await llm.ainvoke([SystemMessage(content=q_sys), HumanMessage(content=raw_input)])
            msg_content = resp.content if hasattr(resp, "content") else str(resp)
        except Exception as e:
            logger.warning(f"Failed LLM question invocation: {str(e)}")
            msg_content = f"Here is the explanation for your question: {raw_input}"

        return {
            "workflow_routing": router_result,
            "agent_message": msg_content,
            "requirement_state": req_state
        }

    elif workflow_type == "COMMAND":
        logger.info("[WORKFLOW ROUTER] Handling as COMMAND. Routing backend command.")
        lower = raw_input.lower()
        new_target = target_agent
        if any(w in lower for w in ["audit", "auditor", "validate"]):
            new_target = "auditor"
        elif any(w in lower for w in ["prd", "diagram", "architect", "export"]):
            new_target = "architect"

        return {
            "workflow_routing": router_result,
            "target_agent": new_target,
            "agent_message": f"Command routed successfully: {raw_input}",
            "requirement_state": req_state
        }

    else: # REQUIREMENT
        logger.info("[WORKFLOW ROUTER] Handling as REQUIREMENT. Proceeding to Requirement Matcher & Intent Detection.")
        return {
            "workflow_routing": router_result,
            "requirement_state": req_state
        }

async def requirement_matcher_node(state: AgentState) -> Dict[str, Any]:
    """
    Requirement Matcher Node:
    Runs between Intent Detection and Gatherer Agent.
    Determines which existing requirement(s) the user's message refers to before any modification occurs.
    """
    raw_input = state.get("raw_input", "")

    project_id = state.get("project_id", "PROJ-UNKNOWN")
    
    # Use session from state if available, otherwise let function create one
    db_session = state.get("db_session")
    req_state = await get_or_init_requirement_state(project_id, session=db_session, current_version=state.get("current_version", 1))
    existing_stories = req_state.get("user_stories", [])

    detected_intent = state.get("detected_intent")
    if not detected_intent and raw_input:
        intent_res = await detect_requirement_intent(raw_input, existing_stories)
        detected_intent = intent_res.get("intent", "NEW_REQUIREMENT")
    elif not detected_intent:
        detected_intent = "GENERAL_CHAT"

    match_result = await match_requirement(raw_input, detected_intent, existing_stories)
    matcher_status = str(match_result.get("status", "MATCHED")).upper()
    matcher_confidence = float(match_result.get("confidence", 1.0))
    reason = match_result.get("reason", "")
    candidates = match_result.get("candidates", [])

    logger.info(f"[REQUIREMENT MATCHER] Match Result: {match_result}")

    if raw_input and (matcher_status in ["AMBIGUOUS", "LOW_CONFIDENCE"] or matcher_confidence < 0.75):
        logger.warning(f"[REQUIREMENT MATCHER] Ambiguous or low confidence match (status={matcher_status}, confidence={matcher_confidence}). Halting and asking clarification.")
        
        clarification_text = reason
        if matcher_status == "AMBIGUOUS" and candidates:
            clarification_text = f"Your request could refer to multiple requirements: {', '.join(candidates)}. Which requirement did you intend to update or delete?"
        elif not clarification_text:
            clarification_text = f"I am not sure which requirement your request refers to (Confidence: {matcher_confidence:.2f}). Please specify the ticket code (e.g. US-001)."

        cqs = [{
            "checklist_category": "Requirement Matcher Ambiguity",
            "target_user_story_id": candidates[0] if candidates else None,
            "question_text": clarification_text,
            "user_answer": None,
            "is_resolved": False
        }]
        existing_cqs = req_state.get("clarification_questions", []) or []
        preserved_cqs = [q for q in existing_cqs if not q.get("is_resolved", False)]
        req_state["clarification_questions"] = preserved_cqs + cqs
        req_state["validation_status"] = "invalid"
        req_state["current_workflow_state"] = "requirement_matcher_node"
        req_state["detected_intent"] = detected_intent

        await ConversationMessageRepository.save_message(
            project_id=project_id,
            role="assistant",
            message=f"⚠️ **Clarification Needed (Requirement Matcher):**\n{clarification_text}",
            workflow_state="requirement_matcher_node",
            intent="CLARIFICATION"
        )

        return {
            "requirement_state": req_state,
            "detected_intent": detected_intent,
            "requirement_match": match_result,
            "current_version": req_state.get("version_number", 1)
        }

    return {
        "requirement_state": req_state,
        "detected_intent": detected_intent,
        "requirement_match": match_result
    }

def _default_requirement_code(index: int = 0) -> str:
    """Deterministic fallback requirement code (REQ-001, REQ-002, ...)."""
    return f"REQ-{index + 1:03d}"


def _previous_requirement_identity(req_state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Return the first previously persisted requirement dict (possibly empty).

    Preserving the stored ``requirement_code`` / ``title`` / ``description``
    keeps database identity stable across synthetic rebuilds instead of
    hardcoding a fixed code such as ``REQ-001`` onto every project.
    """
    previous_reqs = req_state.get("requirements", []) or []
    for r in previous_reqs:
        if isinstance(r, dict):
            return r
    return {}


# Marker section heading from prompts/template.md (the official Krungsri
# Nimble PRD template). Used to detect whether a persisted PRD already follows
# the template or is a legacy document built from the old hard-coded sections.
KRUNGSRI_TEMPLATE_MARKER = "Business & Strategic Overview"
# The LaTeX template escapes the ampersand, so both forms are matched.
KRUNGSRI_TEMPLATE_MARKER_LATEX = "Business \\& Strategic Overview"


def _prd_follows_krungsri_template(prd_markdown: Any) -> bool:
    """
    Heuristically detect whether a stored PRD follows the Krungsri Nimble
    template (prompts/template.md or its LaTeX counterpart
    template-krungsrinimble.tex). Legacy documents generated before the
    template switch lack the template's numbered section headings, so they can
    be told apart cheaply and reliably by this marker string.
    """
    text = str(prd_markdown or "")
    return KRUNGSRI_TEMPLATE_MARKER in text or KRUNGSRI_TEMPLATE_MARKER_LATEX in text


async def gatherer_node(state: AgentState) -> Dict[str, Any]:
    """
    Standardizes messy Product Owner input into high-quality Agile structures.
    Reads/writes to the centralized RequirementState object via persistence service.
    Respects artifact locks - skips locked requirements and user stories.
    """
    logger.info("Executing gatherer_node to structure requirements.")
    project_id = state.get("project_id", "PROJ-UNKNOWN")
    raw_input = state.get("raw_input", "")
    
    # Use session from state if available, otherwise let function create one
    db_session = state.get("db_session")
    req_state = await get_or_init_requirement_state(project_id, session=db_session, current_version=state.get("current_version", 1))
    
    # Store existing user stories before processing passed_structured or raw_input
    existing_user_stories = list(req_state.get("user_stories", []))
    
    # Filter out locked user stories
    unlocked_user_stories = [
        us for us in existing_user_stories
        if not us.get("is_locked", False)
    ]
    if len(unlocked_user_stories) != len(existing_user_stories):
        logger.info(f"[GATHERER] Filtered out {len(existing_user_stories) - len(unlocked_user_stories)} locked user stories.")

    passed_structured = state.get("structured_requirements") or {}
    if passed_structured:
        incoming_reqs = passed_structured.get("requirements")
        if isinstance(incoming_reqs, list) and incoming_reqs:
            # Multi-requirement payload: keep every incoming entry's own
            # code/title; only synthesize codes for entries missing one.
            req_state["requirements"] = [
                {
                    **inc,
                    "requirement_code": inc.get("requirement_code") or _default_requirement_code(idx),
                }
                for idx, inc in enumerate(incoming_reqs)
                if isinstance(inc, dict)
            ]
        else:
            # Legacy epic-only payload: preserve the persisted requirement
            # identity (code/title/description) instead of resetting every
            # project to a hardcoded ``REQ-001``.
            prev_req = _previous_requirement_identity(req_state)
            req_state["requirements"] = [
                {
                    **prev_req,
                    "requirement_code": prev_req.get("requirement_code") or _default_requirement_code(0),
                    "title": passed_structured.get("epic_name") or prev_req.get("title", ""),
                    "description": prev_req.get("description", ""),
                    "user_stories": passed_structured.get("user_stories", []),
                }
            ]
        req_state["version_number"] = passed_structured.get("version", req_state["version_number"])

    result = None
    parsing_error = None

    # Detect user intent before running the Gatherer
    detected_intent = state.get("detected_intent")
    intent_confidence = 1.0
    if not detected_intent and raw_input:
        intent_res = await detect_requirement_intent(raw_input, existing_user_stories)
        detected_intent = intent_res.get("intent", "UPDATE_REQUIREMENT")
        intent_confidence = float(intent_res.get("confidence", 1.0))
    elif not detected_intent:
        detected_intent = "GENERAL_CHAT"

    logger.info(f"Gatherer received raw_input: '{raw_input[:100]}' with detected_intent: {detected_intent}, confidence: {intent_confidence}")

    # Use requirement_match from Requirement Matcher Agent if available
    requirement_match = state.get("requirement_match") or {}
    matched_req_id = requirement_match.get("matched_requirement_id")
    match_action = requirement_match.get("action")

    semantic_recs = []
    if raw_input:
        if matched_req_id and match_action in ["UPDATE", "DELETE"]:
            rec_action = "UPDATE" if match_action == "UPDATE" else "ARCHIVE"
            semantic_recs = [{
                "change_type": "MODIFY_REQUIREMENT" if rec_action == "UPDATE" else "REMOVE_REQUIREMENT",
                "target_requirement_id": matched_req_id,
                "confidence": requirement_match.get("confidence", 0.95),
                "reason": requirement_match.get("reason", "Matched via Requirement Matcher Agent."),
                "recommended_action": rec_action
            }]
            logger.info(f"Gatherer using Requirement Matcher result: target_id={matched_req_id}, action={rec_action}")
        else:
            # Only detect semantic changes on unlocked user stories
            semantic_recs = await detect_semantic_changes(raw_input, unlocked_user_stories)

        
        # Check for low confidence changes
        low_confidence_changes = [c for c in semantic_recs if c.get("confidence", 1.0) < 0.70]
        if low_confidence_changes:
            logger.warning(f"Detected {len(low_confidence_changes)} low confidence semantic changes. Triggering clarification questions.")
            
            # Generate clarification questions
            cqs = []
            for c in low_confidence_changes:
                q_text = f"I detected a possible change with low confidence: '{c.get('reason', '')}'. Which requirement or user story would you like to update, or is this a new requirement?"
                cqs.append({
                    "checklist_category": "Semantic Ambiguity",
                    "target_user_story_id": None,
                    "question_text": q_text,
                    "user_answer": None,
                    "is_resolved": False
                })
            
            # Append to existing questions
            existing_cqs = req_state.get("clarification_questions", []) or []
            preserved_cqs = [q for q in existing_cqs if not q.get("is_resolved", False)]
            combined_cqs = preserved_cqs + cqs
            
            req_state["clarification_questions"] = combined_cqs
            req_state["validation_status"] = "invalid"
            req_state["current_workflow_state"] = "gatherer_node"
            req_state["detected_intent"] = detected_intent
            
            return {
                "requirement_state": req_state,
                "structured_requirements": passed_structured,
                "detected_intent": detected_intent,
                "current_version": req_state.get("version_number", 1)
            }

        # Format current stories context
        requirements = req_state.get("requirements", [])
        existing_epic = requirements[0].get("title", "") if requirements else ""
        context_lines = []
        if existing_epic:
            context_lines.append(f"CURRENT ACTIVE EPIC: {existing_epic}\n(Note: DO NOT change this Epic Name unless the user explicitly requests to change or rename the epic)\n")
        for story in unlocked_user_stories:
            context_lines.append(
                f"- Story {story.get('ticket_code', 'UNKNOWN')}: '{story.get('story_title', '')}'\n"
                f"  As a {story.get('as_a', '')}, I want to {story.get('i_want_to', '')}, So that {story.get('so_that', '')}\n"
                f"  Acceptance Criteria: {json.dumps(story.get('acceptance_criteria', []))}"
            )
        current_context = "\n".join(context_lines) if context_lines else "No existing user stories in this project."
        
        # Format semantic recommendations
        recs_str = json.dumps(semantic_recs, indent=2)

        prompt_template = PromptTemplate(
            template=load_prompt("gatherer"),
            input_variables=["raw_input", "detected_intent", "current_context", "recommendations", "format_instructions"]
        )
        
        # Prepare components for logging
        pydantic_parser = PydanticOutputParser(pydantic_object=GatheredRequirements)
        format_instructions = pydantic_parser.get_format_instructions()
        prompt_value = prompt_template.format(
            raw_input=raw_input,
            detected_intent=detected_intent,
            current_context=current_context,
            recommendations=recs_str,
            format_instructions=format_instructions
        )
        logger.info(f"Gatherer prompt length: {len(prompt_value)} tokens/chars.")
        
        # Strategy: Prefer with_structured_output, fallback to raw LLM invocation + JSON parsing
        result = None
        parsing_error = None

        try:
            result = await invoke_llm_structured(
                llm,
                prompt_template,
                GatheredRequirements,
                variables={
                    "raw_input": raw_input,
                    "detected_intent": detected_intent,
                    "current_context": current_context,
                    "recommendations": recs_str,
                    "format_instructions": "Output ONLY raw JSON. No markdown.",
                },
                description="gatherer",
                format_instructions=format_instructions,
            )
            logger.info("Successfully obtained structured output.")
        except Exception as e2:
            parsing_error = f"All parsing attempts failed: {str(e2)}"
            logger.error(parsing_error)

    else:
        result = passed_structured or {
            "epic_name": "Structured Requirements Draft",
            "version": req_state["version_number"],
            "user_stories": []
        }

    # Stop execution if parsing fails entirely
    if parsing_error:
        raise ValueError(
            f"The Gatherer agent failed to parse raw input into structured JSON requirements. "
            f"Details: {parsing_error}. Please revise your input description or schema constraints."
        )

    # Modify only its own fields in RequirementState
    requirements = req_state.get("requirements", [])
    existing_epic_name = requirements[0].get("title", "") if requirements else ""
    llm_epic_name = result.get("epic_name", "")
    
    raw_input_lower = raw_input.lower() if raw_input else ""
    user_explicitly_changed_epic = any(k in raw_input_lower for k in ["rename epic", "change epic", "new epic", "update epic", "epic name"])
    
    is_placeholder = existing_epic_name in ["", "Untitled Epic", "Structured Requirements Draft"]
    if existing_epic_name and not is_placeholder and not user_explicitly_changed_epic:
        epic_name = existing_epic_name
    else:
        epic_name = llm_epic_name or existing_epic_name or "Structured Requirements Draft"

    # ===============================================
    # Handle multi-requirement output from LLM
    # The LLM now returns: {"epic_name": "...", "version": N, "requirements": [...]}
    # ===============================================
    llm_requirements = result.get("requirements", [])
    
    if llm_requirements and isinstance(llm_requirements, list):
        # New format: multiple requirements with their user stories
        # Build merged stories per requirement, then flatten for backward compat
        req_items_output = []
        all_merged_stories = []
        all_active_stories = []
        all_ac = []
        
        for req_item in llm_requirements:
            req_code = req_item.get("requirement_code", "REQ-000")
            req_title = req_item.get("title", "Untitled Requirement")
            req_desc = req_item.get("description", "")
            newly_generated_stories = req_item.get("user_stories", [])
            
            # Merge stories for this requirement (only unlocked stories)
            merged_stories = merge_user_stories(
                existing_stories=unlocked_user_stories,
                new_incoming_stories=newly_generated_stories,
                semantic_recs=semantic_recs
            )
            
            active_stories = filter_active_stories(merged_stories)
            
            req_items_output.append({
                "requirement_code": req_code,
                "title": req_title,
                "description": req_desc,
                "user_stories": active_stories
            })
            
            all_merged_stories.extend(merged_stories)
            all_active_stories.extend(active_stories)
            all_ac.extend(collect_acceptance_criteria(active_stories))
        
        # Also include any existing stories that were NOT matched by any requirement
        # by checking the merge result - stories from existing requirements not in LLM output
        existing_codes_in_output = set()
        for req_item in llm_requirements:
            for us in req_item.get("user_stories", []):
                tc = us.get("ticket_code", "")
                if tc:
                    existing_codes_in_output.add(tc)
        
        for ex_story in existing_user_stories:
            tc = ex_story.get("ticket_code", "")
            if tc and tc not in existing_codes_in_output and ex_story.get("status", "active") == "active":
                # This existing story was not mentioned in LLM output - keep it unchanged
                # Find which requirement it belongs to by looking at existing req_state
                pass  # handled by merge_user_stories
        
        # Set the requirements list into req_state
        req_state["requirements"] = req_items_output
        req_state["user_stories"] = all_active_stories
        req_state["all_merged_stories"] = all_merged_stories
        req_state["acceptance_criteria"] = all_ac
        
    else:
        # Legacy fallback: flat user_stories in result
        newly_generated_stories = result.get("user_stories", [])
        
        merged_stories = merge_user_stories(
            existing_stories=unlocked_user_stories,
            new_incoming_stories=newly_generated_stories,
            semantic_recs=semantic_recs
        )
        
        active_stories = filter_active_stories(merged_stories)
        ac_list = collect_acceptance_criteria(active_stories)
        
        # Wrap into a single default requirement
        req_state["requirements"] = [{
            "requirement_code": "REQ-001",
            "title": epic_name or "Structured Requirements",
            "description": "",
            "user_stories": active_stories
        }]
        req_state["user_stories"] = active_stories
        req_state["all_merged_stories"] = merged_stories
        req_state["acceptance_criteria"] = ac_list

    version_number = result.get("version", req_state["version_number"])
    
    req_state["version_number"] = version_number
    req_state["current_workflow_state"] = "gatherer_node"
    req_state["semantic_recommendations"] = semantic_recs
    req_state["detected_intent"] = detected_intent

    gatherer_msg = "📥 **Requirements Gathered & Updated!**\nI have successfully structured your input into the Agile Requirements board."
    await ConversationMessageRepository.save_message(
        project_id=project_id,
        role="gatherer",
        message=gatherer_msg,
        workflow_state="gatherer_node",
        intent="REQUIREMENT_REQUEST"
    )
    
    # Sync to outer structure for backend/frontend backward compatibility
    structured_out = {
        "epic_name": epic_name,
        "version": version_number,
        "user_stories": req_state.get("user_stories", []),
        "requirements": req_state.get("requirements", [])
    }
    
    return {
        "requirement_state": req_state,
        "structured_requirements": structured_out,
        "detected_intent": detected_intent,
        "current_version": version_number
    }

async def delete_requirement_node(state: AgentState) -> Dict[str, Any]:
    """
    Delete Requirement Node:
    Handles DELETE_REQUIREMENT intent by archiving the matched requirement/user story.
    Reads the requirement_match from state to identify which story to archive.
    """
    logger.info("Executing delete_requirement_node to archive requirements.")
    project_id = state.get("project_id", "PROJ-UNKNOWN")
    
    # Use session from state if available, otherwise let function create one
    db_session = state.get("db_session")
    req_state = await get_or_init_requirement_state(project_id, session=db_session, current_version=state.get("current_version", 1))
    
    # Get the requirement match result
    requirement_match = state.get("requirement_match") or {}
    matched_req_id = requirement_match.get("matched_requirement_id")
    match_confidence = float(requirement_match.get("confidence", 0.0))
    match_action = requirement_match.get("action", "DELETE")
    
    logger.info(f"[DELETE NODE] Matched requirement: {matched_req_id}, confidence: {match_confidence}, action: {match_action}")
    
    existing_stories = list(req_state.get("user_stories", []))
    
    if matched_req_id and match_confidence >= 0.75:
        # Archive the specific matched story
        archived_stories = []
        matched_story_found = False
        matched_story_locked = False
        for story in existing_stories:
            tc = story.get("ticket_code", "")
            if tc and normalize_ticket_code(tc) == normalize_ticket_code(matched_req_id):
                matched_story_found = True
                # LOCK ENFORCEMENT: Never archive a locked user story
                if story.get("is_locked", False):
                    matched_story_locked = True
                    logger.warning(
                        f"[DELETE NODE] Skipping archive of locked user story {tc} "
                        f"(locked_by={story.get('locked_by', 'unknown')}). AI removal blocked."
                    )
                    archived_stories.append(story)
                else:
                    archived_story = dict(story)
                    archived_story["status"] = "archived"
                    archived_story["change_type"] = "archived"
                    archived_stories.append(archived_story)
                    logger.info(f"[DELETE NODE] Archiving story: {tc}")
            else:
                archived_stories.append(story)
        
        # LOCK ENFORCEMENT: If the matched story is locked, block the deletion entirely
        if matched_story_found and matched_story_locked:
            lock_msg = (
                f"🔒 **Cannot Delete Locked Requirement!**\n"
                f"Requirement `{matched_req_id}` is locked and cannot be deleted. "
                f"Unlock it before deleting."
            )
            logger.warning(f"[DELETE NODE] Blocked deletion of locked requirement {matched_req_id}.")
            await ConversationMessageRepository.save_message(
                project_id=project_id,
                role="assistant",
                message=lock_msg,
                workflow_state="delete_requirement_node",
                intent="DELETE_REQUIREMENT"
            )
            return {
                "requirement_state": req_state,
                "agent_message": lock_msg,
                "current_version": req_state.get("version_number", 1)
            }
        
        req_state["user_stories"] = archived_stories
        req_state["current_workflow_state"] = "delete_requirement_node"
        req_state["validation_status"] = "valid"
        
        # Update requirements list to reflect archived stories
        reqs = req_state.get("requirements", [])
        for req_item in reqs:
            if isinstance(req_item, dict):
                req_stories = req_item.get("user_stories", [])
                updated_req_stories = []
                for rs in req_stories:
                    tc = rs.get("ticket_code", "")
                    if tc and normalize_ticket_code(tc) == normalize_ticket_code(matched_req_id):
                        # LOCK ENFORCEMENT: Never archive a locked user story
                        if rs.get("is_locked", False):
                            logger.warning(
                                f"[DELETE NODE] Skipping archive of locked user story {tc} "
                                f"(locked_by={rs.get('locked_by', 'unknown')}). AI removal blocked."
                            )
                            updated_req_stories.append(rs)
                        else:
                            archived_rs = dict(rs)
                            archived_rs["status"] = "archived"
                            archived_rs["change_type"] = "archived"
                            updated_req_stories.append(archived_rs)
                    else:
                        updated_req_stories.append(rs)
                req_item["user_stories"] = updated_req_stories
        
        # Update acceptance criteria
        all_ac = []
        for story in archived_stories:
            if story.get("status", "active") == "active":
                all_ac.extend(story.get("acceptance_criteria", []))
        req_state["acceptance_criteria"] = all_ac
        
        delete_msg = f"🗑️ **Requirement Deleted!**\nSuccessfully archived requirement `{matched_req_id}` as requested."
        await ConversationMessageRepository.save_message(
            project_id=project_id,
            role="assistant",
            message=delete_msg,
            workflow_state="delete_requirement_node",
            intent="DELETE_REQUIREMENT"
        )
        
        return {
            "requirement_state": req_state,
            "agent_message": delete_msg,
            "current_version": req_state.get("version_number", 1)
        }
    else:
        # No clear match - ask for clarification
        logger.warning(f"[DELETE NODE] No clear match for deletion. matched_req_id={matched_req_id}, confidence={match_confidence}")
        
        clarification_text = f"I'm not sure which requirement you want to delete. Please specify the ticket code (e.g., US-001)."
        if match_action == "AMBIGUOUS":
            candidates = requirement_match.get("candidates", [])
            if candidates:
                clarification_text = f"Your request could refer to multiple requirements: {', '.join(candidates)}. Which requirement did you intend to delete?"
        
        cqs = [{
            "checklist_category": "Delete Requirement Ambiguity",
            "target_user_story_id": matched_req_id,
            "question_text": clarification_text,
            "user_answer": None,
            "is_resolved": False
        }]
        existing_cqs = req_state.get("clarification_questions", []) or []
        preserved_cqs = [q for q in existing_cqs if not q.get("is_resolved", False)]
        req_state["clarification_questions"] = preserved_cqs + cqs
        req_state["validation_status"] = "invalid"
        req_state["current_workflow_state"] = "delete_requirement_node"
        
        await ConversationMessageRepository.save_message(
            project_id=project_id,
            role="assistant",
            message=f"⚠️ **Clarification Needed (Delete):**\n{clarification_text}",
            workflow_state="delete_requirement_node",
            intent="CLARIFY_REQUIREMENT"
        )
        
        return {
            "requirement_state": req_state,
            "agent_message": clarification_text,
            "current_version": req_state.get("version_number", 1)
        }


async def auditor_node(state: AgentState) -> Dict[str, Any]:
    """
    Runs compliance, safety, and business rule audits on structured drafts.
    Reads from and writes to the centralized RequirementState object via persistence service.
    Only audits newly created or modified user stories to save API costs and maintain consistency.
    """
    logger.info("Executing auditor_node to audit compliance.")
    project_id = state.get("project_id", "PROJ-UNKNOWN")
    
    # Use session from state if available, otherwise let function create one
    db_session = state.get("db_session")
    req_state = await get_or_init_requirement_state(project_id, session=db_session, current_version=state.get("current_version", 1))
    
    passed_structured = state.get("structured_requirements") or {}
    if passed_structured:
        # LOCK ENFORCEMENT: Exclude locked user stories from audit
        passed_stories = [
            us for us in passed_structured.get("user_stories", [])
            if not (us.get("is_locked", False))
        ]
        req_state["requirements"] = [
            {
                "requirement_code": "REQ-001",
                "title": passed_structured.get("epic_name", ""),
                "description": "",
                "user_stories": passed_stories
            }
        ]
        req_state["user_stories"] = passed_stories
        req_state["version_number"] = passed_structured.get("version", req_state["version_number"])
        all_ac = []
        for us in req_state["user_stories"]:
            all_ac.extend(us.get("acceptance_criteria", []))
        req_state["acceptance_criteria"] = all_ac

    current_version = req_state["version_number"]
    
    # Step 10 compliance: Segment user stories by change_type
    # LOCK ENFORCEMENT: Exclude locked user stories from audit
    all_stories = req_state.get("user_stories", [])
    unlocked_stories = [
        story for story in all_stories
        if not (story.get("is_locked", False))
    ]
    if len(unlocked_stories) != len(all_stories):
        logger.info(f"[AUDITOR] Filtered out {len(all_stories) - len(unlocked_stories)} locked user stories from audit.")
    to_audit_stories = [story for story in unlocked_stories if story.get("change_type") in ["created", "updated", None]]
    unchanged_stories = [story for story in unlocked_stories if story.get("change_type") == "unchanged"]
    
    logger.info(f"Auditor Node: {len(to_audit_stories)} stories to audit, {len(unchanged_stories)} unchanged stories.")
    
    if not to_audit_stories:
        logger.info("Auditor Node: All user stories are unchanged. Skipping LLM execution and keeping existing validation status.")
        is_valid = req_state.get("validation_status") == "valid"
        fallback_checks = ["Idempotency", "Security", "Audit Logging", "Database Consistency", "Network Timeouts", "Financial Regulatory Compliance", "Edge-Case Failure Handling"]
        result = {
            "is_valid": is_valid,
            "audit_version_reviewed": current_version,
            "passed_checks": fallback_checks if is_valid else [],
            "failed_checks": [] if is_valid else fallback_checks,
            "clarification_questions": req_state.get("clarification_questions", [])
        }
        
        req_state["current_workflow_state"] = "auditor_node"
        req_state["passed_checks"] = result.get("passed_checks", [])
        req_state["failed_checks"] = result.get("failed_checks", [])
        return {
            "requirement_state": req_state,
            "audit_result": result
        }

    # Only send newly created or updated user stories for LLM evaluation
    requirements = req_state.get("requirements", [])
    epic_name = requirements[0].get("title", "") if requirements else ""
    structured_reqs_for_prompt = {
        "epic_name": epic_name,
        "version": req_state["version_number"],
        "user_stories": to_audit_stories
    }
    
    prompt = PromptTemplate(
        template=load_prompt("auditor"),
        input_variables=["structured_requirements", "current_version"]
    )
    
    chain = prompt | llm | parser
    
    try:
        req_json_str = json.dumps(structured_reqs_for_prompt, ensure_ascii=False)
        result = await chain.ainvoke({
            "structured_requirements": req_json_str,
            "current_version": current_version
        })
        
        # Merge new questions with existing unresolved questions targeting unchanged user stories
        new_questions = result.get("clarification_questions", [])
        unchanged_story_codes = {s.get("ticket_code") for s in unchanged_stories}
        existing_questions = req_state.get("clarification_questions", [])
        
        preserved_questions = []
        for q in existing_questions:
            if q.get("target_user_story_id") in unchanged_story_codes and not q.get("is_resolved", False):
                preserved_questions.append(q)
                
        combined_questions = preserved_questions + new_questions
        result["clarification_questions"] = combined_questions
        
        # Determine overall validity
        is_valid = len(combined_questions) == 0
        result["is_valid"] = is_valid
        
        # Modify only its own fields in RequirementState in memory
        req_state["clarification_questions"] = combined_questions
        req_state["validation_status"] = "valid" if is_valid else "invalid"
        req_state["passed_checks"] = result.get("passed_checks", [])
        req_state["failed_checks"] = result.get("failed_checks", [])
        req_state["current_workflow_state"] = "auditor_node"

        if is_valid:
            auditor_msg = "✅ **Compliance Audit Passed!**\nRequirements have successfully validated against all retail banking security and regulatory checks. Ready for PRD compilation."
        else:
            q_texts = "\n".join([f"• {q.get('question_text')}" for q in combined_questions if isinstance(q, dict)])
            auditor_msg = f"⚠️ **Compliance Audit Alert (Auditor Agent):**\nTechnical gaps or missing security constraints were detected in your specifications against our checklist.\n\n**Pending Clarifications:**\n{q_texts or 'None specified'}"

        await ConversationMessageRepository.save_message(
            project_id=project_id,
            role="auditor",
            message=auditor_msg,
            workflow_state="auditor_node",
            intent="AUDIT"
        )
        
        return {
            "requirement_state": req_state,
            "audit_result": result
        }
    except Exception as e:
        logger.error(f"Error parsing structured response in auditor_node: {str(e)}")
        fallback_audit = {
            "is_valid": False,
            "audit_version_reviewed": current_version,
            "passed_checks": [],
            "failed_checks": ["AUDIT_PARSE_ERROR"],
            "clarification_questions": [
                {
                    "checklist_category": "System Error",
                    "target_user_story_id": "ALL",
                    "question_text": f"The Auditor workflow encountered a parsing error: {str(e)}."
                }
            ]
        }
        req_state["clarification_questions"] = fallback_audit["clarification_questions"]
        req_state["validation_status"] = "invalid"
        req_state["passed_checks"] = []
        req_state["failed_checks"] = ["AUDIT_PARSE_ERROR"]
        req_state["current_workflow_state"] = "auditor_node"
        
        return {
            "requirement_state": req_state,
            "audit_result": fallback_audit
        }

async def architect_node(state: AgentState) -> Dict[str, Any]:
    """
    Transforms audited requirements metadata into clean Markdown PRDs with embedded Mermaid diagrams.
    Reads from and writes to the centralized RequirementState object via persistence service.
    Only regenerates sections of the PRD affected by the changes to maintain high consistency.
    """
    logger.info("Executing architect_node to compile PRD specifications.")
    project_id = state.get("project_id", "PROJ-UNKNOWN")
    
    # Use session from state if available, otherwise let function create one
    db_session = state.get("db_session")
    req_state = await get_or_init_requirement_state(project_id, session=db_session, current_version=state.get("current_version", 1))
    
    passed_structured = state.get("structured_requirements") or {}
    if passed_structured:
        # LOCK ENFORCEMENT: Exclude locked user stories from PRD generation
        passed_stories = [
            us for us in passed_structured.get("user_stories", [])
            if not (us.get("is_locked", False))
        ]
        # Preserve database identity from the previous requirement record(s).
        # The synthetic rebuild below must keep the ``id`` field — it is
        # REQUIRED by the RequirementDetail response schema; dropping it made
        # every on-demand PRD generation fail FastAPI response validation with
        # an opaque HTTP 500 ("PRD Generation Failed — No Document Saved").
        # The stored requirement_code / title are preserved as well instead of
        # being reset onto a hardcoded ``REQ-001``.
        incoming_reqs = passed_structured.get("requirements")
        if isinstance(incoming_reqs, list) and any(isinstance(r, dict) for r in incoming_reqs):
            rebuilt_reqs = []
            for idx, inc in enumerate(incoming_reqs):
                if not isinstance(inc, dict):
                    continue
                inc_stories = [
                    us for us in (inc.get("user_stories") or [])
                    if isinstance(us, dict) and not us.get("is_locked", False)
                ]
                rebuilt_reqs.append({
                    **inc,
                    "requirement_code": inc.get("requirement_code") or _default_requirement_code(idx),
                    "title": inc.get("title") or passed_structured.get("epic_name", ""),
                    "user_stories": inc_stories or passed_stories
                })
            if rebuilt_reqs:
                req_state["requirements"] = rebuilt_reqs
            else:
                prev_matched = _previous_requirement_identity(req_state)
                req_state["requirements"] = [{
                    **prev_matched,
                    "requirement_code": prev_matched.get("requirement_code") or _default_requirement_code(0),
                    "title": passed_structured.get("epic_name", ""),
                    "description": "",
                    "user_stories": passed_stories
                }]
        else:
            prev_matched = _previous_requirement_identity(req_state)
            req_state["requirements"] = [
                {
                    **prev_matched,
                    "requirement_code": prev_matched.get("requirement_code") or _default_requirement_code(0),
                    "title": passed_structured.get("epic_name") or prev_matched.get("title", ""),
                    "description": prev_matched.get("description", ""),
                    "user_stories": passed_stories
                }
            ]
        req_state["user_stories"] = passed_stories
        req_state["version_number"] = passed_structured.get("version", req_state["version_number"])
        all_ac = []
        for us in req_state["user_stories"]:
            all_ac.extend(us.get("acceptance_criteria", []))
        req_state["acceptance_criteria"] = all_ac

    # Step 11 compliance: Segment user stories to check for changes
    # LOCK ENFORCEMENT: Exclude locked user stories from PRD generation
    all_stories = req_state.get("user_stories", [])
    unlocked_stories = [
        story for story in all_stories
        if not (story.get("is_locked", False))
    ]
    if len(unlocked_stories) != len(all_stories):
        logger.info(f"[ARCHITECT] Filtered out {len(all_stories) - len(unlocked_stories)} locked user stories from PRD generation.")
    to_build_stories = [story for story in unlocked_stories if story.get("change_type") in ["created", "updated", None]]
    
    # If everything is unchanged, and we have an existing PRD/Diagram, bypass LLM entirely.
    # GUARD: only reuse when the stored PRD already follows the official
    # Krungsri Nimble template (prompts/template.md); legacy PRDs generated
    # from the old hard-coded section list must be regenerated so they migrate
    # to the new document structure instead of being served verbatim forever.
    existing_prd = req_state.get("generated_prd")
    existing_diagrams = req_state.get("generated_diagrams")

    if (
        not to_build_stories
        and existing_prd
        and existing_diagrams
        and _prd_follows_krungsri_template(existing_prd)
    ):
        logger.info("Architect Node: All user stories are unchanged. Reusing existing PRD and diagrams without LLM invocation.")
        req_state["current_workflow_state"] = "architect_node"
        return {
            "requirement_state": req_state,
            "prd_markdown": existing_prd,
            "mermaid_diagram": existing_diagrams
        }

    requirements = req_state.get("requirements", [])
    nested = any(
        isinstance(r, dict) and r.get("user_stories") for r in requirements
    )

    if not unlocked_stories and not nested:
        # FAIL LOUDLY: invoking the LLM with an empty story set would only
        # produce a hallucinated PRD. Raise so /api/process-requirements maps
        # this to HTTP 500 and nothing is persisted. Stories may live flat in
        # user_stories OR nested inside requirements - both are valid. A
        # stored LEGACY PRD does not excuse an empty dataset: it is never
        # reused or merged, so there is nothing to regenerate from.
        raise ValueError(
            f"Cannot compile PRD for project {project_id}: no unlocked user stories "
            "are available. Gather requirements before generating a PRD."
        )

    version_history_summaries = state.get("version_history_summaries", "No previous revision logs available.")

    # DETERMINISTIC TEMPLATE FILL: the PRD is the official Krungsri Nimble
    # template with its blank fields filled from the project's own (AI-gathered
    # and AI-validated) data. The skeleton - every table, merged-cell structure
    # and \newpage marker - is ALWAYS the untouched official template, so the
    # result is PDF-exact and compiles every time. No free-form LLM text is
    # spliced into the structure, so exports can no longer fail on model
    # escaping mistakes (dropped row terminators, unbalanced braces, ...).
    from app.prd_filler import fill_template_body

    stories_flat: List[Dict[str, Any]] = []
    if nested:
        for r in requirements:
            if isinstance(r, dict):
                stories_flat.extend(r.get("user_stories") or [])
    else:
        stories_flat = unlocked_stories

    epic_name = requirements[0].get("title", "") if requirements else ""
    data: Dict[str, Any] = {
        "epic_name": epic_name,
        "business_goals": req_state.get("business_goals", []),
        "actors": req_state.get("actors", []),
        "requirements": requirements if nested else [],
        "user_stories": [] if nested else unlocked_stories,
        "acceptance_criteria": [] if nested else req_state.get("acceptance_criteria", []),
        "problem_statement": req_state.get("problem_statement", []),
        "scope_in": [s.get("story_title", "") for s in stories_flat if s.get("story_title")],
        "scope_out": req_state.get("scope_out", []),
    }


    generated_prd = fill_template_body(
        project_id=project_id,
        project_name=req_state.get("project_name", "") or "",
        version=req_state["version_number"],
        data=data,
        version_summary=(version_history_summaries or "").strip() or "Initial approved version",
    )

    req_state["generated_prd"] = generated_prd
    # Keep any previously generated diagram; the template fill owns the document.
    req_state["generated_diagrams"] = req_state.get("generated_diagrams", "")
    req_state["current_workflow_state"] = "architect_node"

    # Persist the freshly filled document as an immutable version record.


    # Create an immutable PRD version record
    try:
        if db_session:
            await PRDVersionRepository.create(project_id, {
                "generated_prd": req_state["generated_prd"],
                "generated_diagram": req_state["generated_diagrams"],
                "generated_by": "automated_agent"
            }, db_session)
            logger.info(f"[PRD VERSION] Created new PRD version for project {project_id}")
    except Exception as version_err:
        logger.error(f"[PRD VERSION] Failed to create PRD version: {str(version_err)}")

    architect_msg = "📄 **Enterprise PRD Compiled Successfully!**\nThe CTO Architect Agent has generated the formal PRD and interactive system sequence flows in the preview panel."
    await ConversationMessageRepository.save_message(
        project_id=project_id,
        role="architect",
        message=architect_msg,
        workflow_state="architect_node",
        intent="PRD_GENERATION"
    )
    
    return {
        "requirement_state": req_state,
        "prd_markdown": req_state["generated_prd"],
        "mermaid_diagram": req_state["generated_diagrams"]
    }

# ==========================================
# ON-DEMAND ROUTING ROUTINE
# ==========================================
def route_on_demand(state: AgentState) -> str:
    """
    Evaluates target_agent parameter in AgentState.
    Routes execution to the designated on-demand agent node,
    preserving full state between disconnected invocations.
    New: Supports 'delete_requirement' target for DELETE_REQUIREMENT intent.
    """
    target = state.get("target_agent", "gatherer")
    detected_intent = state.get("detected_intent", "")
    
    if target == "auditor":
        logger.info("Routing to auditor_node on-demand.")
        return "auditor_node"
    elif target == "architect":
        logger.info("Routing to architect_node on-demand.")
        return "architect_node"
    elif target == "delete_requirement" or detected_intent == "DELETE_REQUIREMENT":
        logger.info("Routing to delete_requirement_node on-demand.")
        return "delete_requirement_node"
    else:
        logger.info("Routing to router_node before Gatherer.")
        return "router_node"

def route_from_router(state: AgentState) -> str:
    """
    Routes based on workflow classification from workflow_router_node.
    """
    routing = state.get("workflow_routing") or {}
    wf = str(routing.get("workflow", "REQUIREMENT")).upper()
    if wf == "REQUIREMENT":
        return "requirement_matcher_node"
    elif wf == "COMMAND":
        target = state.get("target_agent")
        if target == "auditor":
            return "auditor_node"
        elif target == "architect":
            return "architect_node"
        return END
    else:  # CHAT or QUESTION
        return END

def route_from_matcher(state: AgentState) -> str:
    """
    Routes based on requirement matcher validation status.
    """
    req_state = state.get("requirement_state", {})
    if req_state.get("validation_status") == "invalid":
        return END
    return "gatherer_node"

# ==========================================
# GRAPH COMPILATION
# ==========================================
workflow = StateGraph(AgentState)

# Append active node configurations
workflow.add_node("router_node", workflow_router_node)
workflow.add_node("requirement_matcher_node", requirement_matcher_node)
workflow.add_node("gatherer_node", gatherer_node)
workflow.add_node("auditor_node", auditor_node)
workflow.add_node("architect_node", architect_node)
workflow.add_node("delete_requirement_node", delete_requirement_node)

# Set up conditional routing from START based on target_agent
workflow.add_conditional_edges(
    START,
    route_on_demand,
    {
        "router_node": "router_node",
        "auditor_node": "auditor_node",
        "architect_node": "architect_node",
        "delete_requirement_node": "delete_requirement_node"
    }
)

# Route from router_node based on workflow classification
workflow.add_conditional_edges(
    "router_node",
    route_from_router,
    {
        "requirement_matcher_node": "requirement_matcher_node",
        "auditor_node": "auditor_node",
        "architect_node": "architect_node",
        END: END
    }
)

# Route from requirement_matcher_node to gatherer_node or END (if ambiguous / low confidence)
workflow.add_conditional_edges(
    "requirement_matcher_node",
    route_from_matcher,
    {
        "gatherer_node": "gatherer_node",
        END: END
    }
)

# Connect each on-demand agent directly to END to stop workflow execution
workflow.add_edge("gatherer_node", END)
workflow.add_edge("auditor_node", END)
workflow.add_edge("architect_node", END)
workflow.add_edge("delete_requirement_node", END)

# Export compiled graph workflow
prd_workflow = workflow.compile()
logger.info("StateGraph compiled successfully with requirement matcher agent and workflow router.")