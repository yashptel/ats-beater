from pydantic import BaseModel, Field, field_validator

from app.services.latex.templates import ensure_valid_template_id


class ResumeTemplateResponse(BaseModel):
    id: str
    name: str
    description: str
    density_hint: str


class ResumeTemplatesResponse(BaseModel):
    items: list[ResumeTemplateResponse]
    default_template_id: str


class UserPreferencesUpdateRequest(BaseModel):
    default_resume_template_id: str = Field(..., min_length=1)

    @field_validator("default_resume_template_id")
    @classmethod
    def default_template_allowed(cls, v: str) -> str:
        return ensure_valid_template_id(v)


class UserPreferencesResponse(BaseModel):
    default_resume_template_id: str


class JobTemplateUpdateRequest(BaseModel):
    template_id: str = Field(..., min_length=1)

    @field_validator("template_id")
    @classmethod
    def template_id_allowed(cls, v: str) -> str:
        return ensure_valid_template_id(v)
