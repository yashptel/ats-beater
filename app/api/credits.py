import math
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database.session import get_db
from app.models.user import User
from app.models.credit import CreditPack, TimePassTier
from app.dependencies import get_current_user
from app.services.credit.service import CreditService
from app.schemas.credit import RedeemPromoRequest, CreditBalanceResponse

router = APIRouter(prefix="/credits", tags=["credits"])
credit_service = CreditService()


@router.get("/packs")
async def list_packs(db: AsyncSession = Depends(get_db)):
    """Public: list active credit packs and time passes."""
    packs_result = await db.execute(
        select(CreditPack)
        .where(CreditPack.is_active == True)
        .order_by(CreditPack.sort_order, CreditPack.price_paise)
    )
    tiers_result = await db.execute(
        select(TimePassTier)
        .where(TimePassTier.is_active == True)
        .order_by(TimePassTier.sort_order, TimePassTier.price_paise)
    )
    packs = packs_result.scalars().all()
    tiers = tiers_result.scalars().all()
    return {
        "credit_packs": [
            {
                "id": p.id, "name": p.name, "credits": p.credits,
                "price_paise": p.price_paise, "sort_order": p.sort_order,
            }
            for p in packs
        ],
        "time_passes": [
            {
                "id": t.id, "name": t.name, "duration_days": t.duration_days,
                "price_paise": t.price_paise, "sort_order": t.sort_order,
            }
            for t in tiers
        ],
    }


@router.get("/me")
async def get_balance(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Current user's credit balance and status."""
    return await credit_service.get_balance(db, current_user.id)


@router.get("/history")
async def get_history(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    search: str = Query("", max_length=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Paginated transaction history for current user."""
    offset = (page - 1) * limit
    txns, total = await credit_service.get_transactions(
        db, current_user.id, offset=offset, limit=limit, search=search
    )
    return {
        "items": [
            {
                "id": t.id, "amount": t.amount, "type": t.type.value,
                "reference_id": t.reference_id,
                "razorpay_order_id": t.razorpay_order_id,
                "description": t.description,
                "created_at": t.created_at.isoformat(),
            }
            for t in txns
        ],
        "total": total,
        "page": page,
        "pages": math.ceil(total / limit) if total > 0 else 1,
        "limit": limit,
    }


@router.post("/redeem-promo")
async def redeem_promo(
    body: RedeemPromoRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Redeem a promo code."""
    result = await credit_service.redeem_promo(db, current_user.id, body.code)
    balance = await credit_service.get_balance(db, current_user.id)
    return {**result, "balance": balance}
