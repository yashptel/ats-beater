# CLAUDE.md

## What This Is

**ATS Beater** — AI-powered resume tailoring service by Yash Patel. Upload PDF resume → AI structures it → paste a job description → AI tailors a custom resume → LaTeX compiles to PDF.

## Tech Stack

| Layer | Tech |
|-------|------|
| Backend | FastAPI, SQLAlchemy async, PostgreSQL 16 (Docker), Alembic |
| AI | `google-genai` SDK, **gemini-3-flash-preview** (profile/OCR), **gemini-3.1-pro-preview** (resume gen) |
| PDF | pdflatex + `resume.cls`, pdfplumber for text extraction |
| Frontend | Vue 3 + Tailwind + Pinia — all via CDN, no build step, hash router |
| Auth | Google OAuth 2.0 → JWT |
| Payments | Razorpay (credit packs: Day Pass ₹49, Sprint ₹99, Job Hunt ₹199) |
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
uv run pytest tests/ -v --ignore=tests/integration  # 99 unit tests (in-memory SQLite, no external deps)
INTEGRATION=1 uv run pytest tests/integration/ -v   # 9 smoke tests (needs real DB + API key + pdflatex)
```

## Data Flow

```
Upload PDF ──→ pdfplumber extract ──→ Gemini Flash structures ──→ ResumeInfo (JSON in PostgreSQL)
                                                                         │
Job Description ────────────────────────────────────────────────────────→ │
                                                                         ▼
                                                              Gemini Pro tailors
                                                                         │
                                                                         ▼
                                                              CustomResumeInfo
                                                                         │
                                                                         ▼
                                                         LaTeX builder + pdflatex ──→ PDF
```

Phase 1 and Phase 2 are separate API calls. User can review/edit `CustomResumeInfo` between phases.

## Credit System

**Business model**: Daily free quota + purchasable credit packs + unlimited time passes.

### Consumption Priority
1. **Active time pass** → unlimited (no deduction)
2. **Daily free** → 3/day (configurable via `DAILY_FREE_CREDITS`), resets at midnight UTC
3. **Purchased credits** → from balance
4. **No credits** → 429 error, frontend shows paywall modal

### Credit deduction
- Happens **synchronously** in the request handler (before background task starts)
- If background generation fails, a **refund** is issued (except for time pass — unlimited)
- All transactions recorded in `credit_transactions` audit ledger

### Promo codes
- Admin-created, types: `CREDITS` (adds N credits) or `TIME_PASS` (activates tier by ID)
- One redemption per user per code, optional max total redemptions, optional expiry

### Time pass stacking
- If a user buys a second pass while one is active, the new pass **starts at the old expiry**

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
  models/                  # SQLAlchemy ORM (User, Profile, Job, Tenant, Credit*, etc.)
    __init__.py            # MUST import all models (relationship resolution)
    credit.py              # CreditPack, TimePassTier, UserCredit, UserTimePass, CreditTransaction, PromoCode, PromoRedemption
  schemas/
    credit.py              # All credit/payment Pydantic schemas
  database/session.py      # async engine, sessionmaker, get_db() generator
  services/
    ai/inference.py        # GeminiInference — structured output + retry
    ai/prompts.py          # System/user prompt templates
    ai/retry.py            # retry_decor with exponential backoff
    ocr/extractor.py       # PDFExtractor — pdfplumber first, Gemini vision fallback
    latex/builder.py       # CustomResumeInfo → LaTeX string
    latex/compiler.py      # LaTeX string → PDF bytes (60s timeout)
    latex/sanitizer.py     # Escape LaTeX special chars
    profile/service.py     # ProfileService — create, process (background), enhance, CRUD
    job/service.py         # JobService — generate_custom_resume (Phase 1), generate_pdf (Phase 2)
    credit/service.py      # CreditService — balance mgmt, check_and_deduct, promo, refund
    payment/razorpay_client.py  # RazorpayService — order creation, payment/webhook verification
    auth/google_oauth.py   # OAuth URL, code exchange, user info
    auth/jwt_handler.py    # create_access_token, verify_token
  api/
    auth.py                # /auth/google/login, /auth/google/callback, /auth/me
    profiles.py            # /profiles/* CRUD + upload
    jobs.py                # /jobs/* CRUD + generation triggers (credit check on generate)
    credits.py             # /credits/* — packs listing, balance, history, promo redemption
    payments.py            # /payments/* — Razorpay order creation, verification, webhook
    admin.py               # /admin/* — tenants, users, domain rules, credit packs, time passes, promos, transactions, grants
    progress.py            # SSE endpoint

frontend/
  index.html               # SPA shell, CDN imports (incl. Razorpay checkout.js), HELM-inspired CSS
  landing.html             # Public landing page (/landing) — pricing, T&C, privacy, refund policies
  static/js/app.js         # Vue 3 app — stores (auth, profile, job, roast, credit), pages, router

tests/
  conftest.py              # In-memory SQLite, test client, fixtures
  integration/             # Smoke tests (DB, Gemini, LaTeX, GCS) — gated behind INTEGRATION=1
  test_api/                # Route tests (health, profiles, jobs, admin, credits)
  test_models/             # ORM tests (user, profile, job, tenant, credit)
  test_schemas/            # Schema validation tests
  test_latex/              # Builder, sanitizer, compiler
  test_ai/                 # Retry decorator
  test_services/           # JWT, GCS, CreditService

alembic/versions/          # Migrations (run `alembic history` for details)
resume.cls                 # LaTeX document class — copied into temp dir at compile time
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| GET | `/auth/google/login` | Returns OAuth URL |
| GET | `/auth/google/callback` | Exchanges code, redirects with JWT |
| GET | `/auth/me` | Current user info |
| POST | `/profiles/upload` | Upload PDF (202, processes in background) |
| GET | `/profiles/` | List user's profiles |
| GET | `/profiles/{id}` | Get profile with resume_info |
| GET | `/profiles/{id}/status` | Poll processing status |
| PUT | `/profiles/{id}` | Update resume_info |
| POST | `/profiles/{id}/enhance` | AI-enhance profile |
| DELETE | `/profiles/{id}` | Soft delete |
| POST | `/jobs/` | Create job (needs profile_id + job_description) |
| POST | `/jobs/{id}/generate-resume` | Trigger Phase 1 (202, deducts credit) |
| POST | `/jobs/{id}/generate-pdf` | Trigger Phase 2 (202) |
| GET | `/jobs/{id}/status` | Poll job status |
| GET | `/jobs/{id}/custom-resume` | Get generated CustomResumeInfo |
| PUT | `/jobs/{id}/custom-resume` | Edit before PDF generation |
| GET | `/jobs/{id}/pdf` | Download PDF |
| GET | `/jobs/` | List user's jobs |
| GET | `/credits/packs` | List active credit packs + time passes (public) |
| GET | `/credits/me` | Current balance + daily free + active pass |
| GET | `/credits/history` | Paginated transaction history |
| POST | `/credits/redeem-promo` | Redeem a promo code |
| POST | `/payments/create-order` | Create Razorpay order for pack/pass |
| POST | `/payments/verify` | Verify payment signature, credit account |
| POST | `/payments/webhook` | Razorpay webhook (payment.captured safety net) |
| GET | `/landing` | Public landing page (pricing, policies, contact) |
| * | `/admin/*` | Full CRUD: tenants, users, domain-rules, credit-packs, time-pass-tiers, promo-codes, transactions, credits/grant |

## Important Patterns

- `app/models/__init__.py` must import ALL models — SQLAlchemy needs this for relationship resolution
- Background tasks use `async_session_factory` to create independent DB sessions (not the request session)
- LaTeX sanitizer uses a placeholder for backslash to prevent double-escaping of `{}`
- Services call `await db.rollback()` before setting FAILED status in exception handlers
- OAuth callback redirects to `/#/login?access_token=` (hash routing)
- Credit deduction is synchronous (request scope), generation is async (background task)
- All `.env` config documented in `.env.example`
- All admin GET endpoints use pagination envelope: `{items, total, page, pages, limit}`

## Multi-Tenancy

- **Organizational labeling only** — no data isolation. Profiles/Jobs remain scoped by user_id.
- `Tenant` + `TenantDomainRule` models for email domain auto-assignment on OAuth signup
- `User.is_super_admin` gates `/admin/*` via `get_super_admin` dependency
- `User.tenant_id` FK with `ondelete="SET NULL"` — deleting a tenant unassigns users
- Domain rules normalized to lowercase via Pydantic validator
- Frontend admin panel: 7 tabs (Tenants / Users / Domain Rules / Credit Packs / Time Passes / Promo Codes / Transactions), visible only to super admins

## Deployment

See `infra/deploy-cloudrun.sh` for Cloud Run deployment. Configure your own:
- Cloud SQL / PostgreSQL instance
- GCS bucket for PDF storage
- Google OAuth credentials
- Razorpay keys (for payments)

Environment variables are documented in `.env.example`.
## TODOs

- Wire GCS storage into PDF generation (currently PDFs are generated but not persisted)
