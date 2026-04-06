import hashlib
import struct
from datetime import datetime, date, timezone
from fastapi import Depends, Header
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from app.database.session import get_db
from app.config import get_settings, Settings
from app.services.auth.jwt_handler import verify_token
from app.models import User
from app.models.credit import UserCredit
from app.exceptions import AuthenticationError, ForbiddenError

DEV_USER_GOOGLE_ID = "dev-bypass-user"
DEV_USER_EMAIL = "dev@localhost"
DEV_USER_NAME = "Dev User"


async def _get_or_create_dev_user(db: AsyncSession) -> User:
    result = await db.execute(select(User).where(User.google_id == DEV_USER_GOOGLE_ID))
    user = result.scalar_one_or_none()
    if not user:
        user = User(
            google_id=DEV_USER_GOOGLE_ID,
            email=DEV_USER_EMAIL,
            name=DEV_USER_NAME,
            consent_accepted=True,
            consent_accepted_at=datetime.now(timezone.utc),
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

    # Ensure UserCredit row exists
    uc_result = await db.execute(select(UserCredit).where(UserCredit.user_id == user.id))
    if not uc_result.scalar_one_or_none():
        uc = UserCredit(
            user_id=user.id,
            balance=0,
            daily_free_used=0,
            daily_free_reset_date=datetime.now(timezone.utc).date(),
        )
        db.add(uc)
        await db.commit()

    return user


async def get_current_user(
    authorization: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> User:
    settings = get_settings()

    if settings.DEV_AUTH_BYPASS:
        if settings.ENVIRONMENT not in ("DEV", "dev"):
            raise RuntimeError("DEV_AUTH_BYPASS cannot be enabled outside DEV environment")
        return await _get_or_create_dev_user(db)

    if not authorization or not authorization.startswith("Bearer "):
        raise AuthenticationError("Invalid authorization header")
    token = authorization[7:]
    payload = verify_token(token)
    user = await db.get(User, payload["sub"])
    if not user:
        raise AuthenticationError("User not found")
    return user


async def get_super_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    if not current_user.is_super_admin:
        raise ForbiddenError("Super admin access required")
    return current_user


def _lock_key(session_key: str) -> int:
    """Derive a stable int64 from a string for PostgreSQL advisory locks."""
    return struct.unpack("q", hashlib.md5(session_key.encode()).digest()[:8])[0]


async def try_chat_lock(db: AsyncSession, session_key: str) -> bool:
    """Acquire a PostgreSQL advisory lock for a chat session.

    Returns True if acquired, False if another worker already holds it.
    Falls back to True (no-op) for non-PostgreSQL backends (e.g. SQLite tests).
    """
    try:
        result = await db.execute(
            text("SELECT pg_try_advisory_lock(:k)"), {"k": _lock_key(session_key)}
        )
        return result.scalar()
    except Exception:
        return True


async def release_chat_lock(db: AsyncSession, session_key: str, *, rollback_first: bool = False):
    """Release a PostgreSQL advisory lock for a chat session.

    When *rollback_first* is True, issue a ROLLBACK before the unlock to
    ensure the connection is in a clean transaction state (needed after
    agent runs that may have left uncommitted work on the session).
    Advisory locks are session-level and survive ROLLBACK.
    """
    try:
        if rollback_first:
            try:
                await db.rollback()
            except Exception:
                pass
        await db.execute(
            text("SELECT pg_advisory_unlock(:k)"), {"k": _lock_key(session_key)}
        )
    except Exception:
        pass


__all__ = ["get_db", "get_settings", "get_current_user", "get_super_admin", "try_chat_lock", "release_chat_lock"]
