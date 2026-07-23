import logging
import json
from typing import TypedDict, Dict, Any, List, Optional
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import JsonOutputParser, PydanticOutputParser
try:
    from langchain.output_parsers import OutputFixingParser
except ImportError:
    OutputFixingParser = None
from langgraph.graph import StateGraph, START, END
from app.repository import RequirementStateRepository, ConversationMessageRepository
from app.schemas import GatheredRequirements, UserStoryModel
from app.prompt_loader import load_prompt


# Set up logging configuration for the multi-agent framework
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app.agents")

# ==========================================
# SYSTEM PROMPTS (LOADED DYNAMICALLY VIA PROMPT LOADER)
# ==========================================
class _PromptProxy:
    def __init__(self, name: str):
        self.name = name
    def __str__(self) -> str:
        return load_prompt(self.name)
    def __add__(self, other: str) -> str:
        return load_prompt(self.name) + str(other)
    def __radd__(self, other: str) -> str:
        return str(other) + load_prompt(self.name)

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

# ==========================================
# LOCAL LLM ORCHESTRATION CLIENT
# ==========================================
# Safe context limit mapping designed for MacBook Air/Pro M4 16GB execution bounds
llm = ChatOpenAI(
    base_url="http://localhost:1234/v1",
    api_key="lm-studio",
    model="qwen-3.5-9b",
    temperature=0.0,
    max_tokens=800,  # Optimized for structured output
    model_kwargs={"seed": 42}
)

# Json Output Parser for strict structured JSON outputs
parser = JsonOutputParser()

async def get_or_init_requirement_state(project_id: str, current_version: int = 1) -> RequirementState:
    """
    Retrieves or initializes the centralized RequirementState object from Supabase.
    """
    logger.info(f"[DB LOG] [AGENTS] Loading project state for {project_id}...")
    db_state = await RequirementStateRepository.get_by_project_id(project_id)
    logger.info(f"[DB LOG] [AGENTS] Loading project state for {project_id} complete. Found: {db_state is not None}")
    if not db_state:
        db_state = {
            "project_id": project_id,
            "project_name": "PromptPay Settlement Engine",
            "requirements": {},
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

def extract_content_from_response(response) -> str:
    """Robustly extracts content from ChatOpenAI response."""
    # 1. Log everything
    logger.info(f"LLM Response Object Type: {type(response)}")
    # Log representation, limiting length to avoid excessive logging
    logger.info(f"LLM Response Object Repr: {repr(response)[:1000]}")
    logger.info(f"LLM Response Content: {response.content}")
    logger.info(f"LLM Response Additional Kwargs: {response.additional_kwargs}")
    logger.info(f"LLM Response Metadata: {response.response_metadata}")

    # 2. Extract content
    content = ""
    if hasattr(response, "content") and isinstance(response.content, str) and response.content.strip():
        content = response.content
    elif hasattr(response, "additional_kwargs"):
        if "content" in response.additional_kwargs:
            content = response.additional_kwargs["content"]
        # Handle reasoning models (if reasoning_content is present, look for the final answer)
        if "reasoning_content" in response.additional_kwargs:
            logger.info("Reasoning mode detected.")
            # If main content is empty, check if final answer is in another field or mixed in
            if not content:
                content = response.additional_kwargs.get("final_answer", "")
    elif hasattr(response, "response_metadata") and "content" in response.response_metadata:
         content = response.response_metadata["content"]
         
    logger.info(f"Extracted content: {content[:500] if content else 'EMPTY'}")
    return content

def normalize_ticket_code(code: Optional[str]) -> str:
    if not code:
        return ""
    code = str(code).strip().upper()
    if code.startswith("US-"):
        num_part = code[3:]
        if num_part.isdigit():
            return f"US-{int(num_part):03d}"
    return code

def normalize_title(title: Optional[str]) -> str:
    if not title:
        return ""
    return " ".join(str(title).lower().strip().split())

def generate_next_ticket_code(stories: List[Dict[str, Any]]) -> str:
    max_num = 0
    for s in stories:
        tc = s.get("ticket_code", "")
        if tc and str(tc).strip().upper().startswith("US-"):
            num_part = str(tc).strip().upper()[3:]
            if num_part.isdigit():
                max_num = max(max_num, int(num_part))
    return f"US-{max_num + 1:03d}"

def merge_user_stories(
    existing_stories: List[Dict[str, Any]],
    new_incoming_stories: List[Dict[str, Any]],
    semantic_recs: Optional[List[Dict[str, Any]]] = None
) -> List[Dict[str, Any]]:
    """
    Merges newly generated user stories with existing user stories.
    Requirements:
    - Load all existing User Stories.
    - Merge newly generated User Stories.
    - Keep unchanged stories (change_type="unchanged", status="active").
    - Update modified stories (change_type="updated", status="active").
    - Insert new stories (change_type="created", status="active").
    - Archive deleted stories (change_type="archived", status="archived").
    """
    semantic_recs = semantic_recs or []
    
    rec_by_code = {}
    rec_by_title = {}
    for rec in semantic_recs:
        target_id = rec.get("target_requirement_id")
        action = rec.get("recommended_action")
        if target_id and action:
            norm_target = normalize_ticket_code(target_id)
            if norm_target:
                rec_by_code[norm_target] = action
            else:
                rec_by_title[normalize_title(target_id)] = action

    existing_by_id = {}
    existing_by_code = {}
    existing_by_title = {}
    
    active_existing = [s for s in existing_stories if s.get("status", "active") == "active"]
    
    for s in active_existing:
        if s.get("id"):
            existing_by_id[str(s["id"])] = s
        code = normalize_ticket_code(s.get("ticket_code"))
        if code and code != "US-000":
            existing_by_code[code] = s
        title = normalize_title(s.get("story_title"))
        if title:
            existing_by_title[title] = s

    matched_existing_ptrs = set()
    merged_stories: List[Dict[str, Any]] = []

    # 1. Process incoming stories
    for inc in new_incoming_stories:
        inc_id = str(inc["id"]) if inc.get("id") else None
        inc_code = normalize_ticket_code(inc.get("ticket_code"))
        inc_title = normalize_title(inc.get("story_title"))
        
        matched = None
        if inc_id and inc_id in existing_by_id:
            matched = existing_by_id[inc_id]
        elif inc_code and inc_code in existing_by_code:
            matched = existing_by_code[inc_code]
        elif inc_title and inc_title in existing_by_title:
            matched = existing_by_title[inc_title]

        if matched:
            matched_existing_ptrs.add(id(matched))
            
            rec_act = rec_by_code.get(inc_code) or rec_by_code.get(normalize_ticket_code(matched.get("ticket_code"))) or rec_by_title.get(inc_title)
            
            if rec_act == "ARCHIVE" or inc.get("status") == "archived" or inc.get("change_type") == "archived":
                archived_story = dict(matched)
                archived_story["status"] = "archived"
                archived_story["change_type"] = "archived"
                merged_stories.append(archived_story)
                continue

            # Compare fields to check if modified
            m_title = (matched.get("story_title") or "").strip()
            m_as_a = (matched.get("as_a") or "").strip()
            m_i_want = (matched.get("i_want_to") or "").strip()
            m_so_that = (matched.get("so_that") or "").strip()
            m_ac = matched.get("acceptance_criteria", [])

            i_title = (inc.get("story_title") or m_title).strip()
            i_as_a = (inc.get("as_a") or m_as_a).strip()
            i_i_want = (inc.get("i_want_to") or m_i_want).strip()
            i_so_that = (inc.get("so_that") or m_so_that).strip()
            i_ac = inc.get("acceptance_criteria") if "acceptance_criteria" in inc else m_ac

            title_diff = (m_title != i_title)
            as_a_diff = (m_as_a != i_as_a)
            i_want_diff = (m_i_want != i_i_want)
            so_that_diff = (m_so_that != i_so_that)
            ac_diff = (m_ac != i_ac)

            field_changed = title_diff or as_a_diff or i_want_diff or so_that_diff or ac_diff

            if rec_act == "UPDATE":
                is_modified = True
            elif rec_act == "NO_CHANGE":
                is_modified = False
            else:
                is_modified = field_changed

            updated_story = dict(matched)
            updated_story["story_title"] = i_title
            updated_story["as_a"] = i_as_a
            updated_story["i_want_to"] = i_i_want
            updated_story["so_that"] = i_so_that
            updated_story["acceptance_criteria"] = i_ac
            updated_story["status"] = "active"
            updated_story["change_type"] = "updated" if is_modified else "unchanged"

            if inc_code and inc_code != "US-000":
                updated_story["ticket_code"] = inc_code
            elif not updated_story.get("ticket_code"):
                updated_story["ticket_code"] = matched.get("ticket_code") or "US-001"

            merged_stories.append(updated_story)

        else:
            # Unmatched incoming -> New story insertion
            rec_act = rec_by_code.get(inc_code) or rec_by_title.get(inc_title)
            if rec_act == "ARCHIVE" or inc.get("status") == "archived":
                continue

            ticket_code = inc_code
            if not ticket_code or ticket_code == "US-000" or ticket_code in existing_by_code:
                ticket_code = generate_next_ticket_code(active_existing + merged_stories)

            new_story = {
                "ticket_code": ticket_code,
                "story_title": inc.get("story_title", "Untitled Story"),
                "as_a": inc.get("as_a", ""),
                "i_want_to": inc.get("i_want_to", ""),
                "so_that": inc.get("so_that", ""),
                "acceptance_criteria": inc.get("acceptance_criteria", []),
                "status": "active",
                "change_type": "created"
            }
            if inc.get("id"):
                new_story["id"] = inc["id"]

            merged_stories.append(new_story)

    # 2. Process existing active stories that were NOT matched by incoming
    for ex in active_existing:
        if id(ex) in matched_existing_ptrs:
            continue

        ex_code = normalize_ticket_code(ex.get("ticket_code"))
        ex_title = normalize_title(ex.get("story_title"))
        rec_act = rec_by_code.get(ex_code) or rec_by_title.get(ex_title)

        if rec_act == "ARCHIVE":
            archived_story = dict(ex)
            archived_story["status"] = "archived"
            archived_story["change_type"] = "archived"
            merged_stories.append(archived_story)
        else:
            # KEEP UNCHANGED!
            unchanged_story = dict(ex)
            unchanged_story["status"] = "active"
            unchanged_story["change_type"] = "unchanged"
            merged_stories.append(unchanged_story)

    return merged_stories

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
    from app.semantic_service import classify_workflow

    raw_input = state.get("raw_input", "")
    target_agent = state.get("target_agent", "gatherer")

    logger.info(f"[WORKFLOW ROUTER] Intercepted raw_input: '{raw_input[:100]}'")

    # Run classification
    router_result = await classify_workflow(raw_input)
    workflow_type = str(router_result.get("workflow", "REQUIREMENT")).upper()
    logger.info(f"[WORKFLOW ROUTER] Classification: {router_result}")

    project_id = state.get("project_id", "PROJ-UNKNOWN")
    req_state = await get_or_init_requirement_state(project_id, state.get("current_version", 1))

    if workflow_type == "CHAT":
        logger.info("[WORKFLOW ROUTER] Handling as CHAT. Generating conversational response.")
        chat_sys = (
            "You are a helpful, professional AI Business Analyst assistant for core banking projects. "
            "Respond cordially and politely to conversational greetings or pleasantries. "
            "Do NOT attempt to generate, create, or update software requirements."
        )
        try:
            resp = await llm.ainvoke([SystemMessage(content=chat_sys), HumanMessage(content=raw_input)])
            msg_content = resp.content if hasattr(resp, "content") else str(resp)
        except Exception as e:
            logger.warning(f"Failed LLM chat invocation: {str(e)}")
            msg_content = "Hello! How can I assist you with your core banking requirements today?"

        return {
            "workflow_routing": router_result,
            "agent_message": msg_content,
            "requirement_state": req_state
        }

    elif workflow_type == "QUESTION":
        logger.info("[WORKFLOW ROUTER] Handling as QUESTION. Answering direct question.")
        existing_epic = req_state.get("requirements", {}).get("epic_name", "")
        stories = req_state.get("user_stories", [])
        stories_summary = "\n".join([f"- {s.get('ticket_code', 'US')}: {s.get('story_title', '')}" for s in stories[:10]])

        q_sys = (
            "You are an expert Enterprise Software Architect and Business Analyst. "
            "Answer the user's question clearly, precisely, and directly. "
            f"Current Project Context: Epic='{existing_epic}'. Stories:\n{stories_summary}\n"
            "Do NOT create or modify software requirements JSON. Focus purely on answering the question."
        )
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
    from app.semantic_service import detect_requirement_intent, match_requirement

    raw_input = state.get("raw_input", "")
    project_id = state.get("project_id", "PROJ-UNKNOWN")
    req_state = await get_or_init_requirement_state(project_id, state.get("current_version", 1))
    existing_stories = req_state.get("user_stories", [])

    detected_intent = state.get("detected_intent")
    if not detected_intent and raw_input:
        intent_res = await detect_requirement_intent(raw_input, existing_stories)
        detected_intent = intent_res.get("intent", "UPDATE")
    elif not detected_intent:
        detected_intent = "NO_CHANGE"

    match_result = await match_requirement(raw_input, detected_intent, existing_stories)
    matcher_status = str(match_result.get("status", "MATCHED")).upper()
    matcher_confidence = float(match_result.get("confidence", 1.0))
    reason = match_result.get("reason", "")
    matched_id = match_result.get("matched_requirement_id")
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
            message=f"⚠️ **Clarification Needed (Requirement Matcher):**\n{clarification_text}"
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

async def gatherer_node(state: AgentState) -> Dict[str, Any]:
    """
    Standardizes messy Product Owner input into high-quality Agile structures.
    Reads/writes to the centralized RequirementState object via persistence service.
    """
    logger.info("Executing gatherer_node to structure requirements.")
    project_id = state.get("project_id", "PROJ-UNKNOWN")
    raw_input = state.get("raw_input", "")
    req_state = await get_or_init_requirement_state(project_id, state.get("current_version", 1))
    
    # Store existing user stories before processing passed_structured or raw_input
    existing_user_stories = list(req_state.get("user_stories", []))

    passed_structured = state.get("structured_requirements") or {}
    if passed_structured:
        req_state["requirements"] = {"epic_name": passed_structured.get("epic_name", "")}
        req_state["version_number"] = passed_structured.get("version", req_state["version_number"])

    result = None
    parsing_error = None
    
    # Import inside function to prevent circular imports
    from app.semantic_service import detect_semantic_changes, detect_requirement_intent

    # Detect user intent before running the Gatherer
    detected_intent = state.get("detected_intent")
    intent_confidence = 1.0
    intent_reason = ""
    if not detected_intent and raw_input:
        intent_res = await detect_requirement_intent(raw_input, existing_user_stories)
        detected_intent = intent_res.get("intent", "UPDATE")
        intent_confidence = float(intent_res.get("confidence", 1.0))
        intent_reason = intent_res.get("reason", "")
    elif not detected_intent:
        detected_intent = "NO_CHANGE"

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
            semantic_recs = await detect_semantic_changes(raw_input, req_state.get("user_stories", []))

        
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
        existing_epic = req_state.get("requirements", {}).get("epic_name", "")
        context_lines = []
        if existing_epic:
            context_lines.append(f"CURRENT ACTIVE EPIC: {existing_epic}\n(Note: DO NOT change this Epic Name unless the user explicitly requests to change or rename the epic)\n")
        for story in req_state.get("user_stories", []):
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
        
        # Attempt 1: with_structured_output
        try:
            logger.info("Attempting .with_structured_output() in gatherer")
            chain = prompt_template | llm.with_structured_output(GatheredRequirements)
            parsed_output = await chain.ainvoke({
                "raw_input": raw_input,
                "detected_intent": detected_intent,
                "current_context": current_context,
                "recommendations": recs_str,
                "format_instructions": "Output ONLY raw JSON. No markdown."
            })
            result = parsed_output.dict() if hasattr(parsed_output, "dict") else dict(parsed_output)
            logger.info("Successfully obtained structured output.")
        except Exception as e:
            logger.warning(f"with_structured_output failed in gatherer: {str(e)}. Retrying with raw invocation.")
            
            # Attempt 2: Raw invocation + robust manual parsing
            try:
                raw_chain = prompt_template | llm
                raw_response = await raw_chain.ainvoke({
                    "raw_input": raw_input,
                    "detected_intent": detected_intent,
                    "current_context": current_context,
                    "recommendations": recs_str,
                    "format_instructions": format_instructions
                })
                
                raw_content = extract_content_from_response(raw_response)
                
                logger.info(f"LLM completion length: {len(raw_content)}. First 500 chars: {raw_content[:500]}")
                
                # Resilient cleanup: remove markdown, whitespace, etc.
                clean_content = raw_content.strip()
                if clean_content.startswith("```json"): clean_content = clean_content[7:]
                elif clean_content.startswith("```"): clean_content = clean_content[3:]
                if clean_content.endswith("```"): clean_content = clean_content[:-3]
                clean_content = clean_content.strip()
                
                try:
                    result = json.loads(clean_content)
                except json.JSONDecodeError as jde:
                    logger.error(f"Manual JSON parsing failed. Raw: {raw_content[:500]}... Error: {str(jde)}")
                    raise jde
                    
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
    existing_epic_name = req_state.get("requirements", {}).get("epic_name", "")
    llm_epic_name = result.get("epic_name", "")
    
    raw_input_lower = raw_input.lower() if raw_input else ""
    user_explicitly_changed_epic = any(k in raw_input_lower for k in ["rename epic", "change epic", "new epic", "update epic", "epic name"])
    
    is_placeholder = existing_epic_name in ["", "Untitled Epic", "Structured Requirements Draft"]
    if existing_epic_name and not is_placeholder and not user_explicitly_changed_epic:
        epic_name = existing_epic_name
    else:
        epic_name = llm_epic_name or existing_epic_name or "Structured Requirements Draft"

    requirements = {"epic_name": epic_name}
    newly_generated_stories = result.get("user_stories", [])
    
    # Synchronize user stories: merge newly generated user stories with existing user stories
    merged_stories = merge_user_stories(
        existing_stories=existing_user_stories,
        new_incoming_stories=newly_generated_stories,
        semantic_recs=semantic_recs
    )
    
    active_stories = [s for s in merged_stories if s.get("status", "active") == "active"]
    ac_list = []
    for story in active_stories:
        ac_list.extend(story.get("acceptance_criteria", []))
    version_number = result.get("version", req_state["version_number"])
    
    # Perform merge in memory
    req_state["requirements"] = requirements
    req_state["user_stories"] = active_stories
    req_state["all_merged_stories"] = merged_stories
    req_state["acceptance_criteria"] = ac_list
    req_state["version_number"] = version_number
    req_state["current_workflow_state"] = "gatherer_node"
    req_state["semantic_recommendations"] = semantic_recs
    req_state["detected_intent"] = detected_intent

    gatherer_msg = "📥 **Requirements Gathered & Updated!**\nI have successfully structured your input into the Agile Requirements board."
    await ConversationMessageRepository.save_message(
        project_id=project_id,
        role="gatherer",
        message=gatherer_msg
    )
    
    # Sync to outer structure for backend/frontend backward compatibility
    structured_out = {
        "epic_name": epic_name,
        "version": version_number,
        "user_stories": active_stories
    }
    
    return {
        "requirement_state": req_state,
        "structured_requirements": structured_out,
        "detected_intent": detected_intent,
        "current_version": version_number
    }

async def auditor_node(state: AgentState) -> Dict[str, Any]:
    """
    Runs compliance, safety, and business rule audits on structured drafts.
    Reads from and writes to the centralized RequirementState object via persistence service.
    Only audits newly created or modified user stories to save API costs and maintain consistency.
    """
    logger.info("Executing auditor_node to audit compliance.")
    project_id = state.get("project_id", "PROJ-UNKNOWN")
    req_state = await get_or_init_requirement_state(project_id, state.get("current_version", 1))
    
    passed_structured = state.get("structured_requirements") or {}
    if passed_structured:
        req_state["requirements"] = {"epic_name": passed_structured.get("epic_name", "")}
        req_state["user_stories"] = passed_structured.get("user_stories", [])
        req_state["version_number"] = passed_structured.get("version", req_state["version_number"])
        all_ac = []
        for us in req_state["user_stories"]:
            all_ac.extend(us.get("acceptance_criteria", []))
        req_state["acceptance_criteria"] = all_ac

    current_version = req_state["version_number"]
    
    # Step 10 compliance: Segment user stories by change_type
    all_stories = req_state.get("user_stories", [])
    to_audit_stories = [story for story in all_stories if story.get("change_type") in ["created", "updated", None]]
    unchanged_stories = [story for story in all_stories if story.get("change_type") == "unchanged"]
    
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
    structured_reqs_for_prompt = {
        "epic_name": req_state["requirements"].get("epic_name", ""),
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
            message=auditor_msg
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
    req_state = await get_or_init_requirement_state(project_id, state.get("current_version", 1))
    
    passed_structured = state.get("structured_requirements") or {}
    if passed_structured:
        req_state["requirements"] = {"epic_name": passed_structured.get("epic_name", "")}
        req_state["user_stories"] = passed_structured.get("user_stories", [])
        req_state["version_number"] = passed_structured.get("version", req_state["version_number"])
        all_ac = []
        for us in req_state["user_stories"]:
            all_ac.extend(us.get("acceptance_criteria", []))
        req_state["acceptance_criteria"] = all_ac

    current_version = req_state["version_number"]
    
    # Step 11 compliance: Segment user stories to check for changes
    all_stories = req_state.get("user_stories", [])
    to_build_stories = [story for story in all_stories if story.get("change_type") in ["created", "updated", None]]
    unchanged_stories = [story for story in all_stories if story.get("change_type") == "unchanged"]
    
    # If everything is unchanged, and we have an existing PRD/Diagram, bypass LLM entirely
    existing_prd = req_state.get("generated_prd")
    existing_diagrams = req_state.get("generated_diagrams")
    
    if not to_build_stories and existing_prd and existing_diagrams:
        logger.info("Architect Node: All user stories are unchanged. Reusing existing PRD and diagrams without LLM invocation.")
        req_state["current_workflow_state"] = "architect_node"
        return {
            "requirement_state": req_state,
            "prd_markdown": existing_prd,
            "mermaid_diagram": existing_diagrams
        }
        
    structured_reqs_for_prompt = {
        "epic_name": req_state["requirements"].get("epic_name", ""),
        "version": req_state["version_number"],
        "user_stories": req_state["user_stories"]
    }
    version_history_summaries = state.get("version_history_summaries", "No previous revision logs available.")
    
    # Customize prompt for incremental generation if existing PRD exists
    dynamic_instructions = ""
    if existing_prd:
        dynamic_instructions = (
            f"\n\nCRITICAL INCREMENTAL MERGE INSTRUCTIONS:\n"
            f"An existing PRD is provided below. You must ONLY regenerate the sections of the PRD "
            f"affected by the newly created or updated user stories ({json.dumps([s.get('ticket_code') for s in to_build_stories])}). "
            f"All other sections of the PRD must remain completely unchanged, preserving their original wording "
            f"and formatting exactly.\n\n"
            f"<existing_prd_content>\n{existing_prd}\n</existing_prd_content>\n"
        )
        
    prompt = PromptTemplate(
        template=load_prompt("architect") + dynamic_instructions,
        input_variables=["project_id", "current_version", "validated_requirements", "version_history_summaries"]
    )
    
    chain = prompt | llm | parser
    
    try:
        req_json_str = json.dumps(structured_reqs_for_prompt, ensure_ascii=False)
        result = await chain.ainvoke({
            "project_id": project_id,
            "current_version": current_version,
            "validated_requirements": req_json_str,
            "version_history_summaries": version_history_summaries
        })
        
        # Modify only its own fields in RequirementState in memory
        req_state["generated_prd"] = result.get("prd_markdown", "# Core Banking PRD\n\nNo description provided.")
        req_state["generated_diagrams"] = result.get("mermaid_diagram", "graph TD\n  Start --> End")
        req_state["current_workflow_state"] = "architect_node"

        architect_msg = "📄 **Enterprise PRD Compiled Successfully!**\nThe CTO Architect Agent has generated the formal PRD and interactive system sequence flows in the preview panel."
        await ConversationMessageRepository.save_message(
            project_id=project_id,
            role="architect",
            message=architect_msg
        )
        
        return {
            "requirement_state": req_state,
            "prd_markdown": req_state["generated_prd"],
            "mermaid_diagram": req_state["generated_diagrams"]
        }
    except Exception as e:
        logger.error(f"Error parsing structured response in architect_node: {str(e)}")
        req_state["generated_prd"] = f"# Core Banking PRD\n\nFailed to compile PRD correctly due to a localized LLM parsing error: {str(e)}."
        req_state["generated_diagrams"] = "graph TD\n  Start --> End"
        req_state["current_workflow_state"] = "architect_node"
        
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
    """
    target = state.get("target_agent", "gatherer")
    if target == "auditor":
        logger.info("Routing to auditor_node on-demand.")
        return "auditor_node"
    elif target == "architect":
        logger.info("Routing to architect_node on-demand.")
        return "architect_node"
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

# Set up conditional routing from START based on target_agent
workflow.add_conditional_edges(
    START,
    route_on_demand,
    {
        "router_node": "router_node",
        "auditor_node": "auditor_node",
        "architect_node": "architect_node"
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

# Export compiled graph workflow
prd_workflow = workflow.compile()
logger.info("StateGraph compiled successfully with requirement matcher agent and workflow router.")