"""Smoke tests for PostgreSQL database connection and CRUD."""
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.config import get_settings
from app.models.base import Base
from app.models.user import User
from app.models.profile import Profile, ProfileStatus


@pytest.fixture
def db_url():
    return get_settings().DATABASE_URL


@pytest.mark.asyncio
async def test_db_connection(db_url):
    """Verify we can connect to PostgreSQL and execute a simple query."""
    engine = create_async_engine(db_url)
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT 1"))
        assert result.scalar() == 1
    await engine.dispose()


@pytest.mark.asyncio
async def test_db_crud_user(db_url):
    """Create, read, update, delete a user in real PostgreSQL."""
    engine = create_async_engine(db_url)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with factory() as db:
        # Create
        user = User(
            google_id="smoke-test-user",
            email="smoke@test.com",
            name="Smoke Test",
            consent_accepted=True,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        user_id = user.id
        assert user_id is not None

        # Read
        fetched = await db.get(User, user_id)
        assert fetched is not None
        assert fetched.email == "smoke@test.com"

        # Update
        fetched.name = "Updated Smoke"
        await db.commit()
        await db.refresh(fetched)
        assert fetched.name == "Updated Smoke"

        # Delete
        await db.delete(fetched)
        await db.commit()
        gone = await db.get(User, user_id)
        assert gone is None

    await engine.dispose()


@pytest.mark.asyncio
async def test_db_crud_profile(db_url):
    """Create a profile linked to a user and verify the relationship."""
    engine = create_async_engine(db_url)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with factory() as db:
        # Setup user
        user = User(
            google_id="smoke-profile-user",
            email="profile-smoke@test.com",
            name="Profile Smoke",
            consent_accepted=True,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

        # Create profile
        profile = Profile(
            user_id=user.id,
            status=ProfileStatus.PENDING,
            resume_info={"name": "Test", "email": "test@test.com"},
        )
        db.add(profile)
        await db.commit()
        await db.refresh(profile)
        assert profile.id is not None
        assert profile.user_id == user.id

        # Cleanup
        await db.delete(profile)
        await db.delete(user)
        await db.commit()

    await engine.dispose()
