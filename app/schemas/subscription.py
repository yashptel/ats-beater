from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class PlanResponse(BaseModel):
    id: int
    name: str
    price: int
    resume_limit_per_month: int

    model_config = {"from_attributes": True}


class SubscriptionResponse(BaseModel):
    id: int
    user_id: str
    plan_id: int
    razorpay_subscription_id: Optional[str] = None
    status: str
    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None
    resumes_generated_this_period: int
    created_at: datetime

    model_config = {"from_attributes": True}
