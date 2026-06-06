from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.exceptions import InvalidAISettingsError
from app.services.ai.user_settings import AISettingsService, validate_base_url


def _ok_completion():
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="OK"))])


def _patch_openai_client(monkeypatch, service, create):
    fake_client = MagicMock()
    fake_client.chat.completions.create = create
    monkeypatch.setattr(service, "_openai_client", lambda api_key, base_url: fake_client)
    return fake_client


@pytest.mark.asyncio
async def test_validate_openai_success(monkeypatch):
    service = AISettingsService()
    create = AsyncMock(return_value=_ok_completion())
    _patch_openai_client(monkeypatch, service, create)

    await service.validate_configuration(
        provider="openai_compatible",
        api_key="k",
        model_name="qwen-max",
        base_url="https://api.example.com/v1",
        allow_local=True,
    )
    create.assert_awaited_once()


@pytest.mark.asyncio
async def test_validate_openai_failure_raises_invalid(monkeypatch):
    service = AISettingsService()
    create = AsyncMock(side_effect=Exception("401 unauthorized"))
    _patch_openai_client(monkeypatch, service, create)

    with pytest.raises(InvalidAISettingsError):
        await service.validate_configuration(
            provider="openai_compatible",
            api_key="bad",
            model_name="qwen-max",
            base_url="https://api.example.com/v1",
            allow_local=True,
        )


@pytest.mark.asyncio
async def test_validate_openai_omits_reasoning_effort_by_default(monkeypatch):
    service = AISettingsService()
    captured = {}

    async def fake_create(**kwargs):
        captured.update(kwargs)
        return _ok_completion()

    _patch_openai_client(monkeypatch, service, fake_create)

    await service.validate_configuration(
        provider="openai_compatible",
        api_key="k",
        model_name="qwen-max",
        base_url="https://api.example.com/v1",
        reasoning_effort=None,
        allow_local=True,
    )
    assert not captured.get("extra_body")


@pytest.mark.asyncio
async def test_validate_openai_includes_reasoning_effort_when_set(monkeypatch):
    service = AISettingsService()
    captured = {}

    async def fake_create(**kwargs):
        captured.update(kwargs)
        return _ok_completion()

    _patch_openai_client(monkeypatch, service, fake_create)

    await service.validate_configuration(
        provider="openai_compatible",
        api_key="k",
        model_name="qwen-max",
        base_url="https://api.example.com/v1",
        reasoning_effort="high",
        allow_local=True,
    )
    assert captured.get("extra_body") == {"reasoning_effort": "high"}


@pytest.mark.asyncio
async def test_upsert_openai_compatible_persists_config(db_session, test_user, monkeypatch):
    service = AISettingsService()
    monkeypatch.setattr(service, "validate_configuration", AsyncMock(return_value=None))

    saved = await service.upsert_settings(
        db_session,
        test_user.id,
        provider="openai_compatible",
        api_key="sk-proxy-1234",
        model_name="qwen2.5-72b-instruct",
        base_url="https://proxy.example.com/v1",
        reasoning_effort="medium",
    )
    assert saved.provider == "openai_compatible"
    assert saved.base_url == "https://proxy.example.com/v1"
    assert saved.model_name == "qwen2.5-72b-instruct"
    assert saved.reasoning_effort == "medium"
    assert saved.api_key_last4 == "1234"

    resolved = await service.resolve_for_user(db_session, test_user.id)
    assert resolved.provider == "openai_compatible"
    assert resolved.base_url == "https://proxy.example.com/v1"
    assert resolved.reasoning_effort == "medium"
    assert resolved.api_key == "sk-proxy-1234"
    # OpenAI-compatible models are not constrained to the Gemini allow-list.
    assert resolved.model_name == "qwen2.5-72b-instruct"


@pytest.mark.asyncio
async def test_switching_provider_clears_stale_fields(db_session, test_user, monkeypatch):
    service = AISettingsService()
    monkeypatch.setattr(service, "validate_configuration", AsyncMock(return_value=None))

    await service.upsert_settings(
        db_session, test_user.id,
        provider="openai_compatible", api_key="sk-1234",
        model_name="qwen", base_url="https://proxy.example.com/v1",
        reasoning_effort="high",
    )
    saved = await service.upsert_settings(
        db_session, test_user.id,
        provider="gemini", api_key="gemini-key-5678",
        model_name="gemini-3-flash-preview",
    )
    assert saved.provider == "gemini"
    assert saved.base_url is None
    assert saved.reasoning_effort is None
    assert saved.api_key_last4 == "5678"


@pytest.mark.asyncio
async def test_openai_requires_base_url(db_session, test_user, monkeypatch):
    service = AISettingsService()
    monkeypatch.setattr(service, "validate_configuration", AsyncMock(return_value=None))
    with pytest.raises(InvalidAISettingsError):
        await service.upsert_settings(
            db_session, test_user.id,
            provider="openai_compatible", api_key="sk-1234", model_name="qwen",
        )


@pytest.mark.asyncio
async def test_reasoning_effort_omitted_persists_as_none(db_session, test_user, monkeypatch):
    service = AISettingsService()
    monkeypatch.setattr(service, "validate_configuration", AsyncMock(return_value=None))
    saved = await service.upsert_settings(
        db_session, test_user.id,
        provider="openai_compatible", api_key="sk-1234",
        model_name="qwen", base_url="https://proxy.example.com/v1",
        reasoning_effort=None,
    )
    assert saved.reasoning_effort is None


@pytest.mark.asyncio
async def test_validate_openai_rejects_unsafe_url_before_calling(monkeypatch):
    service = AISettingsService()
    create = AsyncMock(return_value=_ok_completion())
    _patch_openai_client(monkeypatch, service, create)

    with pytest.raises(InvalidAISettingsError):
        await service.validate_configuration(
            provider="openai_compatible",
            api_key="k",
            model_name="qwen-max",
            base_url="https://169.254.169.254/v1",
            allow_local=False,
        )
    create.assert_not_awaited()


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/v1",        # non-HTTPS not allowed in prod
        "https://localhost/v1",         # localhost
        "https://127.0.0.1/v1",         # loopback
        "https://10.0.0.5/v1",          # private
        "https://192.168.1.10/v1",      # private
        "https://172.16.4.4/v1",        # private
        "https://169.254.169.254/v1",   # link-local (cloud metadata)
        "https://[::1]/v1",             # IPv6 loopback
        "https://0.0.0.0/v1",           # unspecified
        "https://[::ffff:127.0.0.1]/v1",      # IPv4-mapped loopback
        "https://[::ffff:169.254.169.254]/v1",  # IPv4-mapped cloud metadata
    ],
)
def test_validate_base_url_rejects_unsafe_in_production(url):
    with pytest.raises(InvalidAISettingsError):
        validate_base_url(url, allow_local=False)


def test_validate_base_url_allows_public_https_in_production():
    # Public IP literal — no DNS resolution required.
    validate_base_url("https://8.8.8.8/v1", allow_local=False)


def test_validate_base_url_allows_local_http_in_dev():
    validate_base_url("http://localhost:1234/v1", allow_local=True)
    validate_base_url("http://127.0.0.1:8001/v1", allow_local=True)


def test_validate_base_url_rejects_hostname_resolving_to_private():
    def fake_resolver(host, port):
        return [(None, None, None, None, ("10.0.0.5", 0))]

    with pytest.raises(InvalidAISettingsError):
        validate_base_url("https://evil.example.com/v1", allow_local=False, resolver=fake_resolver)


def test_validate_base_url_allows_hostname_resolving_to_public():
    def fake_resolver(host, port):
        return [(None, None, None, None, ("142.250.72.14", 0))]

    validate_base_url("https://api.example.com/v1", allow_local=False, resolver=fake_resolver)
