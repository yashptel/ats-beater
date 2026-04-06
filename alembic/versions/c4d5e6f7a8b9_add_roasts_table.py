"""add roasts table

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2026-02-16 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c4d5e6f7a8b9"
down_revision: Union[str, None] = "b3c4d5e6f7a8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "roasts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("file_hash", sa.String(64), nullable=False),
        sa.Column("extracted_text", sa.Text(), nullable=True),
        sa.Column("roast_data", sa.JSON(), nullable=True),
        sa.Column(
            "status",
            sa.Enum("PENDING", "PROCESSING", "READY", "FAILED", name="roaststatus"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.UniqueConstraint("user_id", "file_hash", name="uq_roasts_user_file"),
    )
    op.create_index("ix_roasts_user_id", "roasts", ["user_id"])
    op.create_index("ix_roasts_file_hash", "roasts", ["file_hash"])


def downgrade() -> None:
    op.drop_index("ix_roasts_file_hash", table_name="roasts")
    op.drop_index("ix_roasts_user_id", table_name="roasts")
    op.drop_table("roasts")
    sa.Enum("PENDING", "PROCESSING", "READY", "FAILED", name="roaststatus").drop(op.get_bind())
