import pytest
from app.models.token_usage import LLMRequest


@pytest.mark.asyncio
async def test_create_llm_request(db_session, test_user):
    row = LLMRequest(
        user_id=test_user.id,
        purpose="profile_structuring",
        reference_id="42",
        model_name="gemini-3-flash-preview",
        input_tokens=100,
        output_tokens=200,
        total_tokens=300,
        cached_tokens=50,
        response_time_ms=1234,
        success=True,
    )
    db_session.add(row)
    await db_session.commit()
    await db_session.refresh(row)

    assert row.id is not None
    assert row.user_id == test_user.id
    assert row.purpose == "profile_structuring"
    assert row.reference_id == "42"
    assert row.model_name == "gemini-3-flash-preview"
    assert row.input_tokens == 100
    assert row.output_tokens == 200
    assert row.total_tokens == 300
    assert row.cached_tokens == 50
    assert row.response_time_ms == 1234
    assert row.success is True
    assert row.error_message is None
    assert row.created_at is not None


@pytest.mark.asyncio
async def test_create_failed_llm_request(db_session, test_user):
    row = LLMRequest(
        user_id=test_user.id,
        purpose="resume_tailoring",
        reference_id="7",
        model_name="gemini-3.1-pro-preview",
        input_tokens=0,
        output_tokens=0,
        total_tokens=0,
        cached_tokens=0,
        response_time_ms=500,
        success=False,
        error_message="Rate limit exceeded",
    )
    db_session.add(row)
    await db_session.commit()
    await db_session.refresh(row)

    assert row.success is False
    assert row.error_message == "Rate limit exceeded"
    assert row.response_time_ms == 500


@pytest.mark.asyncio
async def test_llm_request_nullable_user(db_session):
    """LLMRequest can be created without a user_id."""
    row = LLMRequest(
        user_id=None,
        purpose="profile_structuring_vision",
        model_name="gemini-3-flash-preview",
        input_tokens=50,
        output_tokens=150,
        total_tokens=200,
        response_time_ms=800,
        success=True,
    )
    db_session.add(row)
    await db_session.commit()
    await db_session.refresh(row)

    assert row.id is not None
    assert row.user_id is None
    assert row.reference_id is None


@pytest.mark.asyncio
async def test_llm_request_defaults(db_session, test_user):
    """Verify default values when minimal fields are provided."""
    row = LLMRequest(
        user_id=test_user.id,
        purpose="resume_roast",
        model_name="gemini-3-flash-preview",
    )
    db_session.add(row)
    await db_session.commit()
    await db_session.refresh(row)

    assert row.input_tokens == 0
    assert row.output_tokens == 0
    assert row.total_tokens == 0
    assert row.cached_tokens == 0
    assert row.response_time_ms == 0
    assert row.success is True
    assert row.error_message is None
