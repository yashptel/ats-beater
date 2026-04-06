"""seed credit packs

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
Create Date: 2026-02-16 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision: str = "f7a8b9c0d1e2"
down_revision: Union[str, None] = "e6f7a8b9c0d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# ── Pricing strategy ────────────────────────────────────────────
#   3 free/day covers 85% of users. Paid packs target the aggressive
#   15% who apply 10-20+/day and can't wait for tomorrow's reset.
#
#   Day Pass :  10 credits @ ₹ 49  → ₹4.90/credit (impulse buy)
#   Sprint   :  30 credits @ ₹ 99  → ₹3.30/credit (week of heavy applying)
#   Job Hunt :  75 credits @ ₹199  → ₹2.65/credit (full 2-week sprint)
#
# "Best value" badge auto-targets lowest price-per-credit → Job Hunt.

packs = sa.table(
    "credit_packs",
    sa.column("name", sa.String),
    sa.column("credits", sa.Integer),
    sa.column("price_paise", sa.Integer),
    sa.column("is_active", sa.Boolean),
    sa.column("sort_order", sa.Integer),
)


def upgrade() -> None:
    op.bulk_insert(packs, [
        {"name": "Day Pass",  "credits": 10, "price_paise":  4900, "is_active": True, "sort_order": 1},
        {"name": "Sprint",   "credits": 30, "price_paise":  9900, "is_active": True, "sort_order": 2},
        {"name": "Job Hunt", "credits": 75, "price_paise": 19900, "is_active": True, "sort_order": 3},
    ])


def downgrade() -> None:
    op.execute("DELETE FROM credit_packs WHERE name IN ('Day Pass', 'Sprint', 'Job Hunt')")
