from pydantic import BaseModel, Field, field_validator
from typing import Optional, Literal
from datetime import datetime


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


class JobResponse(BaseModel):
    id: int
    user_id: str
    profile_id: int
    job_description: dict
    custom_resume_data: Optional[dict] = None
    resume_latex_code: Optional[str] = None
    pdf_gcs_path: Optional[str] = None
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
