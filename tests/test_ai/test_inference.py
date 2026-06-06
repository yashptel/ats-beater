from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import BaseModel

from app.services.ai.inference import GeminiInference


class _Person(BaseModel):
    name: str
    email: str


@pytest.mark.asyncio
async def test_inference_retries_on_same_selected_model():
    with patch("app.services.ai.inference.genai.Client", return_value=SimpleNamespace(aio=None)):
        llm = GeminiInference(
            api_key="test-api-key",
            model_name="gemini-3-flash-preview",
        )

    llm._call_api = AsyncMock(side_effect=Exception("temporary failure"))
    llm._call_api_with_retry = AsyncMock(
        return_value=SimpleNamespace(text="hello world")
    )

    result = await llm.run_inference(
        system_prompt="You are helpful.",
        inputs=["Say hello."],
    )

    assert result == "hello world"
    assert llm._call_api.await_args.args[0] == "gemini-3-flash-preview"
    assert llm._call_api_with_retry.await_args.args[0] == "gemini-3-flash-preview"


@pytest.mark.asyncio
async def test_gemini_structured_validation_retry_adds_repair_context():
    with patch("app.services.ai.inference.genai.Client", return_value=SimpleNamespace(aio=None)):
        llm = GeminiInference(
            api_key="test-api-key",
            model_name="gemini-3-flash-preview",
        )

    llm._call_api = AsyncMock(
        side_effect=[
            SimpleNamespace(text='{"name": "Jane"}'),
            SimpleNamespace(text='{"name": "Jane", "email": "jane@x.com"}'),
        ]
    )

    result = await llm.run_inference(
        system_prompt="Extract.",
        inputs=["Jane jane@x.com"],
        structured_output_schema=_Person,
    )

    assert result == {"name": "Jane", "email": "jane@x.com"}
    assert llm._call_api.await_count == 2
    second_inputs = llm._call_api.await_args_list[1].args[2]
    assert second_inputs[0] == "Jane jane@x.com"
    assert "Validation errors" in second_inputs[-1]
    assert "Previous invalid JSON/content" in second_inputs[-1]
