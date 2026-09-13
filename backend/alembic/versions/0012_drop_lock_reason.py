"""Drop lock_reason column from all artifact tables

Revision ID: 0012_drop_lock_reason
Revises: 0011_prd_version_semver
Create Date: 2026-09-12 00:00:00.000000

Schema audit result (see backend/init.sql for the canonical DDL):

DROP - *.lock_reason                    every artifact table that carried it:
                                           projects, epics, requirements,
                                           user_stories, acceptance_criteria,
                                           clarification_questions,
                                           prd_documents, prd_sections

The column was written by the generic and PRD-section lock endpoints but
NEVER read back by any endpoint, service, or frontend component — the
caller-visible lock metadata is is_locked / locked_by / locked_at (the
frontend does not render the reason anywhere, and no backend logic branches
on its value). Dropping it simplifies the lock cluster and the ERD.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "0012_drop_lock_reason"
down_revision: Union[str, None] = "0011_prd_version_semver"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TARGET_TABLES = [
    "projects",
    "epics",
    "requirements",
    "user_stories",
    "acceptance_criteria",
    "clarification_questions",
    "prd_documents",
    "prd_sections",
]


def _columns(bind, table: str) -> set:
    if table not in inspect(bind).get_table_names():
        return set()
    return {col["name"] for col in inspect(bind).get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    for table in TARGET_TABLES:
        if "lock_reason" in _columns(bind, table):
            op.drop_column(table, "lock_reason")


def downgrade() -> None:
    """Restore lock_reason as a nullable VARCHAR(255) on every artifact table."""
    bind = op.get_bind()
    for table in TARGET_TABLES:
        if "lock_reason" not in _columns(bind, table):
            op.add_column(
                table,
                sa.Column("lock_reason", sa.String(length=255), nullable=True),
            )