import json
import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from app.services.ai.user_settings import ResolvedAISettings


def _tool_call(call_id, name, arguments):
    return SimpleNamespace(
        id=call_id, type="function",
        function=SimpleNamespace(name=name, arguments=arguments),
    )


def _response(content=None, tool_calls=None):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content, tool_calls=tool_calls))],
        usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2),
    )


def _edit_args(operations):
    return json.dumps({"operations_json": json.dumps(operations)})


def _openai_settings():
    return ResolvedAISettings(
        api_key="k", model_name="qwen", provider="openai_compatible",
        base_url="https://proxy.example.com/v1",
    )


@pytest.mark.asyncio
async def test_job_chat_openai_tool_mutation(monkeypatch):
    from app.services.chat.service import ChatService

    service = ChatService()
    create = AsyncMock(
        side_effect=[
            _response(tool_calls=[_tool_call(
                "c1", "edit_resume",
                _edit_args([{"op": "replace", "path": "/summary", "value": "New summary"}]),
            )]),
            _response(content="Updated your summary."),
        ]
    )
    fake_client = MagicMock()
    fake_client.chat.completions.create = create
    monkeypatch.setattr(service, "_make_openai_client", lambda ai_settings: fake_client)

    events = []
    async for ev in service.chat_stream(
        job_id=1, user_id="u", message="change summary",
        job_description={}, profile_info={},
        current_resume={"name": "A", "email": "a@x.com", "summary": "Old"},
        ai_settings=_openai_settings(),
    ):
        events.append(ev)

    assert any(e["type"] == "tool_call" and e["name"] == "edit_resume" for e in events)
    final = events[-1]
    assert final["type"] == "response"
    assert final["response"] == "Updated your summary."
    assert final["resume_modified"] is True
    assert final["custom_resume_data"]["summary"] == "New summary"


@pytest.mark.asyncio
async def test_profile_chat_openai_tool_mutation(monkeypatch):
    from app.services.chat.profile_chat import ProfileChatService

    service = ProfileChatService()
    create = AsyncMock(
        side_effect=[
            _response(tool_calls=[_tool_call(
                "c1", "edit_profile",
                _edit_args([{"op": "replace", "path": "/summary", "value": "Sharper summary"}]),
            )]),
            _response(content="Tightened your summary."),
        ]
    )
    fake_client = MagicMock()
    fake_client.chat.completions.create = create
    monkeypatch.setattr(service, "_make_openai_client", lambda ai_settings: fake_client)

    events = []
    async for ev in service.chat_stream(
        profile_id=7, user_id="u", message="tighten summary",
        current_profile={"name": "A", "email": "a@x.com", "summary": "Old"},
        ai_settings=_openai_settings(),
    ):
        events.append(ev)

    assert any(e["type"] == "tool_call" and e["name"] == "edit_profile" for e in events)
    final = events[-1]
    assert final["type"] == "response"
    assert final["resume_modified"] is True
    assert final["resume_info"]["summary"] == "Sharper summary"
