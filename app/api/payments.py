import json
from fastapi import APIRouter, Depends, Request, Header
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database.session import get_db
from app.models.user import User
from app.models.credit import CreditPack, TimePassTier, CreditTransaction, TransactionType
from app.dependencies import get_current_user
from app.services.credit.service import CreditService
from app.services.payment.razorpay_client import RazorpayService
from app.schemas.credit import CreateOrderRequest, VerifyPaymentRequest
from app.config import get_settings
from logging import getLogger

logger = getLogger(__name__)

router = APIRouter(prefix="/payments", tags=["payments"])
credit_service = CreditService()


@router.post("/create-order")
async def create_order(
    body: CreateOrderRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a Razorpay order for a credit pack or time pass."""
    settings = get_settings()

    if body.item_type == "credit_pack":
        pack = await db.get(CreditPack, body.item_id)
        if not pack or not pack.is_active:
            raise ValueError("Credit pack not found or inactive")
        amount_paise = pack.price_paise
        receipt = f"cp_{current_user.id[:8]}_{pack.id}"
        notes = {"type": "credit_pack", "pack_id": str(pack.id), "user_id": current_user.id}
    elif body.item_type == "time_pass":
        tier = await db.get(TimePassTier, body.item_id)
        if not tier or not tier.is_active:
            raise ValueError("Time pass tier not found or inactive")
        amount_paise = tier.price_paise
        receipt = f"tp_{current_user.id[:8]}_{tier.id}"
        notes = {"type": "time_pass", "tier_id": str(tier.id), "user_id": current_user.id}
    else:
        raise ValueError("Invalid item_type")

    rzp = RazorpayService()
    order = rzp.create_order(amount_paise, receipt, notes)

    return {
        "order_id": order["id"],
        "amount_paise": amount_paise,
        "currency": "INR",
        "razorpay_key_id": settings.RAZORPAY_KEY_ID,
    }


@router.post("/verify")
async def verify_payment(
    body: VerifyPaymentRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Verify Razorpay payment signature and credit the user's account."""
    rzp = RazorpayService()

    # Verify signature
    is_valid = rzp.verify_payment(
        body.razorpay_order_id, body.razorpay_payment_id, body.razorpay_signature
    )
    if not is_valid:
        raise ValueError("Payment verification failed — invalid signature")

    # Check idempotency: skip if already processed
    existing = await db.execute(
        select(CreditTransaction).where(
            CreditTransaction.razorpay_order_id == body.razorpay_order_id
        )
    )
    if existing.scalar_one_or_none():
        balance = await credit_service.get_balance(db, current_user.id)
        return {"status": "already_processed", "balance": balance}

    # Fetch order details from Razorpay to get notes
    order = rzp.fetch_order(body.razorpay_order_id)
    notes = order.get("notes", {})
    item_type = notes.get("type")

    # Verify the order belongs to the current user (prevent order hijacking)
    order_user_id = notes.get("user_id")
    if order_user_id != current_user.id:
        raise ValueError("Payment order does not belong to current user")

    if item_type == "credit_pack":
        pack_id_str = notes.get("pack_id")
        if not pack_id_str:
            raise ValueError("Missing pack_id in order notes")
        pack = await db.get(CreditPack, int(pack_id_str))
        if not pack:
            raise ValueError(f"Credit pack {pack_id_str} not found")
        await credit_service.add_credits(
            db, current_user.id, pack.credits, TransactionType.CREDIT_PURCHASE,
            razorpay_order_id=body.razorpay_order_id,
            description=f"Purchased: {pack.name} ({pack.credits} credits)",
        )
    elif item_type == "time_pass":
        tier_id_str = notes.get("tier_id")
        if not tier_id_str:
            raise ValueError("Missing tier_id in order notes")
        await credit_service.activate_time_pass(
            db, current_user.id, int(tier_id_str),
            razorpay_order_id=body.razorpay_order_id,
        )
    else:
        raise ValueError(f"Unknown order type in notes: {item_type}")

    # Explicit commit — add_credits/activate_time_pass only flush
    await db.commit()

    balance = await credit_service.get_balance(db, current_user.id)
    return {"status": "success", "balance": balance}


@router.post("/webhook")
async def razorpay_webhook(
    request: Request,
    x_razorpay_signature: str = Header(alias="X-Razorpay-Signature", default=""),
):
    """Razorpay webhook handler (safety net for payment.captured events).
    Returns 500 on processing errors so Razorpay retries delivery.
    """
    body_bytes = await request.body()
    rzp = RazorpayService()

    if not rzp.verify_webhook(body_bytes, x_razorpay_signature):
        logger.warning("Webhook signature verification failed")
        return {"status": "ignored"}

    payload = json.loads(body_bytes)
    event = payload.get("event", "")

    if event != "payment.captured":
        return {"status": "ignored", "event": event}

    # Extract order and process idempotently
    payment_entity = payload.get("payload", {}).get("payment", {}).get("entity", {})
    order_id = payment_entity.get("order_id")
    if not order_id:
        return {"status": "ignored", "reason": "no_order_id"}

    from app.database.session import async_session_factory

    try:
        async with async_session_factory() as db:
            # Check if already processed
            existing = await db.execute(
                select(CreditTransaction).where(
                    CreditTransaction.razorpay_order_id == order_id
                )
            )
            if existing.scalar_one_or_none():
                return {"status": "already_processed"}

            # Fetch order notes
            order = rzp.fetch_order(order_id)
            notes = order.get("notes", {})
            user_id = notes.get("user_id")
            item_type = notes.get("type")

            if not user_id or not item_type:
                logger.warning(f"Webhook: missing user_id or type in order {order_id}")
                return {"status": "ignored", "reason": "missing_notes"}

            # Verify user exists before crediting
            user = await db.get(User, user_id)
            if not user:
                logger.warning(f"Webhook: user {user_id} not found for order {order_id}")
                return {"status": "ignored", "reason": "user_not_found"}

            if item_type == "credit_pack":
                pack_id_str = notes.get("pack_id")
                if not pack_id_str:
                    logger.warning(f"Webhook: missing pack_id in order {order_id}")
                    return {"status": "ignored", "reason": "missing_pack_id"}
                pack = await db.get(CreditPack, int(pack_id_str))
                if pack:
                    await credit_service.add_credits(
                        db, user_id, pack.credits, TransactionType.CREDIT_PURCHASE,
                        razorpay_order_id=order_id,
                        description=f"Webhook: {pack.name} ({pack.credits} credits)",
                    )
            elif item_type == "time_pass":
                tier_id_str = notes.get("tier_id")
                if not tier_id_str:
                    logger.warning(f"Webhook: missing tier_id in order {order_id}")
                    return {"status": "ignored", "reason": "missing_tier_id"}
                await credit_service.activate_time_pass(
                    db, user_id, int(tier_id_str), razorpay_order_id=order_id,
                )

            # Explicit commit — add_credits/activate_time_pass only flush
            await db.commit()
    except Exception:
        logger.exception(f"Webhook processing failed for order {order_id}")
        # Return 500 so Razorpay retries — credits must not be lost
        return JSONResponse(
            status_code=500,
            content={"status": "error", "reason": "processing_failed"},
        )

    return {"status": "processed"}
