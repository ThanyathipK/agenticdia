"""Add persistent background generation jobs.

Revision ID: 0022_add_generation_jobs
Revises: 0021_banking_knowledge_rag
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

from app.models import GUID

revision: str = "0022_add_generation_jobs"
down_revision: Union[str, None] = "0021_banking_knowledge_rag"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if "generation_jobs" in set(inspect(op.get_bind()).get_table_names()):
        return
    op.create_table(
        "generation_jobs",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("project_id", GUID(), nullable=False),
        sa.Column("requested_by_user_id", GUID(), nullable=False),
        sa.Column("job_type", sa.String(30), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="queued"),
        sa.Column("progress_stage", sa.String(100), nullable=False, server_default="queued"),
        sa.Column("request_payload", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("result_payload", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_generation_jobs_project_id", "generation_jobs", ["project_id"])
    op.create_index("idx_generation_jobs_requested_by_user_id", "generation_jobs", ["requested_by_user_id"])
    op.create_index("idx_generation_jobs_status", "generation_jobs", ["status"])
    op.create_index("idx_generation_jobs_project_status", "generation_jobs", ["project_id", "status"])
    op.create_index(
        "uq_generation_jobs_active_project",
        "generation_jobs",
        ["project_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued', 'running', 'cancelling')"),
        sqlite_where=sa.text("status IN ('queued', 'running', 'cancelling')"),
    )


def downgrade() -> None:
    if "generation_jobs" not in set(inspect(op.get_bind()).get_table_names()):
        return
    for name in (
        "uq_generation_jobs_active_project",
        "idx_generation_jobs_project_status",
        "idx_generation_jobs_status",
        "idx_generation_jobs_requested_by_user_id",
        "idx_generation_jobs_project_id",
    ):
        op.drop_index(name, table_name="generation_jobs")
    op.drop_table("generation_jobs")
