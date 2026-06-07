from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import BaseModel

from app.schemas.custom_resume import CustomResumeInfo
from app.schemas.roast import RoastResult
from app.services.ai.inference import (
    GeminiInference,
    OpenAICompatibleInference,
    build_structured_output_contract,
)
from app.services.ai.openai_client import (
    OPENAI_COMPATIBLE_USER_AGENT,
    build_openai_compatible_client,
)
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


def test_openai_compatible_client_uses_neutral_user_agent():
    client = build_openai_compatible_client(
        api_key="k", base_url="https://proxy.example.com/v1", timeout=20.0
    )
    assert client.default_headers["User-Agent"] == OPENAI_COMPATIBLE_USER_AGENT


def test_openai_compatible_client_disables_sdk_retries():
    client = build_openai_compatible_client(
        api_key="k", base_url="https://proxy.example.com/v1", timeout=20.0
    )
    assert client.max_retries == 0


def test_structured_output_contract_includes_required_schema_fields():
    roast_contract = build_structured_output_contract(RoastResult)
    resume_contract = build_structured_output_contract(CustomResumeInfo)

    assert "headline" in roast_contract
    assert "roast_points" in roast_contract
    assert "actual_feedback" in roast_contract
    assert "past_experience" in resume_contract
    assert "projects" in resume_contract
    assert "email" in resume_contract


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
    assert any("STRUCTURED OUTPUT CONTRACT" in m["content"] for m in captured["messages"])
    assert any("name" in m["content"] and "email" in m["content"] for m in captured["messages"])
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
    second_call = inf.client.chat.completions.create.await_args_list[1].kwargs
    assert "Validation errors" in second_call["messages"][-1]["content"]
    assert "Previous invalid JSON/content" in second_call["messages"][-1]["content"]
    assert "name" in second_call["messages"][-1]["content"]


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
async def test_openai_inference_passes_per_call_timeout():
    inf = _make_openai()
    captured = {}

    async def fake_create(**kwargs):
        captured.update(kwargs)
        return _completion("ok")

    inf.client = MagicMock()
    inf.client.chat.completions.create = fake_create
    await inf.run_inference(system_prompt="Hi", inputs=["hi"], primary_timeout=123)
    assert captured["timeout"] == 123.0


def test_openai_build_messages_text_only_uses_string_content():
    inf = _make_openai()
    messages = inf._build_messages("Sys", ["a", "b"])
    assert messages[0]["role"] == "system"
    assert messages[-1]["role"] == "user"
    assert messages[-1]["content"] == "a\n\nb"


def test_openai_build_messages_converts_images_to_data_urls():
    inf = _make_openai()
    messages = inf._build_messages(
        "Extract.",
        ["page text", {"inline_data": {"mime_type": "image/jpeg", "data": "QUJD"}}],
    )
    user = messages[-1]
    assert user["role"] == "user"
    assert isinstance(user["content"], list)  # parts list once an image is present
    types = [p["type"] for p in user["content"]]
    assert "text" in types and "image_url" in types
    image_part = next(p for p in user["content"] if p["type"] == "image_url")
    assert image_part["image_url"]["url"] == "data:image/jpeg;base64,QUJD"


@pytest.mark.asyncio
async def test_openai_structured_vision_puts_json_directive_in_user_content():
    inf = _make_openai()
    captured = {}

    async def fake_create(**kwargs):
        captured.update(kwargs)
        return _completion('{"name": "Jane", "email": "jane@x.com"}')

    inf.client = MagicMock()
    inf.client.chat.completions.create = fake_create
    await inf.run_inference(
        system_prompt="Extract the person.",
        inputs=[
            "page text",
            {"inline_data": {"mime_type": "image/jpeg", "data": "QUJD"}},
        ],
        structured_output_schema=_Person,
    )

    user_content = captured["messages"][-1]["content"]
    assert isinstance(user_content, list)
    assert any(
        part.get("type") == "text" and "json" in part.get("text", "").lower()
        for part in user_content
    )


@pytest.mark.asyncio
async def test_openai_structured_vision_repair_preserves_image_parts():
    inf = _make_openai()
    inf.client = MagicMock()
    inf.client.chat.completions.create = AsyncMock(
        side_effect=[
            _completion('{"name": "Jane"}'),
            _completion('{"name": "Jane", "email": "jane@x.com"}'),
        ]
    )

    result = await inf.run_inference(
        system_prompt="Extract the person.",
        inputs=[
            "page text",
            {"inline_data": {"mime_type": "image/jpeg", "data": "QUJD"}},
        ],
        structured_output_schema=_Person,
    )

    assert result == {"name": "Jane", "email": "jane@x.com"}
    second_call = inf.client.chat.completions.create.await_args_list[1].kwargs
    assert second_call["messages"][-1]["role"] == "user"
    assert "Validation errors" in second_call["messages"][-1]["content"]
    assert any(
        isinstance(message.get("content"), list)
        and any(part.get("type") == "image_url" for part in message["content"])
        for message in second_call["messages"]
    )


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
