import pytest

from app.models.ai_settings import UserAISettings


@pytest.mark.asyncio
async def test_new_ai_settings_row_defaults_provider_to_gemini(db_session, test_user):
    """Mirrors the migration default: a row inserted without a provider lands as
    'gemini' with no OpenAI-compatible fields set."""
    row = UserAISettings(
        user_id=test_user.id,
        encrypted_api_key="enc",
        api_key_last4="1234",
        model_name="gemini-3-flash-preview",
    )
    db_session.add(row)
    await db_session.commit()
    await db_session.refresh(row)

    assert row.provider == "gemini"
    assert row.base_url is None
    assert row.reasoning_effort is None
