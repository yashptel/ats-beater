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
from app.services.chat.profile_chat import ProfileChatService
from app.services.profile.service import ProfileService
from app.exceptions import BadRequestError
from logging import getLogger

logger = getLogger(__name__)

router = APIRouter(prefix="/profiles", tags=["profile-chat"])
profile_chat_service = ProfileChatService()
profile_service = ProfileService()

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
    profile = await profile_service.get_profile(db, profile_id, current_user.id)

    if profile.status != ProfileStatus.READY:
        raise BadRequestError(
            f"Chat requires profile status READY, got {profile.status.value}"
        )

    if not profile.resume_info:
        raise BadRequestError("No resume data available for this profile")

    # Prepend client datetime/timezone as context for the AI (not shown in chat)
    message = body.message
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
                    async for event_data in profile_chat_service.chat_stream(
                        profile_id=_profile_id,
                        user_id=_user_id,
                        message=_message,
                        current_profile=_current_profile,
                    ):
                        if (event_data.get("type") == "response"
                                and event_data.get("resume_modified")
                                and event_data.get("resume_info")):
                            await task_db.execute(
                                sa_update(Profile).where(Profile.id == _profile_id).values(
                                    resume_info=event_data["resume_info"]
                                )
                            )
                            await task_db.commit()

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
    messages = await profile_chat_service.get_history(profile_id, current_user.id)
    return {"messages": messages}
