import json

from app.services.ai.prompts import (
    CUSTOM_RESUME_SYSTEM_PROMPT,
    CUSTOM_RESUME_USER_PROMPT,
    ENHANCED_RESUME_SYSTEM_PROMPT,
    STRUCTURED_RESUME_SYSTEM_PROMPT,
)


def test_custom_resume_user_prompt_carries_profile_summary():
    summary_text = "Engineer with 5 years building distributed systems."
    user_info = {
        "name": "Test User",
        "email": "test@example.com",
        "summary": summary_text,
        "skills": [],
    }
    rendered = CUSTOM_RESUME_USER_PROMPT.format(
        user_info=json.dumps(user_info),
        job_description=json.dumps({"title": "Backend Engineer"}),
    )
    assert summary_text in rendered
    assert '"summary"' in rendered


def test_custom_resume_user_prompt_handles_null_summary():
    user_info = {"name": "Test User", "email": "test@example.com", "summary": None}
    rendered = CUSTOM_RESUME_USER_PROMPT.format(
        user_info=json.dumps(user_info),
        job_description=json.dumps({}),
    )
    assert '"summary": null' in rendered


def test_custom_resume_system_prompt_documents_baseline_behavior():
    assert "summary" in CUSTOM_RESUME_SYSTEM_PROMPT.lower()
    assert (
        "baseline" in CUSTOM_RESUME_SYSTEM_PROMPT.lower()
        or "starting point" in CUSTOM_RESUME_SYSTEM_PROMPT.lower()
    )


def test_structured_resume_prompt_extracts_summary_verbatim():
    text = STRUCTURED_RESUME_SYSTEM_PROMPT.lower()
    assert "summary" in text
    assert "verbatim" in text


def test_enhanced_resume_prompt_preserves_null_summary():
    text = ENHANCED_RESUME_SYSTEM_PROMPT.lower()
    assert "summary" in text
    assert "null" in text
