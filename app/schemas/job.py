from pydantic import BaseModel, Field, field_validator
from typing import Optional, Literal
from datetime import datetime

from app.services.latex.templates import ensure_valid_template_id


class JobDescription(BaseModel):
    company: str = Field(..., title="Name of the company")
    role: str = Field(..., title="Role in the company")
    description: str = Field(..., title="Description of the job")
    output_language: Optional[
        Literal["english", "norwegian", "french", "german", "russian", "spanish", "italian"]
    ] = Field(default="english", title="Language in which the resume should be generated")

    @field_validator("description")
    @classmethod
    def description_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Job description cannot be empty")
        return v.strip()


class JobCreate(BaseModel):
    profile_id: int
    job_description: JobDescription
    template_id: Optional[str] = None

    @field_validator("template_id")
    @classmethod
    def template_id_allowed(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        return ensure_valid_template_id(v)


class JobResponse(BaseModel):
    id: int
    user_id: str
    profile_id: int
    job_description: dict
    template_id: str = "jake"
    custom_resume_data: Optional[dict] = None
    resume_latex_code: Optional[str] = None
    pdf_gcs_path: Optional[str] = None
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
