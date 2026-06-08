from app.schemas.custom_resume import (
    CustomExperience,
    CustomLink,
    CustomProject,
    CustomResumeInfo,
    CustomSkills,
)
from app.services.latex.builder import build_resume
from app.services.latex.sanitizer import sanitize_special_chars


def test_build_resume_minimal():
    info = CustomResumeInfo(
        name="John Doe",
        email="john@example.com",
    )
    latex = build_resume(info)
    assert r"\documentclass[letterpaper,11pt]{article}" in latex
    assert r"\documentclass{resume}" not in latex
    assert r"\textbf{\Huge \scshape John Doe}" in latex
    assert r"\begin{document}" in latex
    assert r"\end{document}" in latex


def test_build_resume_with_location_in_header():
    info = CustomResumeInfo(
        name="John Doe",
        email="john@example.com",
        mobile_number="+1-555-0100",
        location="Bengaluru, India",
    )
    latex = build_resume(info)
    assert "Bengaluru, India" in latex
    assert "+1-555-0100" in latex


def test_build_resume_mono_template_uses_typewriter_style():
    info = CustomResumeInfo(
        name="John Doe",
        email="john@example.com",
        location="Remote",
        summary="Backend engineer.",
    )
    latex = build_resume(info, template_id="mono")
    assert r"\usepackage{inconsolata}" in latex
    assert r"\renewcommand{\familydefault}{\ttdefault}" in latex
    assert r"\section{SUMMARY}" in latex
    assert r"\section{Summary}" not in latex
    assert r"{\ttfamily\bfseries\fontsize{22pt}{25.3pt}\selectfont John Doe}" in latex
    assert r"\vspace{14pt}" in latex
    assert r"{\ttfamily\bfseries\fontsize{22pt}{25.3pt}\selectfont John Doe}\\[6pt]" in latex
    assert r"{\ttfamily\bfseries\fontsize{22pt}{25.3pt}\selectfont John Doe}\\\\[6pt]" not in latex
    assert r"Remote\\[0pt]" in latex
    assert r"\end{center}\vspace{-6pt}" not in latex


def test_build_resume_mono_template_uses_google_docs_spacing():
    info = CustomResumeInfo(
        name="John Doe",
        email="john@example.com",
        summary="Backend engineer.",
    )

    latex = build_resume(info, template_id="mono")

    assert r"\documentclass[letterpaper,11pt]{article}" in latex
    assert r"\usepackage[letterpaper,top=0.7cm,bottom=0.5cm,left=1.8cm,right=1.8cm]{geometry}" in latex
    assert r"\usepackage{setspace}" in latex
    assert r"\setstretch{1.15}" in latex
    assert r"\renewcommand{\arraystretch}{1.15}" in latex
    assert r"\setlength{\parskip}{0pt}" in latex
    assert r"\centering\ttfamily\bfseries\fontsize{12pt}{13.8pt}\selectfont" in latex
    assert r"[\vspace{-8pt}\noindent\rule{\linewidth}{0.8pt}]" in latex
    assert r"\titlespacing*{\section}{0pt}{8pt}{0pt}" in latex
    assert (
        r"\begin{itemize}[leftmargin=0in,label={},itemsep=0pt,topsep=0pt,parsep=0pt,partopsep=0pt]"
        in latex
    )
    assert (
        r"\begin{itemize}[leftmargin=0in,label={},itemsep=0pt,topsep=10pt,parsep=0pt,partopsep=0pt]"
        in latex
    )
    assert (
        r"\begin{itemize}[leftmargin=0.30in,itemsep=6pt,topsep=8pt,parsep=0pt,partopsep=0pt,label=$\bullet$]"
        in latex
    )
    assert r"\newcommand{\resumeItemListEnd}{\end{itemize}\vspace{6pt}}" in latex


def test_build_resume_hybrid_template_keeps_proportional_body():
    info = CustomResumeInfo(
        name="John Doe",
        email="john@example.com",
        summary="Backend engineer.",
    )
    latex = build_resume(info, template_id="hybrid")
    assert r"\usepackage{inconsolata}" in latex
    assert r"\renewcommand{\familydefault}{\ttdefault}" not in latex
    assert r"\section{SUMMARY}" in latex


def test_build_resume_template_header_links_show_urls_not_platform_labels():
    info = CustomResumeInfo(
        name="John Doe",
        email="john@example.com",
        links=[
            CustomLink(name="LinkedIn", url="https://linkedin.com/in/johndoe"),
            CustomLink(name="GitHub", url="https://github.com/johndoe"),
        ],
    )

    latex = build_resume(info, template_id="mono")

    assert (
        r"\href{https://linkedin.com/in/johndoe}{\underline{linkedin.com/in/johndoe}}"
        in latex
    )
    assert r"\href{https://github.com/johndoe}{\underline{github.com/johndoe}}" in latex
    assert r"\href{https://linkedin.com/in/johndoe}{\underline{LinkedIn}}" not in latex
    assert r"\href{https://github.com/johndoe}{\underline{GitHub}}" not in latex


def test_build_resume_mono_template_adds_wrapping_guardrails():
    info = CustomResumeInfo(
        name="John Doe",
        email="john@example.com",
        summary="Built CI/CD systems for long-running platform migrations.",
        past_experience=[
            CustomExperience(
                company_name="Acme",
                role="Engineer",
                description=[
                    "Merged oss-serverless/serverless fallback support across CI/CD workflows.",
                ],
            )
        ],
    )

    latex = build_resume(info, template_id="mono")

    assert r"\setlength{\emergencystretch}" in latex
    assert r"\sloppy" in latex
    assert r"CI/\allowbreak{}CD" in latex
    assert r"oss-serverless/\allowbreak{}serverless" in latex


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
    assert "Technical Skills" in latex
    assert r"\textbf{Languages:}" in latex
    assert "Python" in latex
    assert "FastAPI" in latex


def test_build_resume_mono_template_gives_skills_custom_line_spacing():
    info = CustomResumeInfo(
        name="Test",
        email="test@test.com",
        skills=CustomSkills(languages=["Python", "Java"]),
    )

    latex = build_resume(info, template_id="mono")

    assert r"{\setstretch{1.3}" in latex
    assert (
        r"\begin{itemize}[leftmargin=0in,label={},itemsep=0pt,topsep=0pt,parsep=0pt,partopsep=0pt]"
        in latex
    )
    assert latex.index(r"{\setstretch{1.3}") < latex.index(r"\textbf{Languages:}")


def test_build_resume_with_summary():
    info = CustomResumeInfo(
        name="Test",
        email="test@test.com",
        summary="Backend engineer with experience building reliable APIs.",
        skills=CustomSkills(languages=["Python"]),
        past_experience=[
            CustomExperience(
                company_name="Acme",
                role="Dev",
                description=["Built APIs"],
                start_date="2020-01",
                end_date="2023-06",
            )
        ],
    )
    latex = build_resume(info)
    assert r"\section{Summary}" in latex
    assert "Backend engineer with experience building reliable APIs." in latex
    assert latex.index(r"\section{Summary}") < latex.index(r"\section{Technical Skills}")
    assert latex.index(r"\section{Technical Skills}") < latex.index(r"\section{Experience}")


def test_build_resume_omits_summary_when_empty():
    info = CustomResumeInfo(
        name="Test",
        email="test@test.com",
    )
    latex = build_resume(info)
    assert r"\section{Summary}" not in latex


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


def test_build_resume_achievements_use_standard_resume_item_list():
    """Standalone list sections should use the same bullet macro as resume body."""
    info = CustomResumeInfo(
        name="Test",
        email="test@test.com",
        achievements=["Ranked in the top 100 out of 15,000 participants"],
    )

    latex = build_resume(info, template_id="mono")
    section = latex.split(r"\section{ACHIEVEMENTS}", 1)[1]

    assert r"\resumeItemListStart" in section
    assert r"\resumeItem{Ranked in the top 100 out of 15,000 participants}" in section
    assert r"\resumeItemListEnd" in section
    assert r"\begin{itemize}[leftmargin=0.24in]" not in section


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
    latex = build_resume(info, template_id="mono")
    assert "PROJECTS" in latex
    assert "MyProject" in latex
    assert r"\resumeProjectHeading" in latex
    assert r"\end{tabular*}\vspace{-4pt}" in latex
    assert (
        r"\begin{itemize}[leftmargin=0in,label={},itemsep=0pt,topsep=10pt,parsep=0pt,partopsep=0pt]"
        in latex
    )
    assert (
        r"\resumeProjectHeading{\textbf{MyProject}}{\href{https://github.com/test}{github.com/\allowbreak{}test}}"
        in latex
    )
    assert r"\href{https://github.com/test}{\underline{\textbf{MyProject}}}" not in latex
    assert "}{\\underline{Link}}" not in latex
