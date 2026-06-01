"""add resume template preferences

Revision ID: l3m4n5o6p7q
Revises: k2l3m4n5o6p
Create Date: 2026-06-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "l3m4n5o6p7q"
down_revision: Union[str, None] = "k2l3m4n5o6p"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "default_resume_template_id",
            sa.String(),
            server_default="jake",
            nullable=False,
        ),
    )
    op.add_column(
        "jobs",
        sa.Column("template_id", sa.String(), server_default="jake", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("jobs", "template_id")
    op.drop_column("users", "default_resume_template_id")
