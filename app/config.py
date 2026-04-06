import os

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/custom_resume_dev"

    # AI
    GEMINI_API_KEY: str = ""
    GOOGLE_API_KEY: str = ""  # ADK reads this env var for Google AI API auth
    GEMINI_FLASH_MODEL: str = "gemini-3-flash-preview"
    GEMINI_PRO_MODEL: str = "gemini-3.1-pro-preview"

    # Auth
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    JWT_SECRET: str = "change-this-secret"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRY_HOURS: int = 24

    # Razorpay
    RAZORPAY_KEY_ID: str = ""
    RAZORPAY_KEY_SECRET: str = ""
    RAZORPAY_WEBHOOK_SECRET: str = ""

    # Credits
    DAILY_FREE_CREDITS: int = 3

    # Storage
    GCS_BUCKET: str = "your-gcs-bucket"
    GCS_CREDENTIALS_PATH: str = "credentials/gcs-service-account.json"

    # LaTeX
    LATEX_BIN_PATH: str = "/Library/TeX/texbin"

    # App
    ENVIRONMENT: str = "DEV"
    FRONTEND_URL: str = "http://localhost:8000"
    DEV_AUTH_BYPASS: bool = False

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    # Google ADK reads GOOGLE_API_KEY from os.environ (not from Pydantic fields).
    # Ensure it's set so the ADK Runner can create genai.Client() without explicit api_key.
    if settings.GOOGLE_API_KEY and not os.environ.get("GOOGLE_API_KEY"):
        os.environ["GOOGLE_API_KEY"] = settings.GOOGLE_API_KEY
    return settings
