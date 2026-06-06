# Multi-provider BYOK via a single inference abstraction

ATS Beater supports two BYOK providers: **Gemini** (the compatibility baseline)
and **OpenAI-compatible** (custom proxies, Qwen-style endpoints). One active AI
configuration is stored per user in `UserAISettings` (`provider`, encrypted
`api_key`, `model_name`, optional `base_url`, optional `reasoning_effort`).

Every AI-backed feature resolves credentials through
`AISettingsService.resolve_for_user` → `ResolvedAISettings`, then obtains an
inference client through `build_inference(resolved)` (`app/services/ai/provider.py`).
The client implements one `run_inference(...)` contract
(`GeminiInference` | `OpenAICompatibleInference`), so profile structuring,
enhancement, tailoring, OCR vision fallback, and roast carry no provider
branches. Chat editing dispatches by provider to either the existing Gemini
tool loop or the shared OpenAI Chat Completions tool loop
(`app/services/chat/openai_chat.py`).

## Decisions

- **One inference interface, two implementations.** Feature services depend on
  `run_inference`/the chat loop, never on a provider SDK directly.
- **Chat Completions only (v1).** No Responses API. Tool calls use the
  Chat Completions `tools`/`tool_calls` shape.
- **Pydantic is the structured-output authority.** `response_format=json_object`
  is a best-effort hint; `parse_structured_output` + the validation-retry loop
  decide correctness for both providers.
- **No capability detection.** Users pick models that support vision, tool calls,
  structured output, and reasoning effort. Unsupported choices fail as normal AI
  errors, not pre-checks.
- **Images as data URLs.** Gemini-style inline image dicts are converted to
  `data:image/jpeg;base64,...` content parts for OpenAI-compatible vision.
- **`reasoning_effort` is opt-in.** Sent via request `extra_body` only when set;
  omitted (default) lets endpoints use their own default.
- **SSRF protection on user base URLs.** `validate_base_url` runs at save time and
  again in `build_inference`/the chat path (request time). Production allows only
  public HTTPS; localhost/private/loopback/link-local/reserved and IPv4-mapped
  IPv6 are blocked, including hostnames resolving to them. Development
  (`ENVIRONMENT` in DEV/DEVELOPMENT/LOCAL/TEST) allows local HTTP for proxy testing.
- **Provider in telemetry.** `LLMRequest.provider` is logged on every call; admin
  analytics group by provider+model so overlapping model aliases don't merge.

## Considered Options

- **Provider branches inside each feature service.** Rejected: profile, job,
  roast, OCR, and chat would each grow `if provider == ...`; the abstraction keeps
  the branch in one place.
- **An adapter library (LiteLLM / LangChain / Instructor).** Rejected for v1:
  heavier dependency and less control over the existing Pydantic validate/retry
  contract that guards resume data.
- **Trust provider structured-output enforcement.** Rejected: compatible
  endpoints vary; Pydantic validation must remain authoritative.

## Consequences

- Adding a third provider means a new `*Inference` implementation plus a branch in
  `build_inference` — feature services stay untouched.
- `ResolvedAISettings` is the single seam carrying provider context; new
  per-provider knobs belong there.
- DNS rebinding between the request-time SSRF check and the HTTP call is a known
  residual risk (no IP pinning in v1).
