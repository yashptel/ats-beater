import enum
from datetime import datetime, date
from sqlalchemy import (
    Integer, String, Boolean, DateTime, Date, Enum,
    ForeignKey, UniqueConstraint, Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin


class TransactionType(str, enum.Enum):
    DAILY_FREE = "DAILY_FREE"
    CREDIT_PURCHASE = "CREDIT_PURCHASE"
    TIME_PASS_PURCHASE = "TIME_PASS_PURCHASE"
    PROMO_CREDIT = "PROMO_CREDIT"
    PROMO_TIME_PASS = "PROMO_TIME_PASS"
    ADMIN_GRANT = "ADMIN_GRANT"
    REFUND = "REFUND"
    CONSUMPTION = "CONSUMPTION"


class PromoType(str, enum.Enum):
    CREDITS = "CREDITS"
    TIME_PASS = "TIME_PASS"


# ── Admin-defined purchasable packs ─────────────────────────────

class CreditPack(TimestampMixin, Base):
    __tablename__ = "credit_packs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    credits: Mapped[int] = mapped_column(Integer, nullable=False)
    price_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class TimePassTier(TimestampMixin, Base):
    __tablename__ = "time_pass_tiers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    duration_days: Mapped[int] = mapped_column(Integer, nullable=False)
    price_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    user_time_passes = relationship("UserTimePass", back_populates="tier")


# ── Per-user state ──────────────────────────────────────────────

class UserCredit(TimestampMixin, Base):
    __tablename__ = "user_credits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False, index=True
    )
    balance: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    daily_free_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    daily_free_reset_date: Mapped[date] = mapped_column(Date, nullable=False)

    user = relationship("User", back_populates="credit")


class UserTimePass(TimestampMixin, Base):
    __tablename__ = "user_time_passes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tier_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("time_pass_tiers.id", ondelete="RESTRICT"), nullable=False
    )
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    razorpay_order_id: Mapped[str | None] = mapped_column(String, nullable=True)

    tier = relationship("TimePassTier", back_populates="user_time_passes")


# ── Audit ledger ────────────────────────────────────────────────

class CreditTransaction(TimestampMixin, Base):
    __tablename__ = "credit_transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    amount: Mapped[int] = mapped_column(Integer, nullable=False)  # positive = credit, negative = debit
    type: Mapped[TransactionType] = mapped_column(Enum(TransactionType), nullable=False)
    reference_id: Mapped[str | None] = mapped_column(String, nullable=True)  # e.g. job_id
    razorpay_order_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


# ── Promo codes ─────────────────────────────────────────────────

class PromoCode(TimestampMixin, Base):
    __tablename__ = "promo_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    type: Mapped[PromoType] = mapped_column(Enum(PromoType), nullable=False)
    value: Mapped[int] = mapped_column(Integer, nullable=False)  # credits count or tier_id
    max_redemptions: Mapped[int] = mapped_column(Integer, default=0)  # 0 = unlimited
    current_redemptions: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    redemptions = relationship("PromoRedemption", back_populates="promo_code")


class PromoRedemption(TimestampMixin, Base):
    __tablename__ = "promo_redemptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    promo_code_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("promo_codes.id", ondelete="CASCADE"), nullable=False
    )

    promo_code = relationship("PromoCode", back_populates="redemptions")

    __table_args__ = (
        UniqueConstraint("user_id", "promo_code_id", name="uq_user_promo"),
    )
