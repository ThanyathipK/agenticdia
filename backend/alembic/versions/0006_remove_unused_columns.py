"""Remove dead columns and reconcile column-name drift with init.sql

Revision ID: 0006_remove_unused_columns
Revises: 0005_add_prd_sections
Create Date: 2026-09-06 00:00:00.000000

Schema audit result (see backend/init.sql for the canonical DDL):

DROP  - version_history                    whole table: never written at
                                            runtime and never read by any
                                            endpoint; the immutable PRD
                                            ledger (prd_versions) is the
                                            wired replacement
      - requirements.priority              never set by any LLM/agent flow
                                            or the manual UI
      - conversation_messages.conversation_id
                                            never passed by any caller (each
                                            save generated a fresh UUID and
                                            per-message "conversations" were
                                            never grouped or queried)
      - uploaded_documents.original_storage_url
                                            reserved placeholder, never
                                            populated by the upload route
      - prd_versions.generated_diagram     always written as ''; the real
                                            diagram lives in
                                            prd_documents.mermaid_graph

RENAME to align the real database with backend/init.sql (same column,
clearer name used by the Schema Explorer / ERD):
      - audit_results.version_reviewed        -> audit_version_reviewed
      - prd_documents.markdown_content        -> prd_markdown
      - prd_documents.mermaid_graph           -> mermaid_diagram

The renames only apply to databases that were provisioned through
SQLAlchemy metadata (create_all); databases created from init.sql already
carry the target names and are left untouched.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "0006_remove_unused_columns"
down_revision: Union[str, None] = "0005_add_prd_sections"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(bind, table: str) -> bool:
    return table in inspect(bind).get_table_names()


def _columns(bind, table: str) -> set:
    if not _has_table(bind, table):
        return set()
    return {col["name"] for col in inspect(bind).get_columns(table)}


def _drop_index_if_exists(index_name: str) -> None:
    op.execute(f"DROP INDEX IF EXISTS {index_name}")


def _rename_column_if_exists(table: str, old_name: str, new_name: str) -> None:
    """Rename a column across Postgres and SQLite (both support RENAME COLUMN)."""
    bind = op.get_bind()
    cols = _columns(bind, table)
    if old_name in cols and new_name not in cols:
        op.alter_column(table, old_name, new_column_name=new_name)


def _drop_column_if_exists(table: str, column: str) -> None:
    """Drop a column on Postgres / SQLite when it is actually present.

    SQLite requires the column to not be referenced by an index; callers
    must drop dependent indexes *before* invoking this helper.
    """
    bind = op.get_bind()
    cols = _columns(bind, table)
    if column in cols:
        op.drop_column(table, column)


def upgrade() -> None:
    bind = op.get_bind()

    # ------------------------------------------------------------------
    # 1. RENAME drifted columns -> match backend/init.sql
    # ------------------------------------------------------------------
    _rename_column_if_exists("audit_results", "version_reviewed", "audit_version_reviewed")
    _rename_column_if_exists("prd_documents", "markdown_content", "prd_markdown")
    _rename_column_if_exists("prd_documents", "mermaid_graph", "mermaid_diagram")

    # ------------------------------------------------------------------
    # 2. DROP unused columns
    # ------------------------------------------------------------------
    # conversation_messages.conversation_id: drop both the explicit init.sql
    # index and the auto-generated SQLAlchemy index first.
    _drop_index_if_exists("idx_conversation_messages_conversation_id")
    _drop_index_if_exists("ix_conversation_messages_conversation_id")
    _drop_column_if_exists("conversation_messages", "conversation_id")

    _drop_column_if_exists("requirements", "priority")
    _drop_column_if_exists("uploaded_documents", "original_storage_url")
    _drop_column_if_exists("prd_versions", "generated_diagram")

    # ------------------------------------------------------------------
    # 3. DROP the dead version_history table (with its trigger on Postgres)
    # ------------------------------------------------------------------
    if _has_table(bind, "version_history"):
        if bind.dialect.name == "postgresql":
            op.execute("DROP TRIGGER IF EXISTS handle_updated_at_version_history ON version_history")
        op.drop_table("version_history")


def downgrade() -> None:
    """Re-create the removed schema elements.

    This is a best-effort reconstruction for local rollback; a full data
    restore (the dropped table's rows) is intentionally NOT attempted.
    """
    bind = op.get_bind()

    # ------------------------------------------------------------------
    # 1. Restore prd_versions.generated_diagram
    # ------------------------------------------------------------------
    if "generated_diagram" not in _columns(bind, "prd_versions"):
        op.add_column("prd_versions", sa.Column("generated_diagram", sa.Text(), nullable=True))

    # ------------------------------------------------------------------
    # 2. Restore uploaded_documents.original_storage_url
    # ------------------------------------------------------------------
    if "original_storage_url" not in _columns(bind, "uploaded_documents"):
        op.add_column(
            "uploaded_documents",
            sa.Column("original_storage_url", sa.String(length=255), nullable=True),
        )

    # ------------------------------------------------------------------
    # 3. Restore requirements.priority
    # ------------------------------------------------------------------
    if "priority" not in _columns(bind, "requirements"):
        op.add_column("requirements", sa.Column("priority", sa.String(length=50), nullable=True))

    # ------------------------------------------------------------------
    # 4. Restore conversation_messages.conversation_id + index
    # ------------------------------------------------------------------
    if "conversation_id" not in _columns(bind, "conversation_messages"):
        op.add_column("conversation_messages", sa.Column("conversation_id", sa.UUID(), nullable=True))
        op.create_index("idx_conversation_messages_conversation_id", "conversation_messages", ["conversation_id"])

    # ------------------------------------------------------------------
    # 5. Re-create version_history + trigger (Postgres)
    # ------------------------------------------------------------------
    if not _has_table(bind, "version_history"):
        op.create_table(
            "version_history",
            sa.Column("id", sa.UUID(), primary_key=True),
            sa.Column("project_id", sa.UUID(), nullable=False),
            sa.Column("requirement_id", sa.UUID(), nullable=False),
            sa.Column("version_number", sa.Integer(), nullable=False),
            sa.Column("changed_by_user_id", sa.UUID(), nullable=False),
            sa.Column("change_description", sa.Text(), nullable=False),
            sa.Column("state_snapshot", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["requirement_id"], ["requirements.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["changed_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        )
        if bind.dialect.name == "postgresql":
            op.execute(
                "CREATE TRIGGER handle_updated_at_version_history "
                "BEFORE UPDATE ON version_history "
                "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
            )

    # ------------------------------------------------------------------
    # 6. Rename columns back to the SQLAlchemy-era names
    # ------------------------------------------------------------------
    _rename_column_if_exists("audit_results", "audit_version_reviewed", "version_reviewed")
    _rename_column_if_exists("prd_documents", "prd_markdown", "markdown_content")
    _rename_column_if_exists("prd_documents", "mermaid_diagram", "mermaid_graph")