from dataclasses import dataclass


DEFAULT_TEMPLATE_ID = "jake"


@dataclass(frozen=True)
class ResumeTemplate:
    id: str
    name: str
    description: str
    density_hint: str
    section_style: str

    @property
    def uses_uppercase_sections(self) -> bool:
        return self.section_style == "uppercase"


RESUME_TEMPLATES: tuple[ResumeTemplate, ...] = (
    ResumeTemplate(
        id="jake",
        name="Jake",
        description="Classic ATS-friendly layout with compact spacing and familiar section rules.",
        density_hint="Compact layout. Supports slightly denser bullets while staying readable.",
        section_style="title",
    ),
    ResumeTemplate(
        id="mono",
        name="Mono",
        description="Typewriter-style resume using Inconsolata throughout with roomier spacing.",
        density_hint="Roomier layout. Prefer fewer, tighter bullets so the resume does not spill.",
        section_style="uppercase",
    ),
    ResumeTemplate(
        id="hybrid",
        name="Hybrid",
        description="Monospace name and section headings with a proportional body for balance.",
        density_hint="Balanced layout. Keep bullets concise and avoid overfilling sections.",
        section_style="uppercase",
    ),
)

_TEMPLATE_BY_ID = {template.id: template for template in RESUME_TEMPLATES}


def list_resume_templates() -> list[ResumeTemplate]:
    return list(RESUME_TEMPLATES)


def normalize_template_id(template_id: str | None) -> str:
    if template_id in _TEMPLATE_BY_ID:
        return template_id
    return DEFAULT_TEMPLATE_ID


def get_resume_template(template_id: str | None) -> ResumeTemplate:
    return _TEMPLATE_BY_ID[normalize_template_id(template_id)]


def ensure_valid_template_id(template_id: str) -> str:
    if template_id not in _TEMPLATE_BY_ID:
        allowed = ", ".join(sorted(_TEMPLATE_BY_ID))
        raise ValueError(f"Invalid resume template '{template_id}'. Allowed templates: {allowed}")
    return template_id


def serialize_template(template: ResumeTemplate) -> dict:
    return {
        "id": template.id,
        "name": template.name,
        "description": template.description,
        "density_hint": template.density_hint,
    }
