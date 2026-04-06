import pytest


@pytest.mark.asyncio
async def test_list_roasts_empty(client):
    response = await client.get("/roasts/")
    assert response.status_code == 200
    data = response.json()
    assert data["items"] == []
    assert data["total"] == 0
    assert data["page"] == 1
    assert data["pages"] == 1
    assert data["limit"] == 10


@pytest.mark.asyncio
async def test_list_roasts_pagination_params(client):
    response = await client.get("/roasts/?page=2&limit=5")
    assert response.status_code == 200
    data = response.json()
    assert data["page"] == 2
    assert data["limit"] == 5
    assert data["items"] == []


@pytest.mark.asyncio
async def test_list_roasts_page_zero_rejected(client):
    response = await client.get("/roasts/?page=0")
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_list_roasts_limit_too_high(client):
    response = await client.get("/roasts/?limit=100")
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_roast_not_found(client):
    response = await client.get("/roasts/999")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_roast_status_not_found(client):
    response = await client.get("/roasts/999/status")
    assert response.status_code == 404
