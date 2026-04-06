import pytest
from app.models.profile import Profile, ProfileStatus


@pytest.mark.asyncio
async def test_create_profile(db_session, test_user):
    profile = Profile(
        user_id=test_user.id,
        status=ProfileStatus.PENDING,
    )
    db_session.add(profile)
    await db_session.commit()
    await db_session.refresh(profile)

    assert profile.id is not None
    assert profile.status == ProfileStatus.PENDING
    assert profile.is_active is True
    assert profile.resume_info is None


@pytest.mark.asyncio
async def test_profile_status_transition(db_session, test_user):
    profile = Profile(user_id=test_user.id, status=ProfileStatus.PENDING)
    db_session.add(profile)
    await db_session.commit()

    profile.status = ProfileStatus.READY
    profile.resume_info = {"name": "Test", "email": "test@test.com"}
    await db_session.commit()
    await db_session.refresh(profile)

    assert profile.status == ProfileStatus.READY
    assert profile.resume_info["name"] == "Test"
