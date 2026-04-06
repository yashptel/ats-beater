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
from app.models.job import Job, JobStatus
from app.dependencies import get_current_user
from app.services.chat.service import ChatService
from app.services.job.service import JobService
from app.exceptions import BadRequestError
from logging import getLogger

logger = getLogger(__name__)

router = APIRouter(prefix="/jobs", tags=["chat"])
chat_service = ChatService()
job_service = JobService()

# In-flight agent tasks: task_key → (asyncio.Task, asyncio.Queue)
_active_tasks: dict[str, tuple[asyncio.Task, asyncio.Queue]] = {}


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    client_datetime: Optional[str] = None
    client_timezone: Optional[str] = None


CHAT_ALLOWED_STATUSES = {JobStatus.RESUME_GENERATED, JobStatus.READY}


@router.post("/{job_id}/chat")
async def chat_with_job(
    job_id: int,
    body: ChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    job = await job_service.get_job(db, job_id, current_user.id)

    if job.status not in CHAT_ALLOWED_STATUSES:
        raise BadRequestError(
            f"Chat requires job status RESUME_GENERATED or READY, got {job.status.value}"
        )

    if not job.custom_resume_data:
        raise BadRequestError("No resume data available for this job")

    # Load profile for system prompt context
    from app.models.profile import Profile
    profile = await db.get(Profile, job.profile_id)
    profile_info = profile.resume_info if profile and profile.resume_info else {}

    # Prepend client datetime/timezone as context for the AI (not shown in chat)
    message = body.message
    if body.client_datetime:
        ctx = f"[User's current time: {body.client_datetime}"
        if body.client_timezone:
            ctx += f" ({body.client_timezone})"
        ctx += "]\n"
        message = ctx + message

    task_key = f"job_chat_{job_id}_{current_user.id}"

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

    # Capture values for the detached task (request-scoped objects won't survive)
    _job_id = job_id
    _user_id = current_user.id
    _job_description = job.job_description or {}
    _profile_info = profile_info
    _current_resume = job.custom_resume_data
    _message = message

    async def run_agent():
        needs_recompile = False
        try:
            async with async_session_factory() as task_db:
                try:
                    async for event_data in chat_service.chat_stream(
                        job_id=_job_id,
                        user_id=_user_id,
                        message=_message,
                        job_description=_job_description,
                        profile_info=_profile_info,
                        current_resume=_current_resume,
                    ):
                        if (event_data.get("type") == "response"
                                and event_data.get("resume_modified")
                                and event_data.get("custom_resume_data")):
                            await task_db.execute(
                                sa_update(Job).where(Job.id == _job_id).values(
                                    custom_resume_data=event_data["custom_resume_data"]
                                )
                            )
                            await task_db.commit()
                            needs_recompile = True

                        await queue.put(event_data)
                except Exception as e:
                    logger.exception(f"Chat agent error for job {_job_id}")
                    await queue.put({"type": "error", "message": str(e)})

        except Exception as e:
            # Session factory failure
            logger.exception(f"Chat task setup error for job {_job_id}")
            try:
                await queue.put({"type": "error", "message": str(e)})
            except Exception:
                pass
        finally:
            # Clean up in-memory task and close the SSE stream *before* recompiling,
            # so follow-up chat messages aren't blocked during PDF compilation.
            _active_tasks.pop(task_key, None)
            await queue.put(None)  # sentinel — closes client SSE stream

        # Recompile PDF outside all task tracking
        if needs_recompile:
            try:
                async with async_session_factory() as pdf_db:
                    await job_service.generate_pdf(pdf_db, _job_id, _user_id, recompile=True)
            except Exception:
                logger.exception(f"PDF recompile failed for job {_job_id}")

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
            pass  # Client disconnected; agent task continues in background

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/{job_id}/chat/history")
async def get_chat_history(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Verify job ownership
    await job_service.get_job(db, job_id, current_user.id)
    messages = await chat_service.get_history(job_id, current_user.id)
    return {"messages": messages}
