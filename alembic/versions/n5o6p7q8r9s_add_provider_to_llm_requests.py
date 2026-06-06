"""add provider to llm_requests

Revision ID: n5o6p7q8r9s
Revises: m4n5o6p7q8r
Create Date: 2026-06-06 01:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "n5o6p7q8r9s"
down_revision: Union[str, None] = "m4n5o6p7q8r"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Existing logged requests were all Gemini — server_default keeps them readable.
    op.add_column(
        "llm_requests",
        sa.Column("provider", sa.String(), server_default="gemini", nullable=False),
    )
    op.create_index("ix_llm_requests_provider", "llm_requests", ["provider"])


def downgrade() -> None:
    op.drop_index("ix_llm_requests_provider", table_name="llm_requests")
    op.drop_column("llm_requests", "provider")
