"""Add prd_versions.semver (Semantic Version column)

Revision ID: 0011_prd_version_semver
Revises: 0010_prd_version_metadata
Create Date: 2026-09-11 18:00:00.000000

Each PRD snapshot now carries a Semantic Version (MAJOR.MINOR.PATCH)
derived from its per-section change records:

  - MAJOR  structural change — any section created or removed
  - MINOR  AI regeneration that updated section content
  - PATCH  manual part edit / revert, or an always-advancing snapshot with no
           content change (e.g. every changed part was locked)

The first snapshot of a project becomes 1.0.0. Existing rows are backfilled
from their version_number: 1.0.0 for the first row, then PATCH-bumped per
subsequent row (the historical change details were not recorded before
revision 0010, so a MINOR/MAJOR reclassification is impossible — PATCH is the
conservative choice).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "0011_prd_version_semver"
down_revision: Union[str, None] = "0010_prd_version_metadata"
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

    if "semver" not in cols:
        op.add_column(
            "prd_versions",
            sa.Column("semver", sa.String(length=20), nullable=False, server_default="1.0.0"),
        )
        # Backfill existing rows oldest-first: v1 -> 1.0.0, each later row
        # PATCH-bumped from its predecessor (details unknown -> PATCH).
        if "version_number" in cols:
            rows = bind.execute(sa.text(
                "SELECT id FROM prd_versions ORDER BY version_number ASC"
            )).fetchall()
            major, minor, patch = 1, 0, 0
            first = True
            for (row_id,) in rows:
                if first:
                    first = False
                else:
                    patch += 1
                bind.execute(
                    sa.text("UPDATE prd_versions SET semver = :sv WHERE id = :id"),
                    {"sv": f"{major}.{minor}.{patch}", "id": row_id},
                )


def downgrade() -> None:
    cols = _prd_versions_columns(op.get_bind())
    if "semver" in cols:
        op.drop_column("prd_versions", "semver")
