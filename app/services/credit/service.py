from datetime import datetime, date, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select, func, or_
from app.models.credit import (
    UserCredit, UserTimePass, CreditTransaction, CreditPack,
    TimePassTier, PromoCode, PromoRedemption,
    TransactionType, PromoType,
)
from app.models.user import User
from app.config import get_settings
from app.exceptions import UsageLimitExceeded
from logging import getLogger

logger = getLogger(__name__)


def _utc_today() -> date:
    """Return today's date in UTC (timezone-independent)."""
    return datetime.now(timezone.utc).date()


class CreditService:

    # ── Balance management ──────────────────────────────────────

    async def ensure_user_credit(
        self, db: AsyncSession, user_id: str, *, for_update: bool = False
    ) -> UserCredit:
        """Get or create the UserCredit row for a user.
        Uses flush (not commit) so callers control transaction boundaries.
        Pass for_update=True to acquire a row-level lock (SELECT ... FOR UPDATE).
        Handles concurrent insert race with IntegrityError retry.
        """
        query = select(UserCredit).where(UserCredit.user_id == user_id)
        if for_update:
            query = query.with_for_update()
        result = await db.execute(query)
        uc = result.scalar_one_or_none()
        if not uc:
            try:
                uc = UserCredit(
                    user_id=user_id,
                    balance=0,
                    daily_free_used=0,
                    daily_free_reset_date=_utc_today(),
                )
                db.add(uc)
                await db.flush()
            except IntegrityError:
                # Concurrent insert won the race — rollback and re-fetch
                await db.rollback()
                query = select(UserCredit).where(UserCredit.user_id == user_id)
                if for_update:
                    query = query.with_for_update()
                result = await db.execute(query)
                uc = result.scalar_one_or_none()
                if not uc:
                    raise  # Should never happen — re-raise if still missing
        return uc

    async def get_balance(self, db: AsyncSession, user_id: str) -> dict:
        """Return full credit status for a user."""
        settings = get_settings()
        uc = await self.ensure_user_credit(db, user_id)
        self._reset_daily_if_needed(uc)
        await db.flush()

        active_pass = await self._get_active_time_pass(db, user_id)
        active_pass_info = None
        if active_pass:
            tier = await db.get(TimePassTier, active_pass.tier_id)
            active_pass_info = {
                "tier_name": tier.name if tier else "Unknown",
                "expires_at": active_pass.expires_at.isoformat(),
            }

        return {
            "balance": uc.balance,
            "daily_free_remaining": max(0, settings.DAILY_FREE_CREDITS - uc.daily_free_used),
            "daily_free_total": settings.DAILY_FREE_CREDITS,
            "active_time_pass": active_pass_info,
            "has_unlimited": active_pass is not None,
        }

    # ── Consumption ─────────────────────────────────────────────

    async def has_credits_available(self, db: AsyncSession, user_id: str) -> bool:
        """Lightweight check — returns True if the user can afford one generation."""
        settings = get_settings()
        uc = await self.ensure_user_credit(db, user_id)
        self._reset_daily_if_needed(uc)
        if await self._get_active_time_pass(db, user_id):
            return True
        if uc.daily_free_used < settings.DAILY_FREE_CREDITS:
            return True
        if uc.balance > 0:
            return True
        return False

    async def check_and_deduct(
        self, db: AsyncSession, user_id: str, job_id: int
    ) -> str:
        """Deduct one credit. Returns source: 'time_pass', 'daily_free', or 'purchased'.
        Raises UsageLimitExceeded if no credits available.
        """
        settings = get_settings()
        uc = await self.ensure_user_credit(db, user_id, for_update=True)
        self._reset_daily_if_needed(uc)

        # Priority 1: Active time pass (unlimited)
        active_pass = await self._get_active_time_pass(db, user_id)
        if active_pass:
            await self._record_transaction(
                db, user_id, -1, TransactionType.CONSUMPTION,
                reference_id=str(job_id),
                description="Resume generation (time pass)",
            )
            await db.commit()
            return "time_pass"

        # Priority 2: Daily free
        if uc.daily_free_used < settings.DAILY_FREE_CREDITS:
            uc.daily_free_used += 1
            await self._record_transaction(
                db, user_id, -1, TransactionType.CONSUMPTION,
                reference_id=str(job_id),
                description="Resume generation (daily free)",
            )
            await db.commit()
            return "daily_free"

        # Priority 3: Purchased credits
        if uc.balance > 0:
            uc.balance -= 1
            await self._record_transaction(
                db, user_id, -1, TransactionType.CONSUMPTION,
                reference_id=str(job_id),
                description="Resume generation (purchased credit)",
            )
            await db.commit()
            return "purchased"

        raise UsageLimitExceeded(
            "No credits available. Purchase a credit pack or time pass to continue."
        )

    async def refund_credit(
        self, db: AsyncSession, user_id: str, job_id: int, source: str = "purchased"
    ) -> None:
        """Refund 1 credit if generation fails after deduction.
        Refunds to the correct bucket based on source.
        Time pass consumption is unlimited, so no refund needed — just record it.
        """
        uc = await self.ensure_user_credit(db, user_id, for_update=True)
        if source == "time_pass":
            # Time pass is unlimited — no balance to restore, just record the reversal
            pass
        elif source == "daily_free":
            uc.daily_free_used = max(0, uc.daily_free_used - 1)
        else:
            uc.balance += 1
        await self._record_transaction(
            db, user_id, 1, TransactionType.REFUND,
            reference_id=str(job_id),
            description=f"Refund: resume generation failed ({source})",
        )
        await db.commit()

    # ── Credit addition ─────────────────────────────────────────

    async def add_credits(
        self, db: AsyncSession, user_id: str, amount: int,
        txn_type: TransactionType, *,
        razorpay_order_id: str | None = None,
        description: str | None = None,
    ) -> UserCredit:
        """Add credits to user balance and record transaction.
        Uses flush so callers (e.g. redeem_promo) can batch into one commit.
        """
        if amount <= 0:
            raise ValueError("Credit amount must be positive")
        uc = await self.ensure_user_credit(db, user_id, for_update=True)
        uc.balance += amount
        await self._record_transaction(
            db, user_id, amount, txn_type,
            razorpay_order_id=razorpay_order_id,
            description=description,
        )
        await db.flush()
        await db.refresh(uc)
        return uc

    # ── Time pass activation ────────────────────────────────────

    async def activate_time_pass(
        self, db: AsyncSession, user_id: str, tier_id: int, *,
        razorpay_order_id: str | None = None,
    ) -> UserTimePass:
        """Activate a time pass. Stacks: new pass starts after the latest existing pass expires.
        Uses flush so callers can batch into one commit.
        """
        tier = await db.get(TimePassTier, tier_id)
        if not tier:
            raise ValueError(f"Time pass tier {tier_id} not found")

        now = datetime.now(timezone.utc)
        # Find the pass with the latest expires_at in the future (including scheduled ones)
        latest_pass = await self._get_latest_future_pass(db, user_id)

        if latest_pass and latest_pass.expires_at.replace(tzinfo=None) > now.replace(tzinfo=None):
            starts_at = latest_pass.expires_at
        else:
            starts_at = now

        expires_at = starts_at + timedelta(days=tier.duration_days)

        utp = UserTimePass(
            user_id=user_id,
            tier_id=tier_id,
            starts_at=starts_at,
            expires_at=expires_at,
            razorpay_order_id=razorpay_order_id,
        )
        db.add(utp)

        await self._record_transaction(
            db, user_id, 0, TransactionType.TIME_PASS_PURCHASE,
            razorpay_order_id=razorpay_order_id,
            description=f"Time pass: {tier.name} ({tier.duration_days} days)",
        )
        await db.flush()
        await db.refresh(utp)
        return utp

    # ── Promo redemption ────────────────────────────────────────

    async def redeem_promo(self, db: AsyncSession, user_id: str, code: str) -> dict:
        """Validate and apply a promo code atomically. Returns result summary.
        Uses row-level locking on PromoCode to prevent concurrent redemption races.
        """
        code = code.strip().upper()

        # Lock the promo code row to prevent concurrent redemption races
        result = await db.execute(
            select(PromoCode).where(PromoCode.code == code).with_for_update()
        )
        promo = result.scalar_one_or_none()
        if not promo:
            raise ValueError("Invalid promo code")
        if not promo.is_active:
            raise ValueError("This promo code is no longer active")
        if promo.expires_at and promo.expires_at.replace(tzinfo=None) < datetime.now(timezone.utc).replace(tzinfo=None):
            raise ValueError("This promo code has expired")
        if promo.max_redemptions > 0 and promo.current_redemptions >= promo.max_redemptions:
            raise ValueError("This promo code has reached its redemption limit")

        # Check if user already redeemed
        existing = await db.execute(
            select(PromoRedemption).where(
                PromoRedemption.user_id == user_id,
                PromoRedemption.promo_code_id == promo.id,
            )
        )
        if existing.scalar_one_or_none():
            raise ValueError("You have already redeemed this promo code")

        # Apply (add_credits/activate_time_pass use flush, not commit)
        if promo.type == PromoType.CREDITS:
            await self.add_credits(
                db, user_id, promo.value, TransactionType.PROMO_CREDIT,
                description=f"Promo code: {promo.code} (+{promo.value} credits)",
            )
            result_msg = f"Added {promo.value} credits"
        elif promo.type == PromoType.TIME_PASS:
            await self.activate_time_pass(db, user_id, promo.value)
            result_msg = "Time pass activated"
        else:
            raise ValueError("Invalid promo type")

        # Record redemption — all flushed changes commit atomically
        redemption = PromoRedemption(user_id=user_id, promo_code_id=promo.id)
        db.add(redemption)
        promo.current_redemptions += 1
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            raise ValueError("You have already redeemed this promo code")

        return {"message": result_msg, "code": promo.code}

    # ── Transaction queries ─────────────────────────────────────

    async def get_transactions(
        self, db: AsyncSession, user_id: str, *, offset: int = 0, limit: int = 20, search: str = ""
    ) -> tuple[list[CreditTransaction], int]:
        """Paginated user transactions with optional ILIKE search."""
        base = select(CreditTransaction).where(CreditTransaction.user_id == user_id)
        if search:
            pattern = f"%{search}%"
            base = base.where(
                or_(
                    CreditTransaction.description.ilike(pattern),
                    CreditTransaction.type.cast(str).ilike(pattern),
                )
            )
        count_result = await db.execute(select(func.count()).select_from(base.subquery()))
        total = count_result.scalar() or 0
        result = await db.execute(
            base.order_by(CreditTransaction.created_at.desc()).offset(offset).limit(limit)
        )
        return list(result.scalars().all()), total

    async def get_all_transactions(
        self, db: AsyncSession, *, offset: int = 0, limit: int = 20, search: str = ""
    ) -> tuple[list, int]:
        """Admin: all transactions with search on description/type/user_id/razorpay_order_id.
        Returns list of (CreditTransaction, user_email, user_name) tuples.
        """
        base = (
            select(CreditTransaction, User.email, User.name)
            .join(User, CreditTransaction.user_id == User.id)
        )
        if search:
            pattern = f"%{search}%"
            base = base.where(
                or_(
                    CreditTransaction.description.ilike(pattern),
                    CreditTransaction.type.cast(str).ilike(pattern),
                    CreditTransaction.user_id.ilike(pattern),
                    CreditTransaction.razorpay_order_id.ilike(pattern),
                    User.email.ilike(pattern),
                )
            )
        count_q = select(func.count()).select_from(base.subquery())
        count_result = await db.execute(count_q)
        total = count_result.scalar() or 0
        result = await db.execute(
            base.order_by(CreditTransaction.created_at.desc()).offset(offset).limit(limit)
        )
        return list(result.all()), total

    # ── Internal helpers ────────────────────────────────────────

    def _reset_daily_if_needed(self, uc: UserCredit) -> None:
        """Reset daily free counter if the date has rolled over (UTC)."""
        today = _utc_today()
        if uc.daily_free_reset_date < today:
            uc.daily_free_used = 0
            uc.daily_free_reset_date = today

    async def _get_latest_future_pass(self, db: AsyncSession, user_id: str) -> UserTimePass | None:
        """Return the time pass with the latest expires_at in the future (including scheduled).
        Used for stacking: new passes chain after the latest one.
        """
        now = datetime.now(timezone.utc)
        result = await db.execute(
            select(UserTimePass)
            .where(
                UserTimePass.user_id == user_id,
                UserTimePass.expires_at > now,
            )
            .order_by(UserTimePass.expires_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _get_active_time_pass(self, db: AsyncSession, user_id: str) -> UserTimePass | None:
        """Return the active time pass with the latest expiry, or None."""
        now = datetime.now(timezone.utc)
        result = await db.execute(
            select(UserTimePass)
            .where(
                UserTimePass.user_id == user_id,
                UserTimePass.starts_at <= now,
                UserTimePass.expires_at > now,
            )
            .order_by(UserTimePass.expires_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _record_transaction(
        self, db: AsyncSession, user_id: str, amount: int,
        txn_type: TransactionType, *,
        reference_id: str | None = None,
        razorpay_order_id: str | None = None,
        description: str | None = None,
    ) -> CreditTransaction:
        txn = CreditTransaction(
            user_id=user_id,
            amount=amount,
            type=txn_type,
            reference_id=reference_id,
            razorpay_order_id=razorpay_order_id,
            description=description,
        )
        db.add(txn)
        return txn
