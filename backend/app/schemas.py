from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime

# ==========================================
# 1. BASE DB TRANSACTION SCHEMAS
# ==========================================

class ProjectCreate(BaseModel):
    """Schema for introducing new banking systems under compliance review."""
    name: str = Field(..., max_length=255, description="Name of core banking system or microservice.")
    description: Optional[str] = Field(None, description="System functional scope details.")
    industry_standard: str = Field("Krungsri Nimble Baseline", description="Target compliance guideline standard.")

class RequirementState(BaseModel):
    """Schema tracking current locking state and Epic structure attributes."""
    epic_name: str = Field(..., description="High-level functional domain name.")
    total_user_stories: int = Field(0, ge=0, description="Count of parsed customer workflows.")
    current_version: int = Field(1, ge=1, description="Latest revision of the requirement document.")
    is_locked: bool = Field(False, description="When True, active editing is locked pending audit resolution.")

class UserAnswerSubmit(BaseModel):
    """Schema wrapping feedback replies to unresolved compliance query logs."""
    answer_text: str = Field(..., min_length=5, description="Official stakeholder audit clearance resolution text.")


# ==========================================
# 2. LOCAL LLM STRUCTURED OUTPUTS (JSON MODE)
# ==========================================

class CheckResultItem(BaseModel):
    """Individual rule verification structure."""
    rule: str = Field(..., description="Unique code identifier for the rule (e.g. MFA_FALLSAFE, UUID_INTEGRITY).")
    message: str = Field(..., description="Descriptive validation results of rule analysis.")

class LLMStructuredOutput(BaseModel):
    """
    Deterministic schema driving JSON-mode responses from local models.
    Guarantees that local LLMs output compliant structures for parsed user stories.
    """
    is_valid: bool = Field(..., description="Whether the analyzed requirement complies with target regulatory rules.")
    passed_checks: List[CheckResultItem] = Field(default_factory=list, description="Validated and approved rules.")
    failed_checks: List[CheckResultItem] = Field(default_factory=list, description="Rules violating strict compliance specs.")
    suggested_questions: List[str] = Field(
        default_factory=list, 
        description="Clarification queries generated dynamically to resolve ambiguities."
    )

class ChatMessage(BaseModel):
    """Basic structural model for conversations."""
    role: str = Field(..., description="Either 'user', 'assistant' or 'system'.")
    content: str = Field(..., description="Raw text prompt or assistant response.")

class ChatSessionRequest(BaseModel):
    """Input driving conversations and LangGraph multi-agent context."""
    messages: List[ChatMessage] = Field(..., description="Historic conversational timeline states.")
    project_id: Optional[UUID] = Field(None, description="Current project context indicator.")


# ==========================================
# 3. GATHERED REQUIREMENTS SCHEMA FOR LLM
# ==========================================

class UserStoryModel(BaseModel):
    ticket_code: str = Field(..., description="Unique ticket code (e.g. US-001)")
    story_title: str = Field(..., description="Short descriptive action title")
    as_a: str = Field(..., description="The user role or persona (e.g. Corporate Merchant Retailer)")
    i_want_to: str = Field(..., description="The action/system task requested")
    so_that: str = Field(..., description="The business benefit or outcome")
    acceptance_criteria: List[str] = Field(..., description="Behavioral validation checklist (e.g. Given/When/Then)")

class GatheredRequirements(BaseModel):
    epic_name: str = Field(..., description="Unified theme of all extracted stories")
    version: int = Field(default=1, description="Incremental version counter")
    user_stories: List[UserStoryModel] = Field(..., description="Granular product backlog items")

