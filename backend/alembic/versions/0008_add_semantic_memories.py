"""Add semantic_memories table (Option A memory layer)

Revision ID: 0008_semantic_memories
Revises: 0007_add_project_status
Create Date: 2026-09-10 12:00:00.000000

Adds the project-scoped semantic memory store backing
``app.semantic_memory``: distilled facts extracted from conversations,
embedded with the local LM Studio embedding model and recalled at
prompt-build time by blended cosine-relevance + recency scoring.

Embeddings are stored as a JSON float array (not a pgvector column) so the
same schema works on both Supabase Postgres and the SQLite dev fallback;
per-project volumes are bounded by MEMORY_CANDIDATE_LIMIT in-process scoring.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

from app.models import GUID

# revision identifiers, used by Alembic.
revision: str = "0008_semantic_memories"
down_revision: Union[str, None] = "0007_add_project_status"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(bind, name: str) -> bool:
    return name in inspect(bind).get_table_names()


def _indexes(bind, table: str) -> set:
    inspector = inspect(bind)
    return {ix["name"] for ix in inspector.get_indexes(table)}


def upgrade() -> None:
    bind = op.get_bind()

    if not _table_exists(bind, "semantic_memories"):
        op.create_table(
            "semantic_memories",
            sa.Column("id", GUID(), primary_key=True),
            sa.Column(
                "project_id",
                GUID(),
                sa.ForeignKey("projects.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "kind",
                sa.String(30),
                nullable=False,
                server_default="semantic",
            ),
            sa.Column("content", sa.Text(), nullable=False),
            # Unit-normalised float vector from the LM Studio embedding model,
            # stored as JSON for SQLite/Postgres portability.
            sa.Column("embedding", sa.JSON(), nullable=False),
            sa.Column("embedding_model", sa.String(100), nullable=False, server_default=""),
            sa.Column("source_message_id", GUID(), nullable=True),
            sa.Column("recall_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("last_recalled_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
        )

    if "project_id" not in {
        col["name"] for col in inspect(bind).get_columns("semantic_memories")
    }:
        # Defensive: table existed without the column (should not happen).
        op.add_column("semantic_memories", sa.Column("project_id", GUID(), nullable=False))

    existing_indexes = _indexes(bind, "semantic_memories")
    if "ix_semantic_memories_project_id" not in existing_indexes:
        op.create_index(
            "ix_semantic_memories_project_id",
            "semantic_memories",
            ["project_id"],
        )
    if "idx_semantic_memories_project_created" not in existing_indexes:
        op.create_index(
            "idx_semantic_memories_project_created",
            "semantic_memories",
            ["project_id", "created_at"],
        )
    if "ix_semantic_memories_source_message_id" not in existing_indexes:
        op.create_index(
            "ix_semantic_memories_source_message_id",
            "semantic_memories",
            ["source_message_id"],
        )


def downgrade() -> None:
    """Drop the semantic memory store (memory is derived data — safe to drop)."""
    bind = op.get_bind()
    if _table_exists(bind, "semantic_memories"):
        op.drop_table("semantic_memories")
