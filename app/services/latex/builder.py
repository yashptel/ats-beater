import re

from app.schemas.custom_resume import (
    CustomCertification,
    CustomEducation,
    CustomExperience,
    CustomPaper,
    CustomPatent,
    CustomProject,
    CustomResumeInfo,
)
from app.services.latex.sanitizer import (
    convert_markdown_emphasis,
    handle_special_chars,
    strip_markdown_emphasis,
)
from app.services.latex.templates import ResumeTemplate, get_resume_template


_URL_SCHEME_RE = re.compile(r"^https?://", re.IGNORECASE)


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


def _add_break_opportunities(text: str) -> str:
    return text.replace("/", r"/\allowbreak{}")


def _fmt_body(text: str) -> str:
    return _add_break_opportunities(_fmt(text))


def _join_with_breaks(values: list[str]) -> str:
    return ", ".join(_add_break_opportunities(value) for value in values)


def _is_http_url(url: str | None) -> bool:
    return bool(url and _URL_SCHEME_RE.match(url))


def _display_url(url: str) -> str:
    display = _URL_SCHEME_RE.sub("", url)
    if display.lower().startswith("www."):
        display = display[4:]
    return display.rstrip("/") or display


def _latex_link(url: str | None, label: str, *, underline: bool = True) -> str:
    if not _is_http_url(url):
        return label
    rendered_label = rf"\underline{{{label}}}" if underline else label
    return rf"\href{{{url}}}{{{rendered_label}}}"


def _latex_header_link(url: str | None, label: str) -> str:
    if not _is_http_url(url):
        return label
    return _latex_link(url, handle_special_chars(_display_url(url)))


def _date_range(start_date: str | None, end_date: str | None, *, fallback_present: bool = False) -> str:
    if start_date and end_date:
        return f"{start_date} -- {end_date}"
    if start_date and fallback_present:
        return f"{start_date} -- Present"
    return start_date or end_date or ""


def _start_document(template: ResumeTemplate) -> str:
    if template.id == "jake":
        return r"""
\documentclass[letterpaper,11pt]{article}

\usepackage{latexsym}
\usepackage[empty]{fullpage}
\usepackage{titlesec}
\usepackage[usenames,dvipsnames]{color}
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

    font_setup = (
        r"""
\usepackage[T1]{fontenc}
\usepackage{inconsolata}
\renewcommand{\familydefault}{\ttdefault}
"""
        if template.id == "mono"
        else r"""
\usepackage[T1]{fontenc}
\usepackage{inconsolata}
"""
    )

    return rf"""
\documentclass[letterpaper,11pt]{{article}}

{font_setup}
\usepackage{{latexsym}}
\usepackage[empty]{{fullpage}}
\usepackage{{titlesec}}
\usepackage[usenames,dvipsnames]{{color}}
\usepackage{{enumitem}}
\usepackage[hidelinks]{{hyperref}}
\usepackage{{fancyhdr}}
\usepackage[english]{{babel}}
\usepackage{{tabularx}}
\usepackage{{needspace}}
\input{{glyphtounicode}}

\pagestyle{{fancy}}
\fancyhf{{}}
\fancyfoot{{}}
\renewcommand{{\headrulewidth}}{{0pt}}
\renewcommand{{\footrulewidth}}{{0pt}}
\setlength{{\footskip}}{{6pt}}

\addtolength{{\oddsidemargin}}{{-0.25in}}
\addtolength{{\evensidemargin}}{{-0.25in}}
\addtolength{{\textwidth}}{{0.5in}}
\addtolength{{\topmargin}}{{-0.45in}}
\addtolength{{\textheight}}{{0.85in}}

\urlstyle{{same}}
\raggedbottom
\setlength{{\emergencystretch}}{{2em}}
\sloppy
\setlength{{\parindent}}{{0pt}}

\titleformat{{\section}}[block]
  {{\centering\ttfamily\bfseries}}
  {{}}{{0pt}}
  {{}}
  [\vspace{{-2pt}}\noindent\rule{{\linewidth}}{{0.6pt}}]
\titlespacing*{{\section}}{{0pt}}{{12pt}}{{6pt}}

\pdfgentounicode=1

\newcommand{{\resumeItem}}[1]{{\item\small{{#1}}}}

\newcommand{{\resumeSubheading}}[4]{{%
  \Needspace{{4\baselineskip}}%
  \vspace{{5pt}}\item[]%
  \begin{{tabular*}}{{0.99\textwidth}}[t]{{@{{}}l@{{\extracolsep{{\fill}}}}r@{{}}}}
    \if\relax\detokenize{{#4}}\relax #1\else #1, #4\fi & #2 \\
  \end{{tabular*}}\\*[1pt]
  \textbf{{\small #3}}\vspace{{-1pt}}
}}

\newcommand{{\resumeProjectHeading}}[2]{{%
  \item[]%
  \begin{{tabular*}}{{0.99\textwidth}}{{@{{}}l@{{\extracolsep{{\fill}}}}r@{{}}}}
    \small #1 & \small #2 \\
  \end{{tabular*}}\vspace{{-3pt}}
}}

\renewcommand\labelitemii{{$\vcenter{{\hbox{{\tiny$\bullet$}}}}$}}

\newcommand{{\resumeSubHeadingListStart}}{{\begin{{itemize}}[leftmargin=0in, label={{}}]}}
\newcommand{{\resumeSubHeadingListEnd}}{{\end{{itemize}}}}
\newcommand{{\resumeItemListStart}}{{\begin{{itemize}}[leftmargin=0.24in,itemsep=5pt,topsep=6pt,parsep=0pt,partopsep=0pt,label=$\bullet$]}}
\newcommand{{\resumeItemListEnd}}{{\end{{itemize}}\vspace{{2pt}}}}
"""


def _section(template: ResumeTemplate, title: str) -> str:
    return rf"\section{{{title.upper() if template.uses_uppercase_sections else title}}}"


def _add_header(
    resume_latex: str, resume_info: CustomResumeInfo, template: ResumeTemplate
) -> str:
    header_parts: list[str] = []
    if resume_info.location:
        header_parts.append(resume_info.location)
    if resume_info.mobile_number:
        header_parts.append(resume_info.mobile_number)
    if resume_info.email:
        header_parts.append(rf"\underline{{{resume_info.email}}}")
    if resume_info.date_of_birth:
        header_parts.append(resume_info.date_of_birth)
    for link in resume_info.links:
        header_parts.append(_latex_header_link(link.url, link.name))

    if template.id in {"mono", "hybrid"}:
        primary_parts: list[str] = []
        if resume_info.location:
            primary_parts.append(resume_info.location)
        if resume_info.mobile_number:
            primary_parts.append(resume_info.mobile_number)
        if resume_info.date_of_birth:
            primary_parts.append(resume_info.date_of_birth)

        secondary_parts: list[str] = []
        if resume_info.email:
            secondary_parts.append(rf"\underline{{{resume_info.email}}}")
        for link in resume_info.links:
            secondary_parts.append(_latex_header_link(link.url, link.name))

        lines = [
            r"\begin{document}",
            r"\begin{center}",
            rf"    {{\LARGE\ttfamily\bfseries {resume_info.name}}}\\[4pt]",
        ]
        if primary_parts:
            lines.append(r"    \small " + r" $\cdot$ ".join(primary_parts) + r"\\[3pt]")
        if secondary_parts:
            lines.append(r"    \small " + r" $\cdot$ ".join(secondary_parts))
        lines.append(r"\end{center}")
        return resume_latex + "\n".join(lines) + "\n"

    lines = [
        r"\begin{document}",
        r"\begin{center}",
        rf"    \textbf{{\Huge \scshape {resume_info.name}}} \\ \vspace{{1pt}}",
    ]
    if header_parts:
        lines.append("    \\small " + " $|$ ".join(header_parts))
    lines.append(r"\end{center}")
    return resume_latex + "\n".join(lines) + "\n"


def _add_summary(
    resume_latex: str, resume_info: CustomResumeInfo, template: ResumeTemplate
) -> str:
    if not resume_info.summary:
        return resume_latex
    lines = [
        _section(template, "Summary"),
        rf"\small{{{_fmt_body(resume_info.summary)}}}",
        "",
    ]
    return resume_latex + "\n".join(lines)


def _add_skills(
    resume_latex: str, resume_info: CustomResumeInfo, template: ResumeTemplate
) -> str:
    skills = resume_info.skills
    skill_rows: list[str] = []
    if skills.languages:
        skill_rows.append(rf"\textbf{{Languages:}} {_join_with_breaks(skills.languages)}")
    if skills.frameworks:
        skill_rows.append(
            rf"\textbf{{Frameworks:}} {_join_with_breaks(skills.frameworks)}"
        )
    if skills.databases:
        skill_rows.append(rf"\textbf{{Databases:}} {_join_with_breaks(skills.databases)}")
    if skills.other_technologies:
        skill_rows.append(
            rf"\textbf{{Other Technologies:}} {_join_with_breaks(skills.other_technologies)}"
        )
    if not skill_rows:
        return resume_latex

    if template.id == "jake":
        lines = [
            _section(template, "Technical Skills"),
            r"\begin{itemize}[leftmargin=0.15in, label={}]",
            r"    \small{\item{",
            "     " + r" \\ ".join(skill_rows),
            r"    }}",
            r"\end{itemize}",
            "",
        ]
    else:
        lines = [
            _section(template, "Technical Skills"),
            r"\begin{itemize}[leftmargin=0in, label={}]",
            r"    \small{\item[]{",
            "     " + r" \\ ".join(skill_rows),
            r"    }}",
            r"\end{itemize}",
            "",
        ]
    return resume_latex + "\n".join(lines)


def _add_experience(
    resume_latex: str, resume_info: CustomResumeInfo, template: ResumeTemplate
) -> str:
    if not resume_info.past_experience:
        return resume_latex

    lines = [_section(template, "Experience"), r"\resumeSubHeadingListStart"]
    for exp in resume_info.past_experience:
        role = exp.role
        if exp.department:
            role = f"{role}, {exp.department}"
        lines.append(
            rf"\resumeSubheading{{{exp.company_name}}}{{{_date_range(exp.start_date, exp.end_date, fallback_present=True)}}}{{{role}}}{{{exp.location or ''}}}"
        )
        lines.append(r"\resumeItemListStart")
        descriptions = exp.description or [""]
        for point in descriptions:
            lines.append(rf"\resumeItem{{{_fmt_body(point)}}}")
        lines.append(r"\resumeItemListEnd")
        lines.append("")
    lines.append(r"\resumeSubHeadingListEnd")
    lines.append("")
    return resume_latex + "\n".join(lines)


def _project_heading(project: CustomProject) -> tuple[str, str]:
    left = rf"\textbf{{{project.name}}}"
    right = ""
    if _is_http_url(project.link):
        label = _add_break_opportunities(handle_special_chars(_display_url(project.link)))
        right = _latex_link(project.link, label, underline=False)
    return left, right


def _add_projects(
    resume_latex: str, resume_info: CustomResumeInfo, template: ResumeTemplate
) -> str:
    if not resume_info.projects:
        return resume_latex

    lines = [_section(template, "Projects"), r"\resumeSubHeadingListStart"]
    for project in resume_info.projects:
        left, right = _project_heading(project)
        lines.append(rf"\resumeProjectHeading{{{left}}}{{{right}}}")
        lines.append(r"\resumeItemListStart")
        descriptions = project.description or [""]
        for point in descriptions:
            lines.append(rf"\resumeItem{{{_fmt_body(point)}}}")
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


def _add_education(
    resume_latex: str, resume_info: CustomResumeInfo, template: ResumeTemplate
) -> str:
    if not resume_info.educations:
        return resume_latex

    lines = [_section(template, "Education"), r"\resumeSubHeadingListStart"]
    for education in resume_info.educations:
        top_left, top_right, bottom_left, bottom_right = _education_heading(education)
        lines.append(
            rf"\resumeSubheading{{{top_left}}}{{{top_right}}}{{{bottom_left}}}{{{bottom_right}}}"
        )
        lines.append("")
    lines.append(r"\resumeSubHeadingListEnd")
    lines.append("")
    return resume_latex + "\n".join(lines)


def _add_string_list_section(
    resume_latex: str, title: str, items: list[str], template: ResumeTemplate
) -> str:
    if not items:
        return resume_latex

    margin = "0.15in" if template.id == "jake" else "0.24in"
    lines = [_section(template, title), rf"\begin{{itemize}}[leftmargin={margin}]"]
    for item in items:
        lines.append(rf"\resumeItem{{{_fmt_body(item)}}}")
    lines.append(r"\end{itemize}")
    lines.append("")
    return resume_latex + "\n".join(lines)


def _certification_text(certification: CustomCertification) -> str:
    text = _fmt_body(certification.name)
    if not certification.credential_id:
        return text
    if _is_http_url(certification.credential_id):
        return text + rf" -- {_latex_link(certification.credential_id, 'Verify', underline=False)}"
    return text + f" -- ID: {certification.credential_id}"


def _add_certifications(
    resume_latex: str, resume_info: CustomResumeInfo, template: ResumeTemplate
) -> str:
    items = [_certification_text(certification) for certification in resume_info.certifications]
    return _add_string_list_section(resume_latex, "Certifications", items, template)


def _patent_text(patent: CustomPatent) -> str:
    text = _fmt_body(patent.name)
    if patent.date:
        text += f" ({patent.date})"
    if patent.description:
        text += f": {_fmt_body(patent.description)}"
    return text


def _add_patents(
    resume_latex: str, resume_info: CustomResumeInfo, template: ResumeTemplate
) -> str:
    items = [_patent_text(patent) for patent in resume_info.patents]
    return _add_string_list_section(resume_latex, "Patents", items, template)


def _paper_text(paper: CustomPaper) -> str:
    text = _fmt_body(paper.name)
    if paper.date:
        text += f" ({paper.date})"
    if paper.description:
        text += f": {_fmt_body(paper.description)}"
    return text


def _add_publications(
    resume_latex: str, resume_info: CustomResumeInfo, template: ResumeTemplate
) -> str:
    items = [_paper_text(paper) for paper in resume_info.papers]
    return _add_string_list_section(resume_latex, "Publications", items, template)


def _add_achievements(
    resume_latex: str, resume_info: CustomResumeInfo, template: ResumeTemplate
) -> str:
    return _add_string_list_section(
        resume_latex, "Achievements", resume_info.achievements, template
    )


def build_resume(resume_info: CustomResumeInfo, template_id: str | None = None) -> str:
    """Build a complete LaTeX resume from CustomResumeInfo. Data must already be sanitized."""
    template = get_resume_template(template_id)
    resume_latex = _start_document(template)
    resume_latex = _add_header(resume_latex, resume_info, template)
    resume_latex = _add_summary(resume_latex, resume_info, template)
    resume_latex = _add_skills(resume_latex, resume_info, template)
    resume_latex = _add_experience(resume_latex, resume_info, template)
    resume_latex = _add_projects(resume_latex, resume_info, template)
    resume_latex = _add_education(resume_latex, resume_info, template)
    resume_latex = _add_achievements(resume_latex, resume_info, template)
    resume_latex = _add_certifications(resume_latex, resume_info, template)
    resume_latex = _add_patents(resume_latex, resume_info, template)
    resume_latex = _add_publications(resume_latex, resume_info, template)
    resume_latex += r"\end{document}"
    return resume_latex
