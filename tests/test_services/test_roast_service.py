import pytest
from unittest.mock import AsyncMock, MagicMock

from app.services.roast import service as roast_mod
from app.services.roast.service import RoastService
from app.services.ai.user_settings import ResolvedAISettings
from app.models.roast import RoastStatus


@pytest.mark.asyncio
async def test_roast_routes_through_active_provider(db_session, test_user, monkeypatch):
    service = RoastService()
    roast = await service.create_roast(db_session, test_user.id, "hash123")

    service.ai_settings_service.resolve_for_user = AsyncMock(
        return_value=ResolvedAISettings(
            api_key="k", model_name="qwen-vl", provider="openai_compatible",
            base_url="https://proxy.example.com/v1",
        )
    )
    service.pdf_to_images = AsyncMock(
        return_value=[{"inline_data": {"mime_type": "image/jpeg", "data": "QUJD"}}]
    )

    fake_llm = MagicMock()
    fake_llm.run_inference = AsyncMock(return_value={"verdict": "ok"})
    captured = {}

    def fake_build(resolved):
        captured["resolved"] = resolved
        return fake_llm

    monkeypatch.setattr(roast_mod, "build_inference", fake_build)

    await service.process_roast(db_session, roast.id, b"pdf-bytes", extracted_text="resume text")

    assert captured["resolved"].provider == "openai_compatible"
    kwargs = fake_llm.run_inference.await_args.kwargs
    assert kwargs["purpose"] == "resume_roast"
    # Page images are passed through; extracted text context is preserved.
    assert any(isinstance(i, dict) and "inline_data" in i for i in kwargs["inputs"])
    assert any(isinstance(i, str) and "resume text" in i for i in kwargs["inputs"])

    await db_session.refresh(roast)
    assert roast.status == RoastStatus.READY
