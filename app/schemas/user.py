from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class UserResponse(BaseModel):
    id: str
    email: str
    name: str
    picture_url: Optional[str] = None
    consent_accepted: bool
    is_super_admin: bool = False
    tenant_id: Optional[str] = None
    tenant_name: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class TokenPayload(BaseModel):
    sub: str
    email: str
    exp: int
