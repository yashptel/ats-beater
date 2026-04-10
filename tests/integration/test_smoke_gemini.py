"""Smoke tests for Gemini AI inference — plain text and structured output."""
import pytest
from pydantic import BaseModel, Field
from typing import List, Optional

from app.services.ai.inference import GeminiInference
from app.config import get_settings


class SimpleOutput(BaseModel):
    """A simple structured output for testing."""
    greeting: str = Field(..., title="A greeting message")
    language: str = Field(..., title="The language of the greeting")


class PersonInfo(BaseModel):
    """More complex structured output."""
    name: str = Field(..., title="Person's name")
    age: Optional[int] = Field(default=None, title="Person's age")
    skills: List[str] = Field(default=[], title="List of skills")


@pytest.mark.asyncio
async def test_gemini_plain_text():
    """Verify Gemini can return a plain text response."""
    settings = get_settings()
    llm = GeminiInference(
        api_key=settings.GEMINI_API_KEY,
        model_name=settings.GEMINI_FLASH_MODEL,
    )

    result = await llm.run_inference(
        system_prompt="You are a helpful assistant. Reply briefly.",
        inputs=["Say 'hello world' and nothing else."],
    )

    assert isinstance(result, str)
    assert len(result) > 0
    assert "hello" in result.lower()


@pytest.mark.asyncio
async def test_gemini_structured_output():
    """Verify Gemini can return structured JSON output matching a Pydantic schema."""
    settings = get_settings()
    llm = GeminiInference(
        api_key=settings.GEMINI_API_KEY,
        model_name=settings.GEMINI_FLASH_MODEL,
    )

    result = await llm.run_inference(
        system_prompt="You generate structured data. Always respond in JSON matching the schema.",
        inputs=["Generate a greeting in English."],
        structured_output_schema=SimpleOutput,
    )

    assert isinstance(result, dict)
    assert "greeting" in result
    assert "language" in result
    assert isinstance(result["greeting"], str)
    assert len(result["greeting"]) > 0


@pytest.mark.asyncio
async def test_gemini_structured_output_complex():
    """Verify Gemini handles a more complex schema with lists and optionals."""
    settings = get_settings()
    llm = GeminiInference(
        api_key=settings.GEMINI_API_KEY,
        model_name=settings.GEMINI_FLASH_MODEL,
    )

    result = await llm.run_inference(
        system_prompt="You extract person information from text. Respond as JSON.",
        inputs=["John Doe is 30 years old and knows Python, JavaScript, and SQL."],
        structured_output_schema=PersonInfo,
    )

    assert isinstance(result, dict)
    assert result.get("name") is not None
    assert isinstance(result.get("skills", []), list)
    assert len(result["skills"]) > 0
