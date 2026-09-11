"""Add is_flagged to projects for dashboard ★ flagging

Revision ID: 0009_project_is_flagged
Revises: 0008_semantic_memories
Create Date: 2026-09-11 12:00:00.000000

Adds the ``projects.is_flagged`` boolean column backing the dashboard's
★ flag (star) toggle and "Flagged" filter tab. Flagging is intentionally
independent of ``projects.is_pinned``: a flag marks a project for attention
in the projects overview table and NEVER affects the sidebar's pinned-first
ordering.

Fresh databases already include the column because ``Base.metadata.create_all``
in revision 0001 uses the current ``ProjectModel``; this migration only alters
databases that were created before the column existed.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "0009_project_is_flagged"
down_revision: Union[str, None] = "0008_semantic_memories"
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

    if "is_flagged" in cols:
        # Already present (e.g. fresh databases created from the current model).
        return

    op.add_column(
        "projects",
        sa.Column(
            "is_flagged",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    """Drop the is_flagged column for rollbacks of pre-flag databases."""
    bind = op.get_bind()
    cols = _projects_columns(bind)

    if "is_flagged" not in cols:
        return

    op.drop_column("projects", "is_flagged")