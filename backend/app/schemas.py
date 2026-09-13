from pydantic import BaseModel, Field, ConfigDict, field_validator
from typing import List, Optional, Dict, Any, Union
from uuid import UUID

# ==========================================
# 1. BASE DB TRANSACTION SCHEMAS
# ==========================================

class ProjectCreate(BaseModel):
    """Schema for introducing new banking systems under compliance review."""
    name: str = Field(..., description="Name of core banking system or microservice (max 40 characters).")
    description: Optional[str] = Field(None, description="System functional scope details.")
    industry_standard: str = Field("Krungsri Nimble Baseline", description="Target compliance guideline standard.")

    @field_validator("name")
    @classmethod
    def _strip_and_require_name(cls, value: str) -> str:
        """Trim surrounding whitespace, reject blank names, and cap at 40 characters.

        Duplicate-name detection (see ``ProjectRepository.name_exists``)
        compares trimmed, lower-cased names, so the stored name is
        canonicalized here once at the schema boundary. The 40-character cap
        keeps names short (dashboard table, PRD export filename), is applied
        AFTER trimming so padded names count their real length, and applies to
        BOTH create and rename (both routes share this schema).
        """
        stripped = value.strip()
        if not stripped:
            raise ValueError("Project name must not be empty.")
        if len(stripped) > 40:
            raise ValueError("Project name must be 40 characters or fewer.")
        return stripped

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
# 2. CHAT SCHEMAS
# ==========================================

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

class RequirementItem(BaseModel):
    requirement_code: str = Field(..., description="Unique requirement code (e.g. REQ-001)")
    title: str = Field(..., description="Short descriptive title of the requirement")
    description: Optional[str] = Field(default="", description="Detailed description or goal of this requirement")
    user_stories: List[UserStoryModel] = Field(..., description="Granular product backlog items under this requirement")

class GatheredRequirements(BaseModel):
    epic_name: str = Field(..., description="Unified theme of all extracted stories")
    version: int = Field(default=1, description="Incremental version counter")
    requirements: List[RequirementItem] = Field(..., description="Multiple requirements with their user stories")


# ==========================================
# 4. REQUIREMENT INTENT DETECTION SCHEMA
# ==========================================

class RequirementIntentDetectionResult(BaseModel):
    intent: str = Field(
        ..., 
        description="Detected user intent: GENERAL_CHAT, CREATE_REQUIREMENT, UPDATE_REQUIREMENT, DELETE_REQUIREMENT, or CLARIFY_REQUIREMENT."
    )
    confidence: float = Field(default=1.0, description="Confidence score from 0.0 to 1.0")
    reason: str = Field(default="", description="Detailed reasoning explaining the intent classification.")
    reasoning: Optional[str] = Field(default="", description="Brief reasoning explaining the intent classification.")


# ==========================================
# 5. WORKFLOW ROUTING SCHEMA
# ==========================================

class WorkflowRoutingResult(BaseModel):
    workflow: str = Field(..., description="Classified workflow type: CHAT, QUESTION, COMMAND, or REQUIREMENT")
    confidence: float = Field(default=1.0, description="Confidence score from 0.0 to 1.0")
    reason: str = Field(default="", description="Brief explanation of the workflow classification decision.")

# ==========================================
# 6. REQUIREMENT MATCHER SCHEMA
# ==========================================

class RequirementMatcherResult(BaseModel):
    matched_requirement_id: Optional[str] = Field(None, description="The matched requirement/ticket code (e.g. US-001) if applicable, or null.")
    confidence: float = Field(default=1.0, description="Confidence score from 0.0 to 1.0")
    reason: str = Field(default="", description="Detailed reasoning explaining the match.")
    action: str = Field(..., description="Action recommendation: NEW, UPDATE, DELETE, or CLARIFY")
    status: Optional[str] = Field(default="MATCHED", description="Status: MATCHED, AMBIGUOUS, or LOW_CONFIDENCE")
    candidates: Optional[List[str]] = Field(default=None, description="List of candidate requirement IDs if ambiguous.")


# ==========================================
# 8. ROUTER REQUEST SCHEMAS
# ==========================================

class ProcessRequirementsRequest(BaseModel):
    """Request body for the multi-agent Agile requirements processing endpoint."""
    project_id: str
    raw_input: Optional[str] = Field(default="")
    current_version: Optional[int] = Field(default=1)
    version_history_summaries: Optional[str] = Field(default="No previous history.")
    target_agent: Optional[str] = Field(default="gatherer")
    structured_requirements: Optional[Dict[str, Any]] = Field(default_factory=dict)


class ArtifactLockRequest(BaseModel):
    """Request body for locking/unlocking any artifact."""
    locked_by: Optional[str] = Field(default="user", description="Identifier of who is locking/unlocking the artifact.")


class RequirementLockRequest(BaseModel):
    """Request body for locking/unlocking a requirement."""
    locked_by: Optional[str] = Field(default="user", description="Identifier of who is locking/unlocking the requirement.")


class WorkflowRouterRequest(BaseModel):
    """Request body for the workflow router endpoint."""
    message: str


class IntentDetectorRequest(BaseModel):
    """Request body for the intent detector endpoint."""
    message: str
    project_id: Optional[str] = None


class RequirementMatcherRequest(BaseModel):
    """Request body for the requirement matcher endpoint."""
    message: str
    project_id: Optional[str] = None
    detected_intent: Optional[str] = "UPDATE"
# ==========================================
# 9. RESPONSE MODELS (OPENAPI / DOCS)
# ==========================================

class HealthResponse(BaseModel):
    """Liveness + LM Studio readiness payload returned by ``GET /api/health``.

    Finding #40: the liveness probe now runs a real ``GET /models`` round-trip
    against the local LM Studio gateway so callers (uptime checks, the React UI)
    can detect an offline LLM and degrade gracefully instead of assuming it runs.
    ``status`` is always ``"online"`` when the app itself is reachable; the LM
    Studio connectivity is reported separately via ``lm_studio_online``.
    """
    status: str = Field(..., description="Liveness status, always 'online' when the app is reachable.")
    app_name: str = Field(..., description="Application name as configured.")
    local_inference_gateway: str = Field(..., description="Local (LM Studio) inference endpoint URL.")
    macbook_context_window_budget: str = Field(..., description="Configured maximum context-window budget, e.g. '8000 tokens'.")
    lm_studio_online: bool = Field(False, description="True when the local LM Studio server responded to the /models probe.")
    lm_studio_model: Optional[str] = Field(None, description="Configured LM_STUDIO_MODEL_FALLBACK id.")
    lm_studio_model_loaded: bool = Field(False, description="True when the configured model is currently loaded in LM Studio.")
    lm_studio_loaded_models: List[str] = Field(default_factory=list, description="Model ids currently served by the local gateway.")
    lm_studio_latency_ms: Optional[float] = Field(None, description="Probe round-trip latency in milliseconds (None when offline).")
    lm_studio_error: Optional[str] = Field(None, description="Human-readable failure reason when the probe could not reach LM Studio.")
    lm_studio_last_checked: Optional[str] = Field(None, description="ISO-8601 UTC timestamp of the last successful probe result.")


class ChatResponse(BaseModel):
    """Assistant reply returned by ``POST /api/chat``."""
    message: str = Field(..., description="The assistant's generated reply text.")


class ProjectSummary(BaseModel):
    """Project summary record returned by project list/detail endpoints."""
    id: str = Field(..., description="Project UUID string.")
    name: str = Field(..., description="Human-readable project name.")
    description: Optional[str] = Field(None, description="Optional functional-scope description.")
    industry_standard: str = Field(..., description="Target compliance guideline standard.")
    is_pinned: bool = Field(False, description="True when the project/chat is pinned to the top of the sidebar.")
    is_flagged: bool = Field(False, description="True when the project is flagged with the dashboard ★ marker (independent of pinning).")
    status: str = Field(
        "draft",
        description="User-editable workflow status: 'draft' | 'in_review_hpo' | 'in_review_po' | 'approved' | 'revised'.",
    )
    updated_at: Optional[str] = Field(
        None,
        description="ISO-8601 timestamp of the last project update (drives the dashboard 'Updated' column).",
    )
    match_snippet: Optional[str] = Field(
        None,
        description="Short excerpt of a conversation message (if the project matched via "
                    "message content) centered on the search term, for sidebar highlighting.",
    )


class ProjectCreated(BaseModel):
    """Payload confirming a successfully created project."""
    id: str = Field(..., description="Newly created project UUID string.")
    name: str = Field(..., description="Created project name.")


class ProjectDeleteResponse(BaseModel):
    """Payload confirming a project was deleted."""
    status: str = Field(..., description="Always 'deleted' on success.")
    project_id: str = Field(..., description="UUID string of the deleted project.")


class ProjectPinRequest(BaseModel):
    """Request body for pinning/unpinning a project (chat)."""
    is_pinned: bool = Field(..., description="True pins the project to the top of the sidebar; False unpins it.")


class ProjectFlagRequest(BaseModel):
    """Request body for flagging/unflagging a project (dashboard ★ marker)."""
    is_flagged: bool = Field(..., description="True marks the project with the dashboard ★ flag; False removes it.")


class ProjectStatusRequest(BaseModel):
    """Request body for setting a project's user-editable workflow status (dashboard table)."""
    status: str = Field(
        ...,
        description="New workflow status: 'draft' | 'in_review_hpo' | 'in_review_po' | 'approved' | 'revised'.",
    )


# --------------------------------------------------------------------------
# Typed nested detail models for the flattened requirement-state payload.
#
# The legacy repository serializers emit denormalized, lock-augmented shapes
# (e.g. user stories enriched with ``acceptance_criteria``, requirements that
# omit ``project_id``/``status``). Every model keeps ``extra='allow'`` and all
# non-identifying fields optional so both the flattened state payload and the
# standalone per-entity responses serialize without loss or validation errors.
# --------------------------------------------------------------------------


class UserStoryDetail(BaseModel):
    """A single user story as emitted by ``serialize_user_story`` (optionally lock-augmented)."""
    model_config = ConfigDict(extra="allow")

    id: Optional[str] = Field(None, description="Story UUID string.")
    project_id: Optional[str] = Field(None, description="Owning project UUID string.")
    ticket_code: Optional[str] = Field(None, description="Ticket code (e.g. US-001).")
    story_title: Optional[str] = Field(None, description="Human-readable story title.")
    title: Optional[str] = Field(None, description="Legacy alias of the story title.")
    as_a: Optional[str] = Field(None, description="User role or persona.")
    i_want_to: Optional[str] = Field(None, description="Requested action/task.")
    so_that: Optional[str] = Field(None, description="Business benefit/outcome.")
    acceptance_criteria: Optional[List[str]] = Field(default_factory=list, description="Given/When/Then criteria.")
    status: Optional[str] = Field("active", description="Current story status.")
    version: Optional[int] = Field(None, description="Story revision.")
    last_modified_by: Optional[str] = Field(None, description="Actor that last modified.")
    change_type: Optional[str] = Field(None, description="Change classification.")
    is_locked: Optional[bool] = Field(False, description="Whether the story is locked.")
    locked_by: Optional[str] = Field(None, description="Locking actor.")
    locked_at: Optional[str] = Field(None, description="ISO8601 lock timestamp.")


class BusinessGoalItem(BaseModel):
    """A parsed business-goal entry (may appear as a plain string in legacy payloads)."""
    model_config = ConfigDict(extra="allow")

    description: Optional[str] = Field(None, description="Business-goal statement.")


class ActorItem(BaseModel):
    """A system-actor definition (may appear as a plain string in legacy payloads)."""
    model_config = ConfigDict(extra="allow")

    name: Optional[str] = Field(None, description="Actor name.")


class AcceptanceCriterionItem(BaseModel):
    """An acceptance criterion (may appear as a plain string in legacy payloads)."""
    model_config = ConfigDict(extra="allow")

    id: Optional[str] = Field(None, description="Criterion UUID string.")
    project_id: Optional[str] = Field(None, description="Owning project UUID string.")
    ticket_code: Optional[str] = Field(None, description="Linked user-story ticket code.")
    user_story_id: Optional[str] = Field(None, description="Linked user-story UUID string.")
    criteria_text: Optional[str] = Field(None, description="Criterion body.")
    status: Optional[str] = Field(None, description="Criterion status.")
    version: Optional[int] = Field(None, description="Criterion version.")
    last_modified_by: Optional[str] = Field(None, description="Actor that last modified.")
    change_type: Optional[str] = Field(None, description="Change classification.")


class ClarificationQuestionDetail(BaseModel):
    """A clarification question on the compliance audit."""
    model_config = ConfigDict(extra="allow")

    id: Optional[str] = Field(None, description="Question UUID string.")
    project_id: Optional[str] = Field(None, description="Owning project UUID string.")
    checklist_category: Optional[str] = Field(None, description="Compliance checklist category.")
    target_user_story_id: Optional[str] = Field(None, description="Target story ticket code or UUID.")
    question_text: Optional[str] = Field(None, description="Human-readable question.")
    user_answer: Optional[str] = Field(None, description="Stakeholder resolution text, if answered.")
    is_resolved: Optional[bool] = Field(None, description="Whether the question has been resolved.")


class RequirementDetail(BaseModel):
    """Requirement record carrying lock metadata and optional nested user stories."""
    model_config = ConfigDict(extra="allow")

    id: str = Field(..., description="Requirement UUID string.")
    project_id: Optional[str] = Field(None, description="Owning project UUID string.")
    epic_id: Optional[str] = Field(None, description="Owning epic UUID string, if any.")
    requirement_code: str = Field(..., description="Requirement code (e.g. REQ-001).")
    title: str = Field(..., description="Requirement title.")
    description: Optional[str] = Field(None, description="Requirement description.")
    status: Optional[str] = Field("active", description="Status: 'active' or 'deleted'.")
    is_locked: Optional[bool] = Field(False, description="Whether locked against edits.")
    locked_by: Optional[str] = Field(None, description="Locking actor.")
    locked_at: Optional[str] = Field(None, description="ISO8601 lock timestamp.")
    user_stories: Optional[List[UserStoryDetail]] = Field(default_factory=list, description="User stories under this requirement.")


class ConversationMessageResponse(BaseModel):
    """A single persisted conversation message."""
    model_config = ConfigDict(extra="allow")

    id: str = Field(..., description="Message UUID string.")
    project_id: str = Field(..., description="Project UUID string the message belongs to.")
    role: str = Field(..., description="Message role: 'user' or 'assistant'.")
    message: str = Field(..., description="Raw message text.")
    content: str = Field(..., description="Alias of the raw message text.")
    workflow_state: str = Field("", description="Workflow state captured at persistence time.")
    intent: str = Field("", description="Detected intent captured at persistence time.")
    created_at: str = Field("", description="ISO8601 timestamp of the message.")


class RequirementStateResponse(BaseModel):
    """
    Flattened requirement-state payload shared by project/requirement routes.

    Because workflow agents may attach additional domain fields (e.g. ``epic_name``,
    ``semantic_recommendations``), unknown keys are preserved via ``extra='allow'``
    rather than being dropped during response serialization.
    """
    model_config = ConfigDict(extra="allow")

    project_id: str = Field(..., description="Project UUID string.")
    project_name: Optional[str] = Field(None, description="Human-readable project name.")
    requirements: List[RequirementDetail] = Field(default_factory=list, description="Requirement entries, each carrying its own user_stories.")
    business_goals: List[Union[str, BusinessGoalItem]] = Field(default_factory=list, description="Parsed business-goal statements.")
    actors: List[Union[str, ActorItem]] = Field(default_factory=list, description="System actor definitions.")
    user_stories: List[UserStoryDetail] = Field(default_factory=list, description="Flattened list of active user stories.")
    acceptance_criteria: List[Union[str, AcceptanceCriterionItem]] = Field(default_factory=list, description="Flattened list of acceptance criteria.")
    clarification_questions: List[ClarificationQuestionDetail] = Field(default_factory=list, description="Open/resolved clarification questions.")
    validation_status: str = Field("pending", description="Compliance validation status: 'pending', 'valid' or 'invalid'.")
    generated_prd: str = Field("", description="Markdown PRD content.")
    generated_diagrams: str = Field("", description="Mermaid diagram source.")
    current_workflow_state: str = Field("gatherer_node", description="Current multi-agent workflow node.")
    version_number: int = Field(1, description="Current requirement-document revision.")
    updated_at: Optional[str] = Field(None, description="ISO8601 timestamp of the last update.")
    conversation_history: List[ConversationMessageResponse] = Field(default_factory=list, description="Persisted conversation messages for the project.")


class RequirementLockResponse(BaseModel):
    """Payload returned when locking/unlocking a requirement."""
    status: str = Field(..., description="'locked' or 'unlocked'.")
    requirement: RequirementDetail = Field(..., description="The affected requirement record.")
class PRDVersionChangedSection(BaseModel):
    """One per-section change record attached to a PRD version snapshot."""
    model_config = ConfigDict(extra="allow")

    section_key: str = Field(..., description="Stable section key ('stakeholders', ...).")
    title: str = Field("", description="Display title of the part.")
    change_kind: str = Field("unchanged", description="'created' | 'updated' | 'unchanged' | 'removed' | 'locked_preserved'.")
    changed: bool = Field(False, description="True when the snapshot actually changed (or protected) this part.")


class PRDVersionResponse(BaseModel):
    """Immutable PRD version record."""
    model_config = ConfigDict(extra="allow")

    version_id: str = Field(..., description="PRD version UUID string.")
    project_id: str = Field(..., description="Project UUID string.")
    version_number: int = Field(..., description="Monotonic version number.")
    generated_prd: str = Field("", description="Markdown PRD content for this version.")
    generated_by: str = Field("automated_agent", description="Actor that produced the version.")
    change_type: str = Field("ai", description="'ai' | 'manual' — origin of the snapshot.")
    # Semantic Version (MAJOR.MINOR.PATCH): MAJOR = sections created/removed,
    # MINOR = AI content updates, PATCH = manual edits / no-change advances.
    semver: str = Field("1.0.0", description="Semantic Version of this snapshot.")
    change_summary: Optional[str] = Field(None, description="Human-readable change description.")
    changed_sections: Optional[List[PRDVersionChangedSection]] = Field(
        None, description="Per-section change records computed at snapshot time."
    )
    created_at: str = Field("", description="ISO8601 creation timestamp.")


class PrdVersionDiffSection(BaseModel):
    """Line-level diff of ONE section between two PRD versions."""
    model_config = ConfigDict(extra="allow")

    section_key: str = Field(..., description="Stable section key.")
    title: str = Field("", description="Display title of the part.")
    change_kind: str = Field("unchanged", description="'created' | 'updated' | 'unchanged' | 'removed' | 'locked_preserved'.")
    changed: bool = Field(False, description="True when the section content differs between the two versions.")
    added: int = Field(0, description="Lines added in the newer version.")
    removed: int = Field(0, description="Lines removed from the older version.")
    diff_lines: List[List[str]] = Field(
        default_factory=list,
        description="Diff lines: [['add'|'del'|'context', line], ...].",
    )


class PrdVersionDiffResponse(BaseModel):
    """Diff between two PRD versions, section by section."""
    model_config = ConfigDict(extra="allow")

    project_id: str = Field(..., description="Project UUID string.")
    to_version: int = Field(..., description="Newer version being compared.")
    base_version: int = Field(..., description="Older base version.")
    sections: List[PrdVersionDiffSection] = Field(default_factory=list, description="Per-section diffs.")


class PRDExportResponse(BaseModel):
    """Payload returned by the PRD export endpoint."""
    project_id: UUID = Field(..., description="Project UUID.")
    version: int = Field(..., description="Persisted PRD version number.")
    version_id: Optional[str] = Field(None, description="PRD version UUID string, null if persistence failed.")
    prd_markdown: str = Field(..., description="Generated PRD markdown.")
    mermaid_diagram: str = Field(..., description="Generated Mermaid diagram source.")


class ArtifactLockResponse(BaseModel):
    """Payload returned when locking/unlocking/reading a generic artifact."""
    status: str = Field(..., description="Operation status: 'locked', 'unlocked' or 'lock_status'.")
    artifact: Dict[str, Any] = Field(..., description="Lock metadata for the artifact.")


class LockStatusResponse(BaseModel):
    """Lock metadata returned by the artifact lock-status endpoint."""
    artifact_type: str = Field(..., description="Type of artifact queried.")
    artifact_id: str = Field(..., description="UUID string of the artifact.")
    is_locked: bool = Field(False, description="Whether the artifact is currently locked.")
    locked_by: Optional[str] = Field(None, description="Identifier of the current locking user/agent.")
    locked_at: Optional[str] = Field(None, description="ISO8601 lock timestamp, if locked.")


class PendingActionResponse(BaseModel):
    """A human-in-the-loop pending (merge) action awaiting confirmation."""
    id: str = Field(..., description="Pending-action UUID string.")
    project_id: str = Field(..., description="Project UUID string.")
    action_type: str = Field(..., description="Action type (e.g. MERGE).")
    target_requirement_id: Optional[str] = Field(None, description="Target requirement code/id, if any.")
    original_user_message: str = Field(..., description="Original message that triggered the action.")
    proposed_changes: Dict[str, Any] = Field(default_factory=dict, description="Proposed merged requirement state.")
    affected_user_story_ids: List[str] = Field(default_factory=list, description="Affected user-story IDs.")
    affected_acceptance_criteria_ids: List[str] = Field(default_factory=list, description="Affected acceptance-criteria IDs.")
    workflow_stage: str = Field(..., description="Workflow stage captured when the action was created.")
    status: str = Field(..., description="Action status (e.g. WAITING_CONFIRMATION).")
    expires_at: str = Field(..., description="ISO8601 expiry timestamp.")


class ConfirmActionResponse(BaseModel):
    """Payload returned after a pending action is confirmed and persisted."""
    status: str = Field(..., description="Always 'confirmed' on success.")
    requirement_state: RequirementStateResponse = Field(..., description="The merged requirement state that was persisted.")


class ActionStatusResponse(BaseModel):
    """Generic single-status payload (e.g. cancel-action response)."""
    status: str = Field(..., description="Result status string.")


class AuditRespondResponse(BaseModel):
    """Payload returned after answering an audit clarification question."""
    status: str = Field(..., description="Always 'success' on completion.")
    message: str = Field(..., description="Human-readable confirmation message.")
    resolved_at: str = Field(..., description="ISO8601 timestamp of the resolution.")
    is_resolved: bool = Field(..., description="True once the question is resolved.")
class EventLogEntry(BaseModel):
    """A single append-only artifact event-log record."""
    event_id: str = Field(..., description="Event UUID string.")
    artifact_type: str = Field(..., description="Type of artifact (requirement, user_story, etc.).")
    artifact_id: str = Field(..., description="UUID string of the affected artifact.")
    action: str = Field(..., description="Action: CREATE, UPDATE, DELETE, ARCHIVE, LOCK or UNLOCK.")
    old_value: Optional[Dict[str, Any]] = Field(None, description="Snapshot of the artifact before the change.")
    new_value: Optional[Dict[str, Any]] = Field(None, description="Snapshot of the artifact after the change.")
    performed_by: str = Field(..., description="Identifier of the actor that performed the action.")
    timestamp: str = Field("", description="ISO8601 event timestamp.")


class EventListResponse(BaseModel):
    """Events across all artifacts, with pagination metadata."""
    events: List[EventLogEntry] = Field(default_factory=list, description="Newest-first event records.")
    total: int = Field(..., description="Number of events returned in this page.")
    limit: int = Field(..., description="Maximum entries returned.")
    offset: int = Field(..., description="Pagination offset.")


class ArtifactEventListResponse(BaseModel):
    """Events for a single artifact, with pagination metadata."""
    artifact_type: str = Field(..., description="Type of artifact queried.")
    artifact_id: str = Field(..., description="UUID string of the artifact queried.")
    events: List[EventLogEntry] = Field(default_factory=list, description="Newest-first event records.")
    total: int = Field(..., description="Number of events returned in this page.")
    limit: int = Field(..., description="Maximum entries returned.")
    offset: int = Field(..., description="Pagination offset.")


class ActionEventListResponse(BaseModel):
    """Events filtered by action type, with pagination metadata."""
    action: str = Field(..., description="Normalized action name (uppercased).")
    events: List[EventLogEntry] = Field(default_factory=list, description="Newest-first event records.")
    total: int = Field(..., description="Number of events returned in this page.")
    limit: int = Field(..., description="Maximum entries returned.")
    offset: int = Field(..., description="Pagination offset.")


class ProjectEventListResponse(BaseModel):
    """Events for a single project, with optional filters and pagination metadata."""
    project_id: str = Field(..., description="Project UUID string.")
    artifact_type: Optional[str] = Field(None, description="Optional artifact-type filter applied.")
    action: Optional[str] = Field(None, description="Optional action filter applied.")
    events: List[EventLogEntry] = Field(default_factory=list, description="Newest-first event records.")
    total: int = Field(..., description="Number of events returned in this page.")
    limit: int = Field(..., description="Maximum entries returned.")
    offset: int = Field(..., description="Pagination offset.")


class StructuredRequirementsDetail(BaseModel):
    """Typed ``structured_requirements`` block returned by the multi-agent workflow.

    The field may be sparse depending on which agent produced it (Gatherer emits
    ``requirements`` + ``user_stories``; earlier stages emit ``epic_name`` only),
    so every field is optional and unknown agent keys are preserved.
    """
    model_config = ConfigDict(extra="allow")

    epic_name: Optional[str] = Field(None, description="Unified theme of extracted stories.")
    version: Optional[int] = Field(None, description="Structured-requirements revision.")
    user_stories: List[UserStoryDetail] = Field(default_factory=list, description="Parsed user stories.")
    requirements: Optional[List[RequirementDetail]] = Field(default_factory=list, description="Requirement entries with nested stories.")


class AuditResultDetail(BaseModel):
    """Typed ``audit_result`` block returned by the compliance auditor node."""
    model_config = ConfigDict(extra="allow")

    id: Optional[str] = Field(None, description="Audit-result UUID string.")
    project_id: Optional[str] = Field(None, description="Owning project UUID string.")
    is_valid: Optional[bool] = Field(None, description="Whether the audited requirements passed.")
    audit_version_reviewed: Optional[int] = Field(None, description="Version reviewed by the auditor.")
    passed_checks: List[str] = Field(default_factory=list, description="Passed compliance checks.")
    failed_checks: List[str] = Field(default_factory=list, description="Failed compliance checks.")
    clarification_questions: List[ClarificationQuestionDetail] = Field(default_factory=list, description="Questions surfaced by the audit.")


class ProcessRequirementsResponse(BaseModel):
    """
    Payload returned by the multi-agent requirements processing endpoint.

    Unknown fields are preserved via ``extra='allow'`` to keep compatibility
    with both the GENERAL_CHAT and the LangGraph workflow response shapes.
    """
    model_config = ConfigDict(extra="allow")

    status: str = Field(..., description="Outcome status: 'completed', 'audit_pending' or 'general_chat'.")
    detected_intent: Optional[str] = Field(None, description="Detected intent (e.g. GENERAL_CHAT, UPDATE_REQUIREMENT).")
    workflow_routing: Optional[Dict[str, Any]] = Field(None, description="Workflow-classification result.")
    structured_requirements: Optional[StructuredRequirementsDetail] = Field(None, description="Structured requirements payload.")
    audit_result: Optional[AuditResultDetail] = Field(None, description="Compliance audit result.")
    prd_markdown: Optional[str] = Field(None, description="Generated PRD markdown, if produced.")
    mermaid_diagram: Optional[str] = Field(None, description="Generated Mermaid diagram source, if produced.")
    message: Optional[str] = Field(None, description="Assistant/agent message text.")
    pending_merge: Optional[bool] = Field(None, description="True when a pending merge action awaits confirmation.")
    pending_action_id: Optional[str] = Field(None, description="Pending-action UUID string awaiting confirmation.")


# ==========================================
# 12. UPLOADED DOCUMENTS (KNOWLEDGE / DOCUMENT STORE)
# ==========================================
# Uploading a document ONLY adds source material to the project's knowledge
# base. It never mutates requirements, user stories, or acceptance criteria.
# The full converted markdown is ALWAYS persisted; token limits apply solely to
# the explicit, user-confirmed extraction path (see routes/documents.py).

class UploadedDocumentResponse(BaseModel):
    """A single uploaded-document record, as serialized by ``serialize_document``.

    ``content_markdown`` is omitted from list/detail responses unless
    ``include_markdown=True`` (the dedicated get-markdown endpoint).
    """
    model_config = ConfigDict(extra="allow")

    id: str = Field(..., description="Document UUID string.")
    project_id: str = Field(..., description="Owning project UUID string.")
    original_filename: str = Field(..., description="Original uploaded file name.")
    original_format: str = Field(..., description="Source format: 'docx' | 'pdf' | 'md' | 'txt'.")
    mime_type: Optional[str] = Field(None, description="Detected MIME type of the upload.")
    content_markdown: Optional[str] = Field(None, description="Canonical converted markdown. Present only when the detail/markdown endpoint is used and the full text is always stored.")
    file_size_bytes: int = Field(0, description="Uploaded file size in bytes.")
    token_count: int = Field(0, description="Markdown token count measured at ingest via count_tokens.")
    status: str = Field("processed", description="'processed' | 'failed'.")
    uploaded_by: str = Field("user", description="Actor that uploaded the document.")
    extraction_status: str = Field("not_extracted", description="'not_extracted' | 'extraction_pending' | 'extraction_applied'.")
    created_at: str = Field("", description="ISO8601 creation timestamp.")
    updated_at: str = Field("", description="ISO8601 last-update timestamp.")


class DocumentMarkdownResponse(BaseModel):
    """Full canonical markdown + metadata returned by the detail/markdown endpoint."""
    model_config = ConfigDict(extra="allow")

    id: str = Field(..., description="Document UUID string.")
    project_id: str = Field(..., description="Owning project UUID string.")
    original_filename: str = Field(..., description="Original uploaded file name.")
    original_format: str = Field(..., description="Source format: 'docx' | 'pdf' | 'md' | 'txt'.")
    content_markdown: str = Field(..., description="FULL canonical converted markdown (never truncated).")
    token_count: int = Field(0, description="Markdown token count measured at ingest.")
    status: str = Field("processed", description="'processed' | 'failed'.")
    extraction_status: str = Field("not_extracted", description="Extraction tracking flag.")


class DocumentProcessResponse(BaseModel):
    """Payload returned by ``POST .../documents/{document_id}/process``.

    The extraction is DRAFT-ONLY: nothing is written to the requirements,
    user_stories, or acceptance_criteria tables. The complete merged draft lives
    in ``pending_action_id``'s ``proposed_changes`` until the user confirms via
    the existing ``/api/confirm-action/{action_id}`` flow.
    """
    status: str = Field(..., description="Outcome: 'draft_ready' | 'failed'.")
    mode: str = Field(..., description="'full' (single pass) | 'chunked' (chunked passes with overlap).")
    chunk_count: int = Field(..., description="Number of gatherer passes executed (1 for full mode).")
    processed_tokens: int = Field(..., description="Total document tokens fed through extraction.")
    pending_action_id: Optional[str] = Field(None, description="Pending-action UUID holding the merged draft, awaiting confirmation.")
    excluded_anything: bool = Field(False, description="True when any content was left out of extraction (never silently).")
    message: str = Field("", description="Human-readable summary including which mode ran and chunk count.")
    document_id: str = Field(..., description="Source document UUID string.")


class DocumentDeleteResponse(BaseModel):
    """Confirmation returned by ``DELETE .../documents/{document_id}``.

    The removal is permanent: the full canonical markdown stored for the
    document is gone. Requirements that were already extracted and confirmed
    from it are NOT affected — they live in the requirement tables and PRD
    version ledger and are untouched by this endpoint.
    """
    status: str = Field(..., description="Outcome, always 'deleted' on success.")
    document_id: str = Field(..., description="UUID of the removed document.")
    project_id: str = Field(..., description="Owning project UUID string.")
    original_filename: str = Field("", description="Name of the removed file.")


# ==========================================
# 10. PRD SECTION SCHEMAS (part-level PRD editing / locking / versioning)
# ==========================================

class PrdSectionUpdate(BaseModel):
    """Request body for editing ONE PRD section (part-by-part editing)."""
    content: str = Field(..., description="Full markdown content for this section (heading line included).")
    base_content: Optional[str] = Field(
        None,
        description="Section text the editor started from. Sent by the UI so the "
        "server can three-way merge the edit onto the latest stored section "
        "(preserving concurrent AI updates outside the edit window).",
    )
    review_status: Optional[str] = Field(
        None, description="Optional new review status: 'draft' | 'satisfied' | 'approved'."
    )
    updated_by: str = Field("user", description="Identifier of who is editing the section.")
    change_summary: Optional[str] = Field(None, description="Optional human-readable change note stored with the version.")


class PrdSectionResponse(BaseModel):
    """One editable, lockable, versioned PART of a project's PRD."""
    model_config = ConfigDict(extra="allow")

    id: str = Field(..., description="Section UUID string.")
    project_id: str = Field(..., description="Owning project UUID string.")
    section_key: str = Field(..., description="Stable key matching the preview part ('title', 'stakeholders', ...).")
    title: str = Field(..., description="Display title of the part.")
    content: str = Field(..., description="Current markdown content of the part (heading included).")
    section_order: int = Field(..., description="Document order used when stitching parts back together.")
    content_source: str = Field("ai", description="'template' | 'ai' | 'human' — who owns the content.")
    ai_generatable: bool = Field(True, description="False => the Architect agent never regenerates this part.")
    review_status: str = Field("draft", description="'draft' | 'satisfied' | 'approved'.")
    is_locked: bool = Field(False, description="When True, edits AND AI regeneration are blocked.")
    locked_by: Optional[str] = Field(None, description="Who locked the part.")
    locked_at: Optional[str] = Field(None, description="ISO8601 lock timestamp.")
    version_number: Optional[int] = Field(None, description="Latest version number in prd_section_versions.")
    created_at: str = Field("", description="ISO8601 creation timestamp.")
    updated_at: str = Field("", description="ISO8601 last-update timestamp.")


class PrdSectionListResponse(BaseModel):
    """All PRD parts of a project, in document order."""
    project_id: str = Field(..., description="Owning project UUID string.")
    sections: List[PrdSectionResponse] = Field(default_factory=list, description="Ordered PRD parts.")


class PrdSectionUpdateResponse(BaseModel):
    """Result of a part-level edit: the saved part plus the re-assembled document."""
    section: PrdSectionResponse = Field(..., description="The saved PRD part.")
    document_markdown: str = Field(..., description="Full PRD markdown stitched from ALL parts after the edit.")


class PrdSectionVersionResponse(BaseModel):
    """One immutable version of a PRD part (append-only history)."""
    model_config = ConfigDict(extra="allow")

    id: str = Field(..., description="Version row UUID string.")
    section_id: str = Field(..., description="Owning PRD section UUID string.")
    version_number: int = Field(..., description="Monotonic per-section version number.")
    content: str = Field(..., description="Snapshot of the section content at this version.")
    changed_by: str = Field("user", description="'user' | 'automated_agent' | 'system'.")
    change_summary: Optional[str] = Field(None, description="Human-readable change note.")
    created_at: str = Field("", description="ISO8601 creation timestamp.")


class PrdSectionRevertResponse(BaseModel):
    """Result of restoring an old version of a PRD part (stored as a NEW version)."""
    section: PrdSectionResponse = Field(..., description="The PRD part after the revert.")
    document_markdown: str = Field(..., description="Full PRD markdown stitched from ALL parts after the revert.")
    restored_from_version: int = Field(..., description="Version number the content was restored from.")


class PrdVersionRestoreResponse(BaseModel):
    """Result of restoring the whole PRD document from a ledger version.

    APPEND-ONLY: the restore is recorded as a NEW version; history is never
    rewritten and locked sections are preserved untouched.
    """
    restored_from_version: int = Field(..., description="Ledger version number the document was restored from.")
    new_version_number: int = Field(..., description="The NEW version number appended for this restore.")
    semver: str = Field("", description="Semantic version of the NEW appended snapshot.")
    document_markdown: str = Field(..., description="Full PRD markdown after the restore (locked sections preserved).")
    restored_sections: int = Field(0, description="Number of unlocked PRD parts whose content was replaced.")
    preserved_locked_sections: int = Field(0, description="Number of locked PRD parts left untouched by the restore.")


# --------------------------------------------------------------------------
# Requirement Traceability Matrix (derived, read-only)
# --------------------------------------------------------------------------
# Requirement Traceability Matrix (derived, read-only)
#
# Links Requirements -> User Stories -> Acceptance Criteria (existing FKs) and
# Requirements <-> PRD sections / diagrams (REQ-/US- code references inside the
# section content and mermaid source). Purely derived — no linkage tables.
# --------------------------------------------------------------------------


class TraceabilityRequirementInfo(BaseModel):
    """The requirement node of a traceability row."""
    model_config = ConfigDict(extra="allow")

    id: str = Field(..., description="Requirement UUID string.")
    requirement_code: str = Field(..., description="Requirement code (e.g. REQ-001).")
    title: str = Field("", description="Requirement title.")
    description: str = Field("", description="Requirement description.")
    epic_name: Optional[str] = Field(None, description="Owning epic name, when any.")
    status: Optional[str] = Field(None, description="Requirement status.")
    version: Optional[int] = Field(None, description="Requirement revision.")
    is_locked: bool = Field(False, description="Whether the requirement is locked.")


class TraceabilityStory(BaseModel):
    """A user story linked to its requirement, with its acceptance criteria."""
    model_config = ConfigDict(extra="allow")

    id: Optional[str] = Field(None, description="Story UUID string.")
    ticket_code: Optional[str] = Field(None, description="Ticket code (e.g. US-001).")
    story_title: Optional[str] = Field(None, description="Story title.")
    as_a: Optional[str] = Field(None, description="User role or persona.")
    i_want_to: Optional[str] = Field(None, description="Requested action/task.")
    so_that: Optional[str] = Field(None, description="Business benefit/outcome.")
    acceptance_criteria: List[str] = Field(default_factory=list, description="Criteria bodies linked to this story.")
    is_locked: bool = Field(False, description="Whether the story is locked.")


class TraceabilityRow(BaseModel):
    """One Requirement Traceability Matrix row: a requirement plus everything that traces to it."""
    model_config = ConfigDict(extra="allow")

    requirement: TraceabilityRequirementInfo = Field(..., description="The requirement node.")
    user_stories: List[TraceabilityStory] = Field(default_factory=list, description="Stories implementing this requirement.")
    prd_sections: List[str] = Field(default_factory=list, description="PRD section keys referencing this requirement (or its stories).")
    diagrams: List[str] = Field(default_factory=list, description="Diagram labels referencing this requirement (e.g. 'PRD v3').")
    traced: bool = Field(False, description="True when the requirement has stories with criteria AND a PRD-section reference.")


class TraceabilityDiagram(BaseModel):
    """A diagram artifact available for traceability."""
    model_config = ConfigDict(extra="allow")

    label: str = Field(..., description="Diagram label (e.g. 'PRD v2').")
    version: int = Field(..., description="PRD version the diagram belongs to.")


class StaleCodeReference(BaseModel):
    """A code referenced by an artifact that does not exist in the project."""
    model_config = ConfigDict(extra="allow")

    code: str = Field(..., description="Referenced code (e.g. REQ-999) with no matching artifact.")
    section_keys: List[str] = Field(default_factory=list, description="PRD sections carrying the stale reference.")
    diagrams: List[str] = Field(default_factory=list, description="Diagrams carrying the stale reference.")


class TraceabilityCoverage(BaseModel):
    """Aggregated coverage + gap report across the whole matrix."""
    model_config = ConfigDict(extra="allow")

    total_requirements: int = Field(0, description="Number of requirements.")
    total_user_stories: int = Field(0, description="Number of active user stories.")
    total_acceptance_criteria: int = Field(0, description="Number of active acceptance criteria.")
    traced_requirements: int = Field(0, description="Requirements fully traced end-to-end.")
    requirements_without_stories: List[str] = Field(default_factory=list, description="Requirement codes with no user story.")
    requirements_without_prd_sections: List[str] = Field(default_factory=list, description="Requirement codes referenced by no PRD section.")
    requirements_without_diagram: List[str] = Field(default_factory=list, description="Requirement codes referenced by no diagram.")
    stories_without_criteria: List[str] = Field(default_factory=list, description="Ticket codes without acceptance criteria.")
    stories_without_prd_sections: List[str] = Field(default_factory=list, description="Ticket codes referenced by no PRD section.")
    stale_section_references: List[StaleCodeReference] = Field(default_factory=list, description="Codes referenced by PRD sections but unknown to the project.")
    stale_diagram_references: List[StaleCodeReference] = Field(default_factory=list, description="Codes referenced by diagrams but unknown to the project.")


class TraceabilityResponse(BaseModel):
    """The complete derived Requirement Traceability Matrix for a project."""
    model_config = ConfigDict(extra="allow")

    project_id: str = Field(..., description="Project UUID string.")
    rows: List[TraceabilityRow] = Field(default_factory=list, description="One matrix row per requirement.")
    diagrams: List[TraceabilityDiagram] = Field(default_factory=list, description="Diagram artifacts considered for tracing.")
    coverage: TraceabilityCoverage = Field(default_factory=TraceabilityCoverage, description="Coverage/gap report.")

