import asyncio
import json
import time
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.models.job import Job, JobStatus
from app.models.profile import Profile, ProfileStatus
from app.schemas.custom_resume import CustomResumeInfo
from app.schemas.job import JobDescription
from app.services.ai.inference import GeminiInference
from app.services.ai.prompts import CUSTOM_RESUME_SYSTEM_PROMPT, CUSTOM_RESUME_USER_PROMPT
from app.services.latex.builder import build_resume
from app.services.latex.compiler import compile_latex
from app.services.latex.sanitizer import sanitize_special_chars
from app.services.storage.gcs import GCSClient
from app.services.ai.user_settings import AISettingsService
from app.exceptions import JobNotFoundError, ProfileNotFoundError
from logging import getLogger

logger = getLogger(__name__)

# Local temp directory for PDFs before GCS upload
PDF_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "pdfs"
PDF_DIR.mkdir(parents=True, exist_ok=True)

GCS_UPLOAD_RETRIES = 3
GCS_UPLOAD_BACKOFF = 2.0  # seconds, exponential


async def _background_gcs_upload(pdf_bytes: bytes, user_id: str, job_id: int) -> None:
    """Upload PDF to GCS in background with retry. Updates job.pdf_gcs_path on success."""
    from app.database.session import async_session_factory

    gcs_path = f"resumes/{user_id}/{job_id}.pdf"
    gcs = GCSClient()

    for attempt in range(GCS_UPLOAD_RETRIES):
        try:
            # GCS client is sync — run in thread to avoid blocking the event loop
            await asyncio.to_thread(gcs.upload_pdf, pdf_bytes, gcs_path)

            # Update DB with GCS path
            async with async_session_factory() as db:
                result = await db.execute(select(Job).where(Job.id == job_id))
                job = result.scalar_one_or_none()
                if job:
                    job.pdf_gcs_path = gcs_path
                    await db.commit()

            # Clean up local temp file
            local_path = PDF_DIR / f"{user_id}_{job_id}.pdf"
            await asyncio.to_thread(local_path.unlink, True)

            logger.info(f"Background GCS upload succeeded for job {job_id}")
            return
        except Exception as e:
            logger.warning(f"GCS upload attempt {attempt + 1}/{GCS_UPLOAD_RETRIES} failed for job {job_id}: {e}")
            if attempt < GCS_UPLOAD_RETRIES - 1:
                await asyncio.sleep(GCS_UPLOAD_BACKOFF * (2 ** attempt))

    logger.error(f"All GCS upload attempts failed for job {job_id}. PDF available locally.")


class JobService:
    def __init__(self):
        self.ai_settings_service = AISettingsService()

    async def create_job(
        self,
        db: AsyncSession,
        user_id: str,
        profile_id: int,
        job_description: JobDescription,
    ) -> Job:
        # Validate profile exists and is ready
        result = await db.execute(
            select(Profile).where(Profile.id == profile_id, Profile.user_id == user_id)
        )
        profile = result.scalar_one_or_none()
        if not profile:
            raise ProfileNotFoundError(f"Profile {profile_id} not found")
        if profile.status != ProfileStatus.READY:
            raise ValueError(f"Profile {profile_id} is not ready (status: {profile.status})")

        job = Job(
            user_id=user_id,
            profile_id=profile_id,
            job_description=job_description.model_dump(),
            status=JobStatus.PENDING,
        )
        db.add(job)
        await db.commit()
        await db.refresh(job)
        return job

    async def generate_custom_resume(self, db: AsyncSession, job_id: int, user_id: str) -> None:
        """Phase 1: AI generates CustomResumeInfo from profile + job description."""
        t_start = time.monotonic()
        try:
            job = await self._get_job(db, job_id, user_id)
            profile = await db.get(Profile, job.profile_id)

            if not profile:
                raise ProfileNotFoundError(f"Profile {job.profile_id} not found for job {job_id}")

            job.status = JobStatus.GENERATING_RESUME
            await db.commit()
            logger.info(f"[job:{job_id}] Phase 1 (resume tailoring) started")

            user_prompt = CUSTOM_RESUME_USER_PROMPT.format(
                user_info=json.dumps(profile.resume_info or {}),
                job_description=json.dumps(job.job_description or {}),
            )

            t0 = time.monotonic()
            ai_settings = await self.ai_settings_service.resolve_for_user(db, user_id)
            llm = GeminiInference(
                api_key=ai_settings.api_key,
                model_name=ai_settings.model_name,
            )
            result = await llm.run_inference(
                system_prompt=CUSTOM_RESUME_SYSTEM_PROMPT,
                inputs=[user_prompt],
                structured_output_schema=CustomResumeInfo,
                user_id=user_id,
                purpose="resume_tailoring",
                reference_id=str(job_id),
            )
            ai_ms = int((time.monotonic() - t0) * 1000)
            logger.info(f"[job:{job_id}] AI tailoring ({ai_settings.model_name}): {ai_ms}ms {'(SLOW >60s)' if ai_ms > 60000 else ''}")

            # Inject PII from profile
            resume_info = profile.resume_info or {}
            result["name"] = resume_info.get("name", "")
            result["email"] = resume_info.get("email", "")
            result["mobile_number"] = resume_info.get("mobile_number")
            result["date_of_birth"] = resume_info.get("date_of_birth")

            t0 = time.monotonic()
            job.custom_resume_data = result
            job.status = JobStatus.RESUME_GENERATED
            await db.commit()
            logger.info(f"[job:{job_id}] DB save: {int((time.monotonic() - t0) * 1000)}ms")

            total_ms = int((time.monotonic() - t_start) * 1000)
            logger.info(f"[job:{job_id}] Phase 1 COMPLETE total={total_ms}ms {'(SLOW >60s)' if total_ms > 60000 else ''}")

        except Exception as e:
            total_ms = int((time.monotonic() - t_start) * 1000)
            logger.exception(f"[job:{job_id}] Phase 1 FAILED after {total_ms}ms: {e}")
            await db.rollback()
            try:
                result = await db.execute(select(Job).where(Job.id == job_id))
                job = result.scalar_one_or_none()
                if job:
                    job.status = JobStatus.FAILED
                    await db.commit()
            except Exception:
                logger.exception(f"Failed to mark job {job_id} as FAILED")
            raise

    async def generate_pdf(
        self, db: AsyncSession, job_id: int, user_id: str, *, recompile: bool = False,
    ) -> None:
        """Phase 2: Build LaTeX from CustomResumeInfo, compile PDF, upload to GCS.

        Saves locally first for immediate availability, then uploads to GCS in background.
        When recompile=True (chat-triggered), failures don't set status to FAILED —
        the previous PDF and READY status are preserved.
        """
        t_start = time.monotonic()
        try:
            job = await self._get_job(db, job_id, user_id)

            if not job.custom_resume_data:
                raise ValueError("No custom resume data found. Run generate_custom_resume first.")

            if not recompile:
                job.status = JobStatus.GENERATING_PDF
                await db.commit()
            logger.info(f"[job:{job_id}] Phase 2 (PDF {'recompile' if recompile else 'generation'}) started")

            # Sanitize and build LaTeX
            t0 = time.monotonic()
            sanitized = sanitize_special_chars(job.custom_resume_data)
            resume_info = CustomResumeInfo.model_validate(sanitized)
            latex_code = build_resume(resume_info)
            logger.info(f"[job:{job_id}] LaTeX build: {int((time.monotonic() - t0) * 1000)}ms ({len(latex_code)} chars)")

            # Compile PDF
            t0 = time.monotonic()
            pdf_bytes = await compile_latex(latex_code)
            logger.info(f"[job:{job_id}] pdflatex compile: {int((time.monotonic() - t0) * 1000)}ms ({len(pdf_bytes)} bytes)")

            # Save locally first (immediate availability)
            t0 = time.monotonic()
            local_path = PDF_DIR / f"{user_id}_{job_id}.pdf"
            await asyncio.to_thread(local_path.write_bytes, pdf_bytes)
            logger.info(f"[job:{job_id}] Local save: {int((time.monotonic() - t0) * 1000)}ms → {local_path}")

            job.resume_latex_code = latex_code
            job.pdf_gcs_path = str(local_path)
            job.status = JobStatus.READY
            await db.commit()

            total_ms = int((time.monotonic() - t_start) * 1000)
            logger.info(f"[job:{job_id}] Phase 2 COMPLETE total={total_ms}ms")

            # Background GCS upload (with retry) — don't block the job status
            asyncio.create_task(_background_gcs_upload(pdf_bytes, user_id, job_id))

        except Exception as e:
            total_ms = int((time.monotonic() - t_start) * 1000)
            logger.exception(f"[job:{job_id}] Phase 2 FAILED after {total_ms}ms: {e}")
            await db.rollback()
            if not recompile:
                # Only set FAILED for initial PDF generation, not chat-triggered recompiles.
                # On recompile failure, the previous PDF and READY status are preserved.
                try:
                    result = await db.execute(select(Job).where(Job.id == job_id))
                    job = result.scalar_one_or_none()
                    if job:
                        job.status = JobStatus.FAILED
                        await db.commit()
                except Exception:
                    logger.exception(f"Failed to mark job {job_id} as FAILED")
            else:
                # Restore READY status if recompile trashed it
                try:
                    result = await db.execute(select(Job).where(Job.id == job_id))
                    job = result.scalar_one_or_none()
                    if job and job.status != JobStatus.READY:
                        job.status = JobStatus.READY
                        await db.commit()
                except Exception:
                    logger.exception(f"Failed to restore READY status for job {job_id}")
            raise

    async def get_jobs(
        self, db: AsyncSession, user_id: str, *, offset: int = 0, limit: int = 10
    ) -> tuple[list[Job], int]:
        base = select(Job).where(Job.user_id == user_id)
        # Total count
        count_result = await db.execute(select(func.count()).select_from(base.subquery()))
        total = count_result.scalar() or 0
        # Paginated items
        result = await db.execute(
            base.order_by(Job.created_at.desc()).offset(offset).limit(limit)
        )
        return list(result.scalars().all()), total

    async def get_job(self, db: AsyncSession, job_id: int, user_id: str, *, for_update: bool = False) -> Job:
        return await self._get_job(db, job_id, user_id, for_update=for_update)

    async def get_pdf(self, db: AsyncSession, job_id: int, user_id: str) -> bytes:
        """Download PDF: try GCS first, fall back to local file, then regenerate from LaTeX.

        If regenerated, schedules a background GCS upload.
        """
        job = await self._get_job(db, job_id, user_id)

        if not job.pdf_gcs_path and not job.resume_latex_code:
            raise ValueError("PDF not yet generated for this job")

        # 1. Try GCS (path is relative like "resumes/user_id/job_id.pdf")
        if job.pdf_gcs_path and not job.pdf_gcs_path.startswith("/"):
            try:
                gcs = GCSClient()
                return await asyncio.to_thread(gcs.download_pdf, job.pdf_gcs_path)
            except Exception:
                logger.warning(f"GCS download failed for job {job_id}, trying local/regenerate")

        # 2. Try local temp file — either from absolute path in DB or known temp location
        local_candidates = []
        if job.pdf_gcs_path and job.pdf_gcs_path.startswith("/"):
            local_candidates.append(Path(job.pdf_gcs_path))
        # Also check the known temp path (file may still exist if GCS upload just completed)
        local_candidates.append(PDF_DIR / f"{user_id}_{job_id}.pdf")
        for local_path in local_candidates:
            if await asyncio.to_thread(local_path.exists):
                pdf_bytes = await asyncio.to_thread(local_path.read_bytes)
                asyncio.create_task(_background_gcs_upload(pdf_bytes, user_id, job_id))
                return pdf_bytes

        # 3. Regenerate from stored LaTeX
        if job.resume_latex_code:
            logger.info(f"Regenerating PDF from LaTeX for job {job_id}")
            pdf_bytes = await compile_latex(job.resume_latex_code)
            # Schedule background GCS upload
            asyncio.create_task(_background_gcs_upload(pdf_bytes, user_id, job_id))
            return pdf_bytes

        raise ValueError("PDF not available — no GCS path, local file, or LaTeX code found")

    async def update_custom_resume(
        self, db: AsyncSession, job_id: int, user_id: str, custom_resume_data: dict
    ) -> Job:
        job = await self._get_job(db, job_id, user_id)
        job.custom_resume_data = custom_resume_data
        await db.commit()
        await db.refresh(job)
        return job

    async def _get_job(self, db: AsyncSession, job_id: int, user_id: str, *, for_update: bool = False) -> Job:
        stmt = select(Job).where(Job.id == job_id, Job.user_id == user_id)
        if for_update:
            stmt = stmt.with_for_update()
        result = await db.execute(stmt)
        job = result.scalar_one_or_none()
        if not job:
            raise JobNotFoundError(f"Job {job_id} not found")
        return job
