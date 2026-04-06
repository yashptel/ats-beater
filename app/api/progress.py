import asyncio
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/progress", tags=["progress"])

# In-memory event bus
_subscribers: dict[str, list[asyncio.Queue]] = {}


def _key(entity_type: str, entity_id: int) -> str:
    return f"{entity_type}:{entity_id}"


async def publish(entity_type: str, entity_id: int, event: dict) -> None:
    key = _key(entity_type, entity_id)
    for queue in _subscribers.get(key, []):
        await queue.put(event)


def subscribe(entity_type: str, entity_id: int) -> asyncio.Queue:
    key = _key(entity_type, entity_id)
    queue = asyncio.Queue()
    _subscribers.setdefault(key, []).append(queue)
    return queue


def unsubscribe(entity_type: str, entity_id: int, queue: asyncio.Queue) -> None:
    key = _key(entity_type, entity_id)
    if key in _subscribers:
        _subscribers[key] = [q for q in _subscribers[key] if q is not queue]
        if not _subscribers[key]:
            del _subscribers[key]


@router.get("/{entity_type}/{entity_id}")
async def stream_progress(entity_type: str, entity_id: int):
    queue = subscribe(entity_type, entity_id)

    async def event_generator():
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                    import json

                    yield f"data: {json.dumps(event)}\n\n"
                    if event.get("status") in ("READY", "FAILED"):
                        break
                except asyncio.TimeoutError:
                    yield f"data: {{}}\n\n"  # keepalive
        finally:
            unsubscribe(entity_type, entity_id, queue)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
