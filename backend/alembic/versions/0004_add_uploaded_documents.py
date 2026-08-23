"""Add uploaded_documents table

Revision ID: 0004_add_uploaded_documents
Revises: 0003_add_project_is_pinned
Create Date: 2026-08-21 22:30:00.000000

Adds the ``uploaded_documents`` table — the project's immutable knowledge /
document store. Uploading a document purely adds source material; it never
writes requirements, user stories, or acceptance criteria. Extracted
requirements are never stored on this table (they live only in a draft
pending_action until the user confirms).

Fresh databases already include the table because ``Base.metadata.create_all``
in revision 0001 uses the current ``DocumentModel``; this migration only creates
the table in databases that were built before the model existed.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

from app.models import GUID  # same platform-independent GUID type as DocumentModel

# revision identifiers, used by Alembic.
revision: str = "0004_add_uploaded_documents"
down_revision: Union[str, None] = "0003_add_project_is_pinned"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _documents_columns(bind) -> set:
    inspector = inspect(bind)
    if "uploaded_documents" not in inspector.get_table_names():
        return set()
    return {col["name"] for col in inspector.get_columns("uploaded_documents")}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "uploaded_documents" in inspector.get_table_names():
        # Already present (e.g. fresh databases created from the current model).
        return

    op.create_table(
        "uploaded_documents",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("project_id", GUID(), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("original_format", sa.String(20), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=True),
        sa.Column("content_markdown", sa.Text(), nullable=False),
        sa.Column("original_storage_url", sa.String(255), nullable=True),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="processed"),
        sa.Column("uploaded_by", sa.String(100), nullable=False, server_default="user"),
        sa.Column("extraction_status", sa.String(30), nullable=False, server_default="not_extracted"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_uploaded_documents_project_id", "uploaded_documents", ["project_id"])


def downgrade() -> None:
    """Drop the uploaded_documents table for rollbacks of pre-document databases."""
    bind = op.get_bind()
    inspector = inspect(bind)
    if "uploaded_documents" not in inspector.get_table_names():
        return
    op.drop_index("ix_uploaded_documents_project_id", table_name="uploaded_documents")
    op.drop_table("uploaded_documents")
