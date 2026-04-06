import json
import pytest
from unittest.mock import AsyncMock, patch

from app.models.profile import Profile, ProfileStatus


SAMPLE_RESUME_INFO = {
    "name": "Test User",
    "email": "test@example.com",
    "links": [],
    "projects": [],
    "past_experience": [],
    "achievements": [],
    "skills": [{"name": "Python", "category": "Programming"}],
    "educations": [],
    "certifications": [],
    "patents": [],
    "papers": [],
}


@pytest.fixture
async def ready_profile(db_session, test_user):
    profile = Profile(
        user_id=test_user.id,
        status=ProfileStatus.READY,
        resume_info=SAMPLE_RESUME_INFO,
    )
    db_session.add(profile)
    await db_session.commit()
    await db_session.refresh(profile)
    return profile


@pytest.fixture
async def pending_profile(db_session, test_user):
    profile = Profile(
        user_id=test_user.id,
        status=ProfileStatus.PENDING,
        resume_info=None,
    )
    db_session.add(profile)
    await db_session.commit()
    await db_session.refresh(profile)
    return profile


def _parse_sse(text: str) -> list[dict]:
    """Parse SSE text into a list of event dicts."""
    events = []
    for line in text.strip().split("\n"):
        if line.startswith("data: "):
            events.append(json.loads(line[6:]))
    return events


# ── POST /profiles/{id}/chat ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_chat_profile_not_found(client):
    response = await client.post("/profiles/999/chat", json={"message": "hello"})
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_chat_profile_not_ready(client, pending_profile):
    response = await client.post(
        f"/profiles/{pending_profile.id}/chat", json={"message": "hello"}
    )
    assert response.status_code == 400
    assert "READY" in response.json()["detail"]


@pytest.mark.asyncio
async def test_chat_profile_no_resume_info(client, db_session, test_user):
    profile = Profile(
        user_id=test_user.id,
        status=ProfileStatus.READY,
        resume_info=None,
    )
    db_session.add(profile)
    await db_session.commit()
    await db_session.refresh(profile)

    response = await client.post(
        f"/profiles/{profile.id}/chat", json={"message": "hello"}
    )
    assert response.status_code == 400
    assert "No resume data" in response.json()["detail"]


@pytest.mark.asyncio
async def test_chat_message_empty(client, ready_profile):
    response = await client.post(
        f"/profiles/{ready_profile.id}/chat", json={"message": ""}
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_chat_message_too_long(client, ready_profile):
    response = await client.post(
        f"/profiles/{ready_profile.id}/chat", json={"message": "x" * 2001}
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_chat_success_no_modification(client, ready_profile):
    async def mock_stream(**kwargs):
        yield {
            "type": "response",
            "response": "Your profile looks great!",
            "resume_modified": False,
            "resume_info": SAMPLE_RESUME_INFO,
        }

    with patch(
        "app.api.profile_chat.profile_chat_service.chat_stream",
        side_effect=mock_stream,
    ):
        response = await client.post(
            f"/profiles/{ready_profile.id}/chat",
            json={"message": "show me my skills"},
        )
    assert response.status_code == 200
    events = _parse_sse(response.text)
    assert len(events) == 1
    assert events[0]["response"] == "Your profile looks great!"
    assert events[0]["resume_modified"] is False


@pytest.mark.asyncio
async def test_chat_success_with_modification(client, db_session, ready_profile):
    updated_info = {
        **SAMPLE_RESUME_INFO,
        "skills": [
            {"name": "Python", "category": "Programming"},
            {"name": "Go", "category": "Programming"},
        ],
    }

    async def mock_stream(**kwargs):
        yield {"type": "tool_call", "name": "get_profile", "label": "Reading profile..."}
        yield {"type": "tool_call", "name": "edit_profile", "label": "Editing profile..."}
        yield {
            "type": "response",
            "response": "Added Go to your Programming skills.",
            "resume_modified": True,
            "resume_info": updated_info,
        }

    with patch(
        "app.api.profile_chat.profile_chat_service.chat_stream",
        side_effect=mock_stream,
    ):
        response = await client.post(
            f"/profiles/{ready_profile.id}/chat",
            json={"message": "add Go to my programming skills"},
        )
    assert response.status_code == 200
    events = _parse_sse(response.text)
    assert len(events) == 3
    assert events[0]["type"] == "tool_call"
    assert events[1]["type"] == "tool_call"
    assert events[2]["resume_modified"] is True
    assert len(events[2]["resume_info"]["skills"]) == 2

    # Verify persisted to DB
    await db_session.refresh(ready_profile)
    assert len(ready_profile.resume_info["skills"]) == 2
    assert ready_profile.resume_info["skills"][1]["name"] == "Go"


# ── GET /profiles/{id}/chat/history ──────────────────────────────────


@pytest.mark.asyncio
async def test_chat_history_profile_not_found(client):
    response = await client.get("/profiles/999/chat/history")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_chat_history_empty(client, ready_profile):
    with patch(
        "app.api.profile_chat.profile_chat_service.get_history",
        new_callable=AsyncMock,
        return_value=[],
    ):
        response = await client.get(
            f"/profiles/{ready_profile.id}/chat/history"
        )
    assert response.status_code == 200
    assert response.json() == {"messages": []}


@pytest.mark.asyncio
async def test_chat_history_with_messages(client, ready_profile):
    mock_messages = [
        {"role": "user", "content": "show my skills", "timestamp": 1700000000.0},
        {"role": "model", "content": "You have Python.", "timestamp": 1700000001.0},
    ]
    with patch(
        "app.api.profile_chat.profile_chat_service.get_history",
        new_callable=AsyncMock,
        return_value=mock_messages,
    ):
        response = await client.get(
            f"/profiles/{ready_profile.id}/chat/history"
        )
    assert response.status_code == 200
    data = response.json()
    assert len(data["messages"]) == 2
    assert data["messages"][0]["role"] == "user"
    assert data["messages"][1]["role"] == "model"
