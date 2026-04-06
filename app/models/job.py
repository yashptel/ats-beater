import enum
from sqlalchemy import Integer, String, Text, Enum, ForeignKey
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin


class JobStatus(str, enum.Enum):
    PENDING = "PENDING"
    GENERATING_RESUME = "GENERATING_RESUME"
    RESUME_GENERATED = "RESUME_GENERATED"
    GENERATING_PDF = "GENERATING_PDF"
    READY = "READY"
    FAILED = "FAILED"


class Job(TimestampMixin, Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False, index=True)
    profile_id: Mapped[int] = mapped_column(Integer, ForeignKey("profiles.id"), nullable=False, index=True)
    job_description: Mapped[dict] = mapped_column(JSON, nullable=False)
    custom_resume_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    resume_latex_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    pdf_gcs_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus), default=JobStatus.PENDING, nullable=False
    )

    user = relationship("User", back_populates="jobs")
    profile = relationship("Profile", back_populates="jobs")
