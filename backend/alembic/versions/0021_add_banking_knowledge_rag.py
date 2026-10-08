"""Add reusable banking knowledge and retrieval audit trail.

Revision ID: 0021_banking_knowledge_rag
Revises: 0020_dependency_regeneration
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

from app.models import GUID

revision: str = "0021_banking_knowledge_rag"
down_revision: Union[str, None] = "0020_dependency_regeneration"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    tables = set(inspect(op.get_bind()).get_table_names())
    if "banking_knowledge_documents" not in tables:
        op.create_table(
            "banking_knowledge_documents",
            sa.Column("id", GUID(), nullable=False),
            sa.Column("owner_user_id", GUID(), nullable=False),
            sa.Column("title", sa.String(255), nullable=False),
            sa.Column("original_filename", sa.String(255), nullable=False),
            sa.Column("original_format", sa.String(20), nullable=False),
            sa.Column("mime_type", sa.String(100), nullable=True),
            sa.Column("document_type", sa.String(100), nullable=False, server_default="best_practice"),
            sa.Column("jurisdiction", sa.String(100), nullable=False, server_default="global"),
            sa.Column("tags", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("content_markdown", sa.Text(), nullable=False),
            sa.Column("content_checksum", sa.String(64), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("status", sa.String(30), nullable=False, server_default="draft"),
            sa.Column("approved_by", GUID(), nullable=True),
            sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["approved_by"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("owner_user_id", "content_checksum", name="uq_banking_knowledge_owner_checksum"),
        )
        op.create_index("idx_banking_knowledge_documents_owner_user_id", "banking_knowledge_documents", ["owner_user_id"])

    if "banking_knowledge_chunks" not in tables:
        op.create_table(
            "banking_knowledge_chunks",
            sa.Column("id", GUID(), nullable=False),
            sa.Column("document_id", GUID(), nullable=False),
            sa.Column("chunk_index", sa.Integer(), nullable=False),
            sa.Column("heading", sa.String(500), nullable=True),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("token_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("embedding", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("embedding_model", sa.String(100), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["document_id"], ["banking_knowledge_documents.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("document_id", "chunk_index", name="uq_banking_knowledge_chunk_index"),
        )
        op.create_index("idx_banking_knowledge_chunks_document_id", "banking_knowledge_chunks", ["document_id"])

    if "banking_knowledge_retrievals" not in tables:
        op.create_table(
            "banking_knowledge_retrievals",
            sa.Column("id", GUID(), nullable=False),
            sa.Column("project_id", GUID(), nullable=False),
            sa.Column("owner_user_id", GUID(), nullable=False),
            sa.Column("query_text", sa.Text(), nullable=False),
            sa.Column("retrieved_chunks", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("embedding_used", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("idx_banking_knowledge_retrievals_project_id", "banking_knowledge_retrievals", ["project_id"])
        op.create_index("idx_banking_knowledge_retrievals_owner_user_id", "banking_knowledge_retrievals", ["owner_user_id"])


def downgrade() -> None:
    tables = set(inspect(op.get_bind()).get_table_names())
    for table, indexes in (
        ("banking_knowledge_retrievals", ["idx_banking_knowledge_retrievals_owner_user_id", "idx_banking_knowledge_retrievals_project_id"]),
        ("banking_knowledge_chunks", ["idx_banking_knowledge_chunks_document_id"]),
        ("banking_knowledge_documents", ["idx_banking_knowledge_documents_owner_user_id"]),
    ):
        if table in tables:
            for index in indexes:
                op.drop_index(index, table_name=table)
            op.drop_table(table)
