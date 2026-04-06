import uuid
from sqlalchemy import String, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin


class Tenant(TimestampMixin, Base):
    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String, nullable=False)

    users = relationship("User", back_populates="tenant")
    domain_rules = relationship("TenantDomainRule", back_populates="tenant", cascade="all, delete-orphan")


class TenantDomainRule(TimestampMixin, Base):
    __tablename__ = "tenant_domain_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    domain: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)

    tenant = relationship("Tenant", back_populates="domain_rules")
