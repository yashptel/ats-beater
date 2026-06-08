import pytest

from app.models.job import Job, JobStatus
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


from unittest.mock import AsyncMock, patch


@pytest.fixture
async def ready_job_with_resume(db_session, test_user, ready_profile):
    job = Job(
        user_id=test_user.id,
        profile_id=ready_profile.id,
        status=JobStatus.READY,
        template_id="jake",
        bold_keywords=True,
        job_description={
            "company": "Acme",
            "role": "Backend Engineer",
            "description": "Build APIs",
        },
        custom_resume_data={
            "name": "Test User",
            "email": "test@example.com",
            "location": "Remote",
            "skills": {"languages": ["Python"], "frameworks": [], "databases": [], "other_technologies": []},
            "past_experience": [
                {
                    "company_name": "Acme",
                    "role": "Dev",
                    "description": ["Worked with **Python**"],
                    "start_date": "2020-01",
                    "end_date": "2023-06",
                }
            ],
            "projects": [],
            "educations": [],
            "achievements": [],
            "certifications": [],
            "patents": [],
            "papers": [],
            "links": [],
        },
        resume_latex_code="old latex",
        pdf_gcs_path="/tmp/old.pdf",
    )
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)
    return job


@pytest.mark.asyncio
async def test_get_job_includes_bold_keywords(client, ready_job_with_resume):
    response = await client.get(f"/jobs/{ready_job_with_resume.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["bold_keywords"] is True


@pytest.mark.asyncio
async def test_toggle_bold_keywords_endpoint(client, db_session, ready_job_with_resume):
    async def noop_upload(*args, **kwargs):
        return None

    # First turn bold off (False)
    with (
        patch("app.services.job.service.compile_latex", new=AsyncMock(return_value=b"%PDF-1.4")),
        patch("app.services.job.service._background_gcs_upload", new=noop_upload),
    ):
        response = await client.post(
            f"/jobs/{ready_job_with_resume.id}/bold-keywords",
            json={"bold_keywords": False},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["bold_keywords"] is False
    assert data["status"] == "READY"

    await db_session.refresh(ready_job_with_resume)
    assert ready_job_with_resume.bold_keywords is False
    assert r"\textbf{Python}" not in ready_job_with_resume.resume_latex_code
    assert "Python" in ready_job_with_resume.resume_latex_code

    # Turn bold back on (True)
    with (
        patch("app.services.job.service.compile_latex", new=AsyncMock(return_value=b"%PDF-1.4")),
        patch("app.services.job.service._background_gcs_upload", new=noop_upload),
    ):
        response = await client.post(
            f"/jobs/{ready_job_with_resume.id}/bold-keywords",
            json={"bold_keywords": True},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["bold_keywords"] is True

    await db_session.refresh(ready_job_with_resume)
    assert ready_job_with_resume.bold_keywords is True
    assert r"\textbf{Python}" in ready_job_with_resume.resume_latex_code

