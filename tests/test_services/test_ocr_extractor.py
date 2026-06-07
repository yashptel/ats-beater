import pytest
from pydantic import ValidationError
from unittest.mock import AsyncMock, MagicMock

from app.services.ocr import extractor as extractor_mod
from app.services.ocr.extractor import PDFExtractor
from app.services.ai.user_settings import ResolvedAISettings
from app.schemas.resume import ExtractedResumeInfo


class _FakePage:
    def save(self, buf, format=None, quality=None):
        buf.write(b"fakejpeg")


@pytest.mark.asyncio
async def test_vision_extraction_routes_through_active_provider(monkeypatch):
    monkeypatch.setattr(
        extractor_mod, "convert_from_bytes", lambda pdf, dpi=200: [_FakePage(), _FakePage()]
    )
    fake_llm = MagicMock()
    fake_llm.run_inference = AsyncMock(
        return_value={
            "name": "X",
            "email": "x@example.com",
            "projects": [
                {"name": "P", "description": ["Built X", "Shipped Y"]},
            ],
        }
    )
    captured = {}

    def fake_build(resolved):
        captured["resolved"] = resolved
        return fake_llm

    monkeypatch.setattr(extractor_mod, "build_inference", fake_build)

    ext = PDFExtractor()
    resolved = ResolvedAISettings(
        api_key="k", model_name="qwen-vl", provider="openai_compatible",
        base_url="https://proxy.example.com/v1",
    )
    result = await ext.extract_and_structure_via_vision(
        b"pdf-bytes",
        ai_settings=resolved,
        user_id="u",
        reference_id="1",
        extracted_text="pdfplumber text with bullet context",
    )

    assert result["name"] == "X"
    assert result["projects"][0]["description"] == "Built X\nShipped Y"
    # The extractor used the active provider, not a hard-coded Gemini client.
    assert captured["resolved"] is resolved
    kwargs = fake_llm.run_inference.await_args.kwargs
    assert kwargs["purpose"] == "profile_structuring_vision"
    assert kwargs["structured_output_schema"] is ExtractedResumeInfo
    assert any(
        isinstance(i, str) and "pdfplumber text with bullet context" in i
        for i in kwargs["inputs"]
    )
    # Page images are still passed as inline-image dicts (provider adapts them).
    assert sum(1 for i in kwargs["inputs"] if isinstance(i, dict) and "inline_data" in i) == 2


@pytest.mark.asyncio
async def test_vision_extraction_rejects_missing_descriptions(monkeypatch):
    monkeypatch.setattr(
        extractor_mod, "convert_from_bytes", lambda pdf, dpi=200: [_FakePage()]
    )
    fake_llm = MagicMock()
    fake_llm.run_inference = AsyncMock(
        return_value={
            "name": "X",
            "email": "x@example.com",
            "projects": [{"name": "P"}],
            "past_experience": [{"company_name": "C", "role": "R"}],
        }
    )
    monkeypatch.setattr(extractor_mod, "build_inference", lambda resolved: fake_llm)

    ext = PDFExtractor()
    resolved = ResolvedAISettings(
        api_key="k",
        model_name="qwen-vl",
        provider="openai_compatible",
        base_url="https://proxy.example.com/v1",
    )

    with pytest.raises(ValidationError):
        await ext.extract_and_structure_via_vision(
            b"pdf-bytes",
            ai_settings=resolved,
            extracted_text="pdfplumber text with bullet context",
        )
