import logging
import json
from typing import List, Dict, Any, Optional
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel, Field
from app.config import settings
from app.agents import llm

logger = logging.getLogger("app.semantic_service")

class SemanticChange(BaseModel):
    change_type: str = Field(..., description="Classification: NEW_REQUIREMENT, MODIFY_REQUIREMENT, REMOVE_REQUIREMENT, RENAME_REQUIREMENT, NO_MEANINGFUL_CHANGE, EXPAND_REQUIREMENT, SPLIT_REQUIREMENT, MERGE_REQUIREMENTS")
    target_requirement_id: Optional[str] = Field(None, description="The ticket_code (e.g. US-001) of the affected user story, if any. Return null if it does not apply.")
    confidence: float = Field(..., description="Confidence score from 0.0 to 1.0")
    reason: str = Field(..., description="Detailed reasoning explaining why this change is classified this way.")
    recommended_action: str = Field(..., description="Action recommendation: INSERT, UPDATE, ARCHIVE, NO_CHANGE")

class SemanticChangeDetectionResult(BaseModel):
    changes: List[SemanticChange] = Field(..., description="List of all detected changes")

SEMANTIC_CHANGE_DETECTION_PROMPT = """
Your role is an Expert Requirements Analyst and AI Semantic Engineer for a Tier-1 Retail Bank.
Your task is to compare the Current Project Context (existing user stories and requirements) with the New User Message, and detect/classify every semantic change requested by the user.

<system_constraints>
- You must output your response 100% strictly in JSON format matching the schema provided.
- Do not include any standard AI introductory or trailing pleasantries (e.g., "Sure, here is...").
- Do not use Markdown, do not use ```json fences, do not use any formatting other than raw JSON.
- Evaluate semantic meaning, not just raw text. For example, "Transfer money" and "Transfer funds" are equivalent and represent the same business intent.
- Be precise when identifying target stories. Map them to their existing ticket_code (e.g. "US-001").
</system_constraints>

<classifications>
1. NEW_REQUIREMENT: A completely new feature or requirement. (e.g., adding QR Payment when only Transfer Money exists).
   Recommended action: "INSERT".
2. MODIFY_REQUIREMENT: Changing/modifying an existing user story or requirement. (e.g., requiring OTP verification for money transfer).
   Recommended action: "UPDATE".
3. REMOVE_REQUIREMENT: The user explicitly wants to remove or stop having some functionality. (e.g., removing scheduled transfers).
   Recommended action: "ARCHIVE".
4. RENAME_REQUIREMENT: Wording changes where meaning remains the same. (e.g., "Transfer Money" to "Funds Transfer").
   Recommended action: "UPDATE" (to keep wording up-to-date) or "NO_CHANGE".
5. NO_MEANINGFUL_CHANGE: Correcting spelling, fixing grammar, minor formatting, or empty/irrelevant messages.
   Recommended action: "NO_CHANGE".
6. EXPAND_REQUIREMENT: Existing requirement remains valid, but additional capabilities are introduced. (e.g., "Support international transfers" in a transfer module).
   Recommended action: "UPDATE".
7. SPLIT_REQUIREMENT: One existing requirement should be separated/split into multiple user stories.
   Recommended action: "UPDATE" (first story) and "INSERT" (remaining stories).
8. MERGE_REQUIREMENTS: Two or more existing requirements now represent a single consolidated feature.
   Recommended action: "MERGE".
</classifications>

<current_project_context>
{current_context}
</current_project_context>

<new_user_message>
{new_message}
</new_user_message>

{format_instructions}
"""

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
        template=SEMANTIC_CHANGE_DETECTION_PROMPT,
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
