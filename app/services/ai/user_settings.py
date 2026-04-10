from dataclasses import dataclass
from datetime import datetime, timezone

from cryptography.fernet import Fernet, MultiFernet
from google import genai
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.exceptions import AISettingsRequiredError, InvalidAISettingsError
from app.models.ai_settings import UserAISettings

ALLOWED_GEMINI_MODELS = (
    "gemini-3-flash-preview",
    "gemini-3.1-pro-preview",
    "gemini-3.1-flash-lite-preview",
)


@dataclass
class ResolvedAISettings:
    api_key: str
    model_name: str
    validated_at: datetime | None = None


class AISettingsService:
    def __init__(self) -> None:
        self.allowed_models = list(ALLOWED_GEMINI_MODELS)

    def _cipher(self) -> MultiFernet:
        settings = get_settings()
        raw_keys = [
            item.strip()
            for item in settings.USER_API_KEY_ENCRYPTION_KEY.split(",")
            if item.strip()
        ]
        if not raw_keys:
            raise RuntimeError("USER_API_KEY_ENCRYPTION_KEY is not configured")
        return MultiFernet([Fernet(key.encode("utf-8")) for key in raw_keys])

    def encrypt_api_key(self, api_key: str) -> str:
        return self._cipher().encrypt(api_key.encode("utf-8")).decode("utf-8")

    def decrypt_api_key(self, encrypted_api_key: str) -> str:
        return self._cipher().decrypt(encrypted_api_key.encode("utf-8")).decode("utf-8")

    def mask_api_key(self, last4: str | None) -> str | None:
        if not last4:
            return None
        return f"••••••••••••{last4}"

    def ensure_allowed_model(self, model_name: str) -> None:
        if model_name not in self.allowed_models:
            raise InvalidAISettingsError(
                "Select one of the supported Gemini models."
            )

    async def get_settings(self, db: AsyncSession, user_id: str) -> UserAISettings | None:
        return await db.get(UserAISettings, user_id)

    async def require_settings(self, db: AsyncSession, user_id: str) -> UserAISettings:
        ai_settings = await self.get_settings(db, user_id)
        if not ai_settings:
            raise AISettingsRequiredError()
        return ai_settings

    async def resolve_for_user(self, db: AsyncSession, user_id: str) -> ResolvedAISettings:
        ai_settings = await self.require_settings(db, user_id)
        self.ensure_allowed_model(ai_settings.model_name)
        return ResolvedAISettings(
            api_key=self.decrypt_api_key(ai_settings.encrypted_api_key),
            model_name=ai_settings.model_name,
            validated_at=ai_settings.validated_at,
        )

    async def validate_configuration(self, api_key: str, model_name: str) -> None:
        self.ensure_allowed_model(model_name)
        try:
            client = genai.Client(api_key=api_key)
            response = await client.aio.models.generate_content(
                model=model_name,
                contents="Reply with OK.",
            )
            if not getattr(response, "text", "").strip():
                raise InvalidAISettingsError("Gemini validation returned an empty response.")
        except InvalidAISettingsError:
            raise
        except Exception as exc:
            raise InvalidAISettingsError(
                "Unable to validate that Gemini API key with the selected model."
            ) from exc

    async def upsert_settings(
        self,
        db: AsyncSession,
        user_id: str,
        *,
        api_key: str | None = None,
        model_name: str | None = None,
    ) -> UserAISettings:
        existing = await self.get_settings(db, user_id)
        if not existing and not api_key:
            raise InvalidAISettingsError("Add a Gemini API key before selecting a model.")

        if existing:
            resolved_api_key = api_key or self.decrypt_api_key(existing.encrypted_api_key)
            resolved_model = model_name or existing.model_name
        else:
            resolved_api_key = api_key or ""
            resolved_model = model_name or self.allowed_models[0]

        await self.validate_configuration(resolved_api_key, resolved_model)

        if not existing:
            existing = UserAISettings(
                user_id=user_id,
                encrypted_api_key=self.encrypt_api_key(resolved_api_key),
                api_key_last4=resolved_api_key[-4:],
                model_name=resolved_model,
                validated_at=datetime.now(timezone.utc),
            )
            db.add(existing)
        else:
            if api_key:
                existing.encrypted_api_key = self.encrypt_api_key(resolved_api_key)
                existing.api_key_last4 = resolved_api_key[-4:]
            existing.model_name = resolved_model
            existing.validated_at = datetime.now(timezone.utc)

        await db.commit()
        await db.refresh(existing)
        return existing

    async def delete_settings(self, db: AsyncSession, user_id: str) -> None:
        existing = await self.get_settings(db, user_id)
        if not existing:
            return
        await db.delete(existing)
        await db.commit()

    def serialize(self, ai_settings: UserAISettings | None) -> dict:
        return {
            "has_ai_settings": ai_settings is not None,
            "selected_model": ai_settings.model_name if ai_settings else None,
            "masked_api_key": self.mask_api_key(ai_settings.api_key_last4 if ai_settings else None),
            "api_key_last4": ai_settings.api_key_last4 if ai_settings else None,
            "validated_at": ai_settings.validated_at if ai_settings else None,
            "allowed_models": list(self.allowed_models),
        }
