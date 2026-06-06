from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class AISettingsUpdateRequest(BaseModel):
    provider: str | None = None
    api_key: str | None = Field(default=None, min_length=1)
    model_name: str | None = None
    base_url: str | None = None
    reasoning_effort: str | None = None

    @model_validator(mode="after")
    def validate_payload(self) -> "AISettingsUpdateRequest":
        if not any([self.provider, self.api_key, self.model_name, self.base_url]):
            raise ValueError("Provide at least one AI settings field")
        return self


class ModelDiscoveryRequest(BaseModel):
    base_url: str
    api_key: str | None = None


class ModelDiscoveryResponse(BaseModel):
    models: list[str]
    error: str | None = None


class AISettingsResponse(BaseModel):
    has_ai_settings: bool
    provider: str | None = None
    selected_model: str | None = None
    base_url: str | None = None
    reasoning_effort: str | None = None
    masked_api_key: str | None = None
    api_key_last4: str | None = None
    validated_at: datetime | None = None
    allowed_models: list[str]
