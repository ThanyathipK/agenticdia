"""Add status to projects for the dashboard workflow table

Revision ID: 0007_project_status
Revises: 0006_remove_unused_columns
Create Date: 2026-09-08 12:00:00.000000

Adds the ``projects.status`` workflow column ('draft' | 'in_review_hpo' |
'in_review_po' | 'approved' | 'revised') backing the user-editable status
badges on the dashboard projects table.

Fresh databases already include the column because ``Base.metadata.create_all``
in revision 0001 uses the current ``ProjectModel``; this migration only alters
databases that were created before the column existed.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "0007_add_project_status"
down_revision: Union[str, None] = "0006_remove_unused_columns"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _projects_columns(bind) -> set:
    inspector = inspect(bind)
    if "projects" not in inspector.get_table_names():
        return set()
    return {col["name"] for col in inspector.get_columns("projects")}


def upgrade() -> None:
    bind = op.get_bind()
    cols = _projects_columns(bind)

    if "status" in cols:
        # Already present (e.g. fresh databases created from the current model).
        return

    op.add_column(
        "projects",
        sa.Column(
            "status",
            sa.String(50),
            nullable=False,
            server_default="draft",
        ),
    )


def downgrade() -> None:
    """Drop the status column for rollbacks of pre-status databases."""
    bind = op.get_bind()
    cols = _projects_columns(bind)

    if "status" not in cols:
        return

    op.drop_column("projects", "status")
