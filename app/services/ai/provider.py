"""Provider abstraction: build the right inference client from resolved settings.

Feature services (profile, job, roast, OCR) call ``build_inference`` and use the
uniform ``run_inference`` interface instead of branching on provider.
"""
from app.services.ai.inference import GeminiInference, OpenAICompatibleInference
from app.services.ai.user_settings import (
    PROVIDER_OPENAI,
    ResolvedAISettings,
    local_endpoints_allowed,
    validate_base_url,
)


def build_inference(resolved: ResolvedAISettings):
    """Return the inference client for the user's active provider.

    For OpenAI-compatible, the base URL is re-validated here (request time) so a
    hostname that has since been rebound to a private/local address is rejected
    even though it passed the save-time SSRF check.
    """
    if resolved.provider == PROVIDER_OPENAI:
        validate_base_url(resolved.base_url or "", allow_local=local_endpoints_allowed())
        return OpenAICompatibleInference(
            api_key=resolved.api_key,
            model_name=resolved.model_name,
            base_url=resolved.base_url,
            reasoning_effort=resolved.reasoning_effort,
        )
    return GeminiInference(
        api_key=resolved.api_key,
        model_name=resolved.model_name,
    )
