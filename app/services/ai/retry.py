import asyncio
import functools
import inspect
from logging import getLogger

logger = getLogger(__name__)


def retry_decor(_func=None, *, retries: int = 5, backoff_base: float = 1.0):
    """Retry decorator with exponential backoff. Works for both sync and async functions."""

    def decorator_retry(func):
        is_coroutine = inspect.iscoroutinefunction(func)

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            last_exception = None
            for i in range(retries):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    logger.warning(f"[async] Error: {e}, retry {i + 1}/{retries}")
                    if i < retries - 1:
                        await asyncio.sleep(backoff_base * (2**i))
            raise last_exception

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            import time

            last_exception = None
            for i in range(retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    logger.warning(f"[sync] Error: {e}, retry {i + 1}/{retries}")
                    if i < retries - 1:
                        time.sleep(backoff_base * (2**i))
            raise last_exception

        return async_wrapper if is_coroutine else sync_wrapper

    return decorator_retry if _func is None else decorator_retry(_func)
