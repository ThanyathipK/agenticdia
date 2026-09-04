"""Add prd_sections + prd_section_versions tables

Revision ID: 0005_add_prd_sections
Revises: 0004_add_uploaded_documents
Create Date: 2026-09-04 12:00:00.000000

Turns the PRD from a single document blob into a COLLECTION of editable,
lockable, versioned PARTS:

  - ``prd_sections``          one row per PRD part (the nine preview parts:
                              title/cover, stakeholders, version_history,
                              reviews, contents, business_overview,
                              product_scope, tech_ops, appendix) with the same
                              lock columns as every other artifact table plus
                              ownership (content_source / ai_generatable) and
                              review_status gates.
  - ``prd_section_versions``  append-only per-part version history — every
                              content change inserts a new row; nothing is
                              ever overwritten or deleted.

Fresh databases already include both tables because ``Base.metadata.create_all``
in revision 0001 uses the current models; this migration only creates them in
databases that were built before the models existed.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

from app.models import GUID  # same platform-independent GUID type as the other tables

# revision identifiers, used by Alembic.
revision: str = "0005_add_prd_sections"
down_revision: Union[str, None] = "0004_add_uploaded_documents"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_names(bind) -> set:
    return set(inspect(bind).get_table_names())


def upgrade() -> None:
    bind = op.get_bind()
    names = _table_names(bind)

    if "prd_sections" not in names:
        op.create_table(
            "prd_sections",
            sa.Column("id", GUID(), primary_key=True),
            sa.Column("project_id", GUID(), nullable=False),
            sa.Column("section_key", sa.String(100), nullable=False),
            sa.Column("title", sa.String(255), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("section_order", sa.Integer(), nullable=False),
            sa.Column("content_source", sa.String(20), nullable=False, server_default="ai"),
            sa.Column("ai_generatable", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("review_status", sa.String(30), nullable=False, server_default="draft"),
            sa.Column("is_locked", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("locked_by", sa.String(100), nullable=True),
            sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("lock_reason", sa.String(255), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("project_id", "section_key", name="uq_prd_sections_project_key"),
        )
        op.create_index("ix_prd_sections_project_id", "prd_sections", ["project_id"])

    if "prd_section_versions" not in names:
        op.create_table(
            "prd_section_versions",
            sa.Column("id", GUID(), primary_key=True),
            sa.Column("section_id", GUID(), nullable=False),
            sa.Column("version_number", sa.Integer(), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("changed_by", sa.String(100), nullable=False, server_default="user"),
            sa.Column("change_summary", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["section_id"], ["prd_sections.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("section_id", "version_number", name="uq_prd_section_versions_section_version"),
        )
        op.create_index("ix_prd_section_versions_section_id", "prd_section_versions", ["section_id"])


def downgrade() -> None:
    """Drop the PRD section tables for rollbacks of pre-section databases."""
    bind = op.get_bind()
    names = _table_names(bind)
    if "prd_section_versions" in names:
        op.drop_index("ix_prd_section_versions_section_id", table_name="prd_section_versions")
        op.drop_table("prd_section_versions")
    if "prd_sections" in names:
        op.drop_index("ix_prd_sections_project_id", table_name="prd_sections")
        op.drop_table("prd_sections")