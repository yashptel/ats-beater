from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


class RoastPoint(BaseModel):
    emoji: str = Field(..., description="A single emoji that fits the roast point")
    text: str = Field(..., description="The roast point text, witty and sharp")

    @model_validator(mode="before")
    @classmethod
    def tolerate_text_only_point(cls, data: Any) -> Any:
        if isinstance(data, str):
            return {"emoji": "🔥", "text": data}
        if isinstance(data, dict) and "emoji" not in data and "text" in data:
            return {**data, "emoji": "🔥"}
        if isinstance(data, dict) and "text" not in data and "point" in data:
            return {"emoji": data.get("emoji", "🔥"), "text": data["point"]}
        return data


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

    @model_validator(mode="before")
    @classmethod
    def tolerate_provider_near_misses(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        values = {**data}
        if "roast_points" not in values and "roast" in values:
            values["roast_points"] = values["roast"]
        if "actual_feedback" not in values:
            for key in ("feedback", "constructive_feedback", "actualFeedback", "advice"):
                if key in values:
                    values["actual_feedback"] = values[key]
                    break
            else:
                verdict = str(values.get("verdict") or "").strip()
                prefix = f"{verdict} " if verdict else ""
                values["actual_feedback"] = (
                    f"{prefix}Address the ATS checklist items, tighten the resume structure, "
                    "and make the strongest experience easier to scan."
                )
        if "headline" not in values:
            values["headline"] = values.get("verdict") or "Resume Roast"

        return values

    @field_validator("actual_feedback", mode="before")
    @classmethod
    def coerce_feedback(cls, value: Any) -> Any:
        if isinstance(value, list):
            return " ".join(str(item).strip() for item in value if str(item).strip())
        return value


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
