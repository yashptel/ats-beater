"""Shared OpenAI-compatible Chat Completions tool-call loop for chat editing.

Both job chat (Custom Resume) and profile chat (Profile Resume) drive the same
tool-call loop, differing only in the tool set, the mutation callback, the
response payload key, and the logging metadata. This module factors that loop
out so the per-service code stays a thin adapter.
"""
import json
import time
from logging import getLogger
from typing import Any, AsyncGenerator, Callable

from app.services.ai.inference import _log_request

logger = getLogger(__name__)


def to_openai_tools(declarations: list[dict]) -> list[dict]:
    """Wrap ``{name, description, parameters}`` dicts as Chat Completions tools."""
    return [{"type": "function", "function": decl} for decl in declarations]


async def _create_and_log(
    *, client, model, messages, tools, reasoning_effort, user_id, purpose, reference_id
):
    t0 = time.monotonic()
    request_kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": 0.2,
    }
    if tools:
        request_kwargs["tools"] = tools
        request_kwargs["tool_choice"] = "auto"
    if reasoning_effort:
        request_kwargs["extra_body"] = {"reasoning_effort": reasoning_effort}

    try:
        response = await client.chat.completions.create(**request_kwargs)
    except Exception as exc:
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        await _log_request(
            model_name=model, user_id=user_id, purpose=purpose, reference_id=reference_id,
            input_tokens=0, output_tokens=0, total_tokens=0, cached_tokens=0,
            response_time_ms=elapsed_ms, success=False, error_message=str(exc)[:500],
        )
        raise

    elapsed_ms = int((time.monotonic() - t0) * 1000)
    usage = getattr(response, "usage", None)
    await _log_request(
        model_name=model, user_id=user_id, purpose=purpose, reference_id=reference_id,
        input_tokens=getattr(usage, "prompt_tokens", 0) if usage else 0,
        output_tokens=getattr(usage, "completion_tokens", 0) if usage else 0,
        total_tokens=getattr(usage, "total_tokens", 0) if usage else 0,
        cached_tokens=0, response_time_ms=elapsed_ms, success=True, error_message=None,
    )
    return response


async def stream_tool_chat(
    *,
    client,
    model: str,
    system_prompt: str,
    message: str,
    tools: list[dict],
    tool_labels: dict[str, str],
    execute_tool: Callable[[str, dict, Any], tuple[dict, Any, bool]],
    initial_state: Any,
    state_key: str,
    user_id: str,
    purpose: str,
    reference_id: str,
    fallback_message: str,
    reasoning_effort: str | None = None,
    max_iters: int = 6,
) -> AsyncGenerator[dict, None]:
    """Run the Chat Completions tool-call loop, yielding tool_call/response events.

    ``execute_tool(name, args, state) -> (result, new_state, modified)`` performs
    the mutation with the caller's validation. Tool results are appended back into
    the conversation until the model returns a final message or ``max_iters`` is hit.
    """
    messages: list[dict] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": message},
    ]
    state = initial_state
    modified = False

    for _ in range(max_iters):
        response = await _create_and_log(
            client=client, model=model, messages=messages, tools=tools,
            reasoning_effort=reasoning_effort, user_id=user_id,
            purpose=purpose, reference_id=reference_id,
        )
        choices = getattr(response, "choices", None) or []
        msg = getattr(choices[0], "message", None) if choices else None
        tool_calls = list(getattr(msg, "tool_calls", None) or []) if msg else []

        if not tool_calls:
            content = (getattr(msg, "content", "") or "").strip() if msg else ""
            yield {"type": "response", "response": content, "resume_modified": modified, state_key: state}
            return

        messages.append(
            {
                "role": "assistant",
                "content": (getattr(msg, "content", "") or ""),
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in tool_calls
                ],
            }
        )

        for tc in tool_calls:
            name = tc.function.name
            yield {"type": "tool_call", "name": name, "label": tool_labels.get(name, name)}
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            result, state, did_modify = execute_tool(name, args, state)
            if did_modify:
                modified = True
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps({"result": result}),
                }
            )

    yield {"type": "response", "response": fallback_message, "resume_modified": modified, state_key: state}
