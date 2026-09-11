"""Add PRD version metadata columns (change_type / change_summary / changed_sections)

Revision ID: 0010_prd_version_metadata
Revises: 0009_project_is_flagged
Create Date: 2026-09-11 16:00:00.000000

Turns ``prd_versions`` from a bare AI-generation snapshot log into the full
immutable PRD change ledger behind the Version History tab:

  - ``change_type``        'ai' | 'manual' — the origin of the snapshot. Every
                           Generate PRD click OR manual part edit/revert records
                           a row, and the version ALWAYS advances (even when the
                           merged content is byte-identical, e.g. all changed
                           sections were locked).
  - ``change_summary``     human-readable change description shown in the ledger
                           (auto-computed when the caller does not supply one).
  - ``changed_sections``   JSON array of per-section change records computed at
                           snapshot time (created / updated / unchanged /
                           locked_preserved), so the ledger can prove exactly
                           what changed and that locked sections were preserved.

Fresh databases already include the columns because ``Base.metadata.create_all``
in revision 0001 uses the current ``PRDVersionModel``; this migration only adds
them to databases that were created before the model had them.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "0010_prd_version_metadata"
down_revision: Union[str, None] = "0009_project_is_flagged"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _prd_versions_columns(bind) -> set:
    inspector = inspect(bind)
    if "prd_versions" not in inspector.get_table_names():
        return set()
    return {col["name"] for col in inspector.get_columns("prd_versions")}


def upgrade() -> None:
    bind = op.get_bind()
    cols = _prd_versions_columns(bind)

    if "change_type" not in cols:
        op.add_column(
            "prd_versions",
            sa.Column("change_type", sa.String(length=20), nullable=False, server_default="ai"),
        )
    if "change_summary" not in cols:
        op.add_column(
            "prd_versions",
            sa.Column("change_summary", sa.Text(), nullable=True),
        )
    if "changed_sections" not in cols:
        op.add_column(
            "prd_versions",
            sa.Column("changed_sections", sa.JSON(), nullable=True),
        )


def downgrade() -> None:
    """Drop the metadata columns for rollbacks of pre-ledger databases."""
    bind = op.get_bind()
    cols = _prd_versions_columns(bind)

    if "changed_sections" in cols:
        op.drop_column("prd_versions", "changed_sections")
    if "change_summary" in cols:
        op.drop_column("prd_versions", "change_summary")
    if "change_type" in cols:
        op.drop_column("prd_versions", "change_type")