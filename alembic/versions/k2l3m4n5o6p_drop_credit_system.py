"""drop credit system (BYOK pivot)

Revision ID: k2l3m4n5o6p
Revises: j1k2l3m4n5o
Create Date: 2026-05-25 00:00:00.000000

The app moved to BYOK (bring-your-own-Gemini-key) and is free; all paywall,
credit ledger, and Razorpay integration is gone. This drops the seven
tables in reverse-FK order and their enum types.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "k2l3m4n5o6p"
down_revision: Union[str, None] = "j1k2l3m4n5o"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table("promo_redemptions")
    op.drop_index("ix_promo_codes_code", table_name="promo_codes")
    op.drop_table("promo_codes")
    op.drop_index("ix_credit_transactions_razorpay_order_id", table_name="credit_transactions")
    op.drop_index("ix_credit_transactions_user_id", table_name="credit_transactions")
    op.drop_table("credit_transactions")
    op.drop_index("ix_user_time_passes_user_id", table_name="user_time_passes")
    op.drop_table("user_time_passes")
    op.drop_index("ix_user_credits_user_id", table_name="user_credits")
    op.drop_table("user_credits")
    op.drop_table("time_pass_tiers")
    op.drop_table("credit_packs")

    sa.Enum(name="transactiontype").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="promotype").drop(op.get_bind(), checkfirst=True)


def downgrade() -> None:
    raise NotImplementedError(
        "Reintroducing the credit/billing system after BYOK pivot is not supported "
        "by this migration. Revert the BYOK commit set instead."
    )
