import pytest
from datetime import date, datetime, timezone, timedelta
from unittest.mock import patch
from app.models.credit import (
    UserCredit, TimePassTier, PromoCode, CreditTransaction,
    TransactionType, PromoType,
)
from app.services.credit.service import CreditService
from app.exceptions import UsageLimitExceeded

service = CreditService()


@pytest.mark.asyncio
async def test_ensure_user_credit_creates(db_session, test_user):
    uc = await service.ensure_user_credit(db_session, test_user.id)
    assert uc is not None
    assert uc.user_id == test_user.id
    assert uc.balance == 0


@pytest.mark.asyncio
async def test_ensure_user_credit_idempotent(db_session, test_user):
    uc1 = await service.ensure_user_credit(db_session, test_user.id)
    uc2 = await service.ensure_user_credit(db_session, test_user.id)
    assert uc1.id == uc2.id


@pytest.mark.asyncio
async def test_check_and_deduct_daily_free(db_session, test_user):
    await service.ensure_user_credit(db_session, test_user.id)
    with patch("app.services.credit.service.get_settings") as mock_settings:
        mock_settings.return_value.DAILY_FREE_CREDITS = 3
        source = await service.check_and_deduct(db_session, test_user.id, 1)
    assert source == "daily_free"


@pytest.mark.asyncio
async def test_check_and_deduct_purchased(db_session, test_user):
    uc = await service.ensure_user_credit(db_session, test_user.id)
    uc.daily_free_used = 3  # Exhaust free
    uc.balance = 5
    await db_session.commit()

    with patch("app.services.credit.service.get_settings") as mock_settings:
        mock_settings.return_value.DAILY_FREE_CREDITS = 3
        source = await service.check_and_deduct(db_session, test_user.id, 2)
    assert source == "purchased"
    await db_session.refresh(uc)
    assert uc.balance == 4


@pytest.mark.asyncio
async def test_check_and_deduct_time_pass(db_session, test_user):
    await service.ensure_user_credit(db_session, test_user.id)
    tier = TimePassTier(name="Weekly", duration_days=7, price_paise=19900)
    db_session.add(tier)
    await db_session.commit()
    await db_session.refresh(tier)

    await service.activate_time_pass(db_session, test_user.id, tier.id)

    with patch("app.services.credit.service.get_settings") as mock_settings:
        mock_settings.return_value.DAILY_FREE_CREDITS = 3
        source = await service.check_and_deduct(db_session, test_user.id, 3)
    assert source == "time_pass"


@pytest.mark.asyncio
async def test_check_and_deduct_raises_when_exhausted(db_session, test_user):
    uc = await service.ensure_user_credit(db_session, test_user.id)
    uc.daily_free_used = 3
    uc.balance = 0
    await db_session.commit()

    with patch("app.services.credit.service.get_settings") as mock_settings:
        mock_settings.return_value.DAILY_FREE_CREDITS = 3
        with pytest.raises(UsageLimitExceeded):
            await service.check_and_deduct(db_session, test_user.id, 4)


@pytest.mark.asyncio
async def test_add_credits(db_session, test_user):
    await service.ensure_user_credit(db_session, test_user.id)
    uc = await service.add_credits(
        db_session, test_user.id, 10, TransactionType.CREDIT_PURCHASE,
        description="Test purchase",
    )
    assert uc.balance == 10


@pytest.mark.asyncio
async def test_refund_credit(db_session, test_user):
    uc = await service.ensure_user_credit(db_session, test_user.id)
    uc.balance = 5
    await db_session.commit()

    await service.refund_credit(db_session, test_user.id, 99)
    await db_session.refresh(uc)
    assert uc.balance == 6


@pytest.mark.asyncio
async def test_time_pass_stacking(db_session, test_user):
    await service.ensure_user_credit(db_session, test_user.id)
    tier = TimePassTier(name="7-Day", duration_days=7, price_paise=19900)
    db_session.add(tier)
    await db_session.commit()
    await db_session.refresh(tier)

    utp1 = await service.activate_time_pass(db_session, test_user.id, tier.id)
    utp2 = await service.activate_time_pass(db_session, test_user.id, tier.id)

    # Second pass should start at first pass's expiry
    assert utp2.starts_at >= utp1.expires_at - timedelta(seconds=1)
    assert utp2.expires_at > utp1.expires_at


@pytest.mark.asyncio
async def test_daily_reset(db_session, test_user):
    uc = await service.ensure_user_credit(db_session, test_user.id)
    uc.daily_free_used = 3
    uc.daily_free_reset_date = date.today() - timedelta(days=1)
    await db_session.commit()

    service._reset_daily_if_needed(uc)
    assert uc.daily_free_used == 0
    assert uc.daily_free_reset_date == date.today()


@pytest.mark.asyncio
async def test_redeem_promo_credits(db_session, test_user):
    await service.ensure_user_credit(db_session, test_user.id)
    promo = PromoCode(code="FREE5", type=PromoType.CREDITS, value=5)
    db_session.add(promo)
    await db_session.commit()

    result = await service.redeem_promo(db_session, test_user.id, "FREE5")
    assert "5 credits" in result["message"]


@pytest.mark.asyncio
async def test_redeem_promo_duplicate_fails(db_session, test_user):
    await service.ensure_user_credit(db_session, test_user.id)
    promo = PromoCode(code="ONCE", type=PromoType.CREDITS, value=1)
    db_session.add(promo)
    await db_session.commit()

    await service.redeem_promo(db_session, test_user.id, "ONCE")
    with pytest.raises(ValueError, match="already redeemed"):
        await service.redeem_promo(db_session, test_user.id, "ONCE")


@pytest.mark.asyncio
async def test_redeem_promo_inactive_fails(db_session, test_user):
    await service.ensure_user_credit(db_session, test_user.id)
    promo = PromoCode(code="DEAD", type=PromoType.CREDITS, value=1, is_active=False)
    db_session.add(promo)
    await db_session.commit()

    with pytest.raises(ValueError, match="no longer active"):
        await service.redeem_promo(db_session, test_user.id, "DEAD")


@pytest.mark.asyncio
async def test_get_balance(db_session, test_user):
    await service.ensure_user_credit(db_session, test_user.id)
    with patch("app.services.credit.service.get_settings") as mock_settings:
        mock_settings.return_value.DAILY_FREE_CREDITS = 3
        balance = await service.get_balance(db_session, test_user.id)
    assert balance["balance"] == 0
    assert balance["daily_free_remaining"] == 3
    assert balance["daily_free_total"] == 3
    assert balance["has_unlimited"] is False


@pytest.mark.asyncio
async def test_get_transactions(db_session, test_user):
    await service.ensure_user_credit(db_session, test_user.id)
    await service.add_credits(
        db_session, test_user.id, 5, TransactionType.ADMIN_GRANT,
        description="Grant",
    )
    txns, total = await service.get_transactions(db_session, test_user.id)
    assert total >= 1
    assert any(t.amount == 5 for t in txns)
