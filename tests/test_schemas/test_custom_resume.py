from app.schemas.custom_resume import CustomResumeInfo, CustomSkills, CustomExperience


def test_custom_resume_info_minimal():
    info = CustomResumeInfo(
        name="John Doe",
        email="john@example.com",
    )
    assert info.name == "John Doe"
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
    assert "Python" in info.skills.languages


def test_custom_resume_info_with_summary():
    info = CustomResumeInfo(
        name="Jane",
        email="jane@example.com",
        summary="Backend engineer with experience in distributed systems.",
    )
    assert info.summary == "Backend engineer with experience in distributed systems."
