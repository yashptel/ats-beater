# Provider Parity QA (Gemini ↔ OpenAI-compatible)

Verification notes for the dual-provider BYOK feature (parent PRD #2, slices
#3–#9). Automated coverage runs without network access; the manual runbook
covers the parts that need live endpoints.

## Coverage matrix

| Capability | Gemini | OpenAI-compatible | Automated coverage |
|---|---|---|---|
| Save / validate settings | ✅ | ✅ | `test_ai_settings_service.py`, `test_openai_settings.py`, `test_auth_routes.py` |
| SSRF guard on base URL (prod blocks private/local, IPv4-mapped IPv6; dev allows local) | n/a | ✅ | `test_openai_settings.py::test_validate_base_url_*` |
| `reasoning_effort` omitted on default / sent when set | n/a | ✅ | `test_openai_settings.py`, `test_provider.py` |
| Model discovery `/models` + manual fallback | n/a | ✅ | `test_openai_settings.py::test_list_openai_models_*`, `test_auth_routes.py::test_discover_models_*` |
| Provider routing (`build_inference`) | ✅ | ✅ | `test_provider.py`, `test_provider_parity.py` |
| Profile Resume structuring (text) | ✅ | ✅ | reroute in `profile/service.py`; `test_provider_parity.py` |
| Profile Resume structuring (OCR vision fallback) | ✅ | ✅ | `test_ocr_extractor.py` |
| Profile enhancement | ✅ | ✅ | reroute in `profile/service.py` |
| Custom Resume tailoring | ✅ | ✅ | reroute in `job/service.py` |
| Roast (images + extracted text) | ✅ | ✅ | `test_roast_service.py` |
| Structured output (Pydantic validate + retry) | ✅ | ✅ | `test_provider.py`, `test_inference.py` |
| Vision image-part construction (data URLs) | ✅ | ✅ | `test_provider.py::test_openai_build_messages_*` |
| Job chat editing (tool calls) | ✅ | ✅ | `test_chat_provider_routing.py`, `test_openai_chat_loop.py` |
| Profile chat editing (tool calls) | ✅ | ✅ | `test_chat_provider_routing.py` |
| Provider in LLM request logging | ✅ | ✅ | `test_logging.py`, `test_llm_request.py` |
| Admin analytics group/filter by provider | ✅ | ✅ | `test_llm_requests_admin.py` |

Run: `uv run pytest tests/ -v --ignore=tests/integration`

## Manual runbook (live endpoints)

Needs a real Gemini key and a real OpenAI-compatible endpoint (e.g. a local
proxy or Qwen's OpenAI-compatible URL). In dev, local HTTP endpoints are allowed.

1. **Gemini regression** — Settings → Provider = Gemini → save key + model.
   Upload a PDF resume → Profile Resume structures. Create a job → generate
   Custom Resume → generate PDF. Run a roast. Open job chat, ask for an edit.
   Confirm everything still works post-abstraction.
2. **OpenAI-compatible, manual model** — Provider = OpenAI-compatible → base URL +
   key → type a model ID (no discovery) → save. Expect a validation call to
   succeed; bad URL/key/model fails clearly.
3. **Model discovery + fallback** — Click DISCOVER with a `/models`-capable
   endpoint → dropdown/datalist populates. Point at an endpoint without `/models`
   → inline error, manual entry still works.
4. **Profile structuring** — Upload a clean PDF (text path) and a scanned/image
   PDF (vision path) on the OpenAI-compatible provider with a vision-capable model.
5. **Custom Resume** — Generate tailored resume on OpenAI-compatible; review/edit
   `CustomResumeInfo`; generate PDF.
6. **Roast** — Run roast on OpenAI-compatible (vision-capable model).
7. **Chat editing** — Job chat and profile chat: request an edit that triggers a
   tool call; confirm the resume/profile updates and the PDF recompiles.
8. **Admin logs** — As super admin, open Overview → the usage table shows a
   Provider column with both Gemini and OpenAI rows; `/admin/llm-requests?provider=…`
   filters correctly.

## Known limitations (v1)

- No provider capability detection — choosing a non-vision/non-tool model fails as
  a normal AI error.
- SSRF is checked at save time and request time, but there is no IP pinning, so a
  DNS-rebinding window between check and HTTP call remains.
- Reasoning effort is passed via `extra_body`; endpoints that ignore or reject it
  behave per their own defaults.
- PDF persistence to GCS is still a pre-existing TODO, unrelated to providers.
