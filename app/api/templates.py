from fastapi import APIRouter

from app.schemas.templates import ResumeTemplatesResponse
from app.services.latex.templates import (
    DEFAULT_TEMPLATE_ID,
    list_resume_templates,
    serialize_template,
)


router = APIRouter(prefix="/resume-templates", tags=["resume-templates"])


@router.get("/", response_model=ResumeTemplatesResponse)
async def list_templates():
    return {
        "items": [serialize_template(template) for template in list_resume_templates()],
        "default_template_id": DEFAULT_TEMPLATE_ID,
    }
