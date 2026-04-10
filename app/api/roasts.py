import asyncio
import math
from logging import getLogger
from fastapi import APIRouter, Depends, UploadFile, File, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.session import get_db
from app.main import create_tracked_task
from app.models.user import User
from app.dependencies import get_current_user
from app.services.roast.service import RoastService
from app.services.ai.user_settings import AISettingsService
from app.services.storage.gcs import GCSClient
from app.models.roast import RoastStatus

logger = getLogger(__name__)

router = APIRouter(prefix="/roasts", tags=["roasts"])
service = RoastService()
ai_settings_service = AISettingsService()


@router.post("/upload", status_code=202)
async def upload_roast(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await ai_settings_service.require_settings(db, current_user.id)
    pdf_bytes = await file.read()
    file_hash = service.compute_hash(pdf_bytes)

    # Check cache
    cached = await service.find_cached(db, current_user.id, file_hash)
    if cached:
        if cached.status.value in ("READY", "PROCESSING", "PENDING"):
            return {
                "roast_id": cached.id,
                "share_id": cached.share_id,
                "status": cached.status.value,
                "cached": cached.status.value == "READY",
                "extracted_text": cached.extracted_text,
            }
        # FAILED — reset and re-process
        roast = cached
        roast.status = RoastStatus.PENDING
        roast.roast_data = None
        await db.commit()
    else:
        roast = await service.create_roast(db, current_user.id, file_hash)

    # Fast text extraction
    extracted_text = await service.extract_text_fast(pdf_bytes)

    # Process in background
    from app.database.session import async_session_factory
    roast_id = roast.id

    async def _process():
        async with async_session_factory() as bg_db:
            await service.process_roast(bg_db, roast_id, pdf_bytes, extracted_text=extracted_text)

    create_tracked_task(_process())

    # Store uploaded PDF in GCS (fire-and-forget)
    async def _store_pdf():
        try:
            gcs = GCSClient()
            gcs_path = f"uploads/roasts/{current_user.id}/{roast_id}.pdf"
            await asyncio.to_thread(gcs.upload_pdf, pdf_bytes, gcs_path)
        except Exception:
            logger.warning(f"Failed to store uploaded PDF for roast {roast_id}", exc_info=True)

    create_tracked_task(_store_pdf())

    return {
        "roast_id": roast_id,
        "share_id": roast.share_id,
        "status": "PENDING",
        "cached": False,
        "extracted_text": extracted_text,
    }


@router.get("/shared/{share_id}")
async def get_shared_roast(
    share_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Public endpoint — no auth required. Returns roast data only (no PII)."""
    roast = await service.get_roast_by_share_id(db, share_id)
    return {
        "share_id": roast.share_id,
        "roast_data": roast.roast_data,
        "created_at": roast.created_at.isoformat(),
    }


@router.get("/")
async def list_roasts(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    offset = (page - 1) * limit
    roasts, total = await service.get_roasts(db, current_user.id, offset=offset, limit=limit)
    return {
        "items": [
            {
                "id": r.id,
                "share_id": r.share_id,
                "status": r.status.value,
                "roast_data": r.roast_data,
                "created_at": r.created_at.isoformat(),
                "updated_at": r.updated_at.isoformat(),
            }
            for r in roasts
        ],
        "total": total,
        "page": page,
        "pages": math.ceil(total / limit) if total > 0 else 1,
        "limit": limit,
    }


@router.get("/{roast_id}")
async def get_roast(
    roast_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    roast = await service.get_roast(db, roast_id, current_user.id)
    return {
        "id": roast.id,
        "share_id": roast.share_id,
        "status": roast.status.value,
        "roast_data": roast.roast_data,
        "created_at": roast.created_at.isoformat(),
        "updated_at": roast.updated_at.isoformat(),
    }


@router.get("/{roast_id}/status")
async def get_roast_status(
    roast_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    roast = await service.get_roast(db, roast_id, current_user.id)
    return {"id": roast.id, "status": roast.status.value}
