from pydantic import BaseModel, field_validator
from typing import Optional
from datetime import datetime


# ── Credit Packs ────────────────────────────────────────────────

class CreditPackCreate(BaseModel):
    name: str
    credits: int
    price_paise: int
    is_active: bool = True
    sort_order: int = 0

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Pack name must not be empty")
        return v

    @field_validator("credits")
    @classmethod
    def credits_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("Credits must be positive")
        return v

    @field_validator("price_paise")
    @classmethod
    def price_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("Price must be positive")
        return v


class CreditPackUpdate(BaseModel):
    name: Optional[str] = None
    credits: Optional[int] = None
    price_paise: Optional[int] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None

    @field_validator("credits")
    @classmethod
    def credits_positive(cls, v):
        if v is not None and v <= 0:
            raise ValueError("Credits must be positive")
        return v

    @field_validator("price_paise")
    @classmethod
    def price_positive(cls, v):
        if v is not None and v <= 0:
            raise ValueError("Price must be positive")
        return v


class CreditPackResponse(BaseModel):
    id: int
    name: str
    credits: int
    price_paise: int
    is_active: bool
    sort_order: int
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Time Pass Tiers ─────────────────────────────────────────────

class TimePassTierCreate(BaseModel):
    name: str
    duration_days: int
    price_paise: int
    is_active: bool = True
    sort_order: int = 0

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Tier name must not be empty")
        return v

    @field_validator("duration_days")
    @classmethod
    def duration_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("Duration must be positive")
        return v

    @field_validator("price_paise")
    @classmethod
    def price_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("Price must be positive")
        return v


class TimePassTierUpdate(BaseModel):
    name: Optional[str] = None
    duration_days: Optional[int] = None
    price_paise: Optional[int] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None

    @field_validator("duration_days")
    @classmethod
    def duration_positive(cls, v):
        if v is not None and v <= 0:
            raise ValueError("Duration must be positive")
        return v

    @field_validator("price_paise")
    @classmethod
    def price_positive(cls, v):
        if v is not None and v <= 0:
            raise ValueError("Price must be positive")
        return v


class TimePassTierResponse(BaseModel):
    id: int
    name: str
    duration_days: int
    price_paise: int
    is_active: bool
    sort_order: int
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Credit Balance ──────────────────────────────────────────────

class ActiveTimePassInfo(BaseModel):
    tier_name: str
    expires_at: datetime


class CreditBalanceResponse(BaseModel):
    balance: int
    daily_free_remaining: int
    daily_free_total: int
    active_time_pass: Optional[ActiveTimePassInfo] = None
    has_unlimited: bool


# ── Transactions ────────────────────────────────────────────────

class TransactionResponse(BaseModel):
    id: int
    amount: int
    type: str
    reference_id: Optional[str] = None
    razorpay_order_id: Optional[str] = None
    description: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class AdminTransactionResponse(TransactionResponse):
    user_id: str
    user_email: Optional[str] = None
    user_name: Optional[str] = None


# ── Promo Codes ─────────────────────────────────────────────────

class PromoCodeCreate(BaseModel):
    code: str
    type: str  # "CREDITS" or "TIME_PASS"
    value: int
    max_redemptions: int = 0
    is_active: bool = True
    expires_at: Optional[datetime] = None

    @field_validator("code")
    @classmethod
    def uppercase_code(cls, v: str) -> str:
        v = v.strip().upper()
        if not v:
            raise ValueError("Promo code must not be empty")
        return v

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        if v not in ("CREDITS", "TIME_PASS"):
            raise ValueError("Type must be CREDITS or TIME_PASS")
        return v

    @field_validator("value")
    @classmethod
    def value_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("Value must be positive")
        return v


class PromoCodeUpdate(BaseModel):
    is_active: Optional[bool] = None
    max_redemptions: Optional[int] = None
    expires_at: Optional[datetime] = None

    @field_validator("max_redemptions")
    @classmethod
    def max_redemptions_non_negative(cls, v):
        if v is not None and v < 0:
            raise ValueError("Max redemptions must be non-negative (0 = unlimited)")
        return v


class PromoCodeResponse(BaseModel):
    id: int
    code: str
    type: str
    value: int
    max_redemptions: int
    current_redemptions: int
    is_active: bool
    expires_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Promo Redemption ────────────────────────────────────────────

class RedeemPromoRequest(BaseModel):
    code: str

    @field_validator("code")
    @classmethod
    def uppercase_code(cls, v: str) -> str:
        return v.strip().upper()


# ── Payments ────────────────────────────────────────────────────

class CreateOrderRequest(BaseModel):
    item_type: str  # "credit_pack" or "time_pass"
    item_id: int

    @field_validator("item_type")
    @classmethod
    def validate_item_type(cls, v: str) -> str:
        if v not in ("credit_pack", "time_pass"):
            raise ValueError("item_type must be credit_pack or time_pass")
        return v


class CreateOrderResponse(BaseModel):
    order_id: str
    amount_paise: int
    currency: str
    razorpay_key_id: str


class VerifyPaymentRequest(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


# ── Admin Grant ─────────────────────────────────────────────────

class AdminGrantRequest(BaseModel):
    user_id: str
    amount: int
    description: Optional[str] = None

    @field_validator("amount")
    @classmethod
    def amount_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("Grant amount must be positive")
        return v


# ── Pagination Envelope ─────────────────────────────────────────

class PaginatedResponse(BaseModel):
    items: list
    total: int
    page: int
    pages: int
    limit: int
