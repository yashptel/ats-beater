from pydantic import BaseModel, field_validator
from typing import Optional
from datetime import datetime


class TenantCreate(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Tenant name must not be empty")
        return v


class TenantUpdate(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Tenant name must not be empty")
        return v


class TenantResponse(BaseModel):
    id: str
    name: str
    user_count: int = 0
    created_at: datetime

    model_config = {"from_attributes": True}


class DomainRuleCreate(BaseModel):
    domain: str
    tenant_id: str

    @field_validator("domain")
    @classmethod
    def normalize_domain(cls, v: str) -> str:
        v = v.strip().lower()
        if not v:
            raise ValueError("Domain must not be empty")
        return v


class DomainRuleResponse(BaseModel):
    id: int
    domain: str
    tenant_id: str
    tenant_name: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class AssignTenantRequest(BaseModel):
    tenant_id: Optional[str] = None


class UserAdminResponse(BaseModel):
    id: str
    email: str
    name: str
    is_super_admin: bool
    tenant_id: Optional[str] = None
    tenant_name: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}
