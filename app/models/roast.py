import enum
from sqlalchemy import Integer, String, Text, Enum, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin


class RoastStatus(str, enum.Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    READY = "READY"
    FAILED = "FAILED"


class Roast(TimestampMixin, Base):
    __tablename__ = "roasts"
    __table_args__ = (
        UniqueConstraint("user_id", "file_hash", name="uq_roasts_user_file"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False, index=True)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    share_id: Mapped[str] = mapped_column(String(16), unique=True, nullable=False, index=True)
    extracted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    roast_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[RoastStatus] = mapped_column(
        Enum(RoastStatus), default=RoastStatus.PENDING, nullable=False
    )

    user = relationship("User", back_populates="roasts")
