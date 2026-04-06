from app.schemas.custom_resume import CustomResumeInfo, CustomSkills, CustomExperience, CustomProject
from app.services.latex.builder import build_resume
from app.services.latex.sanitizer import sanitize_special_chars


def test_build_resume_minimal():
    info = CustomResumeInfo(
        name="John Doe",
        email="john@example.com",
    )
    latex = build_resume(info)
    assert r"\documentclass{resume}" in latex
    assert r"\name{John Doe}" in latex
    assert r"\begin{document}" in latex
    assert r"\end{document}" in latex


def test_build_resume_with_experience():
    info = CustomResumeInfo(
        name="Jane",
        email="jane@example.com",
        past_experience=[
            CustomExperience(
                company_name="Acme",
                role="Dev",
                description=["Built APIs", "Led migrations"],
                start_date="2020-01",
                end_date="2023-06",
            )
        ],
    )
    latex = build_resume(info)
    assert "Experience" in latex
    assert "Acme" in latex
    assert "Built APIs" in latex


def test_build_resume_with_skills():
    info = CustomResumeInfo(
        name="Test",
        email="test@test.com",
        skills=CustomSkills(
            languages=["Python", "Java"],
            frameworks=["FastAPI"],
            databases=["PostgreSQL"],
        ),
    )
    latex = build_resume(info)
    assert "Skills" in latex
    assert "Python" in latex
    assert "FastAPI" in latex


def test_build_resume_with_emphasis():
    """Emphasis markers in bullet points convert to LaTeX bold/italic."""
    data = {
        "name": "Jane",
        "email": "jane@example.com",
        "past_experience": [
            {
                "company_name": "Acme",
                "role": "Dev",
                "description": [
                    "Reduced latency by **40%** using **Redis**",
                    "Led *critical* migration",
                ],
                "start_date": "2020-01",
                "end_date": "2023-06",
            }
        ],
    }
    sanitized = sanitize_special_chars(data)
    info = CustomResumeInfo(**sanitized)
    latex = build_resume(info)
    assert r"\textbf{40\%}" in latex
    assert r"\textbf{Redis}" in latex
    assert r"\textit{critical}" in latex


def test_build_resume_emphasis_in_projects():
    """Emphasis converts in project bullet points too."""
    data = {
        "name": "Test",
        "email": "test@test.com",
        "projects": [
            {
                "name": "MyProject",
                "link": "https://github.com/test",
                "description": ["Built with **FastAPI** and *async* workers"],
            }
        ],
    }
    sanitized = sanitize_special_chars(data)
    info = CustomResumeInfo(**sanitized)
    latex = build_resume(info)
    assert r"\textbf{FastAPI}" in latex
    assert r"\textit{async}" in latex


def test_build_resume_emphasis_in_achievements():
    """Emphasis converts in achievement strings."""
    data = {
        "name": "Test",
        "email": "test@test.com",
        "achievements": ["Won **1st place** in *national* hackathon"],
    }
    sanitized = sanitize_special_chars(data)
    info = CustomResumeInfo(**sanitized)
    latex = build_resume(info)
    assert r"\textbf{1st place}" in latex
    assert r"\textit{national}" in latex


def test_build_resume_emphasis_with_escaped_braces():
    """Emphasis still works when text contains escaped braces from sanitizer.

    Regression test for false-positive brace balance check: absolute count
    of { vs } was skewed by escaped \\{ from sanitizer, causing fallback
    to strip_markdown_emphasis even though the conversion was correct.
    """
    data = {
        "name": "Test",
        "email": "test@test.com",
        "past_experience": [
            {
                "company_name": "Acme",
                "role": "Dev",
                "description": ["Deployed {config} with **Kubernetes**"],
                "start_date": "2023-01",
                "end_date": "Present",
            }
        ],
    }
    sanitized = sanitize_special_chars(data)
    info = CustomResumeInfo(**sanitized)
    latex = build_resume(info)
    # Must have bold conversion despite escaped braces in same string
    assert r"\textbf{Kubernetes}" in latex
    # Escaped braces must still be present
    assert r"\{config\}" in latex


def test_build_resume_no_emphasis_passthrough():
    """Plain text without emphasis markers passes through unchanged."""
    info = CustomResumeInfo(
        name="Test",
        email="test@test.com",
        past_experience=[
            CustomExperience(
                company_name="Acme",
                role="Dev",
                description=["Built APIs with no special formatting"],
                start_date="2020-01",
                end_date="2023-06",
            )
        ],
    )
    latex = build_resume(info)
    assert "Built APIs with no special formatting" in latex


def test_build_resume_with_projects():
    info = CustomResumeInfo(
        name="Test",
        email="test@test.com",
        projects=[
            CustomProject(
                name="MyProject",
                link="https://github.com/test",
                description=["Feature 1", "Feature 2"],
            )
        ],
    )
    latex = build_resume(info)
    assert "Projects" in latex
    assert "MyProject" in latex
