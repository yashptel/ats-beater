import asyncio
import math
from logging import getLogger
from fastapi import APIRouter, Depends, UploadFile, File, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.session import get_db
from app.main import create_tracked_task
from app.models.user import User
from app.dependencies import get_current_user
from app.services.profile.service import ProfileService
from app.services.ai.user_settings import AISettingsService
from app.services.storage.gcs import GCSClient
from app.schemas.profile import UpsertPayload

logger = getLogger(__name__)

router = APIRouter(prefix="/profiles", tags=["profiles"])
service = ProfileService()
ai_settings_service = AISettingsService()


@router.post("/upload", status_code=202)
async def upload_profile(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await ai_settings_service.require_settings(db, current_user.id)
    pdf_bytes = await file.read()
    profile_id = await service.create_profile(db, current_user.id, pdf_bytes)

    # Fast-path: extract text immediately (pdfplumber is near-instant)
    # so the frontend can animate through the content while AI structures in background
    extracted_text = await service.extract_text_fast(pdf_bytes)

    # Process in background — pass extracted text so it doesn't re-extract
    from app.database.session import async_session_factory

    async def _process():
        async with async_session_factory() as bg_db:
            await service.process_profile(bg_db, profile_id, pdf_bytes, extracted_text=extracted_text)

    create_tracked_task(_process())

    # Store uploaded PDF in GCS (fire-and-forget)
    async def _store_pdf():
        try:
            gcs = GCSClient()
            gcs_path = f"uploads/profiles/{current_user.id}/{profile_id}.pdf"
            await asyncio.to_thread(gcs.upload_pdf, pdf_bytes, gcs_path)
        except Exception:
            logger.warning(f"Failed to store uploaded PDF for profile {profile_id}", exc_info=True)

    create_tracked_task(_store_pdf())

    return {"profile_id": profile_id, "status": "PENDING", "extracted_text": extracted_text}


@router.get("/")
async def list_profiles(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    offset = (page - 1) * limit
    profiles, total = await service.get_profiles(db, current_user.id, offset=offset, limit=limit)
    return {
        "items": [
            {
                "id": p.id,
                "status": p.status.value,
                "is_active": p.is_active,
                "resume_info": p.resume_info,
                "created_at": p.created_at.isoformat(),
                "updated_at": p.updated_at.isoformat(),
            }
            for p in profiles
        ],
        "total": total,
        "page": page,
        "pages": math.ceil(total / limit) if total > 0 else 1,
        "limit": limit,
    }


@router.get("/{profile_id}")
async def get_profile(
    profile_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    profile = await service.get_profile(db, profile_id, current_user.id)
    return {
        "id": profile.id,
        "status": profile.status.value,
        "is_active": profile.is_active,
        "resume_info": profile.resume_info,
        "created_at": profile.created_at.isoformat(),
        "updated_at": profile.updated_at.isoformat(),
    }


@router.get("/{profile_id}/status")
async def get_profile_status(
    profile_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    profile = await service.get_profile(db, profile_id, current_user.id)
    return {"id": profile.id, "status": profile.status.value}


@router.put("/{profile_id}")
async def update_profile(
    profile_id: int,
    payload: UpsertPayload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    profile = await service.update_resume_info(db, profile_id, current_user.id, payload.resume_info)
    return {"id": profile.id, "status": profile.status.value}


@router.post("/{profile_id}/enhance")
async def enhance_profile(
    profile_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await ai_settings_service.require_settings(db, current_user.id)
    profile = await service.enhance_profile(db, profile_id, current_user.id)
    return {"id": profile.id, "resume_info": profile.resume_info}


@router.delete("/{profile_id}")
async def delete_profile(
    profile_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await service.deactivate_profile(db, profile_id, current_user.id)
    return {"detail": "Profile deactivated"}
