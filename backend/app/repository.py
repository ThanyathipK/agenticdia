"""
Backwards-compatible shim for the legacy flat repository module.

The 2,756-line monolith that lived here has been split into
``app.repositories`` — one module per entity plus a shared serializer module
(``app.repositories.base``). This file now only re-exports the former public
API so existing imports such as ``from app.repository import ProjectRepository``
keep working without modification.

Prefer importing from ``app.repositories`` (or the per-entity modules) directly.
"""
from app.repositories import (
    AcceptanceCriteriaRepository,
    ArtifactEventLogRepository,
    AuditResultRepository,
    ClarificationQuestionRepository,
    ConversationMessageRepository,
    EpicRepository,
    PendingActionRepository,
    PRDDocumentRepository,
    PRDVersionRepository,
    ProjectRepository,
    RequirementRepository,
    RequirementStateRepository,
    UserStoryRepository,
    VersionHistoryRepository,
)

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
    "VersionHistoryRepository",
    "RequirementStateRepository",
    "ConversationMessageRepository",
    "PendingActionRepository",
    "ArtifactEventLogRepository",
]