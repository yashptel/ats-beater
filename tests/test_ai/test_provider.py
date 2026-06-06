from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import BaseModel

from app.services.ai.inference import GeminiInference, OpenAICompatibleInference
from app.services.ai.provider import build_inference
from app.services.ai.user_settings import ResolvedAISettings


class _Person(BaseModel):
    name: str
    email: str


def test_build_inference_returns_gemini_for_gemini_provider():
    resolved = ResolvedAISettings(
        api_key="k", model_name="gemini-3-flash-preview", provider="gemini"
    )
    assert isinstance(build_inference(resolved), GeminiInference)


def test_build_inference_returns_openai_for_openai_provider():
    resolved = ResolvedAISettings(
        api_key="k",
        model_name="qwen-max",
        provider="openai_compatible",
        base_url="https://proxy.example.com/v1",
    )
    inf = build_inference(resolved)
    assert isinstance(inf, OpenAICompatibleInference)
    assert inf.model == "qwen-max"


def _make_openai(reasoning_effort=None):
    return OpenAICompatibleInference(
        api_key="k",
        model_name="qwen-max",
        base_url="https://proxy.example.com/v1",
        reasoning_effort=reasoning_effort,
    )


def _completion(content):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5, total_tokens=15),
    )


@pytest.mark.asyncio
async def test_openai_inference_structured_output_parses_json():
    inf = _make_openai()
    captured = {}

    async def fake_create(**kwargs):
        captured.update(kwargs)
        return _completion('{"name": "Jane", "email": "jane@x.com"}')

    inf.client = MagicMock()
    inf.client.chat.completions.create = fake_create

    result = await inf.run_inference(
        system_prompt="Extract the person.",
        inputs=["Jane jane@x.com"],
        structured_output_schema=_Person,
    )
    assert result == {"name": "Jane", "email": "jane@x.com"}
    # Request payload shape: system + user messages, JSON response_format hint.
    assert captured["model"] == "qwen-max"
    assert captured["messages"][0]["role"] == "system"
    assert captured["messages"][-1]["role"] == "user"
    assert "Jane jane@x.com" in captured["messages"][-1]["content"]
    assert captured["response_format"] == {"type": "json_object"}


@pytest.mark.asyncio
async def test_openai_inference_handles_markdown_fenced_json():
    inf = _make_openai()
    inf.client = MagicMock()
    inf.client.chat.completions.create = AsyncMock(
        return_value=_completion('```json\n{"name": "Al", "email": "al@x.com"}\n```')
    )
    result = await inf.run_inference(
        system_prompt="Extract.", inputs=["Al al@x.com"], structured_output_schema=_Person
    )
    assert result == {"name": "Al", "email": "al@x.com"}


@pytest.mark.asyncio
async def test_openai_inference_retries_on_invalid_then_succeeds():
    inf = _make_openai()
    inf.client = MagicMock()
    inf.client.chat.completions.create = AsyncMock(
        side_effect=[
            _completion("not json at all"),
            _completion('{"name": "Bo", "email": "bo@x.com"}'),
        ]
    )
    result = await inf.run_inference(
        system_prompt="Extract.", inputs=["Bo bo@x.com"], structured_output_schema=_Person
    )
    assert result == {"name": "Bo", "email": "bo@x.com"}
    assert inf.client.chat.completions.create.await_count == 2


@pytest.mark.asyncio
async def test_openai_inference_plain_text_returns_content():
    inf = _make_openai()
    inf.client = MagicMock()
    inf.client.chat.completions.create = AsyncMock(return_value=_completion("hello world"))
    result = await inf.run_inference(system_prompt="Say hello.", inputs=["hi"])
    assert result == "hello world"


@pytest.mark.asyncio
async def test_openai_inference_omits_reasoning_effort_by_default():
    inf = _make_openai(reasoning_effort=None)
    captured = {}

    async def fake_create(**kwargs):
        captured.update(kwargs)
        return _completion("ok")

    inf.client = MagicMock()
    inf.client.chat.completions.create = fake_create
    await inf.run_inference(system_prompt="Hi", inputs=["hi"])
    assert "extra_body" not in captured


@pytest.mark.asyncio
async def test_openai_inference_includes_reasoning_effort_when_set():
    inf = _make_openai(reasoning_effort="high")
    captured = {}

    async def fake_create(**kwargs):
        captured.update(kwargs)
        return _completion("ok")

    inf.client = MagicMock()
    inf.client.chat.completions.create = fake_create
    await inf.run_inference(system_prompt="Hi", inputs=["hi"])
    assert captured["extra_body"] == {"reasoning_effort": "high"}
