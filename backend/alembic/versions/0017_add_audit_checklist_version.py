"""Record the checklist identity used by every audit.

Revision ID: 0017_add_audit_checklist_version
Revises: 0016_add_audit_evidence
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision: str = "0017_add_audit_checklist_version"
down_revision: Union[str, None] = "0016_add_audit_evidence"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "audit_results" not in set(inspector.get_table_names()):
        return
    columns = {column["name"] for column in inspector.get_columns("audit_results")}
    if "checklist_id" not in columns:
        op.add_column(
            "audit_results",
            sa.Column("checklist_id", sa.String(length=100), nullable=False, server_default="banking-core"),
        )
    if "checklist_version" not in columns:
        op.add_column(
            "audit_results",
            sa.Column("checklist_version", sa.String(length=30), nullable=False, server_default="1.0.0"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "audit_results" not in set(inspector.get_table_names()):
        return
    columns = {column["name"] for column in inspector.get_columns("audit_results")}
    if "checklist_version" in columns:
        op.drop_column("audit_results", "checklist_version")
    if "checklist_id" in columns:
        op.drop_column("audit_results", "checklist_id")
