import asyncio
import base64
import hashlib
import secrets
from datetime import datetime, timezone
from io import BytesIO
from logging import Logger, getLogger
from typing import Any

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from pdf2image import convert_from_bytes

from app.config import get_settings
from app.exceptions import RoastNotFoundError
from app.models.roast import Roast, RoastStatus
from app.schemas.roast import RoastResult
from app.services.ai.inference import GeminiInference
from app.services.ai.prompts import ROAST_SYSTEM_PROMPT
from app.services.ocr.extractor import PDFExtractor

logger: Logger = getLogger(__name__)


class RoastService:
    extractor: PDFExtractor
    flash_model: str

    def __init__(self) -> None:
        self.extractor = PDFExtractor()
        settings = get_settings()
        self.flash_model = settings.GEMINI_FLASH_MODEL

    @staticmethod
    def compute_hash(pdf_bytes: bytes) -> str:
        return hashlib.sha256(pdf_bytes).hexdigest()

    async def find_cached(self, db: AsyncSession, user_id: str, file_hash: str) -> Roast | None:
        result = await db.execute(
            select(Roast).where(Roast.user_id == user_id, Roast.file_hash == file_hash)
        )
        return result.scalar_one_or_none()

    @staticmethod
    def generate_share_id() -> str:
        return secrets.token_urlsafe(6)  # 8 chars

    async def create_roast(self, db: AsyncSession, user_id: str, file_hash: str) -> Roast:
        roast = Roast(
            user_id=user_id,
            file_hash=file_hash,
            share_id=self.generate_share_id(),
            status=RoastStatus.PENDING,
        )
        db.add(roast)
        await db.commit()
        await db.refresh(roast)
        return roast

    async def extract_text_fast(self, pdf_bytes: bytes) -> str:
        try:
            return await asyncio.to_thread(self.extractor.extract_text, pdf_bytes)
        except Exception as e:
            logger.warning(f"Fast text extraction failed: {e}")
            return ""

    async def pdf_to_images(self, pdf_bytes: bytes) -> list[dict[str, Any]]:
        """Convert PDF pages to base64 JPEG dicts for Gemini vision input."""
        pages = await asyncio.to_thread(convert_from_bytes, pdf_bytes, dpi=200)
        images: list[dict[str, Any]] = []
        for page in pages:
            buf: BytesIO = BytesIO()
            page.save(buf, format="JPEG", quality=85)
            b64: str = base64.b64encode(buf.getvalue()).decode("utf-8")
            images.append({"inline_data": {"mime_type": "image/jpeg", "data": b64}})
        return images

    async def process_roast(
        self, db: AsyncSession, roast_id: int, pdf_bytes: bytes, extracted_text: str = ""
    ) -> None:
        roast = await db.get(Roast, roast_id)
        if not roast:
            logger.error(f"Roast {roast_id} not found during processing")
            return

        try:
            roast.status = RoastStatus.PROCESSING
            await db.commit()

            # Store extracted text for the DB record (used by frontend OCR cycling)
            text: str = extracted_text if extracted_text.strip() else ""
            if not text:
                text = await asyncio.to_thread(self.extractor.extract_text, pdf_bytes)
            roast.extracted_text = text

            # Convert PDF to images so the AI sees actual formatting/layout
            images: list[dict[str, Any]] = await self.pdf_to_images(pdf_bytes)

            now: str = datetime.now(timezone.utc).strftime("%B %d, %Y")
            llm: GeminiInference = GeminiInference(model_name=self.flash_model)

            user_message_parts: list[Any] = [
                f"Today's date is {now}. Here is the resume to roast. Examine each page — look at both the content AND the formatting/layout.",
            ]
            if text.strip():
                user_message_parts.append(
                    f"\n\n<ocr_extracted_text>\n{text}\n</ocr_extracted_text>\n\n"
                    "The above is what an automated PDF text extractor pulled from this resume. "
                    "Compare it against what you see in the images to assess machine-readability."
                )

            result: dict[str, Any] = await llm.run_inference(
                system_prompt=ROAST_SYSTEM_PROMPT,
                inputs=[
                    *user_message_parts,
                    *images,
                ],
                structured_output_schema=RoastResult,
                temperature=0.8,
                user_id=roast.user_id,
                purpose="resume_roast",
                reference_id=str(roast_id),
            )

            roast.roast_data = result
            roast.status = RoastStatus.READY
            await db.commit()

        except Exception as e:
            logger.exception(f"Roast processing failed for {roast_id}: {e}")
            await db.rollback()
            try:
                result = await db.execute(
                    select(Roast).where(Roast.id == roast_id)
                )
                roast = result.scalar_one_or_none()
                if roast:
                    roast.status = RoastStatus.FAILED
                    await db.commit()
            except Exception:
                logger.exception(f"Failed to mark roast {roast_id} as FAILED")

    async def get_roast(self, db: AsyncSession, roast_id: int, user_id: str) -> Roast:
        result = await db.execute(
            select(Roast).where(Roast.id == roast_id, Roast.user_id == user_id)
        )
        roast = result.scalar_one_or_none()
        if not roast:
            raise RoastNotFoundError(f"Roast {roast_id} not found")
        return roast

    async def get_roast_by_share_id(self, db: AsyncSession, share_id: str) -> Roast:
        result = await db.execute(
            select(Roast).where(Roast.share_id == share_id, Roast.status == RoastStatus.READY)
        )
        roast = result.scalar_one_or_none()
        if not roast:
            raise RoastNotFoundError(f"Shared roast not found")
        return roast

    async def get_roasts(
        self, db: AsyncSession, user_id: str, *, offset: int = 0, limit: int = 10
    ) -> tuple[list[Roast], int]:
        base = select(Roast).where(Roast.user_id == user_id, Roast.status != RoastStatus.FAILED)
        count_result = await db.execute(select(func.count()).select_from(base.subquery()))
        total = count_result.scalar() or 0
        result = await db.execute(
            base.order_by(Roast.created_at.desc()).offset(offset).limit(limit)
        )
        return list(result.scalars().all()), total
