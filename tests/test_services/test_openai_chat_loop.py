import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from app.services.chat.openai_chat import stream_tool_chat, to_openai_tools


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


def test_to_openai_tools_wraps_declarations():
    tools = to_openai_tools(
        [{"name": "x", "description": "d", "parameters": {"type": "object", "properties": {}}}]
    )
    assert tools[0]["type"] == "function"
    assert tools[0]["function"]["name"] == "x"


@pytest.mark.asyncio
async def test_tool_loop_executes_tool_then_continues():
    create = AsyncMock(
        side_effect=[
            _response(tool_calls=[_tool_call("c1", "edit_state", '{"value": 42}')]),
            _response(content="done"),
        ]
    )
    client = MagicMock()
    client.chat.completions.create = create

    executed = []

    def execute_tool(name, args, state):
        executed.append((name, args))
        return {"status": "success"}, {"value": args["value"]}, True

    events = []
    async for ev in stream_tool_chat(
        client=client, model="m", system_prompt="sys", message="hi",
        tools=[], tool_labels={"edit_state": "Editing..."}, execute_tool=execute_tool,
        initial_state={"value": 0}, state_key="data",
        user_id="u", purpose="p", reference_id="1", fallback_message="fallback",
    ):
        events.append(ev)

    assert any(e["type"] == "tool_call" and e["name"] == "edit_state" for e in events)
    final = events[-1]
    assert final["type"] == "response"
    assert final["response"] == "done"
    assert final["resume_modified"] is True
    assert final["data"] == {"value": 42}
    assert executed == [("edit_state", {"value": 42})]

    # The second model call must include the appended assistant + tool-result messages.
    second_messages = create.await_args_list[1].kwargs["messages"]
    roles = [m["role"] for m in second_messages]
    assert "assistant" in roles and "tool" in roles
    tool_msg = next(m for m in second_messages if m["role"] == "tool")
    assert tool_msg["tool_call_id"] == "c1"


@pytest.mark.asyncio
async def test_tool_loop_no_tool_calls_returns_text_immediately():
    create = AsyncMock(return_value=_response(content="just talking"))
    client = MagicMock()
    client.chat.completions.create = create

    events = []
    async for ev in stream_tool_chat(
        client=client, model="m", system_prompt="sys", message="hi",
        tools=[], tool_labels={}, execute_tool=lambda *a: (None, None, False),
        initial_state={"x": 1}, state_key="data",
        user_id="u", purpose="p", reference_id="1", fallback_message="fallback",
    ):
        events.append(ev)

    assert len(events) == 1
    assert events[0]["type"] == "response"
    assert events[0]["response"] == "just talking"
    assert events[0]["resume_modified"] is False
    assert create.await_count == 1
