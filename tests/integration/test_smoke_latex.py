"""Smoke tests for LaTeX compilation — requires pdflatex installed."""
import pytest

from app.schemas.custom_resume import CustomResumeInfo, CustomExperience, CustomSkills, CustomEducation
from app.services.latex.builder import build_resume
from app.services.latex.compiler import compile_latex
from app.services.latex.sanitizer import sanitize_special_chars


@pytest.mark.asyncio
async def test_latex_minimal_resume():
    """Compile a minimal resume to PDF and verify we get bytes back."""
    info = CustomResumeInfo(
        name="Jane Doe",
        email="jane@example.com",
    )
    latex_code = build_resume(info)
    pdf_bytes = await compile_latex(latex_code)

    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 100
    # PDF magic bytes
    assert pdf_bytes[:5] == b"%PDF-"


@pytest.mark.asyncio
async def test_latex_full_resume():
    """Compile a full resume with all sections populated."""
    info = CustomResumeInfo(
        name="John Smith",
        email="john@example.com",
        mobile_number="+1-555-0100",
        summary="Backend engineer with experience building reliable distributed systems.",
        past_experience=[
            CustomExperience(
                company_name="Acme Corp",
                role="Senior Engineer",
                start_date="Jan 2020",
                end_date="Present",
                description=["Led backend team of 5", "Built microservices architecture"],
            ),
        ],
        skills=CustomSkills(
            languages=["Python", "TypeScript"],
            frameworks=["FastAPI", "React"],
            databases=["PostgreSQL", "Redis"],
        ),
        educations=[
            CustomEducation(
                degree="B.S. Computer Science",
                institution="MIT",
                grade="3.9 GPA",
                start_date="2014",
                end_date="2018",
            ),
        ],
        achievements=["Dean's List 2018", "Hackathon Winner"],
    )

    latex_code = build_resume(info)
    pdf_bytes = await compile_latex(latex_code)

    assert pdf_bytes[:5] == b"%PDF-"
    assert len(pdf_bytes) > 500


@pytest.mark.asyncio
async def test_latex_special_chars_survive():
    """Verify that special characters are properly escaped and don't break compilation."""
    info = CustomResumeInfo(
        name="O'Brien & Associates",
        email="test@example.com",
        achievements=["Saved $50k in costs", "Improved speed by 30%"],
    )

    sanitized = sanitize_special_chars(info.model_dump())
    sanitized_info = CustomResumeInfo.model_validate(sanitized)
    latex_code = build_resume(sanitized_info)
    pdf_bytes = await compile_latex(latex_code)

    assert pdf_bytes[:5] == b"%PDF-"


@pytest.mark.asyncio
async def test_latex_legacy_resume_class_still_compiles():
    """Legacy stored LaTeX that still references resume.cls should keep compiling."""
    legacy_latex = r"""
\documentclass{resume}
\usepackage[left=0.4in,top=0.3in,right=0.4in,bottom=0.3in]{geometry}
\usepackage[T1]{fontenc}
\input{glyphtounicode}
\pdfgentounicode=1
\name{Legacy Resume}
\address{legacy@example.com}
\begin{document}
\begin{rSection}{Experience}
\begin{rSubsection}{Acme Corp}{2020 -- Present}{Engineer}{}
\item Built core systems
\end{rSubsection}
\end{rSection}
\end{document}
"""

    pdf_bytes = await compile_latex(legacy_latex)

    assert pdf_bytes[:5] == b"%PDF-"
