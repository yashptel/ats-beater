"""Provider parity: the same structured-generation contract holds for both
providers when driven through build_inference(). Backs issue #10's automated
coverage of the shared inference path."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel

from app.services.ai.inference import GeminiInference, OpenAICompatibleInference
from app.services.ai.provider import build_inference
from app.services.ai.user_settings import ResolvedAISettings


class _Doc(BaseModel):
    title: str


def _gemini_inference():
    resolved = ResolvedAISettings(
        api_key="k", model_name="gemini-3-flash-preview", provider="gemini"
    )
    with patch("app.services.ai.inference.genai.Client", return_value=SimpleNamespace(aio=None)):
        inf = build_inference(resolved)
    # Mock the transport at _call_api so we don't build a real GenerateContentConfig.
    inf._call_api = AsyncMock(return_value=SimpleNamespace(text='{"title": "Hello"}'))
    return inf


def _openai_inference():
    resolved = ResolvedAISettings(
        api_key="k", model_name="qwen-max", provider="openai_compatible",
        base_url="https://proxy.example.com/v1",
    )
    inf = build_inference(resolved)
    inf.client = MagicMock()
    inf.client.chat.completions.create = AsyncMock(
        return_value=SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"title": "Hello"}'))],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        )
    )
    return inf


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "factory,expected_type",
    [(_gemini_inference, GeminiInference), (_openai_inference, OpenAICompatibleInference)],
)
async def test_structured_inference_parity(factory, expected_type):
    inf = factory()
    assert isinstance(inf, expected_type)
    result = await inf.run_inference(
        system_prompt="Extract the document.",
        inputs=["a document"],
        structured_output_schema=_Doc,
    )
    assert result == {"title": "Hello"}
