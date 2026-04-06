from sqlalchemy import Integer, String, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, TimestampMixin


class RoastView(TimestampMixin, Base):
    __tablename__ = "roast_views"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    roast_id: Mapped[int] = mapped_column(Integer, ForeignKey("roasts.id", ondelete="CASCADE"), nullable=False)
    share_id: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    referer: Mapped[str | None] = mapped_column(Text, nullable=True)
    platform: Mapped[str | None] = mapped_column(String(50), nullable=True)
    os: Mapped[str | None] = mapped_column(String(50), nullable=True)
    browser: Mapped[str | None] = mapped_column(String(50), nullable=True)
