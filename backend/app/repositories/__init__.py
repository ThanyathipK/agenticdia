"""
Repository layer split per entity.

This package replaces the former ``app.repository`` monolith. Each module owns
a single repository class (or two tightly-coupled ones, e.g. PRD + PRDVersion),
while :mod:`app.repositories.base` provides the shared serializers that remove
hundreds of duplicated hand-written ``model -> dict`` conversions.

``app.repository`` is kept as a thin backwards-compatible shim that
re-exports these classes.
"""

from app.repositories.acceptance_criteria import AcceptanceCriteriaRepository
from app.repositories.audit_result import AuditResultRepository
from app.repositories.clarification_question import ClarificationQuestionRepository
from app.repositories.conversation import ConversationMessageRepository
from app.repositories.document import DocumentRepository
from app.repositories.epic import EpicRepository
from app.repositories.event_log import ArtifactEventLogRepository
from app.repositories.pending_action import PendingActionRepository
from app.repositories.prd import PRDDocumentRepository, PRDVersionRepository
from app.repositories.prd_section import PRDSectionRepository, PRDSectionVersionRepository
from app.repositories.project import ProjectRepository
from app.repositories.requirement import RequirementRepository
from app.repositories.requirement_state import RequirementStateRepository
from app.repositories.semantic_memory import SemanticMemoryRepository
from app.repositories.user_story import UserStoryRepository

__all__ = [
    "ProjectRepository",
    "EpicRepository",
    "RequirementRepository",
    "UserStoryRepository",
    "AcceptanceCriteriaRepository",
    "ClarificationQuestionRepository",
    "AuditResultRepository",
    "PRDDocumentRepository",
    "PRDVersionRepository",
    "PRDSectionRepository",
    "PRDSectionVersionRepository",
    "RequirementStateRepository",
    "ConversationMessageRepository",
    "SemanticMemoryRepository",
    "DocumentRepository",
    "PendingActionRepository",
    "ArtifactEventLogRepository",
]