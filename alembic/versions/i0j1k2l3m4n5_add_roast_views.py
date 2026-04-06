"""add roast_views table

Revision ID: i0j1k2l3m4n5
Revises: h9i0j1k2l3m4
Create Date: 2026-03-02 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision: str = "i0j1k2l3m4n5"
down_revision: Union[str, None] = "h9i0j1k2l3m4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "roast_views",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("roast_id", sa.Integer, sa.ForeignKey("roasts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("share_id", sa.String(16), nullable=False, index=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.Text, nullable=True),
        sa.Column("referer", sa.Text, nullable=True),
        sa.Column("platform", sa.String(50), nullable=True),
        sa.Column("os", sa.String(50), nullable=True),
        sa.Column("browser", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("roast_views")
