from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services.ai.inference import GeminiInference


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
