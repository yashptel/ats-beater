# AGENTS.md

## What This Is

**ATS Beater** — AI-powered resume tailoring service by [Yash Patel](https://linkedin.com/in/yashptel). Upload PDF resume → AI structures it → paste a job description → AI tailors a custom resume → LaTeX compiles to PDF.

The app is free. Users bring their own API key (BYOK) for one of two providers — **Gemini** or an **OpenAI-compatible** endpoint (custom proxy / Qwen-style); generation runs against the provider the user saves in Settings. There is no paywall, no payment integration, no credit ledger. The multi-provider design is captured in `docs/adr/0002-multi-provider-byok-abstraction.md`.

## Tech Stack

| Layer | Tech |
|-------|------|
| Backend | FastAPI, SQLAlchemy async, PostgreSQL 16 (Docker), Alembic |
| AI | `google-genai` SDK (Gemini) + `openai` SDK (OpenAI-compatible Chat Completions); user-provided key per provider (BYOK). Env defaults for smoke tests only — **gemini-3-flash-preview** / **gemini-3.1-pro-preview** |
| PDF | pdflatex + `resume.cls`, pdfplumber for text extraction |
| Frontend | Vue 3 + Tailwind + Pinia — all via CDN, no build step, hash router |
| Auth | Google OAuth 2.0 → JWT |
| Package mgr | UV, dependencies in `pyproject.toml` |

**Never use older 2.5 preview models — they are deprecated.**

## How To Run

```bash
docker compose up -d                          # PostgreSQL
uv sync --extra dev                           # install deps
uv run alembic upgrade head                   # migrations
uv run python -m app.main                     # server → http://localhost:8000
```

Set `DEV_AUTH_BYPASS=true` in `.env` to skip Google OAuth during development.

## How To Test

```bash
uv run pytest tests/ -v --ignore=tests/integration  # unit tests (in-memory SQLite, no external deps)
INTEGRATION=1 uv run pytest tests/integration/ -v   # smoke tests (needs real DB + API key + pdflatex)
```

## Data Flow

```
Upload PDF ──→ pdfplumber extract ──→ active provider structures ──→ ResumeInfo (JSON in PostgreSQL)
                                                                         │
Job Description ────────────────────────────────────────────────────────→ │
                                                                         ▼
                                                         active provider tailors
                                                                         │
                                                                         ▼
                                                              CustomResumeInfo
                                                                         │
                                                                         ▼
                                                         LaTeX builder + pdflatex ──→ PDF
```

Phase 1 and Phase 2 are separate API calls. User can review/edit `CustomResumeInfo` between phases.

All AI calls go through the per-user `UserAISettings` row (`provider` + encrypted API key + model name, plus `base_url`/`reasoning_effort` for OpenAI-compatible), resolved via `AISettingsService.resolve_for_user`, then dispatched to the right inference client via `build_inference` (`app/services/ai/provider.py`). No request runs without saved settings.

## Job Status Flow

`PENDING` → `GENERATING_RESUME` → `RESUME_GENERATED` → `GENERATING_PDF` → `READY`

Any step can transition to `FAILED`.

## Project Layout

```
app/
  main.py                  # FastAPI factory, CORS, exception handlers, static file mount
  config.py                # Pydantic BaseSettings from .env
  dependencies.py          # get_current_user, get_super_admin, get_db
  exceptions.py            # Custom exception classes (→ HTTP 4xx handlers in main.py)
  models/                  # SQLAlchemy ORM (User, Profile, Job, Tenant, etc.)
    __init__.py            # MUST import all models (relationship resolution)
  database/session.py      # async engine, sessionmaker, get_db() generator
  services/
    ai/inference.py        # GeminiInference + OpenAICompatibleInference — structured output + retry
    ai/provider.py         # build_inference(resolved) — picks the impl for the active provider
    ai/prompts.py          # System/user prompt templates
    ai/retry.py            # retry_decor with exponential backoff
    ai/user_settings.py    # AISettingsService — provider-aware BYOK (encrypt, validate, /models, SSRF guard)
    ocr/extractor.py       # PDFExtractor — pdfplumber first, provider vision fallback
    latex/builder.py       # CustomResumeInfo → LaTeX string
    latex/compiler.py      # LaTeX string → PDF bytes (60s timeout)
    latex/sanitizer.py     # Escape LaTeX special chars
    profile/service.py     # ProfileService — create, process (background), enhance, CRUD
    job/service.py         # JobService — generate_custom_resume (Phase 1), generate_pdf (Phase 2)
    roast/service.py       # RoastService — free resume roast/critique flow
    chat/service.py        # Job chat — interview answers, referral drafts (dispatches by provider)
    chat/profile_chat.py   # Profile-scoped resume coaching chat (dispatches by provider)
    chat/openai_chat.py    # Shared OpenAI-compatible Chat Completions tool-call loop
    auth/google_oauth.py   # OAuth URL, code exchange, user info
    auth/jwt_handler.py    # create_access_token, verify_token
  api/
    auth.py                # /auth/google/login, /auth/google/callback, /auth/me, /auth/ai-settings
    profiles.py            # /profiles/* CRUD + upload
    jobs.py                # /jobs/* CRUD + generation triggers
    admin.py               # /admin/* — tenants, users, domain rules, LLM requests, share analytics
    progress.py            # SSE endpoint
    roasts.py              # /roasts/* — roast upload, status, share
    chat.py                # /chat/* — job-scoped chat
    profile_chat.py        # /profile-chat/* — profile-scoped chat

frontend/
  index.html               # SPA shell, CDN imports, HELM-inspired CSS
  landing.html             # Public landing page (/landing) — features, FAQ, T&C, privacy
  static/js/app.js         # Vue 3 app — stores (auth, profile, job, roast, aiSettings), pages, router

tests/
  conftest.py              # In-memory SQLite, test client, fixtures
  integration/             # Smoke tests (DB, Gemini, LaTeX, GCS) — gated behind INTEGRATION=1
  test_api/                # Route tests (health, profiles, jobs, admin, auth, roasts, chat)
  test_models/             # ORM tests (user, profile, job, tenant)
  test_schemas/            # Schema validation tests
  test_latex/              # Builder, sanitizer, compiler
  test_ai/                 # Retry decorator, inference
  test_services/           # JWT, GCS, AI settings, chat, etc.

alembic/versions/          # Migrations (run `alembic history` for details)
resume.cls                 # LaTeX document class — copied into temp dir at compile time
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| GET | `/auth/google/login` | Returns OAuth URL |
| GET | `/auth/google/callback` | Exchanges code, redirects with JWT |
| GET | `/auth/me` | Current user info (incl. AI-settings status) |
| GET | `/auth/ai-settings` | Get saved provider config status + Gemini allow-list |
| PUT | `/auth/ai-settings` | Upsert provider/key/model (+ base_url/reasoning_effort); validated against the provider before save |
| DELETE | `/auth/ai-settings` | Remove saved provider config |
| POST | `/auth/ai-settings/models` | Discover models from an OpenAI-compatible `/models` endpoint (graceful fallback to manual entry) |
| POST | `/profiles/upload` | Upload PDF (202, processes in background) |
| GET | `/profiles/` | List user's profiles |
| GET | `/profiles/{id}` | Get profile with resume_info |
| GET | `/profiles/{id}/status` | Poll processing status |
| PUT | `/profiles/{id}` | Update resume_info |
| POST | `/profiles/{id}/enhance` | AI-enhance profile |
| DELETE | `/profiles/{id}` | Soft delete |
| POST | `/jobs/` | Create job (needs profile_id + job_description) |
| POST | `/jobs/{id}/generate-resume` | Trigger Phase 1 (202; requires saved AI settings) |
| POST | `/jobs/{id}/generate-pdf` | Trigger Phase 2 (202) |
| GET | `/jobs/{id}/status` | Poll job status |
| GET | `/jobs/{id}/custom-resume` | Get generated CustomResumeInfo |
| PUT | `/jobs/{id}/custom-resume` | Edit before PDF generation |
| GET | `/jobs/{id}/pdf` | Download PDF |
| GET | `/jobs/` | List user's jobs |
| GET | `/landing` | Public landing page (features, FAQ, T&C, privacy) |
| * | `/admin/*` | Tenants, users, domain rules, LLM requests, share analytics — super admin only |

## Important Patterns

- `app/models/__init__.py` must import ALL models — SQLAlchemy needs this for relationship resolution
- Background tasks use `async_session_factory` to create independent DB sessions (not the request session)
- LaTeX sanitizer uses a placeholder for backslash to prevent double-escaping of `{}`
- Services call `await db.rollback()` before setting FAILED status in exception handlers
- OAuth callback redirects to `/#/login?access_token=` (hash routing)
- AI calls always resolve through `AISettingsService.resolve_for_user` — no fallback to env keys at request time
- Feature services stay provider-agnostic: they call `build_inference(resolved)` (or the chat tool loop), never a provider SDK directly. Adding a provider = new `*Inference` impl + a branch in `build_inference`
- Pydantic parse/validate/retry stays the structured-output authority for both providers (`parse_structured_output`); `response_format=json_object` is only a hint
- User-supplied OpenAI-compatible base URLs are SSRF-guarded (`validate_base_url`) at save **and** request time — prod blocks non-HTTPS/localhost/private/loopback/link-local; dev (`ENVIRONMENT` in DEV/DEVELOPMENT/LOCAL/TEST) allows local HTTP
- `LLMRequest.provider` is logged on every call; admin analytics group by provider+model
- All `.env` config documented in `.env.example`
- All admin GET endpoints use pagination envelope: `{items, total, page, pages, limit}`

## Multi-Tenancy

- **Organizational labeling only** — no data isolation. Profiles/Jobs remain scoped by user_id.
- `Tenant` + `TenantDomainRule` models for email domain auto-assignment on OAuth signup
- `User.is_super_admin` gates `/admin/*` via `get_super_admin` dependency
- `User.tenant_id` FK with `ondelete="SET NULL"` — deleting a tenant unassigns users
- Domain rules normalized to lowercase via Pydantic validator
- Frontend admin panel: 3 tabs (Overview / Users / Settings — tenants + domain rules), visible only to super admins

## Deployment

See `infra/deploy-cloudrun.sh` for Cloud Run deployment. Configure your own:
- Cloud SQL / PostgreSQL instance
- GCS bucket for PDF storage
- Google OAuth credentials

End users supply their own provider API key (Gemini or OpenAI-compatible) via the Settings page; no server-side AI key is needed in production. Set `ENVIRONMENT=PROD` (or any non-dev value) in production so the SSRF guard enforces HTTPS-only public endpoints for OpenAI-compatible base URLs.

Environment variables are documented in `.env.example`.

## TODOs

- Wire GCS storage into PDF generation (currently PDFs are generated but not persisted)
