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
    has_ai_settings: bool = False
    selected_model: Optional[str] = None
    default_resume_template_id: str = "jake"
    created_at: datetime

    model_config = {"from_attributes": True}


class TokenPayload(BaseModel):
    sub: str
    email: str
    exp: int
