"""add resume_generated status to jobstatus enum

Revision ID: a1b2c3d4e5f6
Revises: e88ebc3778ab
Create Date: 2026-02-15 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'e88ebc3778ab'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE jobstatus ADD VALUE IF NOT EXISTS 'RESUME_GENERATED' AFTER 'GENERATING_RESUME'")


def downgrade() -> None:
    # PostgreSQL doesn't support removing enum values directly.
    # In practice, the value can remain; it won't cause issues.
    pass
