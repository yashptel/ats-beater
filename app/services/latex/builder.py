from app.schemas.custom_resume import CustomResumeInfo
from app.services.latex.sanitizer import convert_markdown_emphasis, sanitize_special_chars, strip_markdown_emphasis


def _fmt(text: str) -> str:
    """Convert markdown emphasis to LaTeX commands, with fallback to stripping."""
    try:
        result = convert_markdown_emphasis(text)
        # Sanity check: braces *added* by conversion must be balanced.
        # Using delta avoids false positives from pre-existing escaped braces
        # (e.g. \{ from sanitizer) that skew absolute counts.
        added_open = result.count("{") - text.count("{")
        added_close = result.count("}") - text.count("}")
        if added_open != added_close:
            return strip_markdown_emphasis(text)
        return result
    except Exception:
        return strip_markdown_emphasis(text)


def _add_header(resume_latex: str, resume_info: CustomResumeInfo) -> str:
    resume = resume_latex
    resume += f"\n\\name{{{resume_info.name}}}  \n"

    address_section = ""
    contact_section = r"""\address{"""
    contact_info = [resume_info.mobile_number, resume_info.email, resume_info.date_of_birth]
    contact_info = [info for info in contact_info if info]

    if contact_info:
        contact_section += " \\\\ ".join(contact_info) + "}"
        address_section += contact_section

    links_info = resume_info.links
    if links_info:
        links_section = r"""\address{"""
        for link in links_info:
            links_section += f"\\href{{{link.url}}}{{{link.name}}} | "
        links_section = links_section[:-2] + "}"
        address_section += links_section

    resume += address_section + "\n"
    return resume


def _add_experience(resume_latex: str, resume_info: CustomResumeInfo) -> str:
    if not resume_info.past_experience:
        return resume_latex
    section = r"""\begin{rSection}{Experience}"""
    for exp in resume_info.past_experience:
        date_range = f"{exp.start_date or ''} -- {exp.end_date or 'Present'}"
        section += f"\\begin{{rSubsection}}{{{exp.company_name}}}{{{date_range}}}{{{exp.role}}}{{}}\n"
        if exp.description:
            for point in exp.description:
                section += f"\\item {_fmt(point)}\n"
        else:
            section += "\\item{}\n"  # LaTeX list requires at least one \item
        section += "\\end{rSubsection}\n"
    section += r"""\end{rSection}"""
    return resume_latex + section + "\n"


def _add_projects(resume_latex: str, resume_info: CustomResumeInfo) -> str:
    if not resume_info.projects:
        return resume_latex
    section = r"""\begin{rSection}{Projects}"""
    for project in resume_info.projects:
        link = project.link
        has_valid_link = link and link.startswith(("http://", "https://"))
        if has_valid_link:
            section += f"\\begin{{rSubsection}}{{\\href{{{link}}}{{{project.name}}}}}{{}}{{}}{{}}\\vspace{{-0.8em}}\n"
        else:
            section += f"\\begin{{rSubsection}}{{{project.name}}}{{}}{{}}{{}}\\vspace{{-0.8em}}\n"
        if project.description:
            for point in project.description:
                section += f"\\item {_fmt(point)}\n"
        else:
            section += "\\item{}\n"  # LaTeX list requires at least one \item
        section += "\\end{rSubsection}\n"
    section += r"""\end{rSection}"""
    return resume_latex + section + "\n"


def _add_skills(resume_latex: str, resume_info: CustomResumeInfo) -> str:
    skills = resume_info.skills
    has_skills = skills.languages or skills.frameworks or skills.databases or skills.other_technologies
    if not has_skills:
        return resume_latex

    section = r"""\begin{rSection}{Skills}
\begin{tabularx}{\textwidth}{@{}l X@{}}
"""
    if skills.languages:
        section += f"\\textbf{{Languages:}} & {', '.join(skills.languages)} \\\\"
    if skills.frameworks:
        section += f"\\textbf{{Frameworks:}} & {', '.join(skills.frameworks)} \\\\"
    if skills.databases:
        section += f"\\textbf{{Databases:}} & {', '.join(skills.databases)} \\\\"
    if skills.other_technologies:
        section += f"\\textbf{{Platforms/Other Technologies:}} & {', '.join(skills.other_technologies)} \\\\"

    section += r"""\end{tabularx}
\end{rSection}"""
    return resume_latex + section + "\n"


def _add_education(resume_latex: str, resume_info: CustomResumeInfo) -> str:
    if not resume_info.educations:
        return resume_latex
    lines = [r"\begin{rSection}{Education}"]
    for edu in resume_info.educations:
        entry = f"{{\\bf {edu.institution or ''}}} \\hfill {edu.grade or ''} \\\\"
        entry += f"\\textit{{{edu.degree or ''}}}"
        if edu.start_date or edu.end_date:
            entry += f"\\hfill {edu.start_date or ''}"
            if edu.start_date and edu.end_date:
                entry += f" -- {edu.end_date}"
            elif edu.end_date:
                entry += f"{edu.end_date}"
        lines.append(entry)
        lines.append(r"\\[0.2cm]")
    lines.pop()  # Remove last spacing
    lines.append(r"\end{rSection}")
    return resume_latex + "\n".join(lines) + "\n"


def _add_certifications(resume_latex: str, resume_info: CustomResumeInfo) -> str:
    if not resume_info.certifications:
        return resume_latex
    section = r"""\begin{rSection}{Certifications}"""
    section += r"""\begin{itemize}\itemsep -0.2em"""
    for cert in resume_info.certifications:
        section += f"\\item {_fmt(cert.name)}"
        if cert.credential_id:
            if cert.credential_id.startswith(("http://", "https://")):
                section += f" — \\href{{{cert.credential_id}}}{{Verify}}"
            else:
                section += f" — ID: {cert.credential_id}"
    section += r"""\end{itemize}"""
    section += r"""\end{rSection}"""
    return resume_latex + section + "\n"


def _add_patents(resume_latex: str, resume_info: CustomResumeInfo) -> str:
    if not resume_info.patents:
        return resume_latex
    section = r"""\begin{rSection}{Patents}"""
    section += r"""\begin{itemize}\itemsep -0.2em"""
    for patent in resume_info.patents:
        section += f"\\item {_fmt(patent.name)}"
        if patent.date:
            section += f" ({patent.date})"
        if patent.description:
            section += f": {_fmt(patent.description)}"
    section += r"""\end{itemize}"""
    section += r"""\end{rSection}"""
    return resume_latex + section + "\n"


def _add_publications(resume_latex: str, resume_info: CustomResumeInfo) -> str:
    if not resume_info.papers:
        return resume_latex
    section = r"""\begin{rSection}{Publications}"""
    section += r"""\begin{itemize}\itemsep -0.2em"""
    for paper in resume_info.papers:
        section += f"\\item {_fmt(paper.name)}"
        if paper.date:
            section += f" ({paper.date})"
        if paper.description:
            section += f": {_fmt(paper.description)}"
    section += r"""\end{itemize}"""
    section += r"""\end{rSection}"""
    return resume_latex + section + "\n"


def _add_achievements(resume_latex: str, resume_info: CustomResumeInfo) -> str:
    if not resume_info.achievements:
        return resume_latex
    section = r"""\begin{rSection}{Achievements}"""
    section += r"""\begin{itemize}\itemsep -0.2em"""
    for achievement in resume_info.achievements:
        section += f"\\item {_fmt(achievement)}\n"
    section += r"""\end{itemize}"""
    section += r"""\end{rSection}"""
    return resume_latex + section + "\n"


def build_resume(resume_info: CustomResumeInfo) -> str:
    """Build a complete LaTeX resume from CustomResumeInfo. Data must already be sanitized."""
    resume_latex = r"""
\documentclass{resume}
\usepackage[left=0.4in,top=0.3in,right=0.4in,bottom=0.3in]{geometry}
\usepackage{tabularx}
\usepackage[T1]{fontenc}
\usepackage{lmodern}
\input{glyphtounicode}
\pdfgentounicode=1

"""
    resume_latex = _add_header(resume_latex, resume_info)
    resume_latex += r"""\begin{document}"""
    resume_latex = _add_experience(resume_latex, resume_info)
    resume_latex = _add_projects(resume_latex, resume_info)
    resume_latex = _add_skills(resume_latex, resume_info)
    resume_latex = _add_education(resume_latex, resume_info)
    resume_latex = _add_achievements(resume_latex, resume_info)
    resume_latex = _add_certifications(resume_latex, resume_info)
    resume_latex = _add_patents(resume_latex, resume_info)
    resume_latex = _add_publications(resume_latex, resume_info)
    resume_latex += r"""\end{document}"""
    return resume_latex
