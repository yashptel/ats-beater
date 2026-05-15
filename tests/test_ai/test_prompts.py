import json

from app.services.ai.prompts import (
    CUSTOM_RESUME_SYSTEM_PROMPT,
    CUSTOM_RESUME_USER_PROMPT,
    ENHANCED_RESUME_SYSTEM_PROMPT,
    STRUCTURED_RESUME_SYSTEM_PROMPT,
)
from app.services.chat.service import CHAT_SYSTEM_PROMPT


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


def test_custom_resume_prompt_requires_reverse_chronological_experience():
    """Guards against silent removal of the ordering instruction.

    LLM compliance is non-deterministic; this test only protects the prompt
    from refactor drift. A property test against the live API is the right
    seam for behavioral verification but is out of scope for unit tests.
    """
    text = CUSTOM_RESUME_SYSTEM_PROMPT.lower()
    assert "reverse-chronological" in text or "reverse chronological" in text
    assert "past_experience" in text or "experience" in text


def test_custom_resume_schema_field_title_signals_ordering():
    from app.schemas.custom_resume import CustomResumeInfo

    schema = CustomResumeInfo.model_json_schema()
    past_experience_field = schema["properties"]["past_experience"]
    title = past_experience_field.get("title", "").lower()
    assert "reverse-chronological" in title or "most recent" in title


def test_chat_prompt_contains_interview_answer_section():
    """Guards the Interview Answer Drafting section against silent drift."""
    text = CHAT_SYSTEM_PROMPT
    assert "## Interview Answer Drafting" in text
    lower = text.lower()
    assert "behavioural" in lower or "behavioral" in lower
    assert "star breakdown" in lower
    assert "situation:" in lower
    assert "task:" in lower
    assert "action:" in lower
    assert "result:" in lower


def test_chat_prompt_contains_referral_section():
    """Guards the Referral Message Drafting section against silent drift."""
    text = CHAT_SYSTEM_PROMPT
    assert "## Referral Message Drafting" in text
    lower = text.lower()
    assert "channel" in lower
    assert "recipient" in lower
    assert "subject:" in lower
    assert "linkedin" in lower
    assert "one clarifying question" in lower


def test_chat_prompt_keeps_truthfulness_guard():
    """Both new sections must keep the never-fabricate guardrail."""
    text = CHAT_SYSTEM_PROMPT
    assert text.count("Truthfulness (ABSOLUTE)") >= 2
    lower = text.lower()
    assert "never invent" in lower
    assert "fabricate" in lower
