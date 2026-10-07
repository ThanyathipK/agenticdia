"""Scope artifact event logs to their owning project.

Revision ID: 0014_add_event_project_id
Revises: 0013_add_password_hash
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision: str = "0014_add_event_project_id"
down_revision: Union[str, None] = "0013_add_password_hash"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {col["name"] for col in inspect(bind).get_columns("artifact_event_logs")}
    if "project_id" not in columns:
        with op.batch_alter_table("artifact_event_logs") as batch:
            batch.add_column(sa.Column("project_id", sa.Uuid(), nullable=True))
            batch.add_column(sa.Column("user_id", sa.Uuid(), nullable=True))
            batch.create_foreign_key(
                "fk_artifact_event_logs_project_id_projects",
                "projects", ["project_id"], ["id"], ondelete="SET NULL",
            )
            batch.create_foreign_key(
                "fk_artifact_event_logs_user_id_users",
                "users", ["user_id"], ["id"], ondelete="SET NULL",
            )
            batch.create_index("idx_artifact_event_logs_project_id", ["project_id"])
            batch.create_index("idx_artifact_event_logs_user_id", ["user_id"])


def downgrade() -> None:
    bind = op.get_bind()
    columns = {col["name"] for col in inspect(bind).get_columns("artifact_event_logs")}
    if "project_id" in columns:
        with op.batch_alter_table("artifact_event_logs") as batch:
            batch.drop_index("idx_artifact_event_logs_user_id")
            batch.drop_index("idx_artifact_event_logs_project_id")
            batch.drop_constraint("fk_artifact_event_logs_user_id_users", type_="foreignkey")
            batch.drop_constraint("fk_artifact_event_logs_project_id_projects", type_="foreignkey")
            batch.drop_column("user_id")
            batch.drop_column("project_id")
