import math
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.session import get_db
from app.main import create_tracked_task
from app.models.job import JobStatus
from app.models.user import User
from app.dependencies import get_current_user
from app.services.job.service import JobService
from app.services.credit.service import CreditService
from app.schemas.job import JobCreate
from logging import getLogger

logger = getLogger(__name__)

router = APIRouter(prefix="/jobs", tags=["jobs"])
service = JobService()
credit_service = CreditService()


def _pdf_filename(job) -> str:
    """Build a descriptive PDF filename from job data."""
    jd = job.job_description or {}
    cr = job.custom_resume_data or {}
    name = cr.get("name", "")
    role = jd.get("role", "")
    company = jd.get("company", "")
    if name and role and company:
        filename = f"{name} - {role} ({company}).pdf"
    elif role and company:
        filename = f"{role} ({company}).pdf"
    else:
        filename = f"resume_{job.id}.pdf"
    for ch in '/\\?%*:|"<>':
        filename = filename.replace(ch, "")
    return filename


@router.get("/")
async def list_jobs(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    offset = (page - 1) * limit
    jobs, total = await service.get_jobs(db, current_user.id, offset=offset, limit=limit)
    return {
        "items": [
            {
                "id": j.id,
                "profile_id": j.profile_id,
                "job_description": j.job_description,
                "candidate_name": (j.custom_resume_data or {}).get("name"),
                "status": j.status.value,
                "created_at": j.created_at.isoformat(),
                "updated_at": j.updated_at.isoformat(),
            }
            for j in jobs
        ],
        "total": total,
        "page": page,
        "pages": math.ceil(total / limit) if total > 0 else 1,
        "limit": limit,
    }


@router.post("/", status_code=201)
async def create_job(
    payload: JobCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Pre-check credits before creating the job — don't leave dead PENDING jobs
    has_credits = await credit_service.has_credits_available(db, current_user.id)
    if not has_credits:
        from app.exceptions import UsageLimitExceeded
        raise UsageLimitExceeded("No credits available. Purchase credits or wait for daily free credits to reset.")
    job = await service.create_job(db, current_user.id, payload.profile_id, payload.job_description)
    return {"job_id": job.id, "status": job.status.value}


@router.post("/{job_id}/generate-resume", status_code=202)
async def generate_resume(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # SELECT FOR UPDATE prevents double-charge race: second concurrent request
    # blocks here until the first commits GENERATING_RESUME, then fails the guard.
    job = await service.get_job(db, job_id, current_user.id, for_update=True)

    # Guard: only allow generation from PENDING or FAILED states
    if job.status.value not in ("PENDING", "FAILED"):
        raise ValueError(
            f"Job is already {job.status.value} — cannot re-generate"
        )

    # Deduct credit synchronously — raises 429 if no credits available
    source = await credit_service.check_and_deduct(db, current_user.id, job_id)

    # Update status synchronously to prevent double-charge on rapid re-calls
    job.status = JobStatus.GENERATING_RESUME
    await db.commit()

    from app.database.session import async_session_factory

    user_id = current_user.id

    async def _generate():
        async with async_session_factory() as bg_db:
            phase1_succeeded = False
            try:
                await service.generate_custom_resume(bg_db, job_id, user_id)
                phase1_succeeded = True
                # Auto-chain: if Phase 1 succeeded, immediately run Phase 2
                job = await service.get_job(bg_db, job_id, user_id)
                if job.status.value == "RESUME_GENERATED":
                    await service.generate_pdf(bg_db, job_id, user_id)
            except Exception:
                logger.exception(f"Background generation failed for job {job_id}")
                # Only refund if Phase 1 (AI) failed — if Phase 1 succeeded
                # the user already has their tailored resume and can retry PDF for free.
                if not phase1_succeeded and source != "time_pass":
                    try:
                        await credit_service.refund_credit(bg_db, user_id, job_id, source)
                        logger.info(f"Refunded credit for failed job {job_id}")
                    except Exception:
                        logger.exception(f"Failed to refund credit for job {job_id}")

    create_tracked_task(_generate())
    return {"job_id": job_id, "status": "GENERATING_RESUME"}


@router.post("/{job_id}/generate-pdf", status_code=202)
async def generate_pdf(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    job = await service.get_job(db, job_id, current_user.id)

    # Guard: only allow PDF generation from RESUME_GENERATED or FAILED states
    if job.status.value not in ("RESUME_GENERATED", "FAILED"):
        raise ValueError(
            f"Job is {job.status.value} — PDF generation requires RESUME_GENERATED state"
        )

    from app.database.session import async_session_factory

    user_id = current_user.id

    async def _generate():
        async with async_session_factory() as bg_db:
            await service.generate_pdf(bg_db, job_id, user_id)

    create_tracked_task(_generate())
    return {"job_id": job_id, "status": "GENERATING_PDF"}


@router.get("/{job_id}")
async def get_job(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    job = await service.get_job(db, job_id, current_user.id)
    return {
        "id": job.id,
        "profile_id": job.profile_id,
        "job_description": job.job_description,
        "custom_resume_data": job.custom_resume_data,
        "status": job.status.value,
        "created_at": job.created_at.isoformat(),
        "updated_at": job.updated_at.isoformat(),
    }


@router.get("/{job_id}/status")
async def get_job_status(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    job = await service.get_job(db, job_id, current_user.id)
    return {"id": job.id, "status": job.status.value}


@router.get("/{job_id}/pdf")
async def download_pdf(
    job_id: int,
    inline: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    job = await service.get_job(db, job_id, current_user.id)
    pdf_bytes = await service.get_pdf(db, job_id, current_user.id)
    filename = _pdf_filename(job)
    # RFC 5987: filename* for Unicode, filename for ASCII fallback
    ascii_filename = filename.encode("ascii", "replace").decode("ascii")
    encoded_filename = quote(filename)
    disposition = "inline" if inline else "attachment"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'{disposition}; filename="{ascii_filename}"; '
                f"filename*=UTF-8''{encoded_filename}"
            )
        },
    )
