import asyncio
import json
from typing import Optional

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import update as sa_update
from app.database.session import get_db, async_session_factory
from app.models.user import User
from app.models.profile import Profile, ProfileStatus
from app.dependencies import get_current_user
from app.services.ai.user_settings import AISettingsService
from app.services.chat.profile_chat import ProfileChatService
from app.services.chat.history import append_text_message, append_tool_call
from app.services.profile.service import ProfileService
from app.exceptions import BadRequestError
from logging import getLogger

logger = getLogger(__name__)

router = APIRouter(prefix="/profiles", tags=["profile-chat"])
profile_chat_service = ProfileChatService()
profile_service = ProfileService()
ai_settings_service = AISettingsService()

# In-flight agent tasks: task_key → (asyncio.Task, asyncio.Queue)
_active_tasks: dict[str, tuple[asyncio.Task, asyncio.Queue]] = {}


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    client_datetime: Optional[str] = None
    client_timezone: Optional[str] = None


@router.post("/{profile_id}/chat")
async def chat_with_profile(
    profile_id: int,
    body: ChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await ai_settings_service.require_settings(db, current_user.id)
    profile = await profile_service.get_profile(db, profile_id, current_user.id)

    if profile.status != ProfileStatus.READY:
        raise BadRequestError(
            f"Chat requires profile status READY, got {profile.status.value}"
        )

    if not profile.resume_info:
        raise BadRequestError("No resume data available for this profile")

    # Prepend client datetime/timezone as context for the AI (not shown in chat)
    raw_message = body.message
    message = raw_message
    if body.client_datetime:
        ctx = f"[User's current time: {body.client_datetime}"
        if body.client_timezone:
            ctx += f" ({body.client_timezone})"
        ctx += "]\n"
        message = ctx + message

    task_key = f"profile_chat_{profile_id}_{current_user.id}"

    # If an agent task is already running (same worker), reconnect to its event stream
    existing = _active_tasks.get(task_key)
    if existing and not existing[0].done():
        _, existing_queue = existing

        async def reconnect_stream():
            try:
                while True:
                    event_data = await existing_queue.get()
                    if event_data is None:
                        break
                    yield f"data: {json.dumps(event_data)}\n\n"
            except (asyncio.CancelledError, GeneratorExit):
                pass

        return StreamingResponse(reconnect_stream(), media_type="text/event-stream")

    queue: asyncio.Queue = asyncio.Queue()

    _profile_id = profile_id
    _user_id = current_user.id
    _current_profile = profile.resume_info
    _message = message

    async def run_agent():
        try:
            async with async_session_factory() as task_db:
                try:
                    ai_settings = await ai_settings_service.resolve_for_user(
                        task_db, _user_id
                    )
                    await append_text_message(
                        task_db,
                        user_id=_user_id,
                        entity_type="profile",
                        entity_id=_profile_id,
                        role="user",
                        content=raw_message,
                    )
                    async for event_data in profile_chat_service.chat_stream(
                        profile_id=_profile_id,
                        user_id=_user_id,
                        message=_message,
                        current_profile=_current_profile,
                        api_key=ai_settings.api_key,
                        model_name=ai_settings.model_name,
                    ):
                        if event_data.get("type") == "tool_call":
                            await append_tool_call(
                                task_db,
                                user_id=_user_id,
                                entity_type="profile",
                                entity_id=_profile_id,
                                tool_name=event_data["name"],
                                label=event_data["label"],
                            )

                        if (event_data.get("type") == "response"
                                and event_data.get("resume_modified")
                                and event_data.get("resume_info")):
                            await task_db.execute(
                                sa_update(Profile).where(Profile.id == _profile_id).values(
                                    resume_info=event_data["resume_info"]
                                )
                            )
                            await task_db.commit()
                        if event_data.get("type") == "response":
                            await append_text_message(
                                task_db,
                                user_id=_user_id,
                                entity_type="profile",
                                entity_id=_profile_id,
                                role="model",
                                content=event_data.get("response", ""),
                            )

                        await queue.put(event_data)
                except Exception as e:
                    logger.exception(f"Chat agent error for profile {_profile_id}")
                    await queue.put({"type": "error", "message": str(e)})
        except Exception as e:
            logger.exception(f"Chat task setup error for profile {_profile_id}")
            try:
                await queue.put({"type": "error", "message": str(e)})
            except Exception:
                pass
        finally:
            _active_tasks.pop(task_key, None)
            await queue.put(None)

    task = asyncio.create_task(run_agent())
    _active_tasks[task_key] = (task, queue)

    async def event_stream():
        try:
            while True:
                event_data = await queue.get()
                if event_data is None:
                    break
                yield f"data: {json.dumps(event_data)}\n\n"
        except (asyncio.CancelledError, GeneratorExit):
            pass

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/{profile_id}/chat/history")
async def get_profile_chat_history(
    profile_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Verify profile ownership
    await profile_service.get_profile(db, profile_id, current_user.id)
    messages = await profile_chat_service.get_history(db, profile_id, current_user.id)
    return {"messages": messages}
