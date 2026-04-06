"""add share_id to roasts

Revision ID: h9i0j1k2l3m4
Revises: g8h9i0j1k2l3
Create Date: 2026-02-24 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
import secrets

# revision identifiers
revision: str = "h9i0j1k2l3m4"
down_revision: Union[str, None] = "g8h9i0j1k2l3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add column as nullable first for backfill
    op.add_column("roasts", sa.Column("share_id", sa.String(16), nullable=True))

    # Backfill existing rows with unique share_ids
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id FROM roasts WHERE share_id IS NULL")).fetchall()
    for row in rows:
        share_id = secrets.token_urlsafe(6)
        conn.execute(
            sa.text("UPDATE roasts SET share_id = :sid WHERE id = :rid"),
            {"sid": share_id, "rid": row[0]},
        )

    # Now make it non-nullable and add unique index
    op.alter_column("roasts", "share_id", nullable=False)
    op.create_index("ix_roasts_share_id", "roasts", ["share_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_roasts_share_id", table_name="roasts")
    op.drop_column("roasts", "share_id")
