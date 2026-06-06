from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Any, List, Optional


def _coerce_text_list(value: Any) -> Any:
    if isinstance(value, str):
        return [value]
    return value


def _with_description_alias(data: Any) -> Any:
    if isinstance(data, dict) and "description" not in data and "bullets" in data:
        return {**data, "description": data["bullets"]}
    return data


class CustomLink(BaseModel):
    name: str = Field(..., title="Name of the website")
    url: str = Field(..., title="URL of the website")


class CustomProject(BaseModel):
    name: str = Field(..., title="Name of the project")
    link: Optional[str] = Field(default=None, title="Link to the project")
    description: List[str] = Field(title="Bullet points highlighting the project")

    @model_validator(mode="before")
    @classmethod
    def accept_bullets_alias(cls, data: Any) -> Any:
        return _with_description_alias(data)

    @field_validator("description", mode="before")
    @classmethod
    def coerce_description(cls, value: Any) -> Any:
        return _coerce_text_list(value)


class CustomExperience(BaseModel):
    company_name: str = Field(..., title="Name of the company")
    department: Optional[str] = Field(default=None, title="Department or team name")
    location: Optional[str] = Field(default=None, title="Location")
    start_date: Optional[str] = Field(default=None, title="Start date of the experience")
    end_date: Optional[str] = Field(default=None, title="End date of the experience")
    role: str = Field(..., title="Role in the company")
    description: List[str] = Field(title="Bullet points highlighting the experience")

    @model_validator(mode="before")
    @classmethod
    def accept_bullets_alias(cls, data: Any) -> Any:
        return _with_description_alias(data)

    @field_validator("description", mode="before")
    @classmethod
    def coerce_description(cls, value: Any) -> Any:
        return _coerce_text_list(value)


class CustomSkills(BaseModel):
    languages: List[str] = Field(default=[], title="List of languages")
    frameworks: List[str] = Field(default=[], title="List of frameworks")
    databases: List[str] = Field(default=[], title="List of databases")
    other_technologies: List[str] = Field(default=[], title="List of other technologies")


class CustomEducation(BaseModel):
    degree: str = Field(..., title="Degree")
    start_date: Optional[str] = Field(default=None, title="Start date of the education")
    end_date: Optional[str] = Field(default=None, title="End date of the education")
    grade: Optional[str] = Field(default=None, title="Grade of the education")
    institution: str = Field(..., title="Name of the institution")


class CustomCertification(BaseModel):
    name: str = Field(..., title="Name of the certification")
    credential_id: Optional[str] = Field(default=None, title="Credential ID or verification URL")


class CustomPatent(BaseModel):
    name: str = Field(..., title="Name of the patent")
    date: Optional[str] = Field(default=None, title="Date of the patent")
    description: Optional[str] = Field(default=None, title="Description of the patent")


class CustomPaper(BaseModel):
    name: str = Field(..., title="Name of the paper")
    date: Optional[str] = Field(default=None, title="Date of the paper")
    description: Optional[str] = Field(default=None, title="Description of the paper")


class CustomResumeInfo(BaseModel):
    name: str = Field(..., title="Name")
    email: str = Field(..., title="Email")
    mobile_number: Optional[str] = Field(default=None, title="Mobile number")
    location: Optional[str] = Field(default=None, title="Candidate location")
    date_of_birth: Optional[str] = Field(default=None, title="Date of birth")
    summary: Optional[str] = Field(default=None, title="Optional professional summary")
    links: List[CustomLink] = Field(default=[], title="List of links")
    projects: List[CustomProject] = Field(default=[], title="List of projects")
    past_experience: List[CustomExperience] = Field(
        default=[],
        title="List of experiences in reverse-chronological order (most recent role first)",
    )
    achievements: List[str] = Field(default=[], title="List of achievements")
    skills: CustomSkills = Field(default_factory=CustomSkills, title="Skills")
    educations: List[CustomEducation] = Field(default=[], title="List of educations")
    certifications: List[CustomCertification] = Field(default=[], title="List of certifications")
    patents: List[CustomPatent] = Field(default=[], title="List of patents")
    papers: List[CustomPaper] = Field(default=[], title="List of papers")

    @model_validator(mode="before")
    @classmethod
    def tolerate_provider_near_misses(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        values = {**data}
        values.setdefault("name", "")
        values.setdefault("email", "")

        achievements = values.get("achievements")
        if isinstance(achievements, list):
            values["achievements"] = [
                _achievement_to_string(achievement) for achievement in achievements
            ]

        return values


def _achievement_to_string(value: Any) -> Any:
    if not isinstance(value, dict):
        return value

    name = str(value.get("name") or "").strip()
    description = str(value.get("description") or "").strip()

    if name and description:
        return f"{name} - {description}"
    return name or description
