from pydantic import BaseModel, Field
from typing import List, Literal, Optional


class Link(BaseModel):
    name: str = Field(..., title="Name/type of the link (e.g. github, linkedin, codeforces, portfolio, leetcode)")
    url: str = Field(..., title="URL of the website")


class Project(BaseModel):
    name: str = Field(..., title="Name of the project")
    link: Optional[str] = Field(default=None, title="Link to the project")
    description: str = Field(title="Description of the project")


class Experience(BaseModel):
    company_name: str = Field(..., title="Name of the company")
    department: Optional[str] = Field(default=None, title="Department or team name")
    location: Optional[str] = Field(default=None, title="Location (e.g. Remote, Bangalore, India)")
    start_date: Optional[str] = Field(default=None, title="Start date of the experience")
    end_date: Optional[str] = Field(default=None, title="End date of the experience")
    role: str = Field(..., title="Role in the company")
    description: str = Field(title="Full description of the experience preserving all details and achievements")


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
    date_of_birth: Optional[str] = Field(
        default=None, description='Date of birth in the format "YYYY-MM-DD"'
    )
    email: str = Field(title="Email")
    links: List[Link] = Field(default=[], title="List of all profile links found in the resume")
    projects: List[Project] = Field(default=[], title="List of projects")
    past_experience: List[Experience] = Field(default=[], title="List of experiences")
    achievements: List[Achievement] = Field(default=[], title="List of achievements")
    skills: List[Skill] = Field(default=[], title="List of ALL skills mentioned in the resume")
    educations: List[Education] = Field(default=[], title="List of educations")
    certifications: List[Certification] = Field(default=[], title="List of certifications")
    patents: List[Patent] = Field(default=[], title="List of patents")
    papers: List[Paper] = Field(default=[], title="List of papers")
