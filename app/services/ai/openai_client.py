OPENAI_COMPATIBLE_USER_AGENT = "ATS-Beater/0.1 OpenAI-Compatible"


def build_openai_compatible_client(*, api_key: str, base_url: str, timeout: float):
    """Create an OpenAI SDK client that works with stricter compatible proxies."""
    from openai import AsyncOpenAI

    return AsyncOpenAI(
        api_key=api_key,
        base_url=base_url,
        timeout=timeout,
        max_retries=0,
        default_headers={"User-Agent": OPENAI_COMPATIBLE_USER_AGENT},
    )
