from app.schemas.custom_resume import (
    CustomCertification,
    CustomEducation,
    CustomExperience,
    CustomPaper,
    CustomPatent,
    CustomProject,
    CustomResumeInfo,
)
from app.services.latex.sanitizer import convert_markdown_emphasis, strip_markdown_emphasis


def _fmt(text: str) -> str:
    """Convert markdown emphasis to LaTeX commands, with fallback to stripping."""
    try:
        result = convert_markdown_emphasis(text)
        added_open = result.count("{") - text.count("{")
        added_close = result.count("}") - text.count("}")
        if added_open != added_close:
            return strip_markdown_emphasis(text)
        return result
    except Exception:
        return strip_markdown_emphasis(text)


def _is_http_url(url: str | None) -> bool:
    return bool(url and url.startswith(("http://", "https://")))


def _latex_link(url: str | None, label: str, *, underline: bool = True) -> str:
    if not _is_http_url(url):
        return label
    rendered_label = rf"\underline{{{label}}}" if underline else label
    return rf"\href{{{url}}}{{{rendered_label}}}"


def _date_range(start_date: str | None, end_date: str | None, *, fallback_present: bool = False) -> str:
    if start_date and end_date:
        return f"{start_date} -- {end_date}"
    if start_date and fallback_present:
        return f"{start_date} -- Present"
    return start_date or end_date or ""


def _start_document() -> str:
    return r"""
\documentclass[letterpaper,11pt]{article}

\usepackage{latexsym}
\usepackage[empty]{fullpage}
\usepackage{titlesec}
\usepackage{enumitem}
\usepackage[hidelinks]{hyperref}
\usepackage{fancyhdr}
\usepackage[english]{babel}
\usepackage{tabularx}
\usepackage{array}
\input{glyphtounicode}

\pagestyle{fancy}
\fancyhf{}
\fancyfoot{}
\renewcommand{\headrulewidth}{0pt}
\renewcommand{\footrulewidth}{0pt}
\setlength{\footskip}{6pt}

\addtolength{\oddsidemargin}{-0.5in}
\addtolength{\evensidemargin}{-0.5in}
\addtolength{\textwidth}{1in}
\addtolength{\topmargin}{-0.5in}
\addtolength{\textheight}{1.0in}

\urlstyle{same}
\raggedbottom
\raggedright
\setlength{\tabcolsep}{0in}
\newlength{\datecolumnwidth}
\setlength{\datecolumnwidth}{1.75in}

\titleformat{\section}{
  \vspace{-4pt}\scshape\raggedright\large
}{}{0em}{}[\titlerule \vspace{-5pt}]

\pdfgentounicode=1

\newcommand{\resumeItem}[1]{
  \item\small{{#1 \vspace{-2pt}}}
}

\newcommand{\resumeSubheading}[4]{
  \vspace{-2pt}\item
    \begin{tabular*}{0.97\textwidth}[t]{@{}p{\dimexpr0.97\textwidth-\datecolumnwidth\relax}@{\extracolsep{\fill}}>{\raggedleft\arraybackslash}p{\datecolumnwidth}@{}}
      \textbf{#1} & \textbf{#2} \\
      \textit{\small#3} & \textit{\small #4} \\
    \end{tabular*}\vspace{-5pt}
}

\newcommand{\resumeProjectHeading}[2]{
    \item
    \begin{tabular*}{0.97\textwidth}{@{}p{\dimexpr0.97\textwidth-\datecolumnwidth\relax}@{\extracolsep{\fill}}>{\raggedleft\arraybackslash}p{\datecolumnwidth}@{}}
      \small #1 & \small #2 \\
    \end{tabular*}\vspace{-5pt}
}

\newcommand{\resumeSubHeadingListStart}{\begin{itemize}[leftmargin=0.15in, label={}]}
\newcommand{\resumeSubHeadingListEnd}{\end{itemize}}
\newcommand{\resumeItemListStart}{\begin{itemize}[leftmargin=0.18in,itemsep=2pt,topsep=3pt,parsep=0pt,partopsep=0pt]}
\newcommand{\resumeItemListEnd}{\end{itemize}\vspace{-1pt}}
"""


def _add_header(resume_latex: str, resume_info: CustomResumeInfo) -> str:
    header_parts: list[str] = []
    if resume_info.mobile_number:
        header_parts.append(resume_info.mobile_number)
    if resume_info.email:
        header_parts.append(rf"\underline{{{resume_info.email}}}")
    if resume_info.date_of_birth:
        header_parts.append(resume_info.date_of_birth)
    for link in resume_info.links:
        header_parts.append(_latex_link(link.url, link.name))

    lines = [
        r"\begin{document}",
        r"\begin{center}",
        rf"    \textbf{{\Huge \scshape {resume_info.name}}} \\ \vspace{{1pt}}",
    ]
    if header_parts:
        lines.append("    \\small " + " $|$ ".join(header_parts))
    lines.append(r"\end{center}")
    return resume_latex + "\n".join(lines) + "\n"


def _add_summary(resume_latex: str, resume_info: CustomResumeInfo) -> str:
    if not resume_info.summary:
        return resume_latex
    lines = [
        r"\section{Summary}",
        rf"\small{{{_fmt(resume_info.summary)}}}",
        "",
    ]
    return resume_latex + "\n".join(lines)


def _add_skills(resume_latex: str, resume_info: CustomResumeInfo) -> str:
    skills = resume_info.skills
    skill_rows: list[str] = []
    if skills.languages:
        skill_rows.append(rf"\textbf{{Languages:}} {', '.join(skills.languages)}")
    if skills.frameworks:
        skill_rows.append(rf"\textbf{{Frameworks:}} {', '.join(skills.frameworks)}")
    if skills.databases:
        skill_rows.append(rf"\textbf{{Databases:}} {', '.join(skills.databases)}")
    if skills.other_technologies:
        skill_rows.append(
            rf"\textbf{{Other Technologies:}} {', '.join(skills.other_technologies)}"
        )
    if not skill_rows:
        return resume_latex

    lines = [
        r"\section{Technical Skills}",
        r"\begin{itemize}[leftmargin=0.15in, label={}]",
        r"    \small{\item{",
        "     " + r" \\ ".join(skill_rows),
        r"    }}",
        r"\end{itemize}",
        "",
    ]
    return resume_latex + "\n".join(lines)


def _add_experience(resume_latex: str, resume_info: CustomResumeInfo) -> str:
    if not resume_info.past_experience:
        return resume_latex

    lines = [r"\section{Experience}", r"\resumeSubHeadingListStart"]
    for exp in resume_info.past_experience:
        lines.append(
            rf"\resumeSubheading{{{exp.company_name}}}{{{_date_range(exp.start_date, exp.end_date, fallback_present=True)}}}{{{exp.role}}}{{}}"
        )
        lines.append(r"\resumeItemListStart")
        descriptions = exp.description or [""]
        for point in descriptions:
            lines.append(rf"\resumeItem{{{_fmt(point)}}}")
        lines.append(r"\resumeItemListEnd")
        lines.append("")
    lines.append(r"\resumeSubHeadingListEnd")
    lines.append("")
    return resume_latex + "\n".join(lines)


def _project_heading(project: CustomProject) -> tuple[str, str]:
    left = rf"\textbf{{{project.name}}}"
    if _is_http_url(project.link):
        left = _latex_link(project.link, rf"\textbf{{{project.name}}}")
    return left, ""


def _add_projects(resume_latex: str, resume_info: CustomResumeInfo) -> str:
    if not resume_info.projects:
        return resume_latex

    lines = [r"\section{Projects}", r"\resumeSubHeadingListStart"]
    for project in resume_info.projects:
        left, right = _project_heading(project)
        lines.append(rf"\resumeProjectHeading{{{left}}}{{{right}}}")
        lines.append(r"\resumeItemListStart")
        descriptions = project.description or [""]
        for point in descriptions:
            lines.append(rf"\resumeItem{{{_fmt(point)}}}")
        lines.append(r"\resumeItemListEnd")
        lines.append("")
    lines.append(r"\resumeSubHeadingListEnd")
    lines.append("")
    return resume_latex + "\n".join(lines)


def _education_heading(education: CustomEducation) -> tuple[str, str, str, str]:
    top_left = education.institution
    top_right = _date_range(education.start_date, education.end_date)
    bottom_left = education.degree
    bottom_right = education.grade or ""
    return top_left, top_right, bottom_left, bottom_right


def _add_education(resume_latex: str, resume_info: CustomResumeInfo) -> str:
    if not resume_info.educations:
        return resume_latex

    lines = [r"\section{Education}", r"\resumeSubHeadingListStart"]
    for education in resume_info.educations:
        top_left, top_right, bottom_left, bottom_right = _education_heading(education)
        lines.append(
            rf"\resumeSubheading{{{top_left}}}{{{top_right}}}{{{bottom_left}}}{{{bottom_right}}}"
        )
        lines.append("")
    lines.append(r"\resumeSubHeadingListEnd")
    lines.append("")
    return resume_latex + "\n".join(lines)


def _add_string_list_section(resume_latex: str, title: str, items: list[str]) -> str:
    if not items:
        return resume_latex

    lines = [rf"\section{{{title}}}", r"\begin{itemize}[leftmargin=0.15in]"]
    for item in items:
        lines.append(rf"\resumeItem{{{_fmt(item)}}}")
    lines.append(r"\end{itemize}")
    lines.append("")
    return resume_latex + "\n".join(lines)


def _certification_text(certification: CustomCertification) -> str:
    text = _fmt(certification.name)
    if not certification.credential_id:
        return text
    if _is_http_url(certification.credential_id):
        return text + rf" -- {_latex_link(certification.credential_id, 'Verify', underline=False)}"
    return text + f" -- ID: {certification.credential_id}"


def _add_certifications(resume_latex: str, resume_info: CustomResumeInfo) -> str:
    items = [_certification_text(certification) for certification in resume_info.certifications]
    return _add_string_list_section(resume_latex, "Certifications", items)


def _patent_text(patent: CustomPatent) -> str:
    text = _fmt(patent.name)
    if patent.date:
        text += f" ({patent.date})"
    if patent.description:
        text += f": {_fmt(patent.description)}"
    return text


def _add_patents(resume_latex: str, resume_info: CustomResumeInfo) -> str:
    items = [_patent_text(patent) for patent in resume_info.patents]
    return _add_string_list_section(resume_latex, "Patents", items)


def _paper_text(paper: CustomPaper) -> str:
    text = _fmt(paper.name)
    if paper.date:
        text += f" ({paper.date})"
    if paper.description:
        text += f": {_fmt(paper.description)}"
    return text


def _add_publications(resume_latex: str, resume_info: CustomResumeInfo) -> str:
    items = [_paper_text(paper) for paper in resume_info.papers]
    return _add_string_list_section(resume_latex, "Publications", items)


def _add_achievements(resume_latex: str, resume_info: CustomResumeInfo) -> str:
    return _add_string_list_section(resume_latex, "Achievements", resume_info.achievements)


def build_resume(resume_info: CustomResumeInfo) -> str:
    """Build a complete LaTeX resume from CustomResumeInfo. Data must already be sanitized."""
    resume_latex = _start_document()
    resume_latex = _add_header(resume_latex, resume_info)
    resume_latex = _add_summary(resume_latex, resume_info)
    resume_latex = _add_skills(resume_latex, resume_info)
    resume_latex = _add_experience(resume_latex, resume_info)
    resume_latex = _add_projects(resume_latex, resume_info)
    resume_latex = _add_education(resume_latex, resume_info)
    resume_latex = _add_achievements(resume_latex, resume_info)
    resume_latex = _add_certifications(resume_latex, resume_info)
    resume_latex = _add_patents(resume_latex, resume_info)
    resume_latex = _add_publications(resume_latex, resume_info)
    resume_latex += r"\end{document}"
    return resume_latex
