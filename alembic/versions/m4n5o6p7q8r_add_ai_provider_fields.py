"""add provider fields to user ai settings

Revision ID: m4n5o6p7q8r
Revises: l3m4n5o6p7q
Create Date: 2026-06-06 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "m4n5o6p7q8r"
down_revision: Union[str, None] = "l3m4n5o6p7q"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Existing rows are Gemini configurations — server_default migrates them.
    op.add_column(
        "user_ai_settings",
        sa.Column("provider", sa.String(), server_default="gemini", nullable=False),
    )
    op.add_column(
        "user_ai_settings",
        sa.Column("base_url", sa.String(), nullable=True),
    )
    op.add_column(
        "user_ai_settings",
        sa.Column("reasoning_effort", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("user_ai_settings", "reasoning_effort")
    op.drop_column("user_ai_settings", "base_url")
    op.drop_column("user_ai_settings", "provider")
