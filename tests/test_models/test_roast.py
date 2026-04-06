import pytest
from sqlalchemy.exc import IntegrityError
from app.models.roast import Roast, RoastStatus
from app.schemas.roast import ATSCheckItem, OCRVerification, RoastResult


@pytest.mark.asyncio
async def test_create_roast(db_session, test_user):
    roast = Roast(
        user_id=test_user.id,
        file_hash="a" * 64,
        share_id="test1234",
        status=RoastStatus.PENDING,
    )
    db_session.add(roast)
    await db_session.commit()
    await db_session.refresh(roast)

    assert roast.id is not None
    assert roast.status == RoastStatus.PENDING
    assert roast.roast_data is None
    assert roast.extracted_text is None
    assert roast.file_hash == "a" * 64
    assert roast.share_id == "test1234"


@pytest.mark.asyncio
async def test_roast_status_transition(db_session, test_user):
    roast = Roast(
        user_id=test_user.id,
        file_hash="b" * 64,
        share_id="test5678",
        status=RoastStatus.PENDING,
    )
    db_session.add(roast)
    await db_session.commit()

    roast.status = RoastStatus.READY
    roast.roast_data = {
        "headline": "Test headline",
        "roast_points": [{"emoji": "🔥", "text": "You listed Microsoft Word as a skill"}],
        "actual_feedback": "Some real feedback",
        "score": 5,
        "verdict": "Mid at best",
        "ats_checklist": [
            {"label": "Contact Information", "passed": True, "detail": "Name, email, and phone found.", "category": "content"},
            {"label": "Single Column Layout", "passed": False, "detail": "Multi-column layout detected.", "category": "formatting"},
        ],
        "ocr_verification": {
            "text_matches_visual": True,
            "issues_found": [],
            "summary": "OCR text matches the visual content well.",
        },
    }
    await db_session.commit()
    await db_session.refresh(roast)

    assert roast.status == RoastStatus.READY
    assert roast.roast_data["headline"] == "Test headline"
    assert roast.roast_data["score"] == 5
    assert len(roast.roast_data["ats_checklist"]) == 2
    assert roast.roast_data["ats_checklist"][0]["passed"] is True
    assert roast.roast_data["ocr_verification"]["text_matches_visual"] is True


@pytest.mark.asyncio
async def test_roast_unique_constraint(db_session, test_user):
    file_hash = "c" * 64
    roast1 = Roast(user_id=test_user.id, file_hash=file_hash, share_id="uniq1111", status=RoastStatus.PENDING)
    db_session.add(roast1)
    await db_session.commit()

    roast2 = Roast(user_id=test_user.id, file_hash=file_hash, share_id="uniq2222", status=RoastStatus.PENDING)
    db_session.add(roast2)
    with pytest.raises(IntegrityError):
        await db_session.commit()


# --- Schema validation tests ---

def test_ats_check_item_schema():
    item = ATSCheckItem(label="Contact Info", passed=True, detail="Found email and phone.", category="content")
    assert item.label == "Contact Info"
    assert item.passed is True
    assert item.category == "content"


def test_ocr_verification_schema():
    ocr = OCRVerification(text_matches_visual=False, issues_found=["Skills section missing"], summary="Significant content missing from OCR.")
    assert ocr.text_matches_visual is False
    assert len(ocr.issues_found) == 1


def test_ocr_verification_defaults():
    ocr = OCRVerification(text_matches_visual=True, summary="All good.")
    assert ocr.issues_found == []


def test_roast_result_backward_compat():
    """Existing roasts without ats_checklist/ocr_verification should still parse."""
    old_data = {
        "headline": "Your resume is a cry for help",
        "roast_points": [{"emoji": "🔥", "text": "Word as a skill? Really?"}],
        "actual_feedback": "Honestly, just start over.",
        "score": 3,
        "verdict": "Guilty of resume crimes",
    }
    result = RoastResult(**old_data)
    assert result.ats_checklist == []
    assert result.ocr_verification is None
    assert result.score == 3


def test_roast_result_with_ats_data():
    data = {
        "headline": "Test",
        "roast_points": [{"emoji": "🔥", "text": "Test point"}],
        "actual_feedback": "Feedback",
        "score": 7,
        "verdict": "Verdict",
        "ats_checklist": [
            {"label": "Contact Info", "passed": True, "detail": "All present.", "category": "content"},
        ],
        "ocr_verification": {
            "text_matches_visual": True,
            "issues_found": [],
            "summary": "Good readability.",
        },
    }
    result = RoastResult(**data)
    assert len(result.ats_checklist) == 1
    assert result.ats_checklist[0].passed is True
    assert result.ocr_verification is not None
    assert result.ocr_verification.text_matches_visual is True
