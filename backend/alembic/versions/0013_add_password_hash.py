"""Add password_hash to users table

Revision ID: 0013_add_password_hash
Revises: 0012_drop_lock_reason
Create Date: 2024-09-12

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
# NOTE: must match the descriptive-slug convention used by every other
# revision (0001_initial_schema ... 0012_drop_lock_reason). Bare numeric ids
# here previously broke the chain: 0013 declared down_revision="0012" while the
# real parent revision is "0012_drop_lock_reason", so Alembic could not build
# its revision map and every `upgrade head` (startup migration) aborted with
# `KeyError: '0012'` — on SQLite and Postgres alike.
revision: str = "0013_add_password_hash"
down_revision: Union[str, None] = "0012_drop_lock_reason"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add password_hash column to users table
    op.add_column('users', sa.Column('password_hash', sa.String(255), nullable=False, server_default=''))


def downgrade() -> None:
    # Remove password_hash column from users table
    op.drop_column('users', 'password_hash')
