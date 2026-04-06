import pytest
from app.models.user import User


@pytest.mark.asyncio
async def test_create_user(db_session):
    user = User(
        google_id="google-test-456",
        email="newuser@example.com",
        name="New User",
        consent_accepted=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    assert user.id is not None
    assert user.email == "newuser@example.com"
    assert user.consent_accepted is True
