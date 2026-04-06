"""credit system

Revision ID: e6f7a8b9c0d1
Revises: c4d5e6f7a8b9
Create Date: 2026-02-16 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision: str = "e6f7a8b9c0d1"
down_revision: Union[str, None] = "c4d5e6f7a8b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop old subscription system
    op.drop_table("subscriptions")
    op.drop_table("plans")

    # ── Credit Packs ────────────────────────────────────────────
    op.create_table(
        "credit_packs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("credits", sa.Integer, nullable=False),
        sa.Column("price_paise", sa.Integer, nullable=False),
        sa.Column("is_active", sa.Boolean, default=True),
        sa.Column("sort_order", sa.Integer, default=0),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ── Time Pass Tiers ─────────────────────────────────────────
    op.create_table(
        "time_pass_tiers",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("duration_days", sa.Integer, nullable=False),
        sa.Column("price_paise", sa.Integer, nullable=False),
        sa.Column("is_active", sa.Boolean, default=True),
        sa.Column("sort_order", sa.Integer, default=0),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ── User Credits ────────────────────────────────────────────
    op.create_table(
        "user_credits",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String, sa.ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False),
        sa.Column("balance", sa.Integer, default=0, nullable=False),
        sa.Column("daily_free_used", sa.Integer, default=0, nullable=False),
        sa.Column("daily_free_reset_date", sa.Date, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_user_credits_user_id", "user_credits", ["user_id"])

    # ── User Time Passes ────────────────────────────────────────
    op.create_table(
        "user_time_passes",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tier_id", sa.Integer, sa.ForeignKey("time_pass_tiers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("razorpay_order_id", sa.String, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_user_time_passes_user_id", "user_time_passes", ["user_id"])

    # ── Credit Transactions ─────────────────────────────────────
    transaction_type_enum = sa.Enum(
        "DAILY_FREE", "CREDIT_PURCHASE", "TIME_PASS_PURCHASE",
        "PROMO_CREDIT", "PROMO_TIME_PASS", "ADMIN_GRANT", "REFUND", "CONSUMPTION",
        name="transactiontype",
    )
    op.create_table(
        "credit_transactions",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("amount", sa.Integer, nullable=False),
        sa.Column("type", transaction_type_enum, nullable=False),
        sa.Column("reference_id", sa.String, nullable=True),
        sa.Column("razorpay_order_id", sa.String, nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_credit_transactions_user_id", "credit_transactions", ["user_id"])
    op.create_index("ix_credit_transactions_razorpay_order_id", "credit_transactions", ["razorpay_order_id"])

    # ── Promo Codes ─────────────────────────────────────────────
    promo_type_enum = sa.Enum("CREDITS", "TIME_PASS", name="promotype")
    op.create_table(
        "promo_codes",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("code", sa.String, unique=True, nullable=False),
        sa.Column("type", promo_type_enum, nullable=False),
        sa.Column("value", sa.Integer, nullable=False),
        sa.Column("max_redemptions", sa.Integer, default=0),
        sa.Column("current_redemptions", sa.Integer, default=0),
        sa.Column("is_active", sa.Boolean, default=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_promo_codes_code", "promo_codes", ["code"])

    # ── Promo Redemptions ───────────────────────────────────────
    op.create_table(
        "promo_redemptions",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("promo_code_id", sa.Integer, sa.ForeignKey("promo_codes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "promo_code_id", name="uq_user_promo"),
    )


def downgrade() -> None:
    op.drop_table("promo_redemptions")
    op.drop_table("promo_codes")
    op.drop_table("credit_transactions")
    op.drop_table("user_time_passes")
    op.drop_table("user_credits")
    op.drop_table("time_pass_tiers")
    op.drop_table("credit_packs")

    # Re-create old tables
    op.create_table(
        "plans",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("price", sa.Integer, nullable=False),
        sa.Column("resume_limit_per_month", sa.Integer, nullable=False),
    )
    subscription_status_enum = sa.Enum("ACTIVE", "CANCELLED", "EXPIRED", "PENDING", name="subscriptionstatus")
    op.create_table(
        "subscriptions",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("plan_id", sa.Integer, sa.ForeignKey("plans.id"), nullable=False),
        sa.Column("razorpay_subscription_id", sa.String, nullable=True),
        sa.Column("status", subscription_status_enum, nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resumes_generated_this_period", sa.Integer, default=0),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Drop new enums
    sa.Enum(name="transactiontype").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="promotype").drop(op.get_bind(), checkfirst=True)
