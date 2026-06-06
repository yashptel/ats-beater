from unittest.mock import AsyncMock, patch

import pytest

from app.exceptions import AISettingsRequiredError, InvalidAISettingsError
from app.models.ai_settings import UserAISettings
from app.services.ai.user_settings import AISettingsService


@pytest.mark.asyncio
async def test_resolve_for_user_defaults_to_gemini_provider(db_session, test_user):
    """A settings row saved without an explicit provider (i.e. a migrated legacy
    row) resolves as the Gemini provider and still decrypts the key + model."""
    service = AISettingsService()
    row = UserAISettings(
        user_id=test_user.id,
        encrypted_api_key=service.encrypt_api_key("secret-api-key-1234"),
        api_key_last4="1234",
        model_name="gemini-3-flash-preview",
    )
    db_session.add(row)
    await db_session.commit()

    resolved = await service.resolve_for_user(db_session, test_user.id)

    assert resolved.provider == "gemini"
    assert resolved.api_key == "secret-api-key-1234"
    assert resolved.model_name == "gemini-3-flash-preview"


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


def test_ai_settings_accepts_gemini_3_5_flash():
    service = AISettingsService()
    service.ensure_allowed_model("gemini-3.5-flash")


def test_serialize_exposes_provider_fields():
    service = AISettingsService()
    row = UserAISettings(
        user_id="u1",
        provider="gemini",
        encrypted_api_key=service.encrypt_api_key("k"),
        api_key_last4="1234",
        model_name="gemini-3-flash-preview",
    )

    data = service.serialize(row)
    assert data["provider"] == "gemini"
    assert data["base_url"] is None
    assert data["reasoning_effort"] is None
    assert data["selected_model"] == "gemini-3-flash-preview"


def test_serialize_none_reports_no_provider():
    service = AISettingsService()
    data = service.serialize(None)
    assert data["has_ai_settings"] is False
    assert data["provider"] is None
    assert data["base_url"] is None


@pytest.mark.asyncio
async def test_model_only_update_preserves_encrypted_key_and_provider(db_session, test_user):
    service = AISettingsService()
    with patch.object(service, "validate_configuration", new=AsyncMock(return_value=None)):
        await service.upsert_settings(
            db_session, test_user.id,
            api_key="secret-key-1234", model_name="gemini-3-flash-preview",
        )
        first = await service.get_settings(db_session, test_user.id)
        original_encrypted = first.encrypted_api_key

        await service.upsert_settings(
            db_session, test_user.id, model_name="gemini-3.5-flash",
        )

    updated = await service.get_settings(db_session, test_user.id)
    assert updated.encrypted_api_key == original_encrypted
    assert updated.provider == "gemini"
    assert updated.model_name == "gemini-3.5-flash"


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
