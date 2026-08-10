"""Standardize requirements lock field to is_locked

Revision ID: 0002_requirements_is_locked
Revises: 0001_initial_schema
Create Date: 2026-08-09 20:10:00.000000

Renames the ``requirements.locked`` boolean column to ``requirements.is_locked``
so the requirements table matches every other artifact table (projects, epics,
user_stories, acceptance_criteria, clarification_questions, prd_documents),
which all call the field ``is_locked``.

Previously ``RequirementModel`` was the only model exposing ``locked``, forcing
special-casing in lock_service.py and repository.py. This revision migrates
existing databases without data loss: the boolean value, NOT NULL constraint
and server default are preserved by the column rename. Databases created after
this change already have ``is_locked`` (fresh ``Base.metadata.create_all`` in
revision 0001 uses the current model) and are therefore unaffected. Databases
that never had any boolean lock column on ``requirements`` get ``is_locked``
added so the table matches the model.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
# NOTE: revision ID must fit within alembic_version.version_num (varchar(32)).
revision: str = "0002_requirements_is_locked"
down_revision: Union[str, None] = "0001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _requirements_columns(bind) -> set:
    """Return the set of column names on the requirements table, if it exists."""
    inspector = inspect(bind)
    if "requirements" not in inspector.get_table_names():
        return set()
    return {col["name"] for col in inspector.get_columns("requirements")}


def upgrade() -> None:
    bind = op.get_bind()
    cols = _requirements_columns(bind)

    if "is_locked" in cols:
        # Already renamed (e.g. fresh databases created from the current model).
        return

    if "locked" in cols:
        # Rename preserves the column type, NOT NULL constraint and default.
        op.alter_column("requirements", "locked", new_column_name="is_locked")
    else:
        # Table exists but never had a boolean lock column; add it to match the model.
        op.add_column(
            "requirements",
            sa.Column(
                "is_locked",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
        )


def downgrade() -> None:
    """Restore the legacy ``locked`` column name for rollbacks."""
    bind = op.get_bind()
    cols = _requirements_columns(bind)

    if "is_locked" not in cols or "locked" in cols:
        return

    op.alter_column("requirements", "is_locked", new_column_name="locked")