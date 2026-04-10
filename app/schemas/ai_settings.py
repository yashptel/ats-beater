from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class AISettingsUpdateRequest(BaseModel):
    api_key: str | None = Field(default=None, min_length=1)
    model_name: str | None = None

    @model_validator(mode="after")
    def validate_payload(self) -> "AISettingsUpdateRequest":
        if not self.api_key and not self.model_name:
            raise ValueError("Provide api_key, model_name, or both")
        return self


class AISettingsResponse(BaseModel):
    has_ai_settings: bool
    selected_model: str | None = None
    masked_api_key: str | None = None
    api_key_last4: str | None = None
    validated_at: datetime | None = None
    allowed_models: list[str]
