import pytest
from datetime import date, datetime, timezone, timedelta
from app.models.credit import (
    CreditPack, TimePassTier, UserCredit, UserTimePass,
    CreditTransaction, PromoCode, PromoRedemption,
    TransactionType, PromoType,
)


@pytest.mark.asyncio
async def test_create_credit_pack(db_session):
    pack = CreditPack(name="Starter", credits=10, price_paise=9900, sort_order=1)
    db_session.add(pack)
    await db_session.commit()
    await db_session.refresh(pack)
    assert pack.id is not None
    assert pack.name == "Starter"
    assert pack.credits == 10
    assert pack.price_paise == 9900
    assert pack.is_active is True


@pytest.mark.asyncio
async def test_create_time_pass_tier(db_session):
    tier = TimePassTier(name="Weekly", duration_days=7, price_paise=19900)
    db_session.add(tier)
    await db_session.commit()
    await db_session.refresh(tier)
    assert tier.id is not None
    assert tier.duration_days == 7


@pytest.mark.asyncio
async def test_create_user_credit(db_session, test_user):
    uc = UserCredit(
        user_id=test_user.id,
        balance=5,
        daily_free_used=1,
        daily_free_reset_date=date.today(),
    )
    db_session.add(uc)
    await db_session.commit()
    await db_session.refresh(uc)
    assert uc.balance == 5
    assert uc.daily_free_used == 1


@pytest.mark.asyncio
async def test_create_user_time_pass(db_session, test_user):
    tier = TimePassTier(name="Monthly", duration_days=30, price_paise=49900)
    db_session.add(tier)
    await db_session.commit()
    await db_session.refresh(tier)

    now = datetime.now(timezone.utc)
    utp = UserTimePass(
        user_id=test_user.id,
        tier_id=tier.id,
        starts_at=now,
        expires_at=now + timedelta(days=30),
    )
    db_session.add(utp)
    await db_session.commit()
    await db_session.refresh(utp)
    assert utp.id is not None
    # SQLite strips timezone info, so compare naive
    assert utp.expires_at.replace(tzinfo=None) > now.replace(tzinfo=None)


@pytest.mark.asyncio
async def test_create_credit_transaction(db_session, test_user):
    txn = CreditTransaction(
        user_id=test_user.id,
        amount=-1,
        type=TransactionType.CONSUMPTION,
        description="Test transaction",
    )
    db_session.add(txn)
    await db_session.commit()
    await db_session.refresh(txn)
    assert txn.id is not None
    assert txn.amount == -1
    assert txn.type == TransactionType.CONSUMPTION


@pytest.mark.asyncio
async def test_create_promo_code(db_session):
    promo = PromoCode(
        code="TESTPROMO",
        type=PromoType.CREDITS,
        value=5,
        max_redemptions=100,
    )
    db_session.add(promo)
    await db_session.commit()
    await db_session.refresh(promo)
    assert promo.id is not None
    assert promo.code == "TESTPROMO"
    assert promo.current_redemptions == 0


@pytest.mark.asyncio
async def test_create_promo_redemption(db_session, test_user):
    promo = PromoCode(code="REDEEMME", type=PromoType.CREDITS, value=3)
    db_session.add(promo)
    await db_session.commit()
    await db_session.refresh(promo)

    redemption = PromoRedemption(user_id=test_user.id, promo_code_id=promo.id)
    db_session.add(redemption)
    await db_session.commit()
    await db_session.refresh(redemption)
    assert redemption.id is not None
