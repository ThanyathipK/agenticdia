"""Initial schema baseline

Revision ID: 0001_initial_schema
Revises: 
Create Date: 2026-08-09 19:55:00.000000

This migration establishes the baseline schema for the Agentic AI database.
It replaces the previous ad-hoc startup migrations by:

1. Creating all tables defined in app.models (for fresh databases)
2. Adding missing columns to pre-existing tables (for databases created
   from the older init.sql schema)
3. Dropping the legacy user_stories_ticket_code_key constraint
4. Backfilling audit/lock columns and project_id relationships

Future schema changes must be added as new Alembic revision files.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

from app.database import Base
from app import models  # noqa: F401 - register all models on Base.metadata

# revision identifiers, used by Alembic.
revision: str = "0001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _get_existing_tables(bind) -> set:
    """Return the set of table names currently present in the database."""
    inspector = inspect(bind)
    return set(inspector.get_table_names())


def _get_existing_columns(bind, table: str) -> set:
    """Return the set of column names for a given table."""
    inspector = inspect(bind)
    return {col["name"] for col in inspector.get_columns(table)}


def _add_column_if_missing(bind, table: str, column: str, ddl: str) -> None:
    """Add a column to a table if it does not already exist."""
    if table not in _get_existing_tables(bind):
        return
    if column in _get_existing_columns(bind, table):
        return
    op.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


def upgrade() -> None:
    bind = op.get_bind()

    # ==========================================
    # 1. CREATE ALL TABLES (fresh databases)
    # ==========================================
    # Base.metadata.create_all is idempotent: it only creates tables that
    # do not already exist. This handles both fresh installs and existing
    # databases created from the older init.sql schema.
    Base.metadata.create_all(bind=bind)

    # ==========================================
    # 2. DROP LEGACY CONSTRAINT
    # ==========================================
    # The old schema had a unique constraint on user_stories.ticket_code.
    # The current model uses a composite unique constraint on
    # (project_id, ticket_code) instead.
    if bind.dialect.name == "postgresql":
        op.execute(
            "ALTER TABLE user_stories DROP CONSTRAINT IF EXISTS user_stories_ticket_code_key"
        )

    # ==========================================
    # 3. ADD MISSING COLUMNS TO EXISTING TABLES
    # ==========================================
    # These ALTER TABLE statements bring databases created from the older
    # init.sql schema up to the current model definition.

    # --- user_stories: project_id ---
    _add_column_if_missing(
        bind, "user_stories", "project_id",
        "VARCHAR(36)"
    )

    # --- Audit columns: requirements ---
    _add_column_if_missing(
        bind, "requirements", "status",
        "VARCHAR(50) DEFAULT 'active'"
    )
    _add_column_if_missing(
        bind, "requirements", "last_modified_by",
        "VARCHAR(100) DEFAULT 'automated_agent'"
    )
    _add_column_if_missing(
        bind, "requirements", "change_type",
        "VARCHAR(50) DEFAULT 'created'"
    )

    # --- Audit columns: user_stories ---
    _add_column_if_missing(
        bind, "user_stories", "status",
        "VARCHAR(50) DEFAULT 'active'"
    )
    _add_column_if_missing(
        bind, "user_stories", "version",
        "INTEGER DEFAULT 1"
    )
    _add_column_if_missing(
        bind, "user_stories", "last_modified_by",
        "VARCHAR(100) DEFAULT 'automated_agent'"
    )
    _add_column_if_missing(
        bind, "user_stories", "change_type",
        "VARCHAR(50) DEFAULT 'created'"
    )

    # --- Audit columns: acceptance_criteria ---
    _add_column_if_missing(
        bind, "acceptance_criteria", "status",
        "VARCHAR(50) DEFAULT 'active'"
    )
    _add_column_if_missing(
        bind, "acceptance_criteria", "version",
        "INTEGER DEFAULT 1"
    )
    _add_column_if_missing(
        bind, "acceptance_criteria", "last_modified_by",
        "VARCHAR(100) DEFAULT 'automated_agent'"
    )
    _add_column_if_missing(
        bind, "acceptance_criteria", "change_type",
        "VARCHAR(50) DEFAULT 'created'"
    )

    # --- Lock columns: projects ---
    _add_column_if_missing(
        bind, "projects", "is_locked",
        "BOOLEAN DEFAULT FALSE"
    )
    _add_column_if_missing(
        bind, "projects", "locked_by",
        "VARCHAR(100)"
    )
    _add_column_if_missing(
        bind, "projects", "locked_at",
        "TIMESTAMPTZ"
    )
    _add_column_if_missing(
        bind, "projects", "lock_reason",
        "VARCHAR(255)"
    )

    # --- Lock columns: epics ---
    _add_column_if_missing(
        bind, "epics", "locked_by",
        "VARCHAR(100)"
    )
    _add_column_if_missing(
        bind, "epics", "locked_at",
        "TIMESTAMPTZ"
    )
    _add_column_if_missing(
        bind, "epics", "lock_reason",
        "VARCHAR(255)"
    )

    # --- Lock columns: requirements ---
    _add_column_if_missing(
        bind, "requirements", "locked_by",
        "VARCHAR(100)"
    )
    _add_column_if_missing(
        bind, "requirements", "locked_at",
        "TIMESTAMPTZ"
    )
    _add_column_if_missing(
        bind, "requirements", "lock_reason",
        "VARCHAR(255)"
    )

    # --- Lock columns: user_stories ---
    _add_column_if_missing(
        bind, "user_stories", "is_locked",
        "BOOLEAN DEFAULT FALSE"
    )
    _add_column_if_missing(
        bind, "user_stories", "locked_by",
        "VARCHAR(100)"
    )
    _add_column_if_missing(
        bind, "user_stories", "locked_at",
        "TIMESTAMPTZ"
    )
    _add_column_if_missing(
        bind, "user_stories", "lock_reason",
        "VARCHAR(255)"
    )

    # --- Lock columns: acceptance_criteria ---
    _add_column_if_missing(
        bind, "acceptance_criteria", "is_locked",
        "BOOLEAN DEFAULT FALSE"
    )
    _add_column_if_missing(
        bind, "acceptance_criteria", "locked_by",
        "VARCHAR(100)"
    )
    _add_column_if_missing(
        bind, "acceptance_criteria", "locked_at",
        "TIMESTAMPTZ"
    )
    _add_column_if_missing(
        bind, "acceptance_criteria", "lock_reason",
        "VARCHAR(255)"
    )

    # --- Lock columns: clarification_questions ---
    _add_column_if_missing(
        bind, "clarification_questions", "is_locked",
        "BOOLEAN DEFAULT FALSE"
    )
    _add_column_if_missing(
        bind, "clarification_questions", "locked_by",
        "VARCHAR(100)"
    )
    _add_column_if_missing(
        bind, "clarification_questions", "locked_at",
        "TIMESTAMPTZ"
    )
    _add_column_if_missing(
        bind, "clarification_questions", "lock_reason",
        "VARCHAR(255)"
    )

    # --- Lock columns: prd_documents ---
    _add_column_if_missing(
        bind, "prd_documents", "is_locked",
        "BOOLEAN DEFAULT FALSE"
    )
    _add_column_if_missing(
        bind, "prd_documents", "locked_by",
        "VARCHAR(100)"
    )
    _add_column_if_missing(
        bind, "prd_documents", "locked_at",
        "TIMESTAMPTZ"
    )
    _add_column_if_missing(
        bind, "prd_documents", "lock_reason",
        "VARCHAR(255)"
    )

    # --- conversation_messages: new columns ---
    _add_column_if_missing(
        bind, "conversation_messages", "conversation_id",
        "VARCHAR(36)"
    )
    _add_column_if_missing(
        bind, "conversation_messages", "workflow_state",
        "VARCHAR(50) DEFAULT ''"
    )
    _add_column_if_missing(
        bind, "conversation_messages", "intent",
        "VARCHAR(50) DEFAULT ''"
    )

    # ==========================================
    # 4. BACKFILL DATA
    # ==========================================
    # Backfill audit columns for existing rows.
    existing_tables = _get_existing_tables(bind)

    if "requirements" in existing_tables:
        op.execute(
            "UPDATE requirements SET status = 'active', "
            "last_modified_by = 'automated_agent', change_type = 'unchanged' "
            "WHERE status IS NULL"
        )

    if "user_stories" in existing_tables:
        op.execute(
            "UPDATE user_stories SET status = 'active', version = 1, "
            "last_modified_by = 'automated_agent', change_type = 'unchanged' "
            "WHERE status IS NULL"
        )

    if "acceptance_criteria" in existing_tables:
        op.execute(
            "UPDATE acceptance_criteria SET status = 'active', version = 1, "
            "last_modified_by = 'automated_agent', change_type = 'unchanged' "
            "WHERE status IS NULL"
        )

    # Backfill project_id on user_stories from the parent requirement.
    if "user_stories" in existing_tables and "requirements" in existing_tables:
        user_story_cols = _get_existing_columns(bind, "user_stories")
        if "project_id" in user_story_cols:
            op.execute(
                """
                UPDATE user_stories
                SET project_id = (
                    SELECT r.project_id
                    FROM requirements r
                    WHERE r.id = user_stories.requirement_id
                )
                WHERE project_id IS NULL
                """
            )


def downgrade() -> None:
    """Downgrade is intentionally a no-op for the baseline migration.

    Dropping the entire schema would destroy production data. The baseline
    migration represents the current state of the database; downgrading from
    it is not supported.
    """
    pass