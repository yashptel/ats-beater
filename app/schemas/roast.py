from pydantic import BaseModel, Field


class RoastPoint(BaseModel):
    emoji: str = Field(..., description="A single emoji that fits the roast point")
    text: str = Field(..., description="The roast point text, witty and sharp")


class ATSCheckItem(BaseModel):
    label: str = Field(..., description="Check name, e.g. 'Contact Information'")
    passed: bool = Field(..., description="Whether the resume passes this check")
    detail: str = Field(..., description="1-2 sentence explanation of the result")
    category: str = Field(..., description="One of: parsing, content, formatting, keywords")


class OCRVerification(BaseModel):
    text_matches_visual: bool = Field(..., description="Whether OCR text broadly matches what is visible in the images")
    issues_found: list[str] = Field(default_factory=list, description="Specific discrepancies between OCR text and visual content")
    summary: str = Field(..., description="1-sentence assessment of machine-readability")


class RoastResult(BaseModel):
    headline: str = Field(..., description="A punchy one-liner headline roast")
    roast_points: list[RoastPoint] = Field(..., description="3-6 brutal roast points about the resume")
    actual_feedback: str = Field(..., description="Genuine, constructive feedback paragraph")
    score: int = Field(..., ge=1, le=10, description="Resume score from 1 (dumpster fire) to 10 (flawless)")
    verdict: str = Field(..., description="A short final verdict, like a judge's ruling")
    ats_checklist: list[ATSCheckItem] = Field(default_factory=list, description="8-12 ATS readiness checks")
    ocr_verification: OCRVerification | None = Field(default=None, description="OCR vs visual comparison result")


class RoastUploadResponse(BaseModel):
    roast_id: int
    status: str
    cached: bool
    extracted_text: str | None = None


class RoastResponse(BaseModel):
    id: int
    status: str
    roast_data: dict | None = None
    created_at: str
    updated_at: str
