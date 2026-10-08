"""Add dependency graph and scoped regeneration ledger.

Revision ID: 0020_dependency_regeneration
Revises: 0019_operational_governance
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

from app.models import GUID

revision: str = "0020_dependency_regeneration"
down_revision: Union[str, None] = "0019_operational_governance"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    tables = set(inspect(op.get_bind()).get_table_names())
    if "artifact_dependencies" not in tables:
        op.create_table(
            "artifact_dependencies",
            sa.Column("id", GUID(), nullable=False),
            sa.Column("project_id", GUID(), nullable=False),
            sa.Column("source_type", sa.String(50), nullable=False),
            sa.Column("source_key", sa.String(255), nullable=False),
            sa.Column("target_type", sa.String(50), nullable=False),
            sa.Column("target_key", sa.String(255), nullable=False),
            sa.Column("relationship", sa.String(50), nullable=False),
            sa.Column("evidence", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "project_id", "source_type", "source_key", "target_type", "target_key", "relationship",
                name="uq_artifact_dependencies_edge",
            ),
        )
        op.create_index("idx_artifact_dependencies_project_id", "artifact_dependencies", ["project_id"])
        op.create_index("idx_artifact_dependencies_source", "artifact_dependencies", ["project_id", "source_type", "source_key"])
        op.create_index("idx_artifact_dependencies_target", "artifact_dependencies", ["project_id", "target_type", "target_key"])

    if "regeneration_runs" not in tables:
        op.create_table(
            "regeneration_runs",
            sa.Column("id", GUID(), nullable=False),
            sa.Column("project_id", GUID(), nullable=False),
            sa.Column("requested_by", sa.String(255), nullable=False),
            sa.Column("trigger_artifacts", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("plan", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("status", sa.String(30), nullable=False, server_default="planned"),
            sa.Column("regenerated_sections", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("skipped_locked_sections", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("diagram_regenerated", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("idx_regeneration_runs_project_id", "regeneration_runs", ["project_id"])


def downgrade() -> None:
    tables = set(inspect(op.get_bind()).get_table_names())
    if "regeneration_runs" in tables:
        op.drop_index("idx_regeneration_runs_project_id", table_name="regeneration_runs")
        op.drop_table("regeneration_runs")
    if "artifact_dependencies" in tables:
        op.drop_index("idx_artifact_dependencies_target", table_name="artifact_dependencies")
        op.drop_index("idx_artifact_dependencies_source", table_name="artifact_dependencies")
        op.drop_index("idx_artifact_dependencies_project_id", table_name="artifact_dependencies")
        op.drop_table("artifact_dependencies")
