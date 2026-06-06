from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import app.database.session as session_mod
from app.models.token_usage import LLMRequest
from app.services.ai.inference import GeminiInference, OpenAICompatibleInference, _log_request


@pytest.mark.asyncio
async def test_log_request_persists_provider(async_engine, monkeypatch):
    factory = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(session_mod, "async_session_factory", factory)

    await _log_request(
        model_name="qwen-max", user_id=None, purpose="resume_tailoring",
        reference_id="1", input_tokens=1, output_tokens=2, total_tokens=3,
        cached_tokens=0, response_time_ms=10, success=True, error_message=None,
        provider="openai_compatible",
    )

    async with factory() as db:
        row = (await db.execute(select(LLMRequest))).scalar_one()
        assert row.provider == "openai_compatible"
        assert row.model_name == "qwen-max"


@pytest.mark.asyncio
async def test_gemini_call_api_logs_gemini_provider(monkeypatch):
    captured = []

    async def fake_log(**kwargs):
        captured.append(kwargs)

    monkeypatch.setattr("app.services.ai.inference._log_request", fake_log)
    with patch("app.services.ai.inference.genai.Client", return_value=SimpleNamespace(aio=None)):
        llm = GeminiInference(api_key="k", model_name="gemini-3-flash-preview")

    fake_resp = SimpleNamespace(
        text="hi",
        usage_metadata=SimpleNamespace(
            prompt_token_count=1, candidates_token_count=2,
            total_token_count=3, cached_content_token_count=0,
        ),
    )
    llm.client = MagicMock()
    llm.client.aio.models.generate_content = AsyncMock(return_value=fake_resp)

    await llm._call_api("gemini-3-flash-preview", {}, ["hi"], purpose="resume_tailoring")
    assert captured and captured[-1]["provider"] == "gemini"


@pytest.mark.asyncio
async def test_openai_inference_logs_openai_provider(monkeypatch):
    captured = []

    async def fake_log(**kwargs):
        captured.append(kwargs)

    monkeypatch.setattr("app.services.ai.inference._log_request", fake_log)
    inf = OpenAICompatibleInference(api_key="k", model_name="qwen", base_url="https://p/v1")
    inf.client = MagicMock()
    inf.client.chat.completions.create = AsyncMock(
        return_value=SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="hi"))],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=2, total_tokens=3),
        )
    )
    await inf.run_inference(system_prompt="s", inputs=["hi"], purpose="resume_tailoring")
    assert captured and captured[-1]["provider"] == "openai_compatible"
