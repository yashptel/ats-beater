import pytest

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
async def ready_job(db_session, test_user, ready_profile):
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
async def test_generate_resume_requires_ai_settings(client, ready_job):
    response = await client.post(f"/jobs/{ready_job.id}/generate-resume")
    assert response.status_code == 400
    assert response.json()["detail"] == "ai_setup_required"
