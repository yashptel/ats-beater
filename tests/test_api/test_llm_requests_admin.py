import pytest
from app.models.token_usage import LLMRequest


async def _seed_llm_requests(admin_client):
    """Seed LLMRequest rows via the DB session inside the admin client fixture."""
    from app.database.session import get_db
    app = admin_client._transport.app

    override = app.dependency_overrides.get(get_db)
    if override:
        async for db in override():
            db.add_all([
                LLMRequest(
                    user_id="admin-user-id",
                    purpose="profile_structuring",
                    reference_id="1",
                    model_name="gemini-3-flash-preview",
                    input_tokens=100, output_tokens=200, total_tokens=300,
                    response_time_ms=1000, success=True,
                ),
                LLMRequest(
                    user_id="admin-user-id",
                    purpose="resume_tailoring",
                    reference_id="2",
                    model_name="gemini-3.1-pro-preview",
                    input_tokens=500, output_tokens=800, total_tokens=1300,
                    response_time_ms=3000, success=True,
                ),
                LLMRequest(
                    user_id="admin-user-id",
                    purpose="profile_structuring",
                    reference_id="3",
                    model_name="gemini-3-flash-preview",
                    input_tokens=0, output_tokens=0, total_tokens=0,
                    response_time_ms=200, success=False,
                    error_message="Rate limit",
                ),
                # Row without user_id — tests null user handling
                LLMRequest(
                    user_id=None,
                    purpose="profile_structuring_vision",
                    reference_id="4",
                    model_name="gemini-3-flash-preview",
                    input_tokens=1000, output_tokens=400, total_tokens=1400,
                    response_time_ms=5000, success=True,
                ),
            ])
            await db.commit()
            break


@pytest.mark.asyncio
async def test_list_llm_requests(admin_client):
    await _seed_llm_requests(admin_client)
    resp = await admin_client.get("/admin/llm-requests")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert data["total"] == 4
    assert len(data["items"]) == 4
    assert data["page"] == 1
    assert data["limit"] == 50
    # Verify all expected fields present
    item = data["items"][0]
    expected_keys = {
        "id", "user_email", "purpose", "reference_id", "model_name",
        "input_tokens", "output_tokens", "total_tokens", "cached_tokens",
        "response_time_ms", "success", "error_message", "created_at",
    }
    assert expected_keys == set(item.keys())


@pytest.mark.asyncio
async def test_empty_table(admin_client):
    """No rows seeded — should return empty list, not error."""
    resp = await admin_client.get("/admin/llm-requests")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0
    assert data["items"] == []
    assert data["pages"] == 1


@pytest.mark.asyncio
async def test_filter_by_purpose(admin_client):
    await _seed_llm_requests(admin_client)
    resp = await admin_client.get("/admin/llm-requests?purpose=resume_tailoring")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["purpose"] == "resume_tailoring"


@pytest.mark.asyncio
async def test_filter_by_success_false(admin_client):
    await _seed_llm_requests(admin_client)
    resp = await admin_client.get("/admin/llm-requests?success=false")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["success"] is False
    assert data["items"][0]["error_message"] == "Rate limit"


@pytest.mark.asyncio
async def test_filter_by_success_true(admin_client):
    await _seed_llm_requests(admin_client)
    resp = await admin_client.get("/admin/llm-requests?success=true")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3  # 2 with user + 1 without user


@pytest.mark.asyncio
async def test_filter_by_model_name(admin_client):
    await _seed_llm_requests(admin_client)
    resp = await admin_client.get("/admin/llm-requests?model_name=gemini-3.1-pro-preview")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["model_name"] == "gemini-3.1-pro-preview"


@pytest.mark.asyncio
async def test_combined_filters(admin_client):
    """Filter by purpose + success simultaneously."""
    await _seed_llm_requests(admin_client)
    resp = await admin_client.get(
        "/admin/llm-requests?purpose=profile_structuring&success=true"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["purpose"] == "profile_structuring"
    assert data["items"][0]["success"] is True


@pytest.mark.asyncio
async def test_search_by_email(admin_client):
    await _seed_llm_requests(admin_client)
    resp = await admin_client.get("/admin/llm-requests?search=admin@example.com")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3  # Only rows with user, not the null-user row


@pytest.mark.asyncio
async def test_search_no_match(admin_client):
    await _seed_llm_requests(admin_client)
    resp = await admin_client.get("/admin/llm-requests?search=nobody@nowhere.com")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0


@pytest.mark.asyncio
async def test_null_user_email_in_response(admin_client):
    """LLMRequest with no user should return user_email=None."""
    await _seed_llm_requests(admin_client)
    resp = await admin_client.get("/admin/llm-requests?purpose=profile_structuring_vision")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["user_email"] is None
    assert data["items"][0]["purpose"] == "profile_structuring_vision"


@pytest.mark.asyncio
async def test_pagination(admin_client):
    await _seed_llm_requests(admin_client)
    resp = await admin_client.get("/admin/llm-requests?size=2&page=1")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 2
    assert data["total"] == 4
    assert data["pages"] == 2

    resp2 = await admin_client.get("/admin/llm-requests?size=2&page=2")
    data2 = resp2.json()
    assert len(data2["items"]) == 2


@pytest.mark.asyncio
async def test_pagination_beyond_last_page(admin_client):
    """Requesting a page beyond available data returns empty items."""
    await _seed_llm_requests(admin_client)
    resp = await admin_client.get("/admin/llm-requests?size=50&page=99")
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["total"] == 4


@pytest.mark.asyncio
async def test_regular_user_forbidden(client):
    resp = await client.get("/admin/llm-requests")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_filter_nonexistent_purpose(admin_client):
    """Filtering by a purpose that doesn't exist returns empty."""
    await _seed_llm_requests(admin_client)
    resp = await admin_client.get("/admin/llm-requests?purpose=nonexistent_purpose")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0
    assert data["items"] == []
