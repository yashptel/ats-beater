from unittest.mock import AsyncMock, patch

import pytest

from app.exceptions import AISettingsRequiredError, InvalidAISettingsError
from app.services.ai.user_settings import AISettingsService


def test_ai_settings_encrypts_and_masks_keys():
    service = AISettingsService()
    encrypted = service.encrypt_api_key("secret-api-key-1234")

    assert encrypted != "secret-api-key-1234"
    assert service.decrypt_api_key(encrypted) == "secret-api-key-1234"
    assert service.mask_api_key("1234") == "••••••••••••1234"


def test_ai_settings_rejects_unknown_models():
    service = AISettingsService()
    with pytest.raises(InvalidAISettingsError):
        service.ensure_allowed_model("gemini-2.5-pro-preview")


@pytest.mark.asyncio
async def test_resolve_for_user_requires_saved_settings(db_session, test_user):
    service = AISettingsService()

    with pytest.raises(AISettingsRequiredError):
        await service.resolve_for_user(db_session, test_user.id)


@pytest.mark.asyncio
async def test_upsert_settings_supports_model_only_update(db_session, test_user):
    service = AISettingsService()

    with patch.object(
        service,
        "validate_configuration",
        new=AsyncMock(return_value=None),
    ):
        saved = await service.upsert_settings(
            db_session,
            test_user.id,
            api_key="secret-api-key-1234",
            model_name="gemini-3-flash-preview",
        )

        assert saved.api_key_last4 == "1234"
        assert saved.model_name == "gemini-3-flash-preview"
        assert saved.encrypted_api_key != "secret-api-key-1234"

        updated = await service.upsert_settings(
            db_session,
            test_user.id,
            model_name="gemini-3.1-flash-lite-preview",
        )

    assert updated.api_key_last4 == "1234"
    assert updated.model_name == "gemini-3.1-flash-lite-preview"

    resolved = await service.resolve_for_user(db_session, test_user.id)
    assert resolved.api_key == "secret-api-key-1234"
    assert resolved.model_name == "gemini-3.1-flash-lite-preview"
