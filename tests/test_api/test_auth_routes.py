from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_get_me_includes_ai_status(client):
    response = await client.get("/auth/me")
    assert response.status_code == 200
    assert response.json()["has_ai_settings"] is False
    assert response.json()["selected_model"] is None


@pytest.mark.asyncio
async def test_ai_settings_crud_flow(client):
    response = await client.get("/auth/ai-settings")
    assert response.status_code == 200
    data = response.json()
    assert data["has_ai_settings"] is False
    assert "gemini-3-flash-preview" in data["allowed_models"]

    with patch(
        "app.api.auth.ai_settings_service.validate_configuration",
        new=AsyncMock(return_value=None),
    ):
        save_response = await client.put(
            "/auth/ai-settings",
            json={
                "api_key": "test-api-key-9999",
                "model_name": "gemini-3-flash-preview",
            },
        )
    assert save_response.status_code == 200
    saved = save_response.json()
    assert saved["has_ai_settings"] is True
    assert saved["selected_model"] == "gemini-3-flash-preview"
    assert saved["api_key_last4"] == "9999"
    assert saved["masked_api_key"].endswith("9999")
    assert saved["validated_at"] is not None

    me_response = await client.get("/auth/me")
    assert me_response.status_code == 200
    assert me_response.json()["has_ai_settings"] is True
    assert me_response.json()["selected_model"] == "gemini-3-flash-preview"

    with patch(
        "app.api.auth.ai_settings_service.validate_configuration",
        new=AsyncMock(return_value=None),
    ):
        update_response = await client.put(
            "/auth/ai-settings",
            json={"model_name": "gemini-3.1-flash-lite-preview"},
        )
    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["selected_model"] == "gemini-3.1-flash-lite-preview"
    assert updated["api_key_last4"] == "9999"

    delete_response = await client.delete("/auth/ai-settings")
    assert delete_response.status_code == 200
    deleted = delete_response.json()
    assert deleted["has_ai_settings"] is False
    assert deleted["selected_model"] is None
    assert deleted["masked_api_key"] is None


@pytest.mark.asyncio
async def test_ai_settings_rejects_unsupported_model(client):
    response = await client.put(
        "/auth/ai-settings",
        json={
            "api_key": "test-api-key-9999",
            "model_name": "gemini-2.5-pro-preview",
        },
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "invalid_ai_settings"
