from sqlalchemy import Column, String, Integer, DateTime, JSON, Text, func, ForeignKey, Boolean, UniqueConstraint
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
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

class EpicModel(Base):
    __tablename__ = "epics"
    
    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    project_id = Column(GUID, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    epic_name = Column(String(255), nullable=False)
    version = Column("current_version", Integer, nullable=False, default=1)
    is_locked = Column(Boolean, nullable=False, default=False)
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
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

class PRDDocumentModel(Base):
    __tablename__ = "prd_documents"
    
    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    project_id = Column(GUID, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    prd_markdown = Column("markdown_content", Text, nullable=False)
    mermaid_diagram = Column("mermaid_graph", Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

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
