import logging
import json
import re
from typing import TypedDict, Dict, Any, List, Optional
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from langgraph.graph import StateGraph, START, END
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories import RequirementStateRepository, ConversationMessageRepository
from app.schemas import GatheredRequirements, MermaidDiagramResult
from app.prompt_loader import load_prompt
from app.llm_factory import build_llm, llm, parser
from app.llm_utils import invoke_llm_structured
from app.merge_service import (
    collect_acceptance_criteria,
    format_story_context_lines,
    merge_user_stories_with_report,
    normalize_ticket_code,
    normalize_title,
)
from app.prd_section_service import prd_is_sectioned_markdown
from app.semantic_service import (
    classify_workflow,
    detect_requirement_intent,
    detect_semantic_changes,
    match_requirement,
)


# Set up logging configuration for the multi-agent framework
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app.agents")

# Dedicated client for the flow-diagram call. The shared ``llm`` runs with a
# 3000-token structured-output budget sized for the gatherer/auditor JSON,
# while an architecture flowchart for a larger project can easily need more
# headroom (truncated Mermaid is unrenderable).
diagram_llm = build_llm(max_tokens=4096)

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
    intent_confidence: Optional[float]
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
    intent_confidence = state.get("intent_confidence")
    if not detected_intent and raw_input:
        intent_res = await detect_requirement_intent(raw_input, existing_stories)
        # Safe fallback: when the classifier cannot be reached we must NOT
        # invent a new requirement - treating the message as an update keeps
        # the existing backlog intact (creating bogus stories is worse).
        detected_intent = intent_res.get("intent", "UPDATE_REQUIREMENT")
        intent_confidence = intent_res.get("confidence", 1.0)
    elif not detected_intent:
        detected_intent = "GENERAL_CHAT"
    if intent_confidence is None:
        intent_confidence = 1.0
    intent_confidence = float(intent_confidence)

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
            "intent_confidence": intent_confidence,
            "requirement_match": match_result,
            "current_version": req_state.get("version_number", 1)
        }

    return {
        "requirement_state": req_state,
        "detected_intent": detected_intent,
        "intent_confidence": intent_confidence,
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


# Mermaid diagram families accepted for the Architecture Flows panel. The
# frontend (ArchitectureFlows.tsx) only displays the stored diagram when it
# matches this header pattern, so anything else would silently fall back to
# the derived flowchart instead of the LLM's own diagram.
_MERMAID_HEADER_RE = re.compile(r"^\s*(flowchart|graph)\s+(TD|TB|LR|RL)\b", re.IGNORECASE)


def _sanitize_mermaid_diagram(text: Any) -> str:
    """
    Clean and validate an LLM-produced Mermaid diagram string.

    Strips markdown code fences and surrounding whitespace, then requires the
    classic flowchart header (``flowchart TD`` / ``graph TD`` ...) that the
    Architecture Flows panel accepts. Returns "" for anything else so the
    caller can keep the previously stored diagram instead of persisting an
    unrenderable one.
    """
    clean = str(text or "").strip()
    if clean.startswith("```"):
        # Tolerate fenced payloads (```mermaid ... ``` / ``` ... ```).
        clean = re.sub(r"^```[a-zA-Z]*\s*", "", clean)
        clean = re.sub(r"\s*```$", "", clean).strip()
    if not clean or not _MERMAID_HEADER_RE.match(clean):
        return ""
    return clean


async def _generate_flow_diagram(
    project_id: str,
    req_state: Dict[str, Any],
    project_data: Dict[str, Any],
) -> str:
    """
    Ask the LLM for a Mermaid ``flowchart TD`` of the system described by the
    project's own dataset - the same validated business goals / actors /
    requirements / user stories / acceptance criteria the PRD body was just
    filled from. Returns the sanitized Mermaid source, or "" when the LLM
    fails or answers with something that is not a flowchart; callers keep the
    previously stored diagram in that case, so a diagram hiccup can never
    fail a PRD generation.
    """
    try:
        dataset = {
            "project_name": req_state.get("project_name", "") or "",
            "version": req_state.get("version_number", 1),
            **(project_data or {}),
        }
        prompt_template = PromptTemplate(
            template=load_prompt("architect_diagram"),
            input_variables=["project_name", "current_version", "project_dataset", "format_instructions"],
        )
        format_instructions = PydanticOutputParser(
            pydantic_object=MermaidDiagramResult
        ).get_format_instructions()

        def _is_flowchart(result: Dict[str, Any]) -> bool:
            return bool(_sanitize_mermaid_diagram(result.get("mermaid_diagram", "")))

        result = await invoke_llm_structured(
            diagram_llm,
            prompt_template,
            MermaidDiagramResult,
            variables={
                "project_name": dataset.get("project_name") or "Untitled Project",
                "current_version": dataset.get("version", 1),
                "project_dataset": json.dumps(dataset, ensure_ascii=False),
                "format_instructions": "Output ONLY raw JSON. No markdown.",
            },
            description="architect flow diagram",
            format_instructions=format_instructions,
            validate=_is_flowchart,
        )
        diagram = _sanitize_mermaid_diagram(result.get("mermaid_diagram", ""))
        if diagram:
            logger.info(
                f"[ARCHITECT] Generated flow diagram for project {project_id} ({len(diagram)} chars)."
            )
        else:
            logger.warning(
                f"[ARCHITECT] Flow diagram for project {project_id} was not a valid flowchart; "
                "keeping the previously stored diagram."
            )
        return diagram
    except Exception as diagram_err:
        # FAIL-OPEN: a diagram hiccup must never fail the PRD generation that
        # already succeeded. Callers keep the previously stored diagram.
        logger.error(
            f"[ARCHITECT] Flow diagram generation failed for project {project_id}: {str(diagram_err)}"
        )
        return ""


# ==========================================
# GATHERER HELPERS
# ==========================================
_REQUIREMENT_CODE_RE = re.compile(r"^(?:REQ[-_ ]?)(\d+)$", re.IGNORECASE)
# Below this classifier confidence the Gatherer is told to prefer the safest
# interpretation of an ambiguous message (preserve > invent).
_LOW_INTENT_CONFIDENCE = 0.65
_PLACEHOLDER_EPIC_NAMES = ("", "Untitled Epic", "Structured Requirements Draft", "Document Epic")
_EPIC_RENAME_PATTERNS = (
    r"\brenam\w*\s+(?:the\s+)?epic\b",
    r"\bepic\b[^.;\n]{0,30}\brenam\w*\b",
    r"\bchang\w*\s+(?:the\s+)?epic\b",
    r"\bepic\b[^.;\n]{0,30}\bchang\w*\b",
    r"\b(?:new|set|call(?:ed)?)\s+(?:the\s+)?epic\b",
    r"\bupdate\s+(?:the\s+)?epic\b",
    r"\bepic\s+name\b",
    r"\bepic\b[^.;\n]{0,30}\bshould\s+be\b",
)


def _normalize_requirement_code(code: Any) -> str:
    """Canonicalize an LLM/DB requirement code to ``REQ-NNN`` (``''`` if invalid)."""
    match = _REQUIREMENT_CODE_RE.match(str(code or "").strip())
    return f"REQ-{int(match.group(1)):03d}" if match else ""


def _generate_next_requirement_code(used_codes: Any) -> str:
    """Return the lowest free ``REQ-NNN`` code above every used code."""
    max_num = 0
    for code in used_codes or []:
        match = _REQUIREMENT_CODE_RE.match(str(code or "").strip())
        if match:
            max_num = max(max_num, int(match.group(1)))
    return f"REQ-{max_num + 1:03d}"


def _renumber_fresh_project_codes(
    existing_requirements: Any,
    llm_group_meta: Dict[str, Dict[str, Any]],
) -> Dict[str, str]:
    """Fresh boards always start at ``REQ-001``: declared codes -> 1..N.

    Small local models sometimes copy the gatherer prompt's "new requirement"
    example verbatim and start a brand-new project at ``REQ-002``. Nothing can
    reference requirement codes yet while the board is empty, so the LLM's
    declared groups are deterministically renumbered 1..N in declaration
    order. Returns an empty mapping when renumbering is not applicable — the
    board already holds requirements (legacy codes must never be renumbered:
    the PRD text and traceability references the old codes) or the declared
    codes already run 1..N.
    """
    if existing_requirements or not llm_group_meta:
        return {}
    renumber = {
        old: _default_requirement_code(idx)
        for idx, old in enumerate(llm_group_meta)
    }
    if all(new == old for old, new in renumber.items()):
        return {}
    return renumber


def _user_requests_epic_rename(raw_input: str) -> bool:
    """Regex detection of an explicit epic rename request.

    The previous substring check (``"rename epic"`` etc.) missed natural
    phrasings such as "rename the epic to X" or "the epic should be called X",
    which silently kept a stale epic name after the user renamed it.
    """
    if not raw_input:
        return False
    lowered = raw_input.lower()
    return any(re.search(pattern, lowered) for pattern in _EPIC_RENAME_PATTERNS)


def _resolve_epic_name(req_state: Dict[str, Any], llm_epic_name: str, raw_input: str) -> str:
    """Keep the persisted epic name unless the user explicitly renames it.

    Placeholder/stored-empty epic names always defer to the LLM's suggestion,
    which is how a first extraction names the project epic.
    """
    requirements = req_state.get("requirements", []) or []
    existing_epic_name = requirements[0].get("title", "") if requirements else ""
    is_placeholder = existing_epic_name in _PLACEHOLDER_EPIC_NAMES
    if existing_epic_name and not is_placeholder and not _user_requests_epic_rename(raw_input):
        return existing_epic_name
    return llm_epic_name or existing_epic_name or "Structured Requirements Draft"


def _sanitize_incoming_story(raw: Any) -> Optional[Dict[str, Any]]:
    """Normalize one LLM-drafted user story before it enters the merge.

    Trims every field, coerces acceptance criteria into a de-duplicated list
    of non-empty strings and rejects entries without any usable title/action
    (merge identity matching relies on ticket codes and titles).
    """
    if not isinstance(raw, dict):
        return None
    acs = raw.get("acceptance_criteria") or []
    if isinstance(acs, str):
        acs = [acs]
    cleaned_ac: List[str] = []
    seen_ac = set()
    for ac in acs:
        text = str(ac or "").strip()
        key = " ".join(text.lower().split())
        if text and key not in seen_ac:
            seen_ac.add(key)
            cleaned_ac.append(text)
    story = {
        "ticket_code": normalize_ticket_code(raw.get("ticket_code")),
        "story_title": str(raw.get("story_title") or "").strip(),
        "as_a": str(raw.get("as_a") or "").strip(),
        "i_want_to": str(raw.get("i_want_to") or "").strip(),
        "so_that": str(raw.get("so_that") or "").strip(),
        "acceptance_criteria": cleaned_ac,
    }
    if not story["story_title"] and not story["i_want_to"]:
        return None
    if not cleaned_ac:
        logger.warning(
            "[GATHERER] Story draft has no acceptance criteria; flagging it for audit follow-up: '%s'",
            story["story_title"] or story["i_want_to"],
        )
    return story


def _build_intent_guidance(
    detected_intent: str,
    intent_confidence: float,
    requirement_match: Optional[Dict[str, Any]] = None,
    has_existing_stories: bool = False,
) -> str:
    """Translate the detected intent + matcher result into explicit,
    unambiguous extraction rules injected into the Gatherer prompt.

    Without this the LLM only saw the raw intent label and regularly
    re-emitted the whole backlog (with reworded duplicates) instead of
    extracting just the requested change.
    """
    lines = [f"Detected user intent: {detected_intent} (classifier confidence {intent_confidence:.2f})."]
    if intent_confidence < _LOW_INTENT_CONFIDENCE:
        lines.append(
            f"CAUTION: intent confidence is LOW ({intent_confidence:.2f}). When the raw input is "
            "ambiguous, prefer the SAFEST interpretation: keep every existing user story and its "
            "acceptance criteria untouched and only add a story when the input clearly describes "
            "behaviour that does not exist yet."
        )
    if not has_existing_stories:
        lines.append(
            "This is the FIRST extraction for the project: create fresh requirements, "
            "user stories and acceptance criteria from the raw input."
        )
        return "\n".join(lines)

    if detected_intent == "CREATE_REQUIREMENT":
        lines.append(
            "The user wants to ADD something NEW. Extract ONLY the new feature(s) described in the "
            "raw input as new user stories. PRESERVE every existing user story in "
            "<current_project_context> exactly as-is (same ticket codes, same acceptance "
            "criteria, same parent requirement) — do not re-emit them reworded."
        )
    elif detected_intent == "UPDATE_REQUIREMENT":
        target = (requirement_match or {}).get("matched_requirement_id")
        if target:
            lines.append(
                f"The user wants to MODIFY the existing story {target}. Return that story with the "
                "requested change applied, keeping its exact ticket code and parent requirement. "
                "PRESERVE every other existing story exactly as-is."
            )
        else:
            lines.append(
                "The user wants to MODIFY an existing story. Use <semantic_change_recommendations> "
                "to find the target ticket code and return ONLY that story modified (same ticket "
                "code, same parent requirement). PRESERVE every other existing story exactly as-is."
            )
    elif detected_intent == "DELETE_REQUIREMENT":
        lines.append(
            "The user wants to REMOVE something. Do NOT include the removed story in the output "
            "(see <semantic_change_recommendations> for the target ticket code). PRESERVE every "
            "other existing story exactly as-is."
        )
    elif detected_intent == "CLARIFY_REQUIREMENT":
        lines.append(
            "The user is asking for clarification or validation. Mirror the current requirements "
            "as-is; do NOT invent or apply changes."
        )
    else:
        lines.append(
            "Classify each change using <semantic_change_recommendations> and preserve every "
            "existing story that has no recommendation exactly as-is."
        )
    return "\n".join(lines)


def _build_change_summary(merge_report: Dict[str, Any]) -> str:
    """Compose the chat message describing exactly what the gather changed.

    The old message was a static "Requirements Gathered & Updated!" line that
    gave the Product Owner no idea what had been added, updated or removed.
    """
    buckets: Dict[str, List[str]] = {"created": [], "updated": [], "archived": [], "conflict": []}
    for key, info in (merge_report or {}).items():
        action = str((info or {}).get("action", ""))
        if action in buckets:
            buckets[action].append(str(key))

    lines = ["📥 **Requirements Gathered & Updated!**"]
    if buckets["created"]:
        lines.append(
            f"✅ **Added** {len(buckets['created'])} new user story(ies): {', '.join(sorted(buckets['created']))}"
        )
    if buckets["updated"]:
        lines.append(
            f"🔄 **Updated** {len(buckets['updated'])} user story(ies): {', '.join(sorted(buckets['updated']))}"
        )
    if buckets["archived"]:
        lines.append(
            f"🗑️ **Archived** {len(buckets['archived'])} user story(ies): {', '.join(sorted(buckets['archived']))}"
        )
    if buckets["conflict"]:
        lines.append(
            f"⚠️ {len(buckets['conflict'])} locked story(ies) matched a removal request but stayed active: "
            f"{', '.join(sorted(buckets['conflict']))}"
        )
    if len(lines) == 1:
        lines.append("No changes were needed — the existing requirements already cover your input.")
    return "\n".join(lines)


async def gatherer_node(state: AgentState) -> Dict[str, Any]:
    """
    Standardizes messy Product Owner input into high-quality Agile structures.
    Reads/writes to the centralized RequirementState object via persistence service.

    Pipeline:
    1. Load the centralized RequirementState and split stories into locked
       (protected) and unlocked (mergeable) sets.
    2. Read/detect the user's intent and inject explicit intent guidance into
       the prompt so extraction matches what the user actually asked for.
    3. Guard against no-op invocations (empty input + empty draft) which
       previously destroyed multi-requirement grouping.
    4. Run the Requirement Matcher / semantic change detection and bail out
       with user-visible clarification questions on low-confidence changes.
    5. Extract structured requirements via the LLM, sanitize the draft and
       run ONE merge over the flattened story list.
    6. Reassemble requirement groups: matched/unchanged stories keep their
       original parent requirement, created stories go to the requirement the
       LLM assigned them to, emptied requirement groups are dropped.
    7. Bump the version only when the merge actually changed something and
       post a change-summary assistant message.
    """
    logger.info("Executing gatherer_node to structure requirements.")
    project_id = state.get("project_id", "PROJ-UNKNOWN")
    raw_input = state.get("raw_input", "")

    # Use session from state if available, otherwise let function create one
    db_session = state.get("db_session")
    req_state = await get_or_init_requirement_state(project_id, session=db_session, current_version=state.get("current_version", 1))

    # Store existing user stories before processing passed_structured or raw_input
    existing_user_stories = list(req_state.get("user_stories", []))

    # Split stories into locked (protected from modification) and unlocked sets.
    # Locked stories are still fed to the merge as PROTECTED entries so they stay
    # in the merged output under their original requirement - previously they
    # were excluded from the merge entirely and silently vanished from the board.
    locked_user_stories = [us for us in existing_user_stories if us.get("is_locked", False)]
    unlocked_user_stories = [us for us in existing_user_stories if not us.get("is_locked", False)]
    if locked_user_stories:
        logger.info(f"[GATHERER] {len(locked_user_stories)} locked user story(ies) are protected from modification.")
    locked_protected_ids = [
        pid for pid in (
            [str(us.get("id")) for us in locked_user_stories if us.get("id")]
            + [us.get("ticket_code") for us in locked_user_stories if us.get("ticket_code")]
        ) if pid
    ]

    passed_structured = state.get("structured_requirements") or {}

    # ---- No-op guard -------------------------------------------------------
    # With no raw input AND no structured draft there is nothing to extract.
    # Previously this fell through to the legacy fallback which rebuilt
    # ``requirements`` as a single flat REQ-001, destroying multi-requirement
    # grouping on a no-op invocation.
    if not (raw_input and str(raw_input).strip()) and not passed_structured:
        logger.info("[GATHERER] No raw input and no structured draft - nothing to gather.")
        noop_msg = (
            "I didn't receive any requirement text or draft to process. "
            "Tell me the feature or change you have in mind and I'll structure it for you."
        )
        await ConversationMessageRepository.save_message(
            project_id=project_id,
            role="assistant",
            message=noop_msg,
            workflow_state="gatherer_node",
            intent="GENERAL_CHAT",
        )
        return {
            "requirement_state": req_state,
            "structured_requirements": {},
            "detected_intent": "GENERAL_CHAT",
            "current_version": req_state.get("version_number", 1),
        }

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
    intent_confidence = state.get("intent_confidence")
    if not detected_intent and raw_input:
        intent_res = await detect_requirement_intent(raw_input, existing_user_stories)
        detected_intent = intent_res.get("intent", "UPDATE_REQUIREMENT")
        intent_confidence = intent_res.get("confidence", 1.0)
    elif not detected_intent:
        detected_intent = "GENERAL_CHAT"
    # Reuse the confidence the Requirement Matcher node already classified with
    # (previously hardcoded to 1.0 here, which made the prompt claim a perfect
    # confidence even for a genuinely uncertain classification).
    if intent_confidence is None:
        intent_confidence = 1.0
    intent_confidence = float(intent_confidence)

    logger.info(f"Gatherer received raw_input: '{raw_input[:100]}' with detected_intent: {detected_intent}, confidence: {intent_confidence}")

    if not raw_input:
        # ---- Structured-draft short-circuit --------------------------------
        # A draft payload without new raw input (e.g. the frontend re-syncing
        # the board) must NEVER re-run extraction. Keep the requirement
        # grouping applied above and re-derive the flattened story/AC views
        # from it. The old code fell through to the legacy fallback and
        # flattened every requirement into a single REQ-001 here.
        active_flat = [
            s
            for r in (req_state.get("requirements") or [])
            if isinstance(r, dict)
            for s in (r.get("user_stories") or [])
            if isinstance(s, dict) and s.get("status", "active") == "active"
        ]
        req_state["user_stories"] = active_flat
        req_state["acceptance_criteria"] = collect_acceptance_criteria(active_flat)
        req_state["current_workflow_state"] = "gatherer_node"
        req_state["detected_intent"] = detected_intent
        version_number = req_state.get("version_number", 1)
        epic_name = _resolve_epic_name(req_state, str(passed_structured.get("epic_name") or ""), "")
        structured_out = {
            "epic_name": epic_name,
            "version": version_number,
            "user_stories": active_flat,
            "requirements": req_state.get("requirements", []),
        }
        return {
            "requirement_state": req_state,
            "structured_requirements": structured_out,
            "detected_intent": detected_intent,
            "current_version": version_number,
        }

    if detected_intent == "GENERAL_CHAT":
        # Defensive guard: conversational input must never be extracted into
        # requirements. The router/route normally short-circuits earlier, but
        # a misrouted GENERAL_CHAT previously created bogus user stories.
        logger.info("[GATHERER] GENERAL_CHAT input reached the gatherer; skipping extraction.")
        chat_msg = (
            "That looks like a conversational question rather than a requirement change, "
            "so I did not modify any requirements. Ask me anything, or describe the "
            "feature you would like to add or change."
        )
        await ConversationMessageRepository.save_message(
            project_id=project_id,
            role="assistant",
            message=chat_msg,
            workflow_state="gatherer_node",
            intent="GENERAL_CHAT",
        )
        return {
            "requirement_state": req_state,
            "structured_requirements": passed_structured,
            "detected_intent": "GENERAL_CHAT",
            "current_version": req_state.get("version_number", 1),
        }


    # Use requirement_match from Requirement Matcher Agent if available
    requirement_match = state.get("requirement_match") or {}
    matched_req_id = requirement_match.get("matched_requirement_id")
    match_action = requirement_match.get("action")

    semantic_recs = []
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

        # Surface the clarification to the user: previously this branch saved
        # questions to state only, so the chat showed NOTHING and the gather
        # looked like a silent failure.
        clarify_msg = "⚠️ **Clarification Needed (Requirements):**\n" + "\n".join(f"- {q['question_text']}" for q in cqs)
        await ConversationMessageRepository.save_message(
            project_id=project_id,
            role="assistant",
            message=clarify_msg,
            workflow_state="gatherer_node",
            intent=detected_intent,
        )

        return {
            "requirement_state": req_state,
            "structured_requirements": passed_structured,
            "detected_intent": detected_intent,
            "current_version": req_state.get("version_number", 1)
        }


    # Format current stories context via the shared helper (also used by the
    # semantic/intent/matcher prompts so every agent describes the backlog
    # identically).
    requirements = req_state.get("requirements", [])
    existing_epic = requirements[0].get("title", "") if requirements else ""
    context_lines = []
    if existing_epic:
        context_lines.append(f"CURRENT ACTIVE EPIC: {existing_epic}\n(Note: DO NOT change this Epic Name unless the user explicitly requests to change or rename the epic)\n")
    context_lines.extend(format_story_context_lines(unlocked_user_stories))
    if locked_user_stories:
        # Locked stories ARE rendered (with an explicit marker) so the model can
        # see them and avoid re-creating them as duplicates. They are protected
        # by ``locked_protected_ids`` in the merge, so even a misbehaving draft
        # can never mutate them.
        context_lines.append(
            "\nLOCKED STORIES (human-verified - reproduce EXACTLY as-is, never modify, "
            "renumber, reword or drop them):"
        )
        context_lines.extend(
            f"{line}\n  Flags: LOCKED" for line in format_story_context_lines(locked_user_stories)
        )
    current_context = "\n".join(context_lines) if context_lines else "No existing user stories in this project."

    # Explicit intent rules for the LLM: with only the raw intent label the
    # model regularly re-emitted the whole backlog as reworded duplicates
    # instead of extracting just the requested change.
    intent_guidance = _build_intent_guidance(
        detected_intent=detected_intent,
        intent_confidence=intent_confidence,
        requirement_match=requirement_match,
        has_existing_stories=bool(existing_user_stories),
    )

    # Format semantic recommendations
    recs_str = json.dumps(semantic_recs, indent=2)

    prompt_template = PromptTemplate(
        template=load_prompt("gatherer"),
        input_variables=["raw_input", "detected_intent", "intent_guidance", "current_context", "recommendations", "format_instructions"]
    )

    # Prepare components for logging
    pydantic_parser = PydanticOutputParser(pydantic_object=GatheredRequirements)
    format_instructions = pydantic_parser.get_format_instructions()
    prompt_value = prompt_template.format(
        raw_input=raw_input,
        detected_intent=detected_intent,
        intent_guidance=intent_guidance,
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
                "intent_guidance": intent_guidance,
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

    # Stop execution if parsing fails entirely
    if parsing_error:
        raise ValueError(
            f"The Gatherer agent failed to parse raw input into structured JSON requirements. "
            f"Details: {parsing_error}. Please revise your input description or schema constraints."
        )

    # Keep the persisted epic name unless the user explicitly asked to rename
    # it (regex detection now understands "rename the epic to X", "the epic
    # should be called X", etc. - the old substring check missed those).
    epic_name = _resolve_epic_name(req_state, str(result.get("epic_name") or ""), raw_input)


    # ===============================================
    # Normalize the LLM output into requirement groups
    # ===============================================
    llm_requirements = result.get("requirements")
    if not isinstance(llm_requirements, list):
        llm_requirements = []
    if not llm_requirements and isinstance(result.get("user_stories"), list) and result["user_stories"]:
        # Legacy flat schema -> wrap into one requirement group so the same
        # merge/reassembly pipeline handles both output shapes.
        prev_identity = _previous_requirement_identity(req_state)
        llm_requirements = [{
            "requirement_code": prev_identity.get("requirement_code") or "REQ-001",
            "title": epic_name or prev_identity.get("title") or "Structured Requirements",
            "description": prev_identity.get("description", ""),
            "user_stories": result.get("user_stories", []),
        }]

    existing_requirements = [r for r in (req_state.get("requirements") or []) if isinstance(r, dict)]
    existing_req_by_code: Dict[str, Dict[str, Any]] = {}
    existing_membership: Dict[str, str] = {}
    for req in existing_requirements:
        req_code = _normalize_requirement_code(req.get("requirement_code"))
        if not req_code:
            continue
        existing_req_by_code[req_code] = req
        for us in req.get("user_stories", []) or []:
            if isinstance(us, dict):
                us_code = normalize_ticket_code(us.get("ticket_code"))
                if us_code:
                    existing_membership.setdefault(us_code, req_code)

    # Flatten + sanitize the LLM draft, mapping every incoming story to the
    # requirement group the LLM assigned it to.
    used_req_codes = set(existing_req_by_code.keys())
    incoming_entries: List[Dict[str, Any]] = []
    target_by_key: Dict[str, str] = {}
    llm_group_meta: Dict[str, Dict[str, Any]] = {}

    for req_item in llm_requirements:
        if not isinstance(req_item, dict):
            continue
        raw_code = _normalize_requirement_code(req_item.get("requirement_code"))
        group_title = str(req_item.get("title") or "").strip()
        group_desc = str(req_item.get("description") or "").strip()
        raw_stories = [s for s in (req_item.get("user_stories") or []) if isinstance(s, dict)]

        target_code = raw_code
        if target_code and target_code in existing_req_by_code:
            # The LLM reused an existing requirement code. Treat it as an
            # update to that requirement ONLY when the title is unchanged or
            # at least one story matches the existing group's stories; a
            # recycled code with entirely new content is minted a fresh code
            # so genuinely new features never pollute an existing group.
            incoming_codes = {normalize_ticket_code(s.get("ticket_code")) for s in raw_stories}
            existing_group_codes = {
                normalize_ticket_code(us.get("ticket_code"))
                for us in (existing_req_by_code[target_code].get("user_stories") or [])
                if isinstance(us, dict)
            }
            title_same = normalize_title(group_title) == normalize_title(existing_req_by_code[target_code].get("title"))
            if not title_same and not (incoming_codes & existing_group_codes):
                fresh = _generate_next_requirement_code(used_req_codes)
                logger.warning(
                    f"[GATHERER] LLM recycled {target_code} for a different feature ('{group_title}'); "
                    f"minting {fresh} for the new group."
                )
                target_code = fresh
        if not target_code:
            target_code = _generate_next_requirement_code(used_req_codes)
        used_req_codes.add(target_code)

        if target_code not in llm_group_meta:
            llm_group_meta[target_code] = {
                "title": group_title or f"Requirement {target_code}",
                "description": group_desc,
            }

        for s in raw_stories:
            clean = _sanitize_incoming_story(s)
            if not clean:
                continue
            entry = dict(clean)
            entry["_target_req_code"] = target_code
            incoming_entries.append(entry)
            code_key = normalize_ticket_code(entry.get("ticket_code"))
            title_key = normalize_title(entry.get("story_title"))
            if code_key:
                target_by_key.setdefault(code_key, target_code)
            if title_key:
                target_by_key.setdefault(title_key, target_code)

    # FRESH-PROJECT CODE RENUMBERING: the LLM sometimes copies the gatherer
    # prompt's "new requirement" example verbatim and starts a brand-new
    # project at REQ-002. Nothing references requirement codes yet on an empty
    # board, so remap every declared group to 1..N in declaration order — the
    # first requirement is always REQ-001.
    renumber = _renumber_fresh_project_codes(existing_requirements, llm_group_meta)
    if renumber:
        logger.info(f"[GATHERER] Fresh project: renumbering LLM requirement codes: {renumber}")
        llm_group_meta = {renumber[old]: meta for old, meta in llm_group_meta.items()}
        target_by_key = {key: renumber.get(code, code) for key, code in target_by_key.items()}
        for entry in incoming_entries:
            entry["_target_req_code"] = renumber.get(entry.get("_target_req_code"), entry.get("_target_req_code"))


    # ===============================================
    # ONE merge pass over the FULL flattened story list.
    # Previously merge_user_stories ran once PER LLM requirement with the
    # whole existing backlog, duplicating every existing story into EVERY
    # requirement group. Locked stories are protected (never mutated) but
    # stay in the merge input so they never vanish from the board.
    # ===============================================
    merged_stories, merge_report = merge_user_stories_with_report(
        existing_stories=unlocked_user_stories + locked_user_stories,
        new_incoming_stories=incoming_entries,
        semantic_recs=semantic_recs,
        protected_ids=locked_protected_ids,
    )

    # ===============================================
    # Reassemble requirement groups from the merged story set
    # ===============================================
    req_groups: Dict[str, Dict[str, Any]] = {}
    # Seed with existing requirements to preserve identity & ordering
    for req in existing_requirements:
        req_code = _normalize_requirement_code(req.get("requirement_code"))
        if not req_code or req_code in req_groups:
            continue
        req_groups[req_code] = {
            "requirement_code": req_code,
            "title": req.get("title") or f"Requirement {req_code}",
            "description": req.get("description") or "",
            "user_stories": [],
            "_is_existing": True,
        }
    # Register the LLM-declared groups that are genuinely new
    for code, meta in llm_group_meta.items():
        if code not in req_groups:
            req_groups[code] = {
                "requirement_code": code,
                "title": meta["title"],
                "description": meta["description"],
                "user_stories": [],
                "_is_existing": False,
            }

    first_existing_code = next(
        (c for c, g in req_groups.items() if g.get("_is_existing")),
        "",
    )

    all_active_stories: List[Dict[str, Any]] = []
    for story in merged_stories:
        if story.get("status", "active") != "active":
            continue  # archived stories leave the board (recorded in merge_report)
        clean_story = {k: v for k, v in story.items() if not str(k).startswith("_")}
        code_key = normalize_ticket_code(story.get("ticket_code"))
        title_key = normalize_title(story.get("story_title"))
        change_type = story.get("change_type", "unchanged")
        if change_type == "created":
            # New stories go to the requirement group the LLM assigned them to.
            parent_code = target_by_key.get(code_key) or target_by_key.get(title_key)
        else:
            # Matched/unchanged/conflict stories RETAIN their original parent
            # requirement (mirrors the gatherer prompt contract), falling back
            # to the LLM grouping when the story has no recorded membership.
            parent_code = (
                existing_membership.get(code_key)
                or target_by_key.get(code_key)
                or target_by_key.get(title_key)
            )
        if not parent_code:
            parent_code = first_existing_code or _generate_next_requirement_code(set(req_groups))
        group = req_groups.get(parent_code)
        if group is None:
            meta = llm_group_meta.get(parent_code) or {}
            group = req_groups.setdefault(parent_code, {
                "requirement_code": parent_code,
                "title": meta.get("title") or f"Requirement {parent_code}",
                "description": meta.get("description") or "",
                "user_stories": [],
                "_is_existing": False,
            })
        group["user_stories"].append(clean_story)
        all_active_stories.append(clean_story)

    final_requirements = []
    for code, group in req_groups.items():
        if group["user_stories"]:
            final_requirements.append({k: v for k, v in group.items() if not str(k).startswith("_")})
        else:
            logger.info(
                f"[GATHERER] Requirement group {code} has no remaining stories after the merge; dropping it."
            )

    req_state["requirements"] = final_requirements
    req_state["user_stories"] = all_active_stories
    req_state["acceptance_criteria"] = collect_acceptance_criteria(all_active_stories)


    # ===============================================
    # Versioning: NEVER trust the LLM's ``version`` echo (the model does not
    # know the current version and its schema default of 1 used to RESET the
    # project version on every gather). Bump by exactly one when the merge
    # actually changed something; otherwise keep the current version.
    # ===============================================
    report_actions = {str((info or {}).get("action", "")) for info in merge_report.values()}
    has_changes = bool(report_actions & {"created", "updated", "archived"})
    current_version = req_state.get("version_number") or 1
    version_number = current_version + 1 if has_changes else current_version

    req_state["version_number"] = version_number
    req_state["current_workflow_state"] = "gatherer_node"
    req_state["semantic_recommendations"] = semantic_recs
    req_state["detected_intent"] = detected_intent

    # A change-summary chat message (added/updated/archived ticket codes)
    # persisted as a regular assistant message - the old static message told
    # the Product Owner nothing about what actually changed.
    gatherer_msg = _build_change_summary(merge_report)
    await ConversationMessageRepository.save_message(
        project_id=project_id,
        role="assistant",
        message=gatherer_msg,
        workflow_state="gatherer_node",
        intent=detected_intent,
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
        and (
            _prd_follows_krungsri_template(existing_prd)
            or prd_is_sectioned_markdown(existing_prd)
        )
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

    # FLOW DIAGRAM SYNC: every PRD generation also refreshes the Architecture
    # Flows diagram - the LLM is asked with the project's own (just-validated)
    # dataset and answers with raw Mermaid flowchart code, so the flow always
    # mirrors the freshly generated document. When the model fails or returns
    # unusable output the previously stored diagram is kept instead, so the
    # PRD result is never lost over a diagram hiccup.
    fresh_diagram = await _generate_flow_diagram(project_id, req_state, data)
    req_state["generated_diagrams"] = fresh_diagram or req_state.get("generated_diagrams", "")
    req_state["current_workflow_state"] = "architect_node"

    # PART-LEVEL PRD SYNC: merge the freshly generated document into the
    # project's prd_sections. Human-owned (ai_generatable=False) and locked
    # sections are PRESERVED verbatim — regeneration only touches unlocked,
    # AI-generatable parts. The stitched markdown of ALL parts (AI + human)
    # becomes the current generated_prd so human content survives every run.
    if db_session:
        try:
            from app.prd_section_service import sync_sections_from_prd
            merged_markdown = await sync_sections_from_prd(
                project_id, req_state["generated_prd"], db_session,
                changed_by="automated_agent",
            )
            if merged_markdown:
                req_state["generated_prd"] = merged_markdown
        except Exception as section_sync_err:
            # Never fail PRD generation because of section bookkeeping.
            logger.error(
                f"[PRD SECTIONS] Failed to sync PRD sections for project {project_id}: "
                f"{str(section_sync_err)}"
            )

    # Persist the FINAL document as an immutable PRD version record. The
    # version ALWAYS advances on every Generate PRD click — even when every
    # changed section was locked and the final merged document is byte-identical
    # to the previous snapshot — so the Version ledger never collapses. The
    # per-section change records prove which parts changed and which were
    # locked_preserved by the lock contract.
    if db_session:
        try:
            from app.version_service import record_prd_version
            await record_prd_version(
                project_id, db_session,
                generated_prd=req_state["generated_prd"],
                generated_by="automated_agent",
                change_type="ai",
                change_summary=(version_history_summaries or "").strip()
                    or None,
            )
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