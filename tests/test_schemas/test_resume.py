import pytest
from app.schemas.resume import ResumeInfo, Link, Project, Experience, Skill, Education


def test_resume_info_minimal():
    info = ResumeInfo(name="John Doe", email="john@example.com")
    assert info.name == "John Doe"
    assert info.email == "john@example.com"
    assert info.links == []
    assert info.projects == []
    assert info.past_experience == []


def test_resume_info_full():
    info = ResumeInfo(
        name="Jane Smith",
        email="jane@example.com",
        mobile_number="+1234567890",
        links=[Link(name="LinkedIn", url="https://linkedin.com/in/janesmith")],
        projects=[Project(name="MyApp", description="A cool app")],
        past_experience=[
            Experience(
                company_name="Acme Corp",
                role="Engineer",
                description="Built things",
                start_date="2020-01",
                end_date="2023-06",
            )
        ],
        skills=[Skill(name="Python", category="Programming")],
        educations=[Education(degree="BS CS", institution="MIT")],
    )
    assert len(info.links) == 1
    assert info.links[0].name == "LinkedIn"
    assert len(info.past_experience) == 1


def test_resume_info_from_dict():
    data = {
        "name": "Test",
        "email": "test@test.com",
        "links": [{"name": "GitHub", "url": "https://github.com/test"}],
        "projects": [],
        "past_experience": [],
        "achievements": [],
        "skills": [],
        "educations": [],
        "certifications": [],
        "patents": [],
        "papers": [],
    }
    info = ResumeInfo.model_validate(data)
    assert info.name == "Test"
    assert len(info.links) == 1
