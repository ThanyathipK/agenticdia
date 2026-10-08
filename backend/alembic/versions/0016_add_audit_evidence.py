"""Persist evidence-backed Auditor findings and source references.

Revision ID: 0016_add_audit_evidence
Revises: 0015_restore_lock_reason
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision: str = "0016_add_audit_evidence"
down_revision: Union[str, None] = "0015_restore_lock_reason"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())
    if "audit_results" in tables:
        columns = {c["name"] for c in inspector.get_columns("audit_results")}
        if "findings" not in columns:
            op.add_column("audit_results", sa.Column("findings", sa.JSON(), nullable=False, server_default="[]"))
        if "source_references" not in columns:
            op.add_column("audit_results", sa.Column("source_references", sa.JSON(), nullable=False, server_default="[]"))
        if "verdict" not in columns:
            op.add_column("audit_results", sa.Column("verdict", sa.String(length=50), nullable=False, server_default="needs_clarification"))
        if "project_context" not in columns:
            op.add_column("audit_results", sa.Column("project_context", sa.JSON(), nullable=False, server_default="{}"))
    if "clarification_questions" in tables:
        columns = {c["name"] for c in inspector.get_columns("clarification_questions")}
        if "source_references" not in columns:
            op.add_column("clarification_questions", sa.Column("source_references", sa.JSON(), nullable=False, server_default="[]"))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())
    if "clarification_questions" in tables:
        columns = {c["name"] for c in inspector.get_columns("clarification_questions")}
        if "source_references" in columns:
            op.drop_column("clarification_questions", "source_references")
    if "audit_results" in tables:
        columns = {c["name"] for c in inspector.get_columns("audit_results")}
        if "project_context" in columns:
            op.drop_column("audit_results", "project_context")
        if "verdict" in columns:
            op.drop_column("audit_results", "verdict")
        if "source_references" in columns:
            op.drop_column("audit_results", "source_references")
        if "findings" in columns:
            op.drop_column("audit_results", "findings")
