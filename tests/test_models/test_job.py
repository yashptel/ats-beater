import pytest
from app.models.profile import Profile, ProfileStatus
from app.models.job import Job, JobStatus


@pytest.mark.asyncio
async def test_create_job(db_session, test_user):
    profile = Profile(user_id=test_user.id, status=ProfileStatus.READY)
    db_session.add(profile)
    await db_session.commit()
    await db_session.refresh(profile)

    job = Job(
        user_id=test_user.id,
        profile_id=profile.id,
        job_description={"company": "Acme", "role": "SWE"},
        status=JobStatus.PENDING,
    )
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)

    assert job.id is not None
    assert job.status == JobStatus.PENDING
    assert job.job_description["company"] == "Acme"
