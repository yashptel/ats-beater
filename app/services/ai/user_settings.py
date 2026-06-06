import ipaddress
import socket
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urlparse

from cryptography.fernet import Fernet, MultiFernet
from google import genai
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.exceptions import AISettingsRequiredError, InvalidAISettingsError
from app.models.ai_settings import UserAISettings
from app.services.ai.openai_client import build_openai_compatible_client

PROVIDER_GEMINI = "gemini"
PROVIDER_OPENAI = "openai_compatible"
SUPPORTED_PROVIDERS = (PROVIDER_GEMINI, PROVIDER_OPENAI)

# Hostnames that always resolve to a loopback/local target.
_BLOCKED_HOSTNAMES = {"localhost", "localhost.localdomain", "ip6-localhost"}

# Environments where local/private endpoints are allowed (proxy testing).
_LOCAL_ENV_NAMES = {"DEV", "DEVELOPMENT", "LOCAL", "TEST"}


def local_endpoints_allowed() -> bool:
    """True when local/private OpenAI-compatible endpoints may be used (dev)."""
    env = (get_settings().ENVIRONMENT or "").strip().upper()
    return env in _LOCAL_ENV_NAMES


def _ip_is_blocked(ip: "ipaddress._BaseAddress") -> bool:
    # Unwrap IPv4-mapped IPv6 (e.g. ::ffff:127.0.0.1) so the embedded IPv4 is
    # range-checked — older Python versions don't flag these via is_private.
    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped is not None:
        return _ip_is_blocked(mapped)
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def validate_base_url(url: str, *, allow_local: bool, resolver=socket.getaddrinfo) -> None:
    """SSRF guard for user-supplied OpenAI-compatible base URLs.

    In production (``allow_local=False``) only public HTTPS endpoints are
    permitted: localhost, loopback, private, link-local, and other reserved
    targets are rejected — including hostnames that resolve to those ranges.
    In development (``allow_local=True``) local HTTP endpoints are allowed so
    proxies can be tested.
    """
    if not url or not url.strip():
        raise InvalidAISettingsError("Base URL is required for OpenAI-compatible providers.")

    parsed = urlparse(url.strip())
    scheme = (parsed.scheme or "").lower()
    host = parsed.hostname

    if not host:
        raise InvalidAISettingsError("Enter a valid base URL, e.g. https://host/v1.")

    if allow_local:
        if scheme not in ("http", "https"):
            raise InvalidAISettingsError("Base URL must use http or https.")
        return

    if scheme != "https":
        raise InvalidAISettingsError("Base URL must use HTTPS.")

    if host.lower() in _BLOCKED_HOSTNAMES:
        raise InvalidAISettingsError("Base URL host is not allowed.")

    candidates: list = []
    try:
        candidates.append(ipaddress.ip_address(host))
    except ValueError:
        # Hostname — resolve every address it maps to and check them all.
        try:
            infos = resolver(host, None)
        except Exception as exc:
            raise InvalidAISettingsError("Could not resolve the base URL host.") from exc
        for info in infos:
            ip_str = info[4][0]
            try:
                candidates.append(ipaddress.ip_address(ip_str))
            except ValueError:
                continue

    if not candidates:
        raise InvalidAISettingsError("Could not resolve the base URL host.")

    for ip in candidates:
        if _ip_is_blocked(ip):
            raise InvalidAISettingsError(
                "Base URL host is not allowed (private or local address)."
            )

ALLOWED_GEMINI_MODELS = (
    "gemini-3-flash-preview",
    "gemini-3.1-pro-preview",
    "gemini-3.1-flash-lite-preview",
    "gemini-3.5-flash",
)


@dataclass
class ResolvedAISettings:
    api_key: str
    model_name: str
    provider: str = PROVIDER_GEMINI
    base_url: str | None = None
    reasoning_effort: str | None = None
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
        provider = ai_settings.provider or PROVIDER_GEMINI
        if provider == PROVIDER_GEMINI:
            self.ensure_allowed_model(ai_settings.model_name)
        return ResolvedAISettings(
            api_key=self.decrypt_api_key(ai_settings.encrypted_api_key),
            model_name=ai_settings.model_name,
            provider=provider,
            base_url=ai_settings.base_url,
            reasoning_effort=ai_settings.reasoning_effort,
            validated_at=ai_settings.validated_at,
        )

    def _allow_local_endpoints(self) -> bool:
        return local_endpoints_allowed()

    def _openai_client(self, api_key: str, base_url: str):
        return build_openai_compatible_client(
            api_key=api_key, base_url=base_url, timeout=20.0
        )

    async def validate_configuration(
        self,
        *,
        provider: str = PROVIDER_GEMINI,
        api_key: str,
        model_name: str,
        base_url: str | None = None,
        reasoning_effort: str | None = None,
        allow_local: bool | None = None,
    ) -> None:
        if provider == PROVIDER_GEMINI:
            await self._validate_gemini(api_key, model_name)
        elif provider == PROVIDER_OPENAI:
            if allow_local is None:
                allow_local = self._allow_local_endpoints()
            validate_base_url(base_url or "", allow_local=allow_local)
            await self._validate_openai(
                api_key=api_key,
                base_url=base_url,
                model_name=model_name,
                reasoning_effort=reasoning_effort,
            )
        else:
            raise InvalidAISettingsError("Unsupported AI provider.")

    async def list_openai_models(
        self,
        *,
        api_key: str,
        base_url: str,
        allow_local: bool | None = None,
    ) -> list[str]:
        """Discover model IDs from an OpenAI-compatible endpoint's /models route.

        Convenience only — discovery failures must not block manual model entry,
        and the save-time Chat Completions validation remains authoritative.
        """
        if allow_local is None:
            allow_local = self._allow_local_endpoints()
        validate_base_url(base_url or "", allow_local=allow_local)
        client = self._openai_client(api_key, base_url)
        result = await client.models.list()
        models: list[str] = []
        for item in getattr(result, "data", None) or []:
            model_id = getattr(item, "id", None)
            if model_id:
                models.append(model_id)
        return sorted(set(models))

    async def _validate_gemini(self, api_key: str, model_name: str) -> None:
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

    async def _validate_openai(
        self,
        *,
        api_key: str,
        base_url: str | None,
        model_name: str,
        reasoning_effort: str | None = None,
    ) -> None:
        extra_body = {"reasoning_effort": reasoning_effort} if reasoning_effort else None
        try:
            client = self._openai_client(api_key, base_url)
            response = await client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": "Reply with OK."}],
                extra_body=extra_body,
            )
            if not getattr(response, "choices", None):
                raise InvalidAISettingsError(
                    "OpenAI-compatible validation returned no choices."
                )
        except InvalidAISettingsError:
            raise
        except Exception as exc:
            raise InvalidAISettingsError(
                "Unable to validate the OpenAI-compatible endpoint with the selected model."
            ) from exc

    async def upsert_settings(
        self,
        db: AsyncSession,
        user_id: str,
        *,
        provider: str | None = None,
        api_key: str | None = None,
        model_name: str | None = None,
        base_url: str | None = None,
        reasoning_effort: str | None = None,
    ) -> UserAISettings:
        existing = await self.get_settings(db, user_id)
        current_provider = (existing.provider if existing else None) or PROVIDER_GEMINI
        resolved_provider = provider or current_provider
        if resolved_provider not in SUPPORTED_PROVIDERS:
            raise InvalidAISettingsError("Unsupported AI provider.")

        # A saved API key only carries over while staying on the same provider.
        switching = existing is not None and current_provider != resolved_provider
        has_reusable_key = existing is not None and not switching
        if not has_reusable_key and not api_key:
            raise InvalidAISettingsError("Add an API key before saving these settings.")

        resolved_api_key = api_key or (
            self.decrypt_api_key(existing.encrypted_api_key) if has_reusable_key else ""
        )

        if resolved_provider == PROVIDER_GEMINI:
            resolved_model = (
                model_name
                or (existing.model_name if has_reusable_key else None)
                or self.allowed_models[0]
            )
            resolved_base_url = None
            resolved_reasoning = None
        else:  # PROVIDER_OPENAI — full-config save; stale Gemini fields are dropped.
            resolved_base_url = base_url or (existing.base_url if has_reusable_key else None)
            if not resolved_base_url:
                raise InvalidAISettingsError(
                    "Base URL is required for OpenAI-compatible providers."
                )
            resolved_model = model_name or (existing.model_name if has_reusable_key else None)
            if not resolved_model:
                raise InvalidAISettingsError(
                    "Enter a model ID for the OpenAI-compatible provider."
                )
            resolved_reasoning = reasoning_effort or None

        await self.validate_configuration(
            provider=resolved_provider,
            api_key=resolved_api_key,
            model_name=resolved_model,
            base_url=resolved_base_url,
            reasoning_effort=resolved_reasoning,
        )

        if not existing:
            existing = UserAISettings(user_id=user_id)
            db.add(existing)

        existing.provider = resolved_provider
        if api_key or not has_reusable_key:
            existing.encrypted_api_key = self.encrypt_api_key(resolved_api_key)
            existing.api_key_last4 = resolved_api_key[-4:]
        existing.model_name = resolved_model
        existing.base_url = resolved_base_url
        existing.reasoning_effort = resolved_reasoning
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
            "provider": (ai_settings.provider or PROVIDER_GEMINI) if ai_settings else None,
            "selected_model": ai_settings.model_name if ai_settings else None,
            "base_url": ai_settings.base_url if ai_settings else None,
            "reasoning_effort": ai_settings.reasoning_effort if ai_settings else None,
            "masked_api_key": self.mask_api_key(ai_settings.api_key_last4 if ai_settings else None),
            "api_key_last4": ai_settings.api_key_last4 if ai_settings else None,
            "validated_at": ai_settings.validated_at if ai_settings else None,
            "allowed_models": list(self.allowed_models),
        }
