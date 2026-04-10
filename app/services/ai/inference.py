import asyncio
import json
import time
from logging import getLogger
from typing import Type
from pydantic import BaseModel, ValidationError
from google import genai
from google.genai import types
from app.services.ai.retry import retry_decor

PRIMARY_TIMEOUT_SECONDS = 60

logger = getLogger(__name__)


async def _log_request(
    model_name: str,
    user_id: str | None,
    purpose: str | None,
    reference_id: str | None,
    input_tokens: int,
    output_tokens: int,
    total_tokens: int,
    cached_tokens: int,
    response_time_ms: int,
    success: bool,
    error_message: str | None,
) -> None:
    """Persist an LLMRequest row using an independent DB session.

    Wrapped in try/except so a DB failure never breaks the main flow.
    """
    if not purpose:
        return
    try:
        from app.database.session import async_session_factory
        from app.models.token_usage import LLMRequest

        async with async_session_factory() as db:
            row = LLMRequest(
                user_id=user_id,
                purpose=purpose,
                reference_id=reference_id,
                model_name=model_name,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                cached_tokens=cached_tokens,
                response_time_ms=response_time_ms,
                success=success,
                error_message=error_message,
            )
            db.add(row)
            await db.commit()
    except Exception:
        logger.debug("Failed to persist LLMRequest row", exc_info=True)


class GeminiInference:
    def __init__(self, *, api_key: str, model_name: str):
        self.model = model_name
        self.client = genai.Client(api_key=api_key)

    def parse_output(
        self,
        raw_content: str,
        structured_output_schema: Type[BaseModel] | None,
        is_list: bool = False,
    ) -> dict | list[dict] | str:
        json_str = raw_content.strip()
        if json_str.startswith("```json"):
            json_str = json_str[7:]
        elif json_str.startswith("```"):
            json_str = json_str[3:]
        if json_str.endswith("```"):
            json_str = json_str[:-3]
        json_str = json_str.strip()

        if not structured_output_schema:
            return json_str

        parsed_content = json.loads(json_str)
        if is_list:
            if isinstance(parsed_content, dict):
                parsed_content = [parsed_content]
            return [
                structured_output_schema.model_validate(o).model_dump()
                for o in parsed_content
            ]
        return structured_output_schema.model_validate(parsed_content).model_dump()

    async def _call_api(
        self,
        model: str,
        config_params: dict,
        inputs: list | None,
        *,
        timeout: int | None = None,
        user_id: str | None = None,
        purpose: str | None = None,
        reference_id: str | None = None,
    ):
        """Single Gemini API call with optional timeout. Returns the raw response."""
        t0 = time.monotonic()
        try:
            coro = self.client.aio.models.generate_content(
                model=model,
                config=types.GenerateContentConfig(**config_params),
                contents=inputs,
            )
            if timeout:
                response = await asyncio.wait_for(coro, timeout=timeout)
            else:
                response = await coro
        except asyncio.TimeoutError:
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            logger.warning(
                f"TIMEOUT after {elapsed_ms}ms (limit={timeout}s): "
                f"model={model}, purpose={purpose}"
            )
            await _log_request(
                model_name=model, user_id=user_id, purpose=purpose,
                reference_id=reference_id, input_tokens=0, output_tokens=0,
                total_tokens=0, cached_tokens=0, response_time_ms=elapsed_ms,
                success=False, error_message=f"Timeout after {timeout}s",
            )
            raise
        except Exception as exc:
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            await _log_request(
                model_name=model, user_id=user_id, purpose=purpose,
                reference_id=reference_id, input_tokens=0, output_tokens=0,
                total_tokens=0, cached_tokens=0, response_time_ms=elapsed_ms,
                success=False, error_message=str(exc)[:500],
            )
            raise

        elapsed_ms = int((time.monotonic() - t0) * 1000)
        usage = getattr(response, "usage_metadata", None)
        input_tokens = getattr(usage, "prompt_token_count", 0) if usage else 0
        output_tokens = getattr(usage, "candidates_token_count", 0) if usage else 0
        total_tokens = getattr(usage, "total_token_count", 0) if usage else 0
        cached_tokens = getattr(usage, "cached_content_token_count", 0) if usage else 0

        log_fn = logger.warning if elapsed_ms > 60000 else logger.info
        log_fn(
            f"Inference complete: model={model}, "
            f"tokens={input_tokens}/{output_tokens}/{total_tokens}, "
            f"time={elapsed_ms}ms, purpose={purpose}"
            f"{' (SLOW >60s)' if elapsed_ms > 60000 else ''}"
        )

        await _log_request(
            model_name=model, user_id=user_id, purpose=purpose,
            reference_id=reference_id, input_tokens=input_tokens,
            output_tokens=output_tokens, total_tokens=total_tokens,
            cached_tokens=cached_tokens, response_time_ms=elapsed_ms,
            success=True, error_message=None,
        )

        return response

    @retry_decor(retries=3, backoff_base=1.0)
    async def _call_api_with_retry(
        self,
        model: str,
        config_params: dict,
        inputs: list | None,
        *,
        user_id: str | None = None,
        purpose: str | None = None,
        reference_id: str | None = None,
    ):
        """Gemini API call with retry (no timeout — used for fallback model)."""
        return await self._call_api(
            model, config_params, inputs,
            user_id=user_id, purpose=purpose, reference_id=reference_id,
        )

    async def run_inference(
        self,
        system_prompt: str,
        inputs: list | None = None,
        structured_output_schema: Type[BaseModel] | None = None,
        is_structured_output_list: bool = False,
        temperature: float = 0.1,
        *,
        user_id: str | None = None,
        purpose: str | None = None,
        reference_id: str | None = None,
        thinking_level: str = "LOW",
        primary_timeout: int | None = PRIMARY_TIMEOUT_SECONDS,
    ) -> str | dict | list:
        config_params: dict = {
            "system_instruction": system_prompt,
            "temperature": temperature,
        }

        # Constrain thinking to reduce Gemini 3 preview latency spikes
        if thinking_level:
            config_params["thinking_config"] = types.ThinkingConfig(
                thinking_level=thinking_level,
            )

        if structured_output_schema:
            config_params["response_mime_type"] = "application/json"
            if isinstance(structured_output_schema, type) and issubclass(
                structured_output_schema, BaseModel
            ):
                config_params["response_schema"] = structured_output_schema

        call_kwargs = dict(user_id=user_id, purpose=purpose, reference_id=reference_id)

        async def _get_response():
            try:
                return await self._call_api(
                    self.model, config_params, inputs,
                    timeout=primary_timeout, **call_kwargs,
                )
            except Exception:
                return await self._call_api_with_retry(
                    self.model, config_params, inputs, **call_kwargs,
                )

        # Retry on schema validation failures — the AI returned valid JSON but it
        # doesn't conform to the Pydantic schema. Re-calling gives the model a
        # fresh chance to produce valid output.
        max_validation_retries = 2
        for attempt in range(1 + max_validation_retries):
            response = await _get_response()
            response_str: str = response.text.strip()

            if not structured_output_schema:
                return response_str

            try:
                return self.parse_output(
                    response_str, structured_output_schema, is_structured_output_list
                )
            except (json.JSONDecodeError, ValidationError) as e:
                if attempt >= max_validation_retries:
                    logger.error(
                        f"Schema validation failed after {attempt + 1} attempts: {e}"
                    )
                    raise
                logger.warning(
                    f"Schema validation failed (attempt {attempt + 1}), retrying: {e}"
                )
