import asyncio
import json
import time
from logging import getLogger
from typing import Any, Type
from pydantic import BaseModel, ValidationError
from google import genai
from google.genai import types
from app.services.ai.openai_client import build_openai_compatible_client
from app.services.ai.retry import retry_decor

PRIMARY_TIMEOUT_SECONDS = 60
PROFILE_STRUCTURING_TIMEOUT_SECONDS = 180

logger = getLogger(__name__)
MAX_STRUCTURED_OUTPUT_REPAIR_ATTEMPTS = 2
MAX_REPAIR_JSON_CHARS = 4000


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
    provider: str = "gemini",
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
                provider=provider,
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


def parse_structured_output(
    raw_content: str,
    structured_output_schema: Type[BaseModel] | None,
    is_list: bool = False,
) -> dict | list[dict] | str:
    """Strip markdown fences and parse/validate JSON against a Pydantic schema.

    Provider-agnostic — both the Gemini and OpenAI-compatible inference paths use
    this so Pydantic validation stays the single authority for structured output.
    """
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


def _compact_json_schema(value: Any, *, in_properties: bool = False) -> Any:
    """Remove prose-only JSON schema fields so repair prompts stay focused."""
    if isinstance(value, dict):
        return {
            key: _compact_json_schema(item, in_properties=(key == "properties"))
            for key, item in value.items()
            if in_properties or key not in {"title", "description", "default", "examples"}
        }
    if isinstance(value, list):
        return [_compact_json_schema(item) for item in value]
    return value


def build_structured_output_contract(
    structured_output_schema: Type[BaseModel],
    is_list: bool = False,
) -> str:
    schema_name = structured_output_schema.__name__
    schema = _compact_json_schema(structured_output_schema.model_json_schema())
    root_type = "JSON array" if is_list else "JSON object"
    schema_json = json.dumps(schema, ensure_ascii=True, separators=(",", ":"))
    if is_list:
        schema_json = (
            '{"type":"array","items":'
            f"{schema_json}"
            "}"
        )
    return (
        "STRUCTURED OUTPUT CONTRACT\n"
        f"Return exactly one valid {root_type} matching the {schema_name} JSON schema.\n"
        "Use the exact field names from the schema. Include every required field. "
        "Do not add markdown fences, comments, or prose outside the JSON.\n"
        f"JSON schema: {schema_json}"
    )


def format_structured_output_repair_instruction(
    *,
    raw_content: str,
    error: Exception,
    structured_output_schema: Type[BaseModel],
    is_list: bool = False,
) -> str:
    schema_name = structured_output_schema.__name__
    errors = format_structured_output_error(error)
    invalid_json = raw_content.strip()
    if len(invalid_json) > MAX_REPAIR_JSON_CHARS:
        invalid_json = f"{invalid_json[:MAX_REPAIR_JSON_CHARS]}...[truncated]"
    return (
        "Your previous structured JSON response did not validate.\n"
        f"Schema: {schema_name}\n"
        f"Validation errors: {errors}\n\n"
        f"{build_structured_output_contract(structured_output_schema, is_list)}\n\n"
        "Previous invalid JSON/content:\n"
        f"{invalid_json}\n\n"
        "Return only the corrected JSON. Do not include markdown fences or explanations."
    )


def format_structured_output_error(error: Exception) -> str:
    if not isinstance(error, ValidationError):
        return str(error)

    compact_errors = [
        {
            "path": ".".join(str(part) for part in item.get("loc", ())),
            "message": item.get("msg", ""),
            "type": item.get("type", ""),
        }
        for item in error.errors()
    ]
    return json.dumps(compact_errors, ensure_ascii=True, default=str)


def _log_structured_validation_failure(
    *,
    provider: str,
    model_name: str,
    purpose: str | None,
    structured_output_schema: Type[BaseModel],
    attempt: int,
    error: Exception,
    raw_content: str,
    final: bool = False,
) -> None:
    snippet = raw_content.strip().replace("\n", " ")[:500]
    log_fn = logger.error if final else logger.warning
    log_fn(
        "Schema validation failed%s: provider=%s model=%s purpose=%s schema=%s "
        "attempt=%s error=%s raw_snippet=%r",
        " after retries" if final else "",
        provider,
        model_name,
        purpose,
        structured_output_schema.__name__,
        attempt,
        format_structured_output_error(error)[:500],
        snippet,
    )


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
        return parse_structured_output(raw_content, structured_output_schema, is_list)

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
                provider="gemini",
            )
            raise
        except Exception as exc:
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            await _log_request(
                model_name=model, user_id=user_id, purpose=purpose,
                reference_id=reference_id, input_tokens=0, output_tokens=0,
                total_tokens=0, cached_tokens=0, response_time_ms=elapsed_ms,
                success=False, error_message=str(exc)[:500],
                provider="gemini",
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
            provider="gemini",
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
            contract = build_structured_output_contract(
                structured_output_schema, is_structured_output_list
            )
            config_params["system_instruction"] = f"{system_prompt}\n\n{contract}"

        call_kwargs = dict(user_id=user_id, purpose=purpose, reference_id=reference_id)
        current_inputs = list(inputs or [])

        async def _get_response():
            try:
                return await self._call_api(
                    self.model, config_params, current_inputs,
                    timeout=primary_timeout, **call_kwargs,
                )
            except Exception:
                return await self._call_api_with_retry(
                    self.model, config_params, current_inputs, **call_kwargs,
                )

        for attempt in range(1 + MAX_STRUCTURED_OUTPUT_REPAIR_ATTEMPTS):
            response = await _get_response()
            response_str: str = response.text.strip()

            if not structured_output_schema:
                return response_str

            try:
                return self.parse_output(
                    response_str, structured_output_schema, is_structured_output_list
                )
            except (json.JSONDecodeError, ValidationError) as e:
                if attempt >= MAX_STRUCTURED_OUTPUT_REPAIR_ATTEMPTS:
                    _log_structured_validation_failure(
                        provider="gemini",
                        model_name=self.model,
                        purpose=purpose,
                        structured_output_schema=structured_output_schema,
                        attempt=attempt + 1,
                        error=e,
                        raw_content=response_str,
                        final=True,
                    )
                    raise
                _log_structured_validation_failure(
                    provider="gemini",
                    model_name=self.model,
                    purpose=purpose,
                    structured_output_schema=structured_output_schema,
                    attempt=attempt + 1,
                    error=e,
                    raw_content=response_str,
                )
                current_inputs = [
                    *current_inputs,
                    format_structured_output_repair_instruction(
                        raw_content=response_str,
                        error=e,
                        structured_output_schema=structured_output_schema,
                        is_list=is_structured_output_list,
                    ),
                ]


class OpenAICompatibleInference:
    """Chat Completions inference for OpenAI-compatible endpoints.

    Mirrors GeminiInference.run_inference so feature services stay
    provider-agnostic. Pydantic parse/validate/retry remains the structured
    output authority — response_format is only a best-effort hint.
    """

    def __init__(
        self,
        *,
        api_key: str,
        model_name: str,
        base_url: str,
        reasoning_effort: str | None = None,
        timeout: int | None = PRIMARY_TIMEOUT_SECONDS,
    ):
        self.model = model_name
        self.base_url = base_url
        self.reasoning_effort = reasoning_effort
        self.client = build_openai_compatible_client(
            api_key=api_key,
            base_url=base_url,
            timeout=float(timeout) if timeout else None,
        )

    @staticmethod
    def _to_image_part(item: dict) -> dict | None:
        """Convert a Gemini-style inline image dict to an OpenAI data-URL part."""
        inline = item.get("inline_data") or item.get("inlineData")
        if inline and inline.get("data"):
            mime = inline.get("mime_type") or inline.get("mimeType") or "image/jpeg"
            return {
                "type": "image_url",
                "image_url": {"url": f"data:{mime};base64,{inline['data']}"},
            }
        if item.get("type") == "image_url":  # already an OpenAI-style part
            return item
        return None

    def _build_messages(self, system_prompt: str, inputs: list | None) -> list[dict]:
        messages: list[dict] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        parts: list[dict] = []
        has_image = False
        for item in inputs or []:
            if isinstance(item, str):
                parts.append({"type": "text", "text": item})
            elif isinstance(item, dict):
                image_part = self._to_image_part(item)
                if image_part is not None:
                    parts.append(image_part)
                    has_image = True

        if has_image:
            # Vision endpoints require the multi-part content array.
            messages.append({"role": "user", "content": parts})
        else:
            texts = [p["text"] for p in parts if p.get("type") == "text"]
            messages.append({"role": "user", "content": "\n\n".join(texts)})
        return messages

    def _ensure_json_directive(self, messages: list[dict]) -> list[dict]:
        # json_object mode requires the literal token "json" to appear in the prompt.
        directive = "Respond with a single valid JSON document and no markdown fences."
        has_user_json = False
        for message in messages:
            if message["role"] == "system":
                if "json" not in str(message["content"]).lower():
                    message["content"] = f"{message['content']}\n\n{directive}"
            elif message["role"] == "user":
                content = message["content"]
                if isinstance(content, list):
                    text_parts = [
                        part for part in content
                        if isinstance(part, dict) and part.get("type") == "text"
                    ]
                    has_user_json = any(
                        "json" in str(part.get("text", "")).lower()
                        for part in text_parts
                    )
                    if not has_user_json:
                        content.insert(0, {"type": "text", "text": directive})
                        has_user_json = True
                else:
                    has_user_json = "json" in str(content).lower()
                    if not has_user_json:
                        message["content"] = f"{content}\n\n{directive}" if content else directive
                        has_user_json = True

        if not any(message["role"] == "system" for message in messages):
            messages.insert(0, {"role": "system", "content": directive})
        if not has_user_json:
            messages.append({"role": "user", "content": directive})
        return messages

    def _add_structured_contract(
        self,
        messages: list[dict],
        structured_output_schema: Type[BaseModel],
        is_list: bool,
    ) -> list[dict]:
        contract = build_structured_output_contract(structured_output_schema, is_list)
        insert_at = 0
        while insert_at < len(messages) and messages[insert_at]["role"] == "system":
            insert_at += 1
        return [
            *messages[:insert_at],
            {"role": "system", "content": contract},
            *messages[insert_at:],
        ]

    def _extract_text(self, response) -> str:
        choices = getattr(response, "choices", None) or []
        if not choices:
            return ""
        message = getattr(choices[0], "message", None)
        content = getattr(message, "content", None) if message else None
        return (content or "").strip()

    async def _call_api(
        self,
        messages: list[dict],
        *,
        structured: bool,
        temperature: float,
        timeout: int | None,
        user_id: str | None,
        purpose: str | None,
        reference_id: str | None,
    ):
        t0 = time.monotonic()
        request_kwargs: dict = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        if structured:
            request_kwargs["response_format"] = {"type": "json_object"}
        if timeout:
            request_kwargs["timeout"] = float(timeout)
        if self.reasoning_effort:
            request_kwargs["extra_body"] = {"reasoning_effort": self.reasoning_effort}

        try:
            response = await self.client.chat.completions.create(**request_kwargs)
        except Exception as exc:
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            await _log_request(
                model_name=self.model, user_id=user_id, purpose=purpose,
                reference_id=reference_id, input_tokens=0, output_tokens=0,
                total_tokens=0, cached_tokens=0, response_time_ms=elapsed_ms,
                success=False, error_message=str(exc)[:500],
                provider="openai_compatible",
            )
            raise

        elapsed_ms = int((time.monotonic() - t0) * 1000)
        usage = getattr(response, "usage", None)
        input_tokens = getattr(usage, "prompt_tokens", 0) if usage else 0
        output_tokens = getattr(usage, "completion_tokens", 0) if usage else 0
        total_tokens = getattr(usage, "total_tokens", 0) if usage else 0

        log_fn = logger.warning if elapsed_ms > 60000 else logger.info
        log_fn(
            f"Inference complete: model={self.model}, "
            f"tokens={input_tokens}/{output_tokens}/{total_tokens}, "
            f"time={elapsed_ms}ms, purpose={purpose}"
            f"{' (SLOW >60s)' if elapsed_ms > 60000 else ''}"
        )
        await _log_request(
            model_name=self.model, user_id=user_id, purpose=purpose,
            reference_id=reference_id, input_tokens=input_tokens,
            output_tokens=output_tokens, total_tokens=total_tokens,
            cached_tokens=0, response_time_ms=elapsed_ms,
            success=True, error_message=None,
            provider="openai_compatible",
        )
        return response

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
        messages = self._build_messages(system_prompt, inputs)
        if structured_output_schema:
            messages = self._ensure_json_directive(messages)
            messages = self._add_structured_contract(
                messages, structured_output_schema, is_structured_output_list
            )

        for attempt in range(1 + MAX_STRUCTURED_OUTPUT_REPAIR_ATTEMPTS):
            response = await self._call_api(
                messages,
                structured=bool(structured_output_schema),
                temperature=temperature,
                timeout=primary_timeout,
                user_id=user_id,
                purpose=purpose,
                reference_id=reference_id,
            )
            response_str = self._extract_text(response)

            if not structured_output_schema:
                return response_str

            try:
                return parse_structured_output(
                    response_str, structured_output_schema, is_structured_output_list
                )
            except (json.JSONDecodeError, ValidationError) as e:
                if attempt >= MAX_STRUCTURED_OUTPUT_REPAIR_ATTEMPTS:
                    _log_structured_validation_failure(
                        provider="openai_compatible",
                        model_name=self.model,
                        purpose=purpose,
                        structured_output_schema=structured_output_schema,
                        attempt=attempt + 1,
                        error=e,
                        raw_content=response_str,
                        final=True,
                    )
                    raise
                _log_structured_validation_failure(
                    provider="openai_compatible",
                    model_name=self.model,
                    purpose=purpose,
                    structured_output_schema=structured_output_schema,
                    attempt=attempt + 1,
                    error=e,
                    raw_content=response_str,
                )
                messages = [
                    *messages,
                    {
                        "role": "user",
                        "content": format_structured_output_repair_instruction(
                            raw_content=response_str,
                            error=e,
                            structured_output_schema=structured_output_schema,
                            is_list=is_structured_output_list,
                        ),
                    },
                ]
