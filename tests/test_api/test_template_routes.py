from unittest.mock import AsyncMock, patch

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
            "email": "test@example.com",
            "location": "Remote",
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
        status=JobStatus.READY,
        template_id="jake",
        job_description={
            "company": "Acme",
            "role": "Backend Engineer",
            "description": "Build APIs",
            "output_language": "english",
        },
        custom_resume_data={
            "name": "Test User",
            "email": "test@example.com",
            "location": "Remote",
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
        resume_latex_code="old latex",
        pdf_gcs_path="/tmp/old.pdf",
    )
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)
    return job


@pytest.mark.asyncio
async def test_list_resume_templates(client):
    response = await client.get("/resume-templates/")
    assert response.status_code == 200
    data = response.json()
    assert data["default_template_id"] == "jake"
    assert [item["id"] for item in data["items"]] == ["jake", "mono", "hybrid"]


@pytest.mark.asyncio
async def test_update_default_resume_template(client, db_session, test_user):
    response = await client.put(
        "/auth/preferences",
        json={"default_resume_template_id": "hybrid"},
    )
    assert response.status_code == 200
    assert response.json()["default_resume_template_id"] == "hybrid"

    await db_session.refresh(test_user)
    assert test_user.default_resume_template_id == "hybrid"


@pytest.mark.asyncio
async def test_create_job_uses_user_default_template(client, db_session, test_user, ready_profile):
    test_user.default_resume_template_id = "mono"
    await db_session.commit()

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
    assert response.json()["template_id"] == "mono"


@pytest.mark.asyncio
async def test_create_job_allows_template_override(client, ready_profile):
    response = await client.post(
        "/jobs/",
        json={
            "profile_id": ready_profile.id,
            "template_id": "hybrid",
            "job_description": {
                "company": "Acme",
                "role": "Backend Engineer",
                "description": "Build APIs",
            },
        },
    )

    assert response.status_code == 201
    assert response.json()["template_id"] == "hybrid"


@pytest.mark.asyncio
async def test_apply_job_template_recompiles_without_ai(client, db_session, ready_job):
    async def noop_upload(*args, **kwargs):
        return None

    with (
        patch("app.services.job.service.compile_latex", new=AsyncMock(return_value=b"%PDF-1.4")),
        patch("app.services.job.service._background_gcs_upload", new=noop_upload),
    ):
        response = await client.post(
            f"/jobs/{ready_job.id}/template",
            json={"template_id": "mono"},
        )

    assert response.status_code == 200
    assert response.json()["template_id"] == "mono"

    await db_session.refresh(ready_job)
    assert ready_job.template_id == "mono"
    assert r"\section{TECHNICAL SKILLS}" in ready_job.resume_latex_code
