import logging
import json
from typing import List, Dict, Any, Optional
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel, Field
from app.config import settings
from app.agents import llm
from app.schemas import RequirementIntentDetectionResult, WorkflowRoutingResult, RequirementMatcherResult
from app.prompt_loader import load_prompt

logger = logging.getLogger("app.semantic_service")

class SemanticChange(BaseModel):
    change_type: str = Field(..., description="Classification: NEW_REQUIREMENT, MODIFY_REQUIREMENT, REMOVE_REQUIREMENT, RENAME_REQUIREMENT, NO_MEANINGFUL_CHANGE, EXPAND_REQUIREMENT, SPLIT_REQUIREMENT, MERGE_REQUIREMENTS")
    target_requirement_id: Optional[str] = Field(None, description="The ticket_code (e.g. US-001) of the affected user story, if any. Return null if it does not apply.")
    confidence: float = Field(..., description="Confidence score from 0.0 to 1.0")
    reason: str = Field(..., description="Detailed reasoning explaining why this change is classified this way.")
    recommended_action: str = Field(..., description="Action recommendation: INSERT, UPDATE, ARCHIVE, NO_CHANGE")

class SemanticChangeDetectionResult(BaseModel):
    changes: List[SemanticChange] = Field(..., description="List of all detected changes")

class _PromptProxy:
    def __init__(self, name: str):
        self.name = name
    def __str__(self) -> str:
        return load_prompt(self.name)
    def __add__(self, other: str) -> str:
        return load_prompt(self.name) + str(other)
    def __radd__(self, other: str) -> str:
        return str(other) + load_prompt(self.name)

SEMANTIC_CHANGE_DETECTION_PROMPT = _PromptProxy("semantic")
REQUIREMENT_INTENT_DETECTION_PROMPT = _PromptProxy("intent")
REQUIREMENT_MATCHER_PROMPT = _PromptProxy("matcher")


async def detect_semantic_changes(raw_input: str, current_stories: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Compares existing user stories with raw_input to identify semantic changes and classifications.
    Returns a list of dicts representing detected semantic changes.
    """
    logger.info(f"Running semantic change detection on new message: '{raw_input[:100]}'")
    
    # Format current stories into a clean visual summary for the prompt
    context_lines = []
    for story in current_stories:
        context_lines.append(
            f"- Story {story.get('ticket_code', 'UNKNOWN')}: '{story.get('story_title', '')}'\n"
            f"  As a {story.get('as_a', '')}, I want to {story.get('i_want_to', '')}, So that {story.get('so_that', '')}\n"
            f"  Acceptance Criteria: {json.dumps(story.get('acceptance_criteria', []))}"
        )
    current_context = "\n".join(context_lines) if context_lines else "No existing user stories in this project."

    prompt_template = PromptTemplate(
        template=load_prompt("semantic"),
        input_variables=["current_context", "new_message", "format_instructions"]
    )
    
    pydantic_parser = JsonOutputParser(pydantic_object=SemanticChangeDetectionResult)
    format_instructions = pydantic_parser.get_format_instructions()
    
    result = None
    
    # Attempt with structured output
    try:
        logger.info("Attempting .with_structured_output() for semantic change detection.")
        chain = prompt_template | llm.with_structured_output(SemanticChangeDetectionResult)
        parsed_output = await chain.ainvoke({
            "current_context": current_context,
            "new_message": raw_input,
            "format_instructions": "Output ONLY raw JSON matching the schema."
        })
        result = parsed_output.dict() if hasattr(parsed_output, "dict") else dict(parsed_output)
        logger.info("Successfully obtained structured output for semantic changes.")
    except Exception as e:
        logger.warning(f"with_structured_output failed for semantic changes: {str(e)}. Falling back to manual parse.")
        
        try:
            raw_chain = prompt_template | llm
            raw_response = await raw_chain.ainvoke({
                "current_context": current_context,
                "new_message": raw_input,
                "format_instructions": format_instructions
            })
            
            # Extract content from response
            content = ""
            if hasattr(raw_response, "content") and isinstance(raw_response.content, str):
                content = raw_response.content
            
            clean_content = content.strip()
            if clean_content.startswith("```json"): clean_content = clean_content[7:]
            elif clean_content.startswith("```"): clean_content = clean_content[3:]
            if clean_content.endswith("```"): clean_content = clean_content[:-3]
            clean_content = clean_content.strip()
            
            result = json.loads(clean_content)
        except Exception as e2:
            logger.error(f"Semantic change detection parsing failed completely: {str(e2)}")
            # Fallback to a safe default NEW_REQUIREMENT if LLM fails
            result = {
                "changes": [
                    {
                        "change_type": "NEW_REQUIREMENT",
                        "target_requirement_id": None,
                        "confidence": 1.0,
                        "reason": f"Fallback due to analysis failure: {str(e2)}",
                        "recommended_action": "INSERT"
                    }
                ]
            }

    # Format into a clean list of changes
    changes = result.get("changes", [])
    logger.info(f"Detected {len(changes)} semantic changes.")
    return [c if isinstance(c, dict) else c.dict() for c in changes]


async def detect_requirement_intent(raw_input: str, current_stories: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """
    Uses LLM for semantic intent classification on user message.
    Returns a dict with: intent, confidence, reason.
    """
    if not raw_input or not str(raw_input).strip():
        return {
            "intent": "NO_CHANGE",
            "confidence": 1.0,
            "reason": "Empty input defaulted to NO_CHANGE."
        }
        
    logger.info(f"Detecting requirement intent for message: '{raw_input[:100]}'")
    
    context_lines = []
    if current_stories:
        for story in current_stories:
            context_lines.append(
                f"- Story {story.get('ticket_code', 'UNKNOWN')}: '{story.get('story_title', '')}'\n"
                f"  As a {story.get('as_a', '')}, I want to {story.get('i_want_to', '')}, So that {story.get('so_that', '')}\n"
                f"  Acceptance Criteria: {json.dumps(story.get('acceptance_criteria', []))}"
            )
    current_context = "\n".join(context_lines) if context_lines else "No existing user stories in this project."

    prompt_template = PromptTemplate(
        template=load_prompt("intent"),
        input_variables=["current_context", "user_message", "format_instructions"]
    )
    
    pydantic_parser = JsonOutputParser(pydantic_object=RequirementIntentDetectionResult)
    format_instructions = pydantic_parser.get_format_instructions()
    
    # Attempt 1: with_structured_output
    try:
        chain = prompt_template | llm.with_structured_output(RequirementIntentDetectionResult)
        parsed_output = await chain.ainvoke({
            "current_context": current_context,
            "user_message": raw_input,
            "format_instructions": "Output ONLY raw JSON matching the schema."
        })
        if hasattr(parsed_output, "dict"):
            res_dict = parsed_output.dict()
        elif isinstance(parsed_output, dict):
            res_dict = parsed_output
        else:
            res_dict = dict(parsed_output)

        intent = str(res_dict.get("intent", "")).strip().upper()
        confidence = float(res_dict.get("confidence", 0.95))
        reason = str(res_dict.get("reason") or res_dict.get("reasoning") or "")

        if intent in ["NEW", "UPDATE", "DELETE", "CLARIFY", "NO_CHANGE"]:
            logger.info(f"Successfully detected requirement intent via LLM: {intent} (confidence: {confidence}, reason: {reason})")
            return {
                "intent": intent,
                "confidence": confidence,
                "reason": reason
            }
    except Exception as e:
        logger.warning(f"with_structured_output failed for intent detection: {str(e)}. Retrying with raw invocation.")
        
    # Attempt 2: Raw invocation + JSON parse
    try:
        raw_chain = prompt_template | llm
        raw_response = await raw_chain.ainvoke({
            "current_context": current_context,
            "user_message": raw_input,
            "format_instructions": format_instructions
        })
        
        content = ""
        if hasattr(raw_response, "content") and isinstance(raw_response.content, str):
            content = raw_response.content
        elif isinstance(raw_response, dict) and "content" in raw_response:
            content = raw_response["content"]
            
        clean_content = str(content).strip()
        if clean_content.startswith("```json"): clean_content = clean_content[7:]
        elif clean_content.startswith("```"): clean_content = clean_content[3:]
        if clean_content.endswith("```"): clean_content = clean_content[:-3]
        clean_content = clean_content.strip()
        
        data = json.loads(clean_content)
        intent = str(data.get("intent", "")).strip().upper()
        confidence = float(data.get("confidence", 0.90))
        reason = str(data.get("reason") or data.get("reasoning") or "")

        if intent in ["NEW", "UPDATE", "DELETE", "CLARIFY", "NO_CHANGE"]:
            logger.info(f"Successfully parsed requirement intent from raw LLM output: {intent} (confidence: {confidence})")
            return {
                "intent": intent,
                "confidence": confidence,
                "reason": reason
            }
    except Exception as e2:
        logger.error(f"Intent detection parsing failed completely: {str(e2)}")

    return {
        "intent": "UPDATE",
        "confidence": 0.80,
        "reason": f"Fallback due to parsing failure: {str(e2)}"
    }


async def match_requirement(raw_input: str, detected_intent: str, current_stories: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """
    Requirement Matcher Agent between Intent Detection and Gatherer.
    Determines which existing requirement(s) the user's message refers to before any modification occurs.
    """
    if not raw_input or not str(raw_input).strip():
        return {
            "matched_requirement_id": None,
            "confidence": 1.0,
            "reason": "Empty input.",
            "action": "NEW",
            "status": "MATCHED",
            "candidates": None
        }

    logger.info(f"Running Requirement Matcher for input: '{raw_input[:100]}' with intent: {detected_intent}")

    context_lines = []
    if current_stories:
        for story in current_stories:
            context_lines.append(
                f"- Ticket Code: {story.get('ticket_code', 'UNKNOWN')}\n"
                f"  Title: '{story.get('story_title', '')}'\n"
                f"  As a {story.get('as_a', '')}, I want to {story.get('i_want_to', '')}, So that {story.get('so_that', '')}\n"
                f"  Acceptance Criteria: {json.dumps(story.get('acceptance_criteria', []))}"
            )
    current_context = "\n".join(context_lines) if context_lines else "No existing user stories in this project."

    prompt_template = PromptTemplate(
        template=load_prompt("matcher"),
        input_variables=["current_context", "detected_intent", "user_message", "format_instructions"]
    )

    pydantic_parser = JsonOutputParser(pydantic_object=RequirementMatcherResult)
    format_instructions = pydantic_parser.get_format_instructions()

    # Attempt 1: with_structured_output
    try:
        chain = prompt_template | llm.with_structured_output(RequirementMatcherResult)
        parsed_output = await chain.ainvoke({
            "current_context": current_context,
            "detected_intent": detected_intent,
            "user_message": raw_input,
            "format_instructions": "Output ONLY raw JSON matching the schema."
        })
        if hasattr(parsed_output, "dict"):
            res_dict = parsed_output.dict()
        elif isinstance(parsed_output, dict):
            res_dict = parsed_output
        else:
            res_dict = dict(parsed_output)

        confidence = float(res_dict.get("confidence", 0.95))
        status_val = str(res_dict.get("status", "MATCHED")).upper()
        
        if confidence < 0.75 and status_val == "MATCHED":
            res_dict["status"] = "LOW_CONFIDENCE"
            res_dict["reason"] = f"Confidence {confidence} is below threshold (0.75). Clarification required."

        logger.info(f"Successfully ran Requirement Matcher via structured output: {res_dict}")
        return res_dict
    except Exception as e:
        logger.warning(f"with_structured_output failed for requirement matcher: {str(e)}. Retrying with raw invocation.")

    # Attempt 2: Raw invocation + JSON parse
    try:
        raw_chain = prompt_template | llm
        raw_response = await raw_chain.ainvoke({
            "current_context": current_context,
            "detected_intent": detected_intent,
            "user_message": raw_input,
            "format_instructions": format_instructions
        })

        content = ""
        if hasattr(raw_response, "content") and isinstance(raw_response.content, str):
            content = raw_response.content
        elif isinstance(raw_response, dict) and "content" in raw_response:
            content = raw_response["content"]

        clean_content = str(content).strip()
        if clean_content.startswith("```json"): clean_content = clean_content[7:]
        elif clean_content.startswith("```"): clean_content = clean_content[3:]
        if clean_content.endswith("```"): clean_content = clean_content[:-3]
        clean_content = clean_content.strip()

        data = json.loads(clean_content)
        confidence = float(data.get("confidence", 0.85))
        status_val = str(data.get("status", "MATCHED")).upper()
        if confidence < 0.75 and status_val == "MATCHED":
            data["status"] = "LOW_CONFIDENCE"
            data["reason"] = f"Confidence {confidence} is below threshold (0.75). Clarification required."

        logger.info(f"Successfully parsed requirement matcher from raw LLM output: {data}")
        return data
    except Exception as e2:
        logger.error(f"Requirement matcher parsing failed completely: {str(e2)}")

    is_new = detected_intent in ["NEW", "NO_CHANGE"]
    return {
        "matched_requirement_id": None,
        "confidence": 0.80,
        "reason": f"Fallback due to parsing failure: {str(e2)}",
        "action": detected_intent if detected_intent in ["NEW", "UPDATE", "DELETE"] else "NEW",
        "status": "MATCHED",
        "candidates": None
    }



async def classify_workflow(raw_input: str) -> Dict[str, Any]:
    """
    Lightweight Workflow Router layer before the Gatherer Agent.
    Classifies every incoming user message into one of four workflow types:
    - CHAT
    - QUESTION
    - COMMAND
    - REQUIREMENT
    
    Returns structured JSON dict:
    {
        "workflow": "QUESTION",
        "confidence": 0.96,
        "reason": "The user is asking for an explanation rather than modifying project requirements."
    }
    """
    if not raw_input or not str(raw_input).strip():
        return {
            "workflow": "CHAT",
            "confidence": 1.0,
            "reason": "Empty input defaulted to CHAT."
        }

    clean_input = str(raw_input).strip()
    logger.info(f"Routing workflow classification for input: '{clean_input[:100]}'")

    prompt_template = PromptTemplate(
        template=load_prompt("router"),
        input_variables=["user_message", "format_instructions"]
    )

    pydantic_parser = JsonOutputParser(pydantic_object=WorkflowRoutingResult)
    format_instructions = pydantic_parser.get_format_instructions()

    # Attempt 1: with_structured_output
    try:
        chain = prompt_template | llm.with_structured_output(WorkflowRoutingResult)
        parsed_output = await chain.ainvoke({
            "user_message": clean_input,
            "format_instructions": "Output ONLY raw JSON matching the schema."
        })
        if hasattr(parsed_output, "dict"):
            res_dict = parsed_output.dict()
        elif isinstance(parsed_output, dict):
            res_dict = parsed_output
        else:
            res_dict = dict(parsed_output)

        wf = str(res_dict.get("workflow", "")).strip().upper()
        if wf in ["CHAT", "QUESTION", "COMMAND", "REQUIREMENT"]:
            res_dict["workflow"] = wf
            res_dict["confidence"] = float(res_dict.get("confidence", 0.95))
            res_dict["reason"] = str(res_dict.get("reason", ""))
            logger.info(f"Workflow router classified input via LLM structured output: {res_dict}")
            return res_dict
    except Exception as e:
        logger.warning(f"with_structured_output failed for workflow routing: {str(e)}. Retrying raw invocation.")

    # Attempt 2: Raw invocation + JsonOutputParser
    try:
        raw_chain = prompt_template | llm
        raw_response = await raw_chain.ainvoke({
            "user_message": clean_input,
            "format_instructions": format_instructions
        })
        content = ""
        if hasattr(raw_response, "content") and isinstance(raw_response.content, str):
            content = raw_response.content
        elif isinstance(raw_response, dict) and "content" in raw_response:
            content = raw_response["content"]

        clean_content = str(content).strip()
        if clean_content.startswith("```json"): clean_content = clean_content[7:]
        elif clean_content.startswith("```"): clean_content = clean_content[3:]
        if clean_content.endswith("```"): clean_content = clean_content[:-3]
        clean_content = clean_content.strip()

        data = json.loads(clean_content)
        wf = str(data.get("workflow", "")).strip().upper()
        if wf in ["CHAT", "QUESTION", "COMMAND", "REQUIREMENT"]:
            data["workflow"] = wf
            data["confidence"] = float(data.get("confidence", 0.90))
            data["reason"] = str(data.get("reason", ""))
            logger.info(f"Workflow router classified input via raw LLM response: {data}")
            return data
    except Exception as e2:
        logger.error(f"Workflow router raw parsing failed: {str(e2)}")

    # Heuristic Fallback
    lower_inp = clean_input.lower()
    if lower_inp in ["hello", "hi", "thank you", "thanks", "good morning", "good afternoon", "good evening"]:
        return {
            "workflow": "CHAT",
            "confidence": 0.95,
            "reason": "The user is providing a conversational greeting or pleasantry."
        }
    elif lower_inp.startswith("what") or lower_inp.startswith("explain") or lower_inp.startswith("how") or lower_inp.startswith("can you explain") or lower_inp.endswith("?"):
        return {
            "workflow": "QUESTION",
            "confidence": 0.90,
            "reason": "The user is asking a direct question or seeking an explanation."
        }
    elif any(cmd in lower_inp for cmd in ["run auditor", "generate prd", "generate diagram", "export docx", "audit requirements"]):
        return {
            "workflow": "COMMAND",
            "confidence": 0.90,
            "reason": "The user is requesting an automated backend command execution."
        }
    else:
        return {
            "workflow": "REQUIREMENT",
            "confidence": 0.85,
            "reason": "The user input describes a software requirement or functional modification."
        }


