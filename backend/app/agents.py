import logging
import json
from typing import TypedDict, Dict, Any, List, Optional
from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import JsonOutputParser, PydanticOutputParser
try:
    from langchain.output_parsers import OutputFixingParser
except ImportError:
    OutputFixingParser = None
from langgraph.graph import StateGraph, START, END
from app.repository import RequirementStateRepository
from app.schemas import GatheredRequirements, UserStoryModel


# Set up logging configuration for the multi-agent framework
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app.agents")

# ==========================================
# SYSTEM PROMPTS
# ==========================================
GATHERER_PROMPT = """
Your role is a Senior Business Analyst and Requirements Engineer. Your task is to process raw, messy, or conversational text from a User/Product Owner and extract them into clean, standardized Agile Requirements.

<system_constraints>
- You must output your response 100% strictly in JSON format matching the schema provided below.
- Do not include any standard AI introductory or trailing pleasantries (e.g., "Sure, here is...").
- Do not use Markdown, do not use ```json fences, do not use any formatting other than raw JSON.
- Keep terminology objective, precise, and structured according to corporate banking principles.
- The output MUST be valid, RFC8259-compliant JSON with no trailing commas, no comments, and using only double quotes.
</system_constraints>

<instructions>
1. Evaluate the information inside the `<raw_user_input>` tag.
2. Formulate a standardized high-level Feature Epic Name.
3. Break down the core intent into granular "User Stories" following the strict format: "As a [role], I want to [action], So that [value]".
4. For every User Story generated, write at least two highly detailed, testable "Acceptance Criteria" utilizing the strict behavior-driven syntax: "Given [context], When [action], Then [expected outcome]".
5. You MUST align your output with the `<semantic_change_recommendations>` provided:
   - For any "MODIFY_REQUIREMENT", "EXPAND_REQUIREMENT", or "RENAME_REQUIREMENT" recommendation targeting a specific ticket code, find the matching user story in `<current_project_context>`, modify or expand it according to the raw user input, and ensure it retains its exact `ticket_code`.
   - For any "NEW_REQUIREMENT" recommendation, generate a brand new user story and assign it a new unique ticket code.
   - For any "REMOVE_REQUIREMENT" recommendation targeting a ticket code, do NOT include that user story in the output.
   - For any other user story in `<current_project_context>` that has no recommendations or is "NO_CHANGE", preserve it exactly as-is in the output (retaining its ticket code, title, role, want, value, and acceptance criteria).
</instructions>

<current_project_context>
{current_context}
</current_project_context>

<semantic_change_recommendations>
{recommendations}
</semantic_change_recommendations>

<raw_user_input>
{raw_input}
</raw_user_input>

{format_instructions}
"""

AUDITOR_PROMPT = """
Your role is a Principal Software Architect and Risk Compliance Auditor for a Tier-1 Retail Bank. Your task is to audit the provided structured user stories against our rigid internal technical checklist to guarantee high availability, system safety, and absolute data integrity.

<system_constraints>
- Evaluate the input data strictly against the Mandatory 7-Point Banking Checklist.
- If ANY checklist metric is missing, unaddressed, or vague, you MUST set "is_valid" to false and write highly specific clarification questions in the array.
- Only if ALL checklist elements are thoroughly covered by the requirements can you set "is_valid" to true and leave the questions array empty.
- Output must be purely valid JSON. No open prose.
</system_constraints>

<mandatory_7_point_banking_checklist>
1. Idempotency & De-duplication: Does the story specify how back-to-back duplicate transaction payloads are caught? Is there an Explicit Idempotency Key mechanism outlined?
2. Security & Data Masking: Are sensitive elements (PII, citizen IDs, account balances) masked in app logs and encrypted both in transit and at rest?
3. Audit Logging & Traceability: Is there an unalterable transaction ledger trail specified? Who, when, and what changed must be logged.
4. Database Consistency & Rollback: Are database transactions atomic? Is a clear rollback pathway mapped out in case of intermediate network dropouts?
5. Network Timeouts & Retry Strategies: Is there a designated timeout ceiling and circuit-breaker retry pattern mentioned for dependent 3rd-party node queries?
6. Financial Regulatory Compliance: Does the workflow adhere strictly to local central banking standards (e.g., Bank of Thailand PromptPay infrastructure, AML/KYC directives)?
7. Edge-Case Failure Handling: Are system behaviors explicitly mapped out for insufficient funds, frozen accounts, database timeouts, or user dropouts?
</mandatory_7_point_banking_checklist>

<input_structured_requirements>
{structured_requirements}
</input_structured_requirements>

<historical_context>
Current Requirement Version: {current_version}
</historical_context>

<instructions>
1. Conduct a rigorous verification pass over the user stories and acceptance criteria.
2. Cross-reference them line-by-line with the 7-Point Banking Checklist.
3. If a requirement misses a check point, generate a direct, highly technical question targeted at that specific user story to prompt the TPO/BA for the missing detail.
</instructions>

<expected_json_output_schema>
{{
  "is_valid": false,
  "audit_version_reviewed": {current_version},
  "passed_checks": ["Array of strings matching categories that passed"],
  "failed_checks": ["Array of strings matching categories that failed or are missing info"],
  "clarification_questions": [
    {{
      "checklist_category": "String (e.g., Idempotency)",
      "target_user_story_id": "String (e.g., US-001)",
      "question_text": "String (e.g., The transaction loop for US-001 does not specify an idempotency token duration or key generation logic. Please define how the backend prevents double-posting during timeout retries.)"
    }}
  ]
}}
</expected_json_output_schema>
"""

ARCHITECT_PROMPT = """
Your role is a Chief Technology Officer (CTO) and Enterprise Solutions Architect. The requirements have successfully passed the banking audit. Your job is to compile the final verified requirements into a comprehensive, authoritative Markdown Product Requirement Document (PRD) and generate a matching architectural visualization schema.

<system_constraints>
- Your output must be a single structured JSON object containing "prd_markdown" and "mermaid_diagram".
- The "mermaid_diagram" string field must contain ONLY valid, raw Mermaid.js visualization syntax. Do not append markdown backticks inside the JSON value string.
</system_constraints>

<input_validated_dataset>
Project ID: {project_id}
Final Approved Version: {current_version}
Validated Requirements JSON: {validated_requirements}
Audit Logs & History References: {version_history_summaries}
</input_validated_dataset>

<instructions>
1. **Draft PRD Markdown:** Write a pristine corporate PRD. Use detailed headings (`#`, `##`, `###`). Structure it with: 1. Executive Summary, 2. Technical Architecture & System Constraints, 3. Fully Audited User Stories with explicit Given-When-Then criteria, 4. Critical Error Handling & Database Rollback Matrices, 5. Data Governance & Regulatory Compliance mapping, 6. Revision History Record.
2. **Draft System Flowcharts:** Write an extensive, syntactically perfect Mermaid.js Sequence Diagram (`sequenceDiagram`) or Flowchart (`graph TD`) mapping out the architecture. Show exactly how a payload moves from Frontend React -> FastAPI Backend Router -> Security Validation Node -> Core Bank API Gateway -> Database Persistency Layer.
</instructions>

<expected_json_output_schema>
{{
  "project_id": "{project_id}",
  "final_version": {current_version},
  "prd_markdown": "# PRD - Feature Document Title\n\n## 1. Executive Summary...\n\n## 2. Technical Infrastructure Architecture...\n\n## 3. Audited User Stories...",
  "mermaid_diagram": "sequenceDiagram\n  autonumber\n  Client Browser->>FastAPI Backend: HTTP POST /api/transaction\n  FastAPI Backend->>Supabase DB: Verify Idempotency Key"
}}
</expected_json_output_schema>
"""

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

class AgentState(TypedDict):
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
        logger.info(f"[DB LOG] [AGENTS] Saving new project state for {project_id}...")
        db_state = await RequirementStateRepository.save_or_update(project_id, db_state)
        logger.info(f"[DB LOG] [AGENTS] Saving new project state for {project_id} complete.")
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

async def gatherer_node(state: AgentState) -> Dict[str, Any]:
    """
    Standardizes messy Product Owner input into high-quality Agile structures.
    Reads/writes to the centralized RequirementState object via persistence service.
    """
    logger.info("Executing gatherer_node to structure requirements.")
    project_id = state.get("project_id", "PROJ-UNKNOWN")
    raw_input = state.get("raw_input", "")
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

    result = None
    parsing_error = None
    
    # Import inside function to prevent circular imports
    from app.semantic_service import detect_semantic_changes
    
    semantic_recs = []
    if raw_input:
        # Run Semantic Change Detection
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
            
            updates = {
                "clarification_questions": combined_cqs,
                "validation_status": "invalid",
                "current_workflow_state": "gatherer_node"
            }
            logger.info(f"[DB LOG] [GATHERER] Saving clarification questions due to low confidence...")
            persisted_state = await RequirementStateRepository.save_or_update(project_id, updates)
            
            # Synchronize State
            req_state = persisted_state.copy()
            req_state["current_workflow_state"] = "gatherer_node"
            req_state["validation_status"] = "invalid"
            
            return {
                "requirement_state": req_state,
                "structured_requirements": passed_structured,
                "current_version": req_state.get("version_number", 1)
            }

        # Format current stories context
        context_lines = []
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
            template=GATHERER_PROMPT,
            input_variables=["raw_input", "current_context", "recommendations", "format_instructions"]
        )
        
        # Prepare components for logging
        pydantic_parser = PydanticOutputParser(pydantic_object=GatheredRequirements)
        format_instructions = pydantic_parser.get_format_instructions()
        prompt_value = prompt_template.format(
            raw_input=raw_input,
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
    epic_name = result.get("epic_name", "Structured Requirements Draft")
    requirements = {"epic_name": epic_name}
    user_stories = result.get("user_stories", [])
    ac_list = []
    for story in user_stories:
        ac_list.extend(story.get("acceptance_criteria", []))
    version_number = result.get("version", req_state["version_number"])
    
    # Save to database immediately using repository (isolating direct database communication)
    # Under Sprint 1 - Prompt 6C, we save user stories and requirements into their dedicated tables
    updates = {
        "requirements": requirements,
        "user_stories": user_stories,
        "version_number": version_number,
        "current_workflow_state": "gatherer_node",
        "semantic_recommendations": semantic_recs
    }
    logger.info(f"[DB LOG] [GATHERER] Saving updated requirements for project {project_id}...")
    persisted_state = await RequirementStateRepository.save_or_update(project_id, updates)
    logger.info(f"[DB LOG] [GATHERER] Saving updated requirements for project {project_id} complete.")
    
    # Sync and preserve newly generated in-memory state for downstream agent nodes and frontend compatibility
    req_state = persisted_state.copy()
    req_state["requirements"] = requirements
    req_state["user_stories"] = user_stories
    req_state["acceptance_criteria"] = ac_list
    req_state["version_number"] = version_number
    req_state["current_workflow_state"] = "gatherer_node"
    
    # Sync to outer structure for backend/frontend backward compatibility
    structured_out = {
        "epic_name": epic_name,
        "version": version_number,
        "user_stories": user_stories
    }
    
    return {
        "requirement_state": req_state,
        "structured_requirements": structured_out,
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
        updates = {
            "clarification_questions": req_state["clarification_questions"],
            "validation_status": req_state["validation_status"],
            "passed_checks": result.get("passed_checks", []),
            "failed_checks": result.get("failed_checks", []),
            "current_workflow_state": "auditor_node"
        }
        req_state = await RequirementStateRepository.save_or_update(project_id, updates)
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
        template=AUDITOR_PROMPT,
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
        
        # Modify only its own fields in RequirementState
        req_state["clarification_questions"] = combined_questions
        req_state["validation_status"] = "valid" if is_valid else "invalid"
        req_state["current_workflow_state"] = "auditor_node"
        
        # Save to database immediately using repository (isolating direct database communication)
        updates = {
            "clarification_questions": req_state["clarification_questions"],
            "validation_status": req_state["validation_status"],
            "passed_checks": result.get("passed_checks", []),
            "failed_checks": result.get("failed_checks", []),
            "current_workflow_state": "auditor_node"
        }
        logger.info(f"[DB LOG] [AUDITOR] Saving audit results for project {project_id}...")
        req_state = await RequirementStateRepository.save_or_update(project_id, updates)
        logger.info(f"[DB LOG] [AUDITOR] Saving audit results for project {project_id} complete.")
        
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
        req_state["current_workflow_state"] = "auditor_node"
        
        # Save fallback to database
        updates = {
            "clarification_questions": req_state["clarification_questions"],
            "validation_status": req_state["validation_status"],
            "passed_checks": [],
            "failed_checks": ["AUDIT_PARSE_ERROR"],
            "current_workflow_state": "auditor_node"
        }
        logger.info(f"[DB LOG] [AUDITOR] Saving fallback audit state for project {project_id}...")
        req_state = await RequirementStateRepository.save_or_update(project_id, updates)
        logger.info(f"[DB LOG] [AUDITOR] Saving fallback audit state for project {project_id} complete.")
        
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
        updates = {
            "generated_prd": existing_prd,
            "generated_diagrams": existing_diagrams,
            "current_workflow_state": "architect_node"
        }
        req_state = await RequirementStateRepository.save_or_update(project_id, updates)
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
        template=ARCHITECT_PROMPT + dynamic_instructions,
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
        
        # Modify only its own fields in RequirementState
        req_state["generated_prd"] = result.get("prd_markdown", "# Core Banking PRD\n\nNo description provided.")
        req_state["generated_diagrams"] = result.get("mermaid_diagram", "graph TD\n  Start --> End")
        req_state["current_workflow_state"] = "architect_node"
        
        # Save to database immediately using repository (isolating direct database communication)
        updates = {
            "generated_prd": req_state["generated_prd"],
            "generated_diagrams": req_state["generated_diagrams"],
            "current_workflow_state": "architect_node"
        }
        logger.info(f"[DB LOG] [ARCHITECT] Saving generated PRD/diagrams for project {project_id}...")
        req_state = await RequirementStateRepository.save_or_update(project_id, updates)
        logger.info(f"[DB LOG] [ARCHITECT] Saving generated PRD/diagrams for project {project_id} complete.")
        
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
        
        # Save error outcome to database
        updates = {
            "generated_prd": req_state["generated_prd"],
            "generated_diagrams": req_state["generated_diagrams"],
            "current_workflow_state": "architect_node"
        }
        logger.info(f"[DB LOG] [ARCHITECT] Saving fallback generated PRD/diagrams for project {project_id}...")
        req_state = await RequirementStateRepository.save_or_update(project_id, updates)
        logger.info(f"[DB LOG] [ARCHITECT] Saving fallback generated PRD/diagrams for project {project_id} complete.")
        
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
        logger.info("Routing to gatherer_node on-demand.")
        return "gatherer_node"

# ==========================================
# GRAPH COMPILATION
# ==========================================
workflow = StateGraph(AgentState)

# Append active node configurations
workflow.add_node("gatherer_node", gatherer_node)
workflow.add_node("auditor_node", auditor_node)
workflow.add_node("architect_node", architect_node)

# Set up conditional routing from START based on target_agent
workflow.add_conditional_edges(
    START,
    route_on_demand,
    {
        "gatherer_node": "gatherer_node",
        "auditor_node": "auditor_node",
        "architect_node": "architect_node"
    }
)

# Connect each on-demand agent directly to END to stop workflow execution
workflow.add_edge("gatherer_node", END)
workflow.add_edge("auditor_node", END)
workflow.add_edge("architect_node", END)

# Export compiled graph workflow
prd_workflow = workflow.compile()
logger.info("StateGraph compiled successfully with on-demand agent routing as `prd_workflow`.")