import asyncio
import base64
from io import BytesIO
import pdfplumber
from pdf2image import convert_from_bytes
from app.services.ai.provider import build_inference
from app.services.ai.inference import PRIMARY_TIMEOUT_SECONDS
from app.services.ai.prompts import STRUCTURED_RESUME_SYSTEM_PROMPT
from app.schemas.resume import ExtractedResumeInfo
from logging import getLogger

logger = getLogger(__name__)


class PDFExtractor:
    def extract_text(self, pdf_bytes: bytes) -> str:
        """Fast extraction using pdfplumber without LLM."""
        texts = []
        with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    texts.append(text)
        # Strip null bytes — some PDFs embed \x00 which PostgreSQL rejects
        return "\n".join(texts).replace("\x00", "")

    async def extract_and_structure_via_vision(
        self,
        pdf_bytes: bytes,
        *,
        ai_settings,
        user_id: str | None = None,
        reference_id: str | None = None,
        primary_timeout: int | None = PRIMARY_TIMEOUT_SECONDS,
        extracted_text: str = "",
    ) -> dict:
        """Convert PDF to images and send ALL pages + structuring prompt in a single
        call through the user's active provider. Returns a ResumeInfo dict directly
        (no separate structuring step).
        """
        pages = await asyncio.to_thread(convert_from_bytes, pdf_bytes, dpi=200)
        images = []
        for page in pages:
            buf = BytesIO()
            page.save(buf, format="JPEG", quality=85)
            b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
            images.append({"inline_data": {"mime_type": "image/jpeg", "data": b64}})

        llm = build_inference(ai_settings)
        input_parts: list = [
            "Extract and structure ALL information from these resume page images into the given JSON schema. Use the page images to recover visual section and bullet boundaries.",
        ]
        if extracted_text.strip():
            input_parts.append(
                "\n\n<pdf_text_extraction>\n"
                f"{extracted_text}"
                "\n</pdf_text_extraction>\n\n"
                "The text above came from local PDF text extraction. Use it for exact wording, "
                "but trust the page images when deciding where bullets and sections begin. "
                "Every distinct visual bullet must become its own item in the description arrays."
            )
        input_parts.extend(images)

        result = await llm.run_inference(
            system_prompt=STRUCTURED_RESUME_SYSTEM_PROMPT,
            inputs=input_parts,
            structured_output_schema=ExtractedResumeInfo,
            user_id=user_id,
            purpose="profile_structuring_vision",
            reference_id=reference_id,
            primary_timeout=primary_timeout,
        )
        return ExtractedResumeInfo.model_validate(result).to_resume_info().model_dump()

    @staticmethod
    def _has_high_non_ascii_ratio(text: str) -> bool:
        if not text:
            return True
        non_ascii = sum(1 for c in text if ord(c) > 127)
        return (non_ascii / len(text)) > 0.3
