from app.services.chat.profile_chat import edit_profile
from app.services.chat.service import ChatService, edit_resume


def test_job_chat_system_prompt_renders_patch_example():
    prompt = ChatService()._build_system_prompt(
        {"company": "Acme", "role": "Backend Engineer"},
        {"name": "Jane Doe"},
    )

    assert '`[{"op":"replace","path":"/past_experience/0/description/0","value":"Built **X** with **Y**"}]`' in prompt
    assert "linked when a valid project URL exists" in prompt
    assert "delete `/summary` or set it to null" in prompt


def test_edit_resume_handles_missing_op_key_gracefully():
    original_resume = {
        "name": "Jane Doe",
        "email": "jane@example.com",
        "summary": "Backend engineer",
        "links": [],
        "projects": [],
        "past_experience": [],
        "achievements": [],
        "skills": {
            "languages": ["Python"],
            "frameworks": [],
            "databases": [],
            "other_technologies": [],
        },
        "educations": [],
        "certifications": [],
        "patents": [],
        "papers": [],
    }

    result, updated_resume = edit_resume(
        {"operations": [{"path": "/summary", "value": None}]},
        original_resume,
    )

    assert result["status"] == "error"
    assert updated_resume == original_resume


def test_edit_profile_handles_missing_op_key_gracefully():
    original_profile = {
        "name": "Jane Doe",
        "email": "jane@example.com",
        "mobile_number": None,
        "date_of_birth": None,
        "links": [],
        "past_experience": [],
        "projects": [],
        "skills": [],
        "educations": [],
        "achievements": [],
        "certifications": [],
        "patents": [],
        "papers": [],
    }

    result, updated_profile = edit_profile(
        {"operations": [{"path": "/name", "value": "Janet Doe"}]},
        original_profile,
    )

    assert result["status"] == "error"
    assert updated_profile == original_profile
