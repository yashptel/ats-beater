from datetime import date
from unittest.mock import patch

import pytest
from sqlalchemy import select

from app.models.credit import CreditTransaction, UserCredit
from app.models.job import Job
from app.models.profile import Profile, ProfileStatus


@pytest.fixture
async def ready_profile(db_session, test_user):
    profile = Profile(
        user_id=test_user.id,
        status=ProfileStatus.READY,
        resume_info={
            "name": "Test User",
            "skills": [],
            "projects": [],
            "past_experience": [],
            "achievements": [],
            "educations": [],
            "certifications": [],
            "patents": [],
            "papers": [],
            "links": [],
        },
    )
    db_session.add(profile)
    await db_session.commit()
    await db_session.refresh(profile)
    return profile


@pytest.fixture
async def job_with_credit_balance(db_session, test_user, ready_profile):
    credit = UserCredit(
        user_id=test_user.id,
        balance=12,
        daily_free_used=0,
        daily_free_reset_date=date.today(),
    )
    job = Job(
        user_id=test_user.id,
        profile_id=ready_profile.id,
        job_description={
            "company": "Acme",
            "role": "Backend Engineer",
            "description": "Build APIs",
            "output_language": "english",
        },
    )
    db_session.add(credit)
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)
    return job


@pytest.mark.asyncio
async def test_list_jobs_empty(client):
    response = await client.get("/jobs/")
    assert response.status_code == 200
    data = response.json()
    assert data["items"] == []
    assert data["total"] == 0
    assert data["page"] == 1
    assert data["pages"] == 1
    assert data["limit"] == 10


@pytest.mark.asyncio
async def test_list_jobs_pagination_params(client):
    response = await client.get("/jobs/?page=2&limit=5")
    assert response.status_code == 200
    data = response.json()
    assert data["page"] == 2
    assert data["limit"] == 5
    assert data["items"] == []


@pytest.mark.asyncio
async def test_list_jobs_page_zero_rejected(client):
    response = await client.get("/jobs/?page=0")
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_list_jobs_limit_too_high(client):
    response = await client.get("/jobs/?limit=100")
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_job_without_ai_settings_still_works(client, ready_profile):
    response = await client.post(
        "/jobs/",
        json={
            "profile_id": ready_profile.id,
            "job_description": {
                "company": "Acme",
                "role": "Backend Engineer",
                "description": "Build APIs",
            },
        },
    )
    assert response.status_code == 201
    assert response.json()["status"] == "PENDING"


@pytest.mark.asyncio
async def test_generate_resume_requires_ai_settings(client, job_with_credit_balance):
    response = await client.post(f"/jobs/{job_with_credit_balance.id}/generate-resume")
    assert response.status_code == 400
    assert response.json()["detail"] == "ai_setup_required"


@pytest.mark.asyncio
async def test_generate_resume_no_longer_deducts_credits(
    client,
    db_session,
    configured_ai_settings,
    job_with_credit_balance,
):
    def _close_task(coro):
        coro.close()
        return None

    with patch("app.api.jobs.create_tracked_task", side_effect=_close_task):
        response = await client.post(f"/jobs/{job_with_credit_balance.id}/generate-resume")

    assert response.status_code == 202

    credit = await db_session.scalar(
        select(UserCredit).where(UserCredit.user_id == "test-user-id")
    )
    assert credit is not None
    assert credit.balance == 12

    transactions = await db_session.execute(select(CreditTransaction))
    assert transactions.scalars().all() == []
