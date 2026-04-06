import pytest


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
