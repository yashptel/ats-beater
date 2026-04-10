from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat_message import ChatMessage


async def append_text_message(
    db: AsyncSession,
    *,
    user_id: str,
    entity_type: str,
    entity_id: int,
    role: str,
    content: str,
) -> None:
    db.add(
        ChatMessage(
            user_id=user_id,
            entity_type=entity_type,
            entity_id=entity_id,
            message_type="message",
            role=role,
            content=content,
        )
    )
    await db.commit()


async def append_tool_call(
    db: AsyncSession,
    *,
    user_id: str,
    entity_type: str,
    entity_id: int,
    tool_name: str,
    label: str,
) -> None:
    db.add(
        ChatMessage(
            user_id=user_id,
            entity_type=entity_type,
            entity_id=entity_id,
            message_type="tool_call",
            tool_name=tool_name,
            label=label,
        )
    )
    await db.commit()


async def load_history(
    db: AsyncSession,
    *,
    user_id: str,
    entity_type: str,
    entity_id: int,
) -> list[dict]:
    result = await db.execute(
        select(ChatMessage)
        .where(
            ChatMessage.user_id == user_id,
            ChatMessage.entity_type == entity_type,
            ChatMessage.entity_id == entity_id,
        )
        .order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc())
    )
    messages = []
    for row in result.scalars().all():
        timestamp = row.created_at.timestamp()
        if row.message_type == "tool_call":
            messages.append(
                {
                    "type": "tool_call",
                    "name": row.tool_name,
                    "label": row.label,
                    "timestamp": timestamp,
                }
            )
        else:
            messages.append(
                {
                    "role": row.role,
                    "content": row.content,
                    "timestamp": timestamp,
                }
            )
    return messages
