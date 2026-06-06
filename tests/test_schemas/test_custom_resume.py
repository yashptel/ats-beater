from app.schemas.custom_resume import CustomResumeInfo, CustomSkills, CustomExperience


def test_custom_resume_info_minimal():
    info = CustomResumeInfo(
        name="John Doe",
        email="john@example.com",
        location="Remote",
    )
    assert info.name == "John Doe"
    assert info.location == "Remote"
    assert info.summary is None
    assert info.achievements == []
    assert info.skills.languages == []


def test_custom_resume_info_with_experience():
    info = CustomResumeInfo(
        name="Jane",
        email="jane@example.com",
        past_experience=[
            CustomExperience(
                company_name="BigCo",
                role="SWE",
                location="Bengaluru",
                description=["Built microservices", "Led team of 5"],
            )
        ],
        skills=CustomSkills(
            languages=["Python", "Go"],
            frameworks=["FastAPI", "Django"],
            databases=["PostgreSQL"],
            other_technologies=["Docker", "K8s"],
        ),
    )
    assert len(info.past_experience) == 1
    assert len(info.past_experience[0].description) == 2
    assert info.past_experience[0].location == "Bengaluru"
    assert "Python" in info.skills.languages


def test_custom_resume_info_with_summary():
    info = CustomResumeInfo(
        name="Jane",
        email="jane@example.com",
        summary="Backend engineer with experience in distributed systems.",
    )
    assert info.summary == "Backend engineer with experience in distributed systems."


def test_custom_resume_info_accepts_common_openai_compatible_near_miss_shape():
    info = CustomResumeInfo.model_validate(
        {
            "name": "Will Be Replaced",
            "projects": [
                {
                    "name": "Resume Tailor",
                    "bullets": ["Built a FastAPI service", "Added structured resume output"],
                }
            ],
            "past_experience": [
                {
                    "company_name": "BigCo",
                    "role": "SWE",
                    "bullets": ["Owned backend APIs", "Improved reliability"],
                }
            ],
            "achievements": [
                {"name": "Hackathon", "description": "Won first place"},
                {"description": "Published a technical article"},
            ],
        }
    )

    assert info.email == ""
    assert info.projects[0].description == [
        "Built a FastAPI service",
        "Added structured resume output",
    ]
    assert info.past_experience[0].description == [
        "Owned backend APIs",
        "Improved reliability",
    ]
    assert info.achievements == [
        "Hackathon - Won first place",
        "Published a technical article",
    ]


def test_custom_resume_info_coerces_string_descriptions_to_bullet_lists():
    info = CustomResumeInfo(
        name="Jane",
        email="jane@example.com",
        projects=[{"name": "Parser", "description": "Parsed messy resumes"}],
        past_experience=[
            {
                "company_name": "BigCo",
                "role": "SWE",
                "description": "Built services",
            }
        ],
    )

    assert info.projects[0].description == ["Parsed messy resumes"]
    assert info.past_experience[0].description == ["Built services"]
