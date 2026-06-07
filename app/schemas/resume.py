import re
from typing import Any, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


_BULLET_SEPARATOR_RE = re.compile(r"(?:^|\s)[\u2022\u00b7]\s*(?:[\u2022\u00b7]\s*)*")
_LINE_BULLET_PREFIX_RE = re.compile(r"^\s*(?:[\u2022\u00b7\-–—*]\s*)+")


def normalize_profile_description(value: Any) -> Any:
    """Canonicalize source-profile descriptions without dropping content.

    Profile descriptions stay strings, but bullets are represented as one clean
    line per bullet. This prevents PDF extraction artifacts such as
    "• · First. · Second." from leaking into downstream tailoring.
    """
    if not isinstance(value, str):
        return value

    normalized = value.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    if "\u2022" in normalized or "\u00b7" in normalized:
        normalized = re.sub(r"\s+", " ", normalized).strip()

    lines: list[str] = []
    for raw_line in normalized.split("\n"):
        line = raw_line.strip()
        if not line:
            continue

        parts = [part.strip() for part in _BULLET_SEPARATOR_RE.split(line)]
        for part in parts:
            cleaned = _LINE_BULLET_PREFIX_RE.sub("", part).strip()
            if cleaned:
                lines.append(cleaned)

    return "\n".join(lines)


class Link(BaseModel):
    name: str = Field(..., title="Name/type of the link (e.g. github, linkedin, codeforces, portfolio, leetcode)")
    url: str = Field(..., title="URL of the website")


class Project(BaseModel):
    name: str = Field(..., title="Name of the project")
    link: Optional[str] = Field(default=None, title="Link to the project")
    description: str = Field(title="Description of the project")

    @field_validator("description", mode="before")
    @classmethod
    def normalize_description(cls, value: Any) -> Any:
        return normalize_profile_description(value)


class Experience(BaseModel):
    company_name: str = Field(..., title="Name of the company")
    department: Optional[str] = Field(default=None, title="Department or team name")
    location: Optional[str] = Field(default=None, title="Location (e.g. Remote, Bangalore, India)")
    start_date: Optional[str] = Field(default=None, title="Start date of the experience")
    end_date: Optional[str] = Field(default=None, title="End date of the experience")
    role: str = Field(..., title="Role in the company")
    description: str = Field(title="Full description of the experience preserving all details and achievements")

    @field_validator("description", mode="before")
    @classmethod
    def normalize_description(cls, value: Any) -> Any:
        return normalize_profile_description(value)


def _join_extracted_description(value: list[str]) -> str:
    lines: list[str] = []
    for item in value:
        normalized = normalize_profile_description(item)
        if isinstance(normalized, str):
            lines.extend(line for line in normalized.split("\n") if line.strip())
    return "\n".join(lines)


_EXTRACTED_DESCRIPTION_ALIASES = (
    "description",
    "descriptions",
    "bullets",
    "bullet_points",
    "bulletPoints",
    "details",
    "highlights",
    "responsibilities",
)
_EXTRACTED_DESCRIPTION_TEXT_KEYS = (
    "text",
    "description",
    "bullet",
    "point",
    "content",
    "detail",
)


def _with_extracted_description_alias(data: Any) -> Any:
    if not isinstance(data, dict) or "description" in data:
        return data

    for key in _EXTRACTED_DESCRIPTION_ALIASES:
        if key in data:
            return {**data, "description": data[key]}
    return data


def _coerce_extracted_description(value: Any) -> Any:
    raw_items = [value] if isinstance(value, str) else value
    if not isinstance(raw_items, list):
        return value

    lines: list[str] = []
    for item in raw_items:
        if isinstance(item, dict):
            item = next(
                (
                    item[key]
                    for key in _EXTRACTED_DESCRIPTION_TEXT_KEYS
                    if isinstance(item.get(key), str) and item[key].strip()
                ),
                item,
            )
        if not isinstance(item, str):
            return value
        normalized = normalize_profile_description(item)
        if isinstance(normalized, str):
            lines.extend(line.strip() for line in normalized.split("\n") if line.strip())

    return lines


def _require_extracted_description(value: list[str]) -> list[str]:
    lines = _coerce_extracted_description(value)
    if not isinstance(lines, list) or not all(isinstance(line, str) for line in lines):
        return value
    if not lines:
        raise ValueError("description must include at least one extracted bullet or detail")
    return lines


class ExtractedProject(BaseModel):
    name: str = Field(..., title="Name of the project")
    link: Optional[str] = Field(default=None, title="Link to the project")
    description: List[str] = Field(
        ...,
        title="Project bullet points, one distinct resume bullet per item",
    )

    @model_validator(mode="before")
    @classmethod
    def accept_description_aliases(cls, data: Any) -> Any:
        return _with_extracted_description_alias(data)

    @field_validator("description", mode="before")
    @classmethod
    def coerce_description(cls, value: Any) -> Any:
        return _coerce_extracted_description(value)

    @field_validator("description")
    @classmethod
    def require_description(cls, value: list[str]) -> list[str]:
        return _require_extracted_description(value)

    def to_project(self) -> Project:
        return Project(
            name=self.name,
            link=self.link,
            description=_join_extracted_description(self.description),
        )


class ExtractedExperience(BaseModel):
    company_name: str = Field(..., title="Name of the company")
    department: Optional[str] = Field(default=None, title="Department or team name")
    location: Optional[str] = Field(default=None, title="Location")
    start_date: Optional[str] = Field(default=None, title="Start date of the experience")
    end_date: Optional[str] = Field(default=None, title="End date of the experience")
    role: str = Field(..., title="Role in the company")
    description: List[str] = Field(
        ...,
        title="Experience bullet points, one distinct resume bullet per item",
    )

    @model_validator(mode="before")
    @classmethod
    def accept_description_aliases(cls, data: Any) -> Any:
        return _with_extracted_description_alias(data)

    @field_validator("description", mode="before")
    @classmethod
    def coerce_description(cls, value: Any) -> Any:
        return _coerce_extracted_description(value)

    @field_validator("description")
    @classmethod
    def require_description(cls, value: list[str]) -> list[str]:
        return _require_extracted_description(value)

    def to_experience(self) -> Experience:
        return Experience(
            company_name=self.company_name,
            department=self.department,
            location=self.location,
            start_date=self.start_date,
            end_date=self.end_date,
            role=self.role,
            description=_join_extracted_description(self.description),
        )


class Achievement(BaseModel):
    name: str = Field(..., title="Name of the achievement")
    description: Optional[str] = Field(default=None, title="Description of the achievement")


class Skill(BaseModel):
    name: str = Field(..., title="Name of the skill")
    category: str = Field(..., title="Category of the skill (e.g. Programming, Frameworks, Cloud/Infra, Data, AI, Quant/Systems, Soft Skills, Languages)")


class Education(BaseModel):
    degree: str = Field(..., title="Degree")
    start_date: Optional[str] = Field(default=None, title="Start date of the education")
    end_date: Optional[str] = Field(default=None, title="End date of the education")
    grade: Optional[str] = Field(default=None, title="Grade of the education")
    institution: str = Field(..., title="Name of the institution")


class Certification(BaseModel):
    name: str = Field(..., title="Name of the certification")
    credential_id: Optional[str] = Field(default=None, title="Credential ID if mentioned")


class Patent(BaseModel):
    name: str = Field(..., title="Name of the patent")
    date: Optional[str] = Field(default=None, title="Date of the patent")
    description: Optional[str] = Field(default=None, title="Description of the patent")


class Paper(BaseModel):
    name: str = Field(..., title="Name of the paper")
    date: Optional[str] = Field(default=None, title="Date of the paper")
    description: Optional[str] = Field(default=None, title="Description of the paper")


class ResumeInfo(BaseModel):
    name: str = Field(title="Name")
    mobile_number: Optional[str] = Field(default=None, title="Mobile number")
    location: Optional[str] = Field(default=None, title="Candidate location")
    date_of_birth: Optional[str] = Field(
        default=None, description='Date of birth in the format "YYYY-MM-DD"'
    )
    email: str = Field(title="Email")
    summary: Optional[str] = Field(
        default=None,
        title="Optional professional summary extracted verbatim from the resume",
    )
    links: List[Link] = Field(default=[], title="List of all profile links found in the resume")
    projects: List[Project] = Field(default=[], title="List of projects")
    past_experience: List[Experience] = Field(default=[], title="List of experiences")
    achievements: List[Achievement] = Field(default=[], title="List of achievements")
    skills: List[Skill] = Field(default=[], title="List of ALL skills mentioned in the resume")
    educations: List[Education] = Field(default=[], title="List of educations")
    certifications: List[Certification] = Field(default=[], title="List of certifications")
    patents: List[Patent] = Field(default=[], title="List of patents")
    papers: List[Paper] = Field(default=[], title="List of papers")


class ExtractedResumeInfo(BaseModel):
    """LLM-only extraction schema.

    Public profile data still serializes descriptions as strings, but extraction
    asks the model for bullet arrays so schema validation can enforce boundaries.
    """

    name: str = Field(title="Name")
    mobile_number: Optional[str] = Field(default=None, title="Mobile number")
    location: Optional[str] = Field(default=None, title="Candidate location")
    date_of_birth: Optional[str] = Field(
        default=None, description='Date of birth in the format "YYYY-MM-DD"'
    )
    email: str = Field(title="Email")
    summary: Optional[str] = Field(
        default=None,
        title="Optional professional summary extracted verbatim from the resume",
    )
    links: List[Link] = Field(default=[], title="List of all profile links found in the resume")
    projects: List[ExtractedProject] = Field(default=[], title="List of projects")
    past_experience: List[ExtractedExperience] = Field(default=[], title="List of experiences")
    achievements: List[Achievement] = Field(default=[], title="List of achievements")
    skills: List[Skill] = Field(default=[], title="List of ALL skills mentioned in the resume")
    educations: List[Education] = Field(default=[], title="List of educations")
    certifications: List[Certification] = Field(default=[], title="List of certifications")
    patents: List[Patent] = Field(default=[], title="List of patents")
    papers: List[Paper] = Field(default=[], title="List of papers")

    def to_resume_info(self) -> ResumeInfo:
        return ResumeInfo(
            name=self.name,
            mobile_number=self.mobile_number,
            location=self.location,
            date_of_birth=self.date_of_birth,
            email=self.email,
            summary=self.summary,
            links=self.links,
            projects=[project.to_project() for project in self.projects],
            past_experience=[exp.to_experience() for exp in self.past_experience],
            achievements=self.achievements,
            skills=self.skills,
            educations=self.educations,
            certifications=self.certifications,
            patents=self.patents,
            papers=self.papers,
        )
