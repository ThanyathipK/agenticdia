"""Restore optional lock reasons for lockable artifacts.

Revision ID: 0015_restore_lock_reason
Revises: 0014_add_event_project_id
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision: str = "0015_restore_lock_reason"
down_revision: Union[str, None] = "0014_add_event_project_id"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TARGET_TABLES = [
    "projects", "epics", "requirements", "user_stories",
    "acceptance_criteria", "prd_documents", "prd_sections",
]


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    table_names = set(inspector.get_table_names())
    for table in TARGET_TABLES:
        if table not in table_names:
            continue
        columns = {column["name"] for column in inspector.get_columns(table)}
        if "lock_reason" not in columns:
            op.add_column(table, sa.Column("lock_reason", sa.String(length=255), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    table_names = set(inspector.get_table_names())
    for table in TARGET_TABLES:
        if table not in table_names:
            continue
        columns = {column["name"] for column in inspector.get_columns(table)}
        if "lock_reason" in columns:
            op.drop_column(table, "lock_reason")
