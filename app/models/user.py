import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    google_id: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    picture_url: Mapped[str | None] = mapped_column(String, nullable=True)
    consent_accepted: Mapped[bool] = mapped_column(Boolean, default=False)
    consent_accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_super_admin: Mapped[bool] = mapped_column(Boolean, server_default="false", default=False)
    tenant_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("tenants.id", ondelete="SET NULL"), nullable=True, index=True
    )

    profiles = relationship("Profile", back_populates="user")
    jobs = relationship("Job", back_populates="user")
    credit = relationship("UserCredit", back_populates="user", uselist=False)
    tenant = relationship("Tenant", back_populates="users")
    roasts = relationship("Roast", back_populates="user")
