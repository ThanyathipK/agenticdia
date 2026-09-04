from sqlalchemy import Column, String, Integer, DateTime, JSON, Text, func, ForeignKey, Boolean, UniqueConstraint, Index
from sqlalchemy.types import TypeDecorator, CHAR
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
import uuid
from app.database import Base

class GUID(TypeDecorator):
    """Platform-independent GUID type.
    Uses PostgreSQL's UUID type, otherwise CHAR(36), keeping a string on other databases.
    """
    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == 'postgresql':
            return dialect.type_descriptor(PG_UUID(as_uuid=True))
        else:
            return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        elif dialect.name == 'postgresql':
            return value
        else:
            if isinstance(value, uuid.UUID):
                return str(value)
            else:
                return str(uuid.UUID(value))

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        else:
            if not isinstance(value, uuid.UUID):
                return uuid.UUID(value)
            return value

class UserModel(Base):
    __tablename__ = "users"
    
    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False)
    full_name = Column(String(255), nullable=False)
    role = Column(String(50), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

class ProjectModel(Base):
    __tablename__ = "projects"
    
    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    user_id = Column(GUID, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    industry_standard = Column(String(100), nullable=False)
    is_pinned = Column(Boolean, nullable=False, default=False)
    is_locked = Column(Boolean, nullable=False, default=False)
    locked_by = Column(String(100), nullable=True)
    locked_at = Column(DateTime(timezone=True), nullable=True)
    lock_reason = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

class EpicModel(Base):
    __tablename__ = "epics"
    
    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    project_id = Column(GUID, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    epic_name = Column(String(255), nullable=False)
    version = Column(Integer, nullable=False, default=1)
    is_locked = Column(Boolean, nullable=False, default=False)
    locked_by = Column(String(100), nullable=True)
    locked_at = Column(DateTime(timezone=True), nullable=True)
    lock_reason = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    status = Column(String(50), nullable=False, default="active", server_default="active")

class RequirementModel(Base):
    __tablename__ = "requirements"
    
    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    project_id = Column(GUID, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    epic_id = Column(GUID, ForeignKey("epics.id", ondelete="CASCADE"), nullable=True, index=True)
    requirement_code = Column(String(50), nullable=False) # e.g. REQ-001
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    priority = Column(String(50), nullable=True)
    status = Column(String(50), nullable=False, default="active", server_default="active")
    version = Column(Integer, nullable=False, default=1, server_default="1")
    is_locked = Column(Boolean, nullable=False, default=False, server_default="false")
    locked_by = Column(String(100), nullable=True)
    locked_at = Column(DateTime(timezone=True), nullable=True)
    lock_reason = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

class UserStoryModel(Base):
    __tablename__ = "user_stories"
    
    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    project_id = Column(GUID, ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True)
    requirement_id = Column(GUID, ForeignKey("requirements.id", ondelete="CASCADE"), nullable=False, index=True)
    ticket_code = Column(String(50), nullable=False)
    story_title = Column(String(255), nullable=False)
    as_a = Column(Text, nullable=False)
    i_want_to = Column(Text, nullable=False)
    so_that = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    status = Column(String(50), nullable=False, default="active", server_default="active")
    version = Column(Integer, nullable=False, default=1, server_default="1")
    last_modified_by = Column(String(100), nullable=False, default="automated_agent", server_default="automated_agent")
    change_type = Column(String(50), nullable=False, default="created", server_default="created")
    is_locked = Column(Boolean, nullable=False, default=False)
    locked_by = Column(String(100), nullable=True)
    locked_at = Column(DateTime(timezone=True), nullable=True)
    lock_reason = Column(String(255), nullable=True)

    __table_args__ = (
        UniqueConstraint("project_id", "ticket_code", name="uq_user_stories_project_id_ticket_code"),
    )

class AcceptanceCriteriaModel(Base):
    __tablename__ = "acceptance_criteria"
    
    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    user_story_id = Column(GUID, ForeignKey("user_stories.id", ondelete="CASCADE"), nullable=False, index=True)
    criteria_text = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    status = Column(String(50), nullable=False, default="active", server_default="active")
    version = Column(Integer, nullable=False, default=1, server_default="1")
    last_modified_by = Column(String(100), nullable=False, default="automated_agent", server_default="automated_agent")
    change_type = Column(String(50), nullable=False, default="created", server_default="created")
    is_locked = Column(Boolean, nullable=False, default=False)
    locked_by = Column(String(100), nullable=True)
    locked_at = Column(DateTime(timezone=True), nullable=True)
    lock_reason = Column(String(255), nullable=True)

class AuditResultModel(Base):
    __tablename__ = "audit_results"
    
    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    requirement_id = Column(GUID, ForeignKey("requirements.id", ondelete="CASCADE"), nullable=False, index=True)
    audit_version_reviewed = Column("version_reviewed", Integer, nullable=False)
    is_valid = Column(Boolean, nullable=False, default=False)
    passed_checks = Column(JSON, nullable=False, default=list)
    failed_checks = Column(JSON, nullable=False, default=list)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

class ClarificationQuestionModel(Base):
    __tablename__ = "clarification_questions"
    
    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    audit_result_id = Column(GUID, ForeignKey("audit_results.id", ondelete="CASCADE"), nullable=False, index=True)
    checklist_category = Column(String(100), nullable=False)
    target_user_story_id = Column(GUID, ForeignKey("user_stories.id", ondelete="SET NULL"), nullable=True, index=True)
    question_text = Column(Text, nullable=False)
    user_answer = Column(Text, nullable=True)
    is_resolved = Column(Boolean, nullable=False, default=False)
    is_locked = Column(Boolean, nullable=False, default=False)
    locked_by = Column(String(100), nullable=True)
    locked_at = Column(DateTime(timezone=True), nullable=True)
    lock_reason = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

class PRDDocumentModel(Base):
    __tablename__ = "prd_documents"

    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    project_id = Column(GUID, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    prd_markdown = Column("markdown_content", Text, nullable=False)
    mermaid_diagram = Column("mermaid_graph", Text, nullable=True)
    is_locked = Column(Boolean, nullable=False, default=False)
    locked_by = Column(String(100), nullable=True)
    locked_at = Column(DateTime(timezone=True), nullable=True)
    lock_reason = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class PRDVersionModel(Base):
    """
    Dedicated immutable PRD version repository.
    Each PRD generation creates a new version record.
    Never overwrites previous versions.
    """
    __tablename__ = "prd_versions"

    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    project_id = Column(GUID, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    version_number = Column(Integer, nullable=False)
    generated_prd = Column(Text, nullable=False)
    generated_diagram = Column(Text, nullable=True)
    generated_by = Column(String(100), nullable=False, default="automated_agent")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class PRDSectionModel(Base):
    """
    One editable, lockable, versioned PART of the project's PRD document.

    The PRD is no longer only a single ``markdown_content`` blob: each part
    (cover, stakeholders, version history, reviews, contents, business
    overview, product scope, tech ops, appendix) lives in its own row so it
    can be edited part-by-part in the preview, locked individually, and
    excluded from AI regeneration.

    ``content`` stores the CURRENT markdown fragment of the section (heading
    line included, matching the frontend ``parsePRDToSections`` output). The
    full document is assembled by stitching rows in ``section_order``.

    Lock columns follow the exact same pattern as every other artifact table
    so ``LockService`` can manage ``prd_section`` generically.
    """
    __tablename__ = "prd_sections"

    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    project_id = Column(GUID, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    section_key = Column(String(100), nullable=False)
    title = Column(String(255), nullable=False)
    content = Column(Text, nullable=False, default="")
    section_order = Column(Integer, nullable=False, default=0)
    # Who owns the content: 'template' | 'ai' | 'human'
    content_source = Column(String(20), nullable=False, default="ai", server_default="ai")
    # When False the Architect agent NEVER regenerates this section.
    ai_generatable = Column(Boolean, nullable=False, default=True)
    # 'draft' | 'satisfied' | 'approved' — the "user satisfies it" gate.
    review_status = Column(String(30), nullable=False, default="draft", server_default="draft")
    is_locked = Column(Boolean, nullable=False, default=False)
    locked_by = Column(String(100), nullable=True)
    locked_at = Column(DateTime(timezone=True), nullable=True)
    lock_reason = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("project_id", "section_key", name="uq_prd_sections_project_key"),
    )


class PRDSectionVersionModel(Base):
    """
    Append-only per-section version history. A new row is inserted on EVERY
    content change (manual edit, revert, or an AI regeneration that actually
    changed the content) — the current text is materialized on
    ``prd_sections.content`` for fast reads, but it is never modified without
    a corresponding history row here. Nothing is ever overwritten or deleted.
    """
    __tablename__ = "prd_section_versions"

    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    section_id = Column(GUID, ForeignKey("prd_sections.id", ondelete="CASCADE"), nullable=False, index=True)
    version_number = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    changed_by = Column(String(100), nullable=False, default="user", server_default="user")
    change_summary = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("section_id", "version_number", name="uq_prd_section_versions_section_version"),
    )

class VersionHistoryModel(Base):
    __tablename__ = "version_history"
    
    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    project_id = Column(GUID, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    requirement_id = Column(GUID, ForeignKey("requirements.id", ondelete="CASCADE"), nullable=False, index=True)
    version = Column("version_number", Integer, nullable=False)
    changed_by_user_id = Column(GUID, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    description = Column("change_description", Text, nullable=False)
    requirements_snapshot = Column("state_snapshot", JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    @property
    def timestamp(self) -> str:
        return self.created_at.isoformat() if self.created_at else ""

    @timestamp.setter
    def timestamp(self, value):
        pass

    @property
    def author(self) -> str:
        return "Automated BA Agent"

    @author.setter
    def author(self, value):
        pass

class RequirementStateModel(Base):
    """
    SQLAlchemy model for centralizing the RequirementState in Supabase.
    Isolates agent fields and persists specifications cleanly.
    """
    __tablename__ = "requirement_states"
    
    project_id = Column(GUID, ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True, index=True)
    project_name = Column(String(255), nullable=False, default="Default Project")
    requirements = Column(JSON, nullable=False, default=dict)
    business_goals = Column(JSON, nullable=False, default=list)
    actors = Column(JSON, nullable=False, default=list)
    user_stories = Column(JSON, nullable=False, default=list)
    acceptance_criteria = Column(JSON, nullable=False, default=list)
    clarification_questions = Column(JSON, nullable=False, default=list)
    validation_status = Column(String(50), nullable=False, default="pending")
    generated_prd = Column(Text, nullable=False, default="")
    generated_diagrams = Column(Text, nullable=False, default="")
    current_workflow_state = Column(String(50), nullable=False, default="gatherer_node")
    version_number = Column(Integer, nullable=False, default=1)
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

class ConversationMessageModel(Base):
    """
    SQLAlchemy model for persisting conversation messages per project.
    Uses a dedicated table independent from requirement_states.
    """
    __tablename__ = "conversation_messages"
    
    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    conversation_id = Column(GUID, nullable=True, index=True, default=uuid.uuid4)
    project_id = Column(GUID, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(50), nullable=False)
    message = Column(Text, nullable=False)
    workflow_state = Column(String(50), nullable=True, default="")
    intent = Column(String(50), nullable=True, default="")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

class PendingActionModel(Base):
    __tablename__ = "pending_actions"
    
    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    project_id = Column(GUID, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    action_type = Column(String(50), nullable=False)
    target_requirement_id = Column(String(50), nullable=True)
    original_user_message = Column(Text, nullable=False)
    proposed_changes = Column(JSON, nullable=False, default=dict)
    affected_user_story_ids = Column(JSON, nullable=False, default=list)
    affected_acceptance_criteria_ids = Column(JSON, nullable=False, default=list)
    workflow_stage = Column(String(100), nullable=False)
    status = Column(String(50), nullable=False, default="WAITING_CONFIRMATION")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=False)


class DocumentModel(Base):
    """
    Uploaded project document — the immutable knowledge/document store.

    Uploading a document ONLY adds source material to the knowledge base: it
    never mutates requirements, user stories, or acceptance criteria. The full
    converted markdown is ALWAYS persisted (no token truncation at save time —
    token limits apply only to the explicit LLM extraction path). Extracted
    requirements are never stored here; they live only in the draft merge state
    (a pending_action) until the user confirms.
    """
    __tablename__ = "uploaded_documents"

    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    project_id = Column(GUID, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    original_filename = Column(String(255), nullable=False)
    original_format = Column(String(20), nullable=False)  # 'docx' | 'pdf' | 'md' | 'txt'
    mime_type = Column(String(100), nullable=True)
    content_markdown = Column(Text, nullable=False, default="")  # canonical converted markdown, ALWAYS full
    original_storage_url = Column(String(255), nullable=True)  # reserved for object storage later
    file_size_bytes = Column(Integer, nullable=False, default=0)
    token_count = Column(Integer, nullable=False, default=0)  # measured at ingest via count_tokens
    status = Column(String(20), nullable=False, default="processed")  # 'processed' | 'failed'
    uploaded_by = Column(String(100), nullable=False, default="user", server_default="user")
    # Tracks whether the user has explicitly triggered extraction for this
    # document: 'not_extracted' | 'extraction_pending' | 'extraction_applied'.
    # Extracted requirements are NEVER stored on this table.
    extraction_status = Column(String(30), nullable=False, default="not_extracted", server_default="not_extracted")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class ArtifactEventLogModel(Base):
    """
    Append-only immutable event log for tracking all artifact modifications.
    Stores historical records of CREATE, UPDATE, DELETE, ARCHIVE, LOCK, UNLOCK events.
    Never overwrites or deletes existing records.
    No foreign keys — purely historical traceability, not production data.
    """
    __tablename__ = "artifact_event_logs"

    event_id = Column(GUID, primary_key=True, default=uuid.uuid4)
    artifact_type = Column(String(50), nullable=False, index=True)
    artifact_id = Column(String(36), nullable=False, index=True)
    action = Column(String(20), nullable=False, index=True)
    old_value = Column(JSON, nullable=True)
    new_value = Column(JSON, nullable=True)
    performed_by = Column(String(100), nullable=False, default="automated_agent")
    timestamp = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # Composite index for querying events by artifact
    __table_args__ = (
        Index("idx_artifact_event_logs_artifact", "artifact_type", "artifact_id"),
        Index("idx_artifact_event_logs_timestamp", "timestamp"),
    )