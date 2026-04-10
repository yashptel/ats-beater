import json
from unittest.mock import patch

import pytest

from app.models.job import Job, JobStatus
from app.models.profile import Profile, ProfileStatus


@pytest.fixture
async def ready_job(db_session, test_user):
    profile = Profile(
        user_id=test_user.id,
        status=ProfileStatus.READY,
        resume_info={"name": "Test User", "skills": [], "projects": []},
    )
    db_session.add(profile)
    await db_session.commit()
    await db_session.refresh(profile)

    job = Job(
        user_id=test_user.id,
        profile_id=profile.id,
        status=JobStatus.READY,
        job_description={
            "company": "Acme",
            "role": "Backend Engineer",
            "description": "Build APIs",
            "output_language": "english",
        },
        custom_resume_data={
            "name": "Test User",
            "skills": {"languages": ["Python"], "frameworks": [], "databases": [], "other_technologies": []},
            "past_experience": [],
            "projects": [],
            "educations": [],
            "achievements": [],
            "certifications": [],
            "patents": [],
            "papers": [],
            "links": [],
        },
    )
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)
    return job


def _parse_sse(text: str) -> list[dict]:
    events = []
    for line in text.strip().split("\n"):
        if line.startswith("data: "):
            events.append(json.loads(line[6:]))
    return events


@pytest.mark.asyncio
async def test_job_chat_requires_ai_settings(client, ready_job):
    response = await client.post(f"/jobs/{ready_job.id}/chat", json={"message": "hello"})
    assert response.status_code == 400
    assert response.json()["detail"] == "ai_setup_required"


@pytest.mark.asyncio
async def test_job_chat_persists_history(client, ready_job, configured_ai_settings):
    async def mock_stream(**kwargs):
        yield {"type": "tool_call", "name": "get_resume", "label": "Reading resume..."}
        yield {
            "type": "response",
            "response": "Your tailored resume already highlights Python.",
            "resume_modified": False,
            "custom_resume_data": kwargs["current_resume"],
        }

    with patch(
        "app.api.chat.chat_service.chat_stream",
        side_effect=mock_stream,
    ):
        response = await client.post(
            f"/jobs/{ready_job.id}/chat",
            json={"message": "what stands out here?"},
        )

    assert response.status_code == 200
    events = _parse_sse(response.text)
    assert len(events) == 2
    assert events[0]["type"] == "tool_call"
    assert events[1]["type"] == "response"

    history_response = await client.get(f"/jobs/{ready_job.id}/chat/history")
    assert history_response.status_code == 200
    history = history_response.json()["messages"]
    assert history[0]["role"] == "user"
    assert history[0]["content"] == "what stands out here?"
    assert history[1]["type"] == "tool_call"
    assert history[1]["name"] == "get_resume"
    assert history[2]["role"] == "model"
    assert history[2]["content"] == "Your tailored resume already highlights Python."
