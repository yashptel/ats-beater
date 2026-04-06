import pytest
from app.services.ai.retry import retry_decor


@pytest.mark.asyncio
async def test_retry_async_success():
    call_count = 0

    @retry_decor(retries=3, backoff_base=0.01)
    async def flaky():
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise ValueError("fail")
        return "ok"

    result = await flaky()
    assert result == "ok"
    assert call_count == 2


@pytest.mark.asyncio
async def test_retry_async_exhausted():
    @retry_decor(retries=2, backoff_base=0.01)
    async def always_fails():
        raise ValueError("always fail")

    with pytest.raises(ValueError, match="always fail"):
        await always_fails()


def test_retry_sync_success():
    call_count = 0

    @retry_decor(retries=3, backoff_base=0.01)
    def flaky():
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise ValueError("fail")
        return "ok"

    result = flaky()
    assert result == "ok"
    assert call_count == 2
