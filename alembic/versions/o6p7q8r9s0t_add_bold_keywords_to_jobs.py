"""add bold_keywords to jobs

Revision ID: o6p7q8r9s0t
Revises: n5o6p7q8r9s
Create Date: 2026-06-08 11:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "o6p7q8r9s0t"
down_revision: Union[str, None] = "n5o6p7q8r9s"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "jobs",
        sa.Column("bold_keywords", sa.Boolean(), server_default="true", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("jobs", "bold_keywords")
