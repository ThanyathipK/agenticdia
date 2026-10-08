"""Add governed project review history and approval metadata.

Revision ID: 0018_project_review_workflow
Revises: 0017_add_audit_checklist_version
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from app.models import GUID

revision: str = "0018_project_review_workflow"
down_revision: Union[str, None] = "0017_add_audit_checklist_version"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())
    if "projects" in tables:
        columns = {column["name"] for column in inspector.get_columns("projects")}
        if "last_approved_prd_version" not in columns:
            op.add_column("projects", sa.Column("last_approved_prd_version", sa.Integer(), nullable=True))
        if "last_approved_audit_version" not in columns:
            op.add_column("projects", sa.Column("last_approved_audit_version", sa.Integer(), nullable=True))
        added_approved_by = "last_approved_by" not in columns
        if added_approved_by:
            op.add_column("projects", sa.Column("last_approved_by", GUID(), nullable=True))
            if bind.dialect.name == "postgresql":
                op.create_foreign_key(
                    "fk_projects_last_approved_by_users",
                    "projects", "users", ["last_approved_by"], ["id"], ondelete="SET NULL",
                )
        if "last_approved_at" not in columns:
            op.add_column("projects", sa.Column("last_approved_at", sa.DateTime(timezone=True), nullable=True))
    if "project_review_events" not in tables:
        op.create_table(
            "project_review_events",
            sa.Column("id", GUID(), nullable=False),
            sa.Column("project_id", GUID(), nullable=False),
            sa.Column("from_status", sa.String(50), nullable=False),
            sa.Column("to_status", sa.String(50), nullable=False),
            sa.Column("action", sa.String(50), nullable=False),
            sa.Column("comment", sa.Text(), nullable=True),
            sa.Column("actor_id", GUID(), nullable=True),
            sa.Column("actor_name", sa.String(255), nullable=False),
            sa.Column("actor_role", sa.String(100), nullable=False),
            sa.Column("prd_version_number", sa.Integer(), nullable=True),
            sa.Column("audit_version_reviewed", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("idx_project_review_events_project_id", "project_review_events", ["project_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())
    if "project_review_events" in tables:
        op.drop_index("idx_project_review_events_project_id", table_name="project_review_events")
        op.drop_table("project_review_events")
    if "projects" in tables:
        columns = {column["name"] for column in inspector.get_columns("projects")}
        if "last_approved_by" in columns and bind.dialect.name == "postgresql":
            foreign_keys = {fk.get("name") for fk in inspector.get_foreign_keys("projects")}
            if "fk_projects_last_approved_by_users" in foreign_keys:
                op.drop_constraint("fk_projects_last_approved_by_users", "projects", type_="foreignkey")
        for name in ("last_approved_at", "last_approved_by", "last_approved_audit_version", "last_approved_prd_version"):
            if name in columns:
                op.drop_column("projects", name)
