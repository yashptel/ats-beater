import pytest

from app.models.profile import Profile, ProfileStatus


@pytest.fixture
async def ready_profile(db_session, test_user):
    profile = Profile(
        user_id=test_user.id,
        status=ProfileStatus.READY,
        resume_info={"name": "Test User", "skills": []},
    )
    db_session.add(profile)
    await db_session.commit()
    await db_session.refresh(profile)
    return profile


@pytest.mark.asyncio
async def test_list_profiles_empty(client):
    response = await client.get("/profiles/")
    assert response.status_code == 200
    data = response.json()
    assert data["items"] == []
    assert data["total"] == 0
    assert data["page"] == 1
    assert data["pages"] == 1
    assert data["limit"] == 10


@pytest.mark.asyncio
async def test_list_profiles_pagination_params(client):
    response = await client.get("/profiles/?page=2&limit=5")
    assert response.status_code == 200
    data = response.json()
    assert data["page"] == 2
    assert data["limit"] == 5
    assert data["items"] == []


@pytest.mark.asyncio
async def test_list_profiles_page_zero_rejected(client):
    response = await client.get("/profiles/?page=0")
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_list_profiles_limit_too_high(client):
    response = await client.get("/profiles/?limit=100")
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_profile_not_found(client):
    response = await client.get("/profiles/999")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_upload_requires_ai_settings(client):
    response = await client.post(
        "/profiles/upload",
        files={"file": ("resume.pdf", b"%PDF-1.4 test", "application/pdf")},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "ai_setup_required"


@pytest.mark.asyncio
async def test_enhance_requires_ai_settings(client, ready_profile):
    response = await client.post(f"/profiles/{ready_profile.id}/enhance")
    assert response.status_code == 400
    assert response.json()["detail"] == "ai_setup_required"


@pytest.mark.asyncio
async def test_put_profile_persists_summary(client, ready_profile):
    summary_text = "Engineer with 5 years building distributed systems."
    response = await client.put(
        f"/profiles/{ready_profile.id}",
        json={
            "resume_info": {
                "name": "Test User",
                "email": "test@example.com",
                "summary": summary_text,
                "skills": [],
            }
        },
    )
    assert response.status_code == 200

    fetched = await client.get(f"/profiles/{ready_profile.id}")
    assert fetched.status_code == 200
    assert fetched.json()["resume_info"]["summary"] == summary_text


@pytest.mark.asyncio
async def test_put_profile_clears_summary_with_null(client, ready_profile):
    await client.put(
        f"/profiles/{ready_profile.id}",
        json={
            "resume_info": {
                "name": "Test User",
                "email": "test@example.com",
                "summary": "Some text to be cleared.",
            }
        },
    )

    response = await client.put(
        f"/profiles/{ready_profile.id}",
        json={
            "resume_info": {
                "name": "Test User",
                "email": "test@example.com",
                "summary": None,
            }
        },
    )
    assert response.status_code == 200

    fetched = await client.get(f"/profiles/{ready_profile.id}")
    assert fetched.json()["resume_info"]["summary"] is None
