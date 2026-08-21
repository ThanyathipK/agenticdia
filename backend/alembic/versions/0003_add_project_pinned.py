"""Add is_pinned to projects for pinned chats

Revision ID: 0003_project_is_pinned
Revises: 0002_requirements_is_locked
Create Date: 2026-08-21 12:00:00.000000

Adds the ``projects.is_pinned`` boolean column so users can pin conversations
(chats/projects) to the top of the sidebar, mirroring chat-app pinning behavior.

Fresh databases already include the column because ``Base.metadata.create_all``
in revision 0001 uses the current ``ProjectModel``; this migration only alters
databases that were created before the column existed.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "0003_add_project_is_pinned"
down_revision: Union[str, None] = "0002_requirements_is_locked"
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

    if "is_pinned" in cols:
        # Already present (e.g. fresh databases created from the current model).
        return

    op.add_column(
        "projects",
        sa.Column(
            "is_pinned",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    """Drop the is_pinned column for rollbacks of pre-pin databases."""
    bind = op.get_bind()
    cols = _projects_columns(bind)

    if "is_pinned" not in cols:
        return

    op.drop_column("projects", "is_pinned")