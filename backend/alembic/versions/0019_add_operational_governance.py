"""Add immutable audit runs and governed waivers.

Revision ID: 0019_operational_governance
Revises: 0018_project_review_workflow
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

from app.models import GUID

revision: str = "0019_operational_governance"
down_revision: Union[str, None] = "0018_project_review_workflow"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    tables = set(inspect(bind).get_table_names())
    if "audit_runs" not in tables:
        op.create_table(
            "audit_runs",
            sa.Column("id", GUID(), nullable=False),
            sa.Column("project_id", GUID(), nullable=False),
            sa.Column("audit_result_id", GUID(), nullable=True),
            sa.Column("run_number", sa.Integer(), nullable=False),
            sa.Column("audit_version_reviewed", sa.Integer(), nullable=False),
            sa.Column("is_valid", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("verdict", sa.String(50), nullable=False),
            sa.Column("findings", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("passed_checks", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("failed_checks", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("source_references", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("project_context", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("checklist_id", sa.String(100), nullable=False),
            sa.Column("checklist_version", sa.String(30), nullable=False),
            sa.Column("comparison", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["audit_result_id"], ["audit_results.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("project_id", "run_number", name="uq_audit_runs_project_number"),
        )
        op.create_index("idx_audit_runs_project_id", "audit_runs", ["project_id"])
    if "audit_waivers" not in tables:
        op.create_table(
            "audit_waivers",
            sa.Column("id", GUID(), nullable=False),
            sa.Column("project_id", GUID(), nullable=False),
            sa.Column("rule_id", sa.String(100), nullable=False),
            sa.Column("target_requirement_id", sa.String(100), nullable=True),
            sa.Column("reason", sa.Text(), nullable=False),
            sa.Column("compensating_control", sa.Text(), nullable=True),
            sa.Column("owner", sa.String(255), nullable=False),
            sa.Column("approved_by", GUID(), nullable=True),
            sa.Column("approved_by_name", sa.String(255), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("status", sa.String(30), nullable=False, server_default="active"),
            sa.Column("revoked_reason", sa.Text(), nullable=True),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["approved_by"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("idx_audit_waivers_project_id", "audit_waivers", ["project_id"])


def downgrade() -> None:
    tables = set(inspect(op.get_bind()).get_table_names())
    if "audit_waivers" in tables:
        op.drop_index("idx_audit_waivers_project_id", table_name="audit_waivers")
        op.drop_table("audit_waivers")
    if "audit_runs" in tables:
        op.drop_index("idx_audit_runs_project_id", table_name="audit_runs")
        op.drop_table("audit_runs")
