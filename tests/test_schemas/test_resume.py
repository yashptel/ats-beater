import pytest
from app.schemas.resume import (
    Education,
    Experience,
    ExtractedResumeInfo,
    Link,
    Project,
    ResumeInfo,
    Skill,
)


def test_resume_info_minimal():
    info = ResumeInfo(name="John Doe", email="john@example.com", location="Remote")
    assert info.name == "John Doe"
    assert info.email == "john@example.com"
    assert info.location == "Remote"
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


def test_resume_info_summary_defaults_to_none():
    info = ResumeInfo(name="No Summary", email="ns@example.com")
    assert info.summary is None


def test_resume_info_summary_missing_key_is_none():
    data = {"name": "Legacy", "email": "legacy@example.com"}
    info = ResumeInfo.model_validate(data)
    assert info.summary is None


def test_resume_info_summary_roundtrip():
    text = "Engineer with 5 years building distributed systems."
    info = ResumeInfo(name="Roundtrip", email="rt@example.com", summary=text)
    dumped = info.model_dump()
    assert dumped["summary"] == text
    rehydrated = ResumeInfo.model_validate(dumped)
    assert rehydrated.summary == text


def test_resume_info_summary_explicit_null():
    info = ResumeInfo.model_validate(
        {"name": "Null", "email": "null@example.com", "summary": None}
    )
    assert info.summary is None


def test_resume_info_normalizes_collapsed_bullet_descriptions():
    info = ResumeInfo.model_validate(
        {
            "name": "Yash Patel",
            "email": "yash@example.com",
            "past_experience": [
                {
                    "company_name": "Eventbrite",
                    "role": "Software Engineer II",
                    "description": (
                        "• · Reduced annual localization costs by about 60% by leading "
                        "3 engineers. · Cut translation keys from over 10 million to "
                        "about 1 to 2 million. · Shortened production-incident triage."
                    ),
                }
            ],
            "projects": [
                {
                    "name": "Sidekick",
                    "description": (
                        "• · Built and launched Sidekick, an always-on AI desktop overlay. "
                        "· Developed a local STT pipeline with approximately 500ms to "
                        "1.5s partial-transcription latency."
                    ),
                }
            ],
        }
    )

    assert info.past_experience[0].description == (
        "Reduced annual localization costs by about 60% by leading 3 engineers.\n"
        "Cut translation keys from over 10 million to about 1 to 2 million.\n"
        "Shortened production-incident triage."
    )
    assert info.projects[0].description == (
        "Built and launched Sidekick, an always-on AI desktop overlay.\n"
        "Developed a local STT pipeline with approximately 500ms to "
        "1.5s partial-transcription latency."
    )


def test_resume_info_normalization_preserves_plain_prose():
    text = "Built Node.js services for B2B SaaS across React.js and PostgreSQL."
    info = ResumeInfo(
        name="Plain",
        email="plain@example.com",
        projects=[Project(name="Plain Project", description=text)],
    )
    assert info.projects[0].description == text


def test_resume_info_normalizes_wrapped_pdf_extraction_pattern():
    info = ResumeInfo.model_validate(
        {
            "name": "Yash Patel",
            "email": "yash@example.com",
            "projects": [
                {
                    "name": "SERO",
                    "description": (
                        "• · Launched a multi-tenant manufacturing scheduling SaaS with "
                        "a TypeScript React frontend, Go/GraphQL\n"
                        "backend, and PostgreSQL. · Created a heuristic DAG-based "
                        "production scheduler with topological\n"
                        "ready-queue and critical-path ranking."
                    ),
                }
            ],
        }
    )

    assert info.projects[0].description == (
        "Launched a multi-tenant manufacturing scheduling SaaS with a TypeScript "
        "React frontend, Go/GraphQL backend, and PostgreSQL.\n"
        "Created a heuristic DAG-based production scheduler with topological "
        "ready-queue and critical-path ranking."
    )


def test_extracted_resume_info_converts_bullet_arrays_to_public_profile_strings():
    extracted = ExtractedResumeInfo.model_validate(
        {
            "name": "Yash Patel",
            "email": "yash@example.com",
            "past_experience": [
                {
                    "company_name": "Toddle",
                    "role": "Software Engineer II",
                    "description": [
                        "Designed a 64-bit Snowflake-style ID system.",
                        "Executed a zero-downtime PostgreSQL migration of 2B rows.",
                    ],
                }
            ],
            "projects": [
                {
                    "name": "Sidekick",
                    "description": [
                        "Built an always-on AI desktop overlay.",
                        "Developed local Whisper STT with 500ms to 1.5s latency.",
                    ],
                }
            ],
        }
    )

    info = extracted.to_resume_info()

    assert isinstance(info, ResumeInfo)
    assert info.past_experience[0].description == (
        "Designed a 64-bit Snowflake-style ID system.\n"
        "Executed a zero-downtime PostgreSQL migration of 2B rows."
    )
    assert info.projects[0].description == (
        "Built an always-on AI desktop overlay.\n"
        "Developed local Whisper STT with 500ms to 1.5s latency."
    )
