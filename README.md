# ATS Beater

Open-source AI-powered resume tailoring service. Upload your PDF resume, paste a job description, and get an ATS-optimized tailored resume compiled to PDF.

Built with FastAPI, Vue 3, Google Gemini, and LaTeX.

**Live at [resume.squiwo.com](http://resume.squiwo.com/)**

## How It Works

```mermaid
flowchart LR
    A[Upload PDF] --> B[pdfplumber\nextract text]
    B --> C[Gemini Flash\nstructure profile]
    C --> D[(ResumeInfo\nstored in DB)]
    E[Job Description] --> F[Gemini Pro\ntailor resume]
    D --> F
    F --> G[CustomResumeInfo\nreview & edit]
    G --> H[LaTeX builder\n+ pdflatex]
    H --> I[PDF]
```

**Phase 1 — AI Generation:** Your structured profile + the job description go to Gemini Pro, which produces a tailored, keyword-optimized resume. You can review and edit before proceeding.

**Phase 2 — PDF Compilation:** The tailored resume is converted to LaTeX using a custom document class (`resume.cls`), then compiled to PDF via `pdflatex`.

### Job Status Flow

```mermaid
stateDiagram-v2
    [*] --> PENDING
    PENDING --> GENERATING_RESUME
    GENERATING_RESUME --> RESUME_GENERATED
    RESUME_GENERATED --> GENERATING_PDF
    GENERATING_PDF --> READY
    READY --> [*]
    GENERATING_RESUME --> FAILED
    GENERATING_PDF --> FAILED
```

## Features

- **Resume Roast** — Free AI-powered resume analysis with ATS readiness checklist
- **AI Resume Tailoring** — Gemini Pro tailors your resume for each specific job description
- **LaTeX PDF Generation** — Professional typesetting that passes ATS parsing reliably
- **AI Chat Editor** — Refine your resume through conversation (powered by Google ADK)
- **Bring Your Own Key (BYOK)** — Users supply their own Gemini API key in Settings; the app is free
- **Multi-tenancy** — Organization labeling with auto-assignment via email domain rules
- **Admin Panel** — Manage users, tenants, domain rules, LLM request log, and share analytics
- **Shareable Roast Links** — Share your resume roast results with a public link

## Tech Stack

| Layer | Tech |
|-------|------|
| Backend | FastAPI, SQLAlchemy (async), PostgreSQL, Alembic |
| AI | Google `google-genai` SDK, Google ADK (chat agents) |
| PDF | pdflatex + custom `resume.cls`, pdfplumber for extraction |
| Frontend | Vue 3 + Tailwind CSS + Pinia — all via CDN, no build step |
| Auth | Google OAuth 2.0 → JWT |
| Storage | Google Cloud Storage |
| Package mgr | [UV](https://docs.astral.sh/uv/) |

## Quick Start

### Prerequisites

- **Python 3.12+**
- **Docker** (for PostgreSQL)
- **TeX Live** with `pdflatex`
  - macOS: `brew install --cask mactex`
  - Ubuntu: `apt install texlive-latex-base texlive-latex-recommended texlive-latex-extra texlive-fonts-recommended texlive-fonts-extra lmodern`
- **UV** package manager: `curl -LsSf https://astral.sh/uv/install.sh | sh`

### Setup

```bash
# Clone
git clone https://github.com/yashptel/ats-beater.git && cd ats-beater  # Or your own fork

# Copy environment file and fill in your keys
cp .env.example .env

# Start PostgreSQL
docker compose up -d

# Install dependencies
uv sync --extra dev

# Run database migrations
uv run alembic upgrade head

# Start the server
uv run python -m app.main
```

Open **http://localhost:8000**. Set `DEV_AUTH_BYPASS=true` in `.env` to skip Google OAuth during development.

### Required API Keys

| Key | Where to get it |
|-----|----------------|
| `GEMINI_API_KEY` | [Google AI Studio](https://aistudio.google.com/apikey) — optional, only used by integration smoke tests |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | [Google Cloud Console](https://console.cloud.google.com/apis/credentials) — create OAuth 2.0 credentials |

## Running Tests

```bash
# Unit tests (in-memory SQLite, no external dependencies)
uv run pytest tests/ -v --ignore=tests/integration

# Integration smoke tests (needs running DB + Gemini API key + pdflatex)
INTEGRATION=1 uv run pytest tests/integration/ -v
```

Unit tests cover models, schemas, API routes, LaTeX builder/sanitizer, JWT handler, AI settings service, and more.

## Project Structure

```
app/
  main.py                  # FastAPI factory, CORS, exception handlers
  config.py                # Pydantic BaseSettings from .env
  dependencies.py          # Auth (JWT/dev bypass), DB session
  models/                  # SQLAlchemy ORM (User, Profile, Job, Roast, Tenant, ChatMessage, etc.)
  schemas/                 # Pydantic schemas (ResumeInfo, CustomResumeInfo, etc.)
  services/
    ai/                    # Gemini inference + prompts + retry + per-user BYOK settings
    ocr/                   # PDF text extraction (pdfplumber + Gemini vision fallback)
    latex/                 # LaTeX builder, compiler, sanitizer
    chat/                  # AI chat agents (Google ADK) for resume editing
    profile/               # Profile CRUD + background processing
    job/                   # Job generation (Phase 1 + Phase 2)
    roast/                 # Free resume roast / critique flow
    storage/               # GCS upload/download
  api/                     # FastAPI route handlers

frontend/
  index.html               # SPA shell (CDN imports, CSS)
  landing.html             # Public landing page
  static/js/app.js         # Entire Vue 3 app (stores, pages, router)

tests/                     # Unit tests + integration smoke tests
alembic/                   # Database migrations
resume.cls                 # LaTeX document class
infra/                     # Docker, Cloud Run deploy script, entrypoint
```

## API Endpoints

### Auth
| Method | Path | Description |
|--------|------|-------------|
| GET | `/auth/google/login` | Returns Google OAuth URL |
| GET | `/auth/google/callback` | Exchanges auth code, redirects with JWT |
| GET | `/auth/me` | Current user info |
| GET / PUT / DELETE | `/auth/ai-settings` | Manage the user's saved Gemini API key + model |

### Profiles
| Method | Path | Description |
|--------|------|-------------|
| POST | `/profiles/upload` | Upload PDF resume (202, background processing) |
| GET | `/profiles/` | List profiles (paginated) |
| GET | `/profiles/{id}` | Get profile with resume_info |
| PUT | `/profiles/{id}` | Update resume_info |
| DELETE | `/profiles/{id}` | Soft delete |

### Jobs
| Method | Path | Description |
|--------|------|-------------|
| POST | `/jobs/` | Create job (profile_id + job description) |
| POST | `/jobs/{id}/generate-resume` | Trigger AI tailoring (202; requires saved AI settings) |
| POST | `/jobs/{id}/generate-pdf` | Trigger LaTeX compilation (202) |
| GET | `/jobs/{id}/pdf` | Download generated PDF |
| GET | `/jobs/{id}` | Get job details |
| POST | `/jobs/{id}/chat` | Chat with AI to edit resume (SSE stream) |

### Roasts
| Method | Path | Description |
|--------|------|-------------|
| POST | `/roasts/upload` | Upload PDF for AI roast (free, 202) |
| GET | `/roasts/` | List roasts (paginated) |
| GET | `/roasts/shared/{share_id}` | Public shared roast (no auth) |

### Admin
CRUD for tenants, users, and domain rules under `/admin/*`, plus the LLM request log and roast share analytics. Requires `is_super_admin` flag.

## Admin & Roles

### Setting up a super admin

The first user to sign up won't have admin access. Set it directly in the database:

```sql
UPDATE users SET is_super_admin = true WHERE email = 'your-email@example.com';
```

Once set, the **Admin** tab appears in the sidebar. Super admins can:
- View dashboard KPIs (users, jobs, LLM usage)
- Manage users (search, assign tenants)
- Manage tenants and domain rules
- Inspect the LLM request log and roast share analytics

### Multi-Tenancy & Domain Rules

Tenants are organizations (companies, universities) used for labeling — **not data isolation**. All data remains scoped by user.

**How it works:**
1. Create a tenant in the Admin panel (e.g. "MIT", "Google")
2. Add a domain rule mapping an email domain to that tenant (e.g. `mit.edu` → "MIT")
3. When a user signs up via Google OAuth with `@mit.edu`, they're auto-assigned to the "MIT" tenant

**Manual assignment:** Admins can also manually assign any user to a tenant from the Users tab.

**What tenants give you:**
- Organizational labeling in the admin panel
- Tenant name shown on user profiles
- Ability to filter/search users by organization
- Domain-based auto-assignment on signup

```sql
-- Example: Create a tenant and domain rule
INSERT INTO tenants (id, name) VALUES (gen_random_uuid(), 'MIT');
INSERT INTO tenant_domain_rules (tenant_id, domain)
  VALUES ('<tenant-id-from-above>', 'mit.edu');
```

Or do it via the Admin UI → Settings tab → Tenants & Domain Rules.

## Bring Your Own Key (BYOK)

The app is free. Every Gemini call is made against the API key the signed-in user saved in Settings; there is no server-wide fallback at request time.

- Users obtain a key from [Google AI Studio](https://aistudio.google.com/apikey) and paste it into Settings.
- The key is encrypted at rest with a Fernet key (`USER_API_KEY_ENCRYPTION_KEY`).
- Before saving, the backend validates the key + model with a live Gemini call.
- Until a key is saved, AI features (tailoring, roast, chat, profile parsing) return a 400 `ai_setup_required` error and the frontend prompts the user to add one.
- The `GEMINI_FLASH_MODEL` / `GEMINI_PRO_MODEL` / `GEMINI_API_KEY` env vars are only used by `infra/preflight.py` and integration smoke tests — they are not in the request path.

## AI Chat Agents

Both the profile and job pages have AI chat panels powered by [Google ADK](https://google.github.io/adk-docs/) (Agent Development Kit).

### Profile Chat (`profile_editor` agent)
- Reads and edits the user's master profile data (`ResumeInfo`)
- Tools: `get_profile`, `edit_profile` (JSON Patch operations)
- Knows the full product flow — correctly directs users to the Jobs section for PDF downloads
- Will not fabricate UI elements that don't exist

### Job Chat (`resume_editor` agent)
- Reads and edits the tailored resume (`CustomResumeInfo`)
- Tools: `get_resume`, `edit_resume` (JSON Patch operations)
- After edits, auto-recompiles the PDF in the background
- Knows about the fixed LaTeX template — will explain section ordering when asked
- Refuses to generate fake metrics or fabricate experience

### Chat persistence
Chat history is stored via ADK's `DatabaseSessionService` in PostgreSQL (`sessions` and `events` tables). Sessions are keyed by `profile_chat_{id}` or `job_chat_{id}`.

## Resume Roast

Free AI-powered resume critique. Users upload a PDF and get:
1. **Comedic roast** — AI-generated roast points about the resume
2. **ATS readiness checklist** — 8 criteria (machine readability, contact info, skills, dates, etc.)
3. **Shareable link** — public URL with OG meta tags for social sharing

Roasts use content-based deduplication (SHA-256 hash). Re-uploading the same PDF returns the cached result.

### Share link analytics
Every view of a shared roast link is tracked (`roast_views` table) with:
- IP address, user agent, referer
- Parsed platform (WhatsApp, etc.), OS, browser

## Deployment

### Docker

```bash
docker build -t ats-beater .
docker run -p 8080:8080 --env-file .env ats-beater
```

### Cloud Run

```bash
export GCP_PROJECT_ID=your-project
bash infra/deploy-cloudrun.sh
```

The deploy script handles Artifact Registry, Docker build, push, and Cloud Run deployment. See `infra/deploy-cloudrun.sh` for details.

### Dokploy

Use `docker-compose-deploy.yml` with **Docker Compose** mode, not **Stack** mode. Dokploy Stack uses
`docker stack deploy`, which ignores `build:` and requires prebuilt images from a registry.

Recommended Dokploy setup:

1. Set the compose type to `docker-compose`
2. Set the compose path to `./docker-compose-deploy.yml`
3. Add your runtime secrets in Dokploy's Environment tab
4. Set `DATABASE_URL` to use the internal Postgres hostname:
   `postgresql+asyncpg://postgres:postgres@postgres:5432/custom_resume_dev`
5. Configure the public domain in Dokploy's **Domains** tab and target container port `8080`

The Dokploy compose file intentionally keeps Postgres in the same deployment, waits for the database
healthcheck before starting the app, and relies on Dokploy Domains UI for routing instead of manual
Traefik labels in the repo.

### Environment

All configuration is via environment variables. See `.env.example` for the full list.

For production, you'll need:
- PostgreSQL instance (Cloud SQL or self-hosted)
- GCS bucket for PDF storage
- Google OAuth credentials with correct redirect URI

## Environment Variables Reference

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | Yes | — | PostgreSQL async connection string (`postgresql+asyncpg://...`) |
| `GEMINI_API_KEY` | No | — | Optional Google AI API key; only used by `infra/preflight.py` and integration smoke tests (runtime uses per-user keys) |
| `GEMINI_FLASH_MODEL` | No | `gemini-3-flash-preview` | Default model name for smoke tests |
| `GEMINI_PRO_MODEL` | No | `gemini-3.1-pro-preview` | Default model name for smoke tests |
| `USER_API_KEY_ENCRYPTION_KEY` | Yes | — | Fernet key used to encrypt users' saved Gemini API keys at rest |
| `GOOGLE_CLIENT_ID` | Prod | — | Google OAuth 2.0 client ID |
| `GOOGLE_CLIENT_SECRET` | Prod | — | Google OAuth 2.0 client secret |
| `JWT_SECRET` | Yes | `change-this-secret` | Secret for signing JWTs (min 32 chars in production) |
| `JWT_ALGORITHM` | No | `HS256` | JWT signing algorithm |
| `JWT_EXPIRY_HOURS` | No | `24` | JWT token expiry in hours |
| `GCS_BUCKET` | No | — | GCS bucket name for PDF storage (skip for local-only) |
| `GCS_CREDENTIALS_PATH` | No | — | Path to GCS service account JSON (uses ADC if omitted) |
| `LATEX_BIN_PATH` | No | `/Library/TeX/texbin` | Directory containing `pdflatex` binary |
| `ENVIRONMENT` | No | `DEV` | `DEV` or `PROD` — affects error verbosity |
| `FRONTEND_URL` | No | `http://localhost:8000` | Used for CORS origins and OAuth redirect |
| `DEV_AUTH_BYPASS` | No | `false` | Set `true` to skip OAuth in development (auto-creates a test user) |
| `RUN_MIGRATIONS` | No | `false` | Set `true` to run Alembic migrations on container startup |

## Pre-flight Check

Verify all external services before deploying:

```bash
uv run python infra/preflight.py
```

Checks PostgreSQL connectivity + schema, Gemini Flash & Pro models, LaTeX compiler, and GCS bucket. Exits with code 0 if all pass, 1 if any fail.

## Troubleshooting

### "LaTeX compilation timed out"
- pdflatex has a 90-second timeout per pass. Image-heavy PDFs or CPU-constrained containers can hit this.
- Fix: increase CPU allocation (2 vCPU recommended) or increase `PDFLATEX_TIMEOUT` in `app/services/latex/compiler.py`.

### "No /Root object! - Is this really a PDF?"
- The uploaded file isn't a valid PDF (might be a .docx or image renamed to .pdf).
- The frontend enforces a 5MB limit and PDF MIME type check.

### "Memory limit exceeded"
- Large/image-heavy PDFs can cause pdfplumber to consume excessive memory during text extraction.
- Fix: increase container memory (2Gi recommended) or reduce the upload size limit.

### LaTeX special characters breaking compilation
- The sanitizer (`app/services/latex/sanitizer.py`) escapes `& % $ # _ { } ~ ^` and common Unicode.
- URLs are handled specially — only `%` is escaped (to `\%`) to prevent LaTeX comment breakage.
- If you encounter a new character that breaks compilation, add it to `_UNICODE_MAP` or `handle_special_chars`.

### Chat returns "A chat request is already in progress"
- Concurrency is managed via in-memory task tracking (`_active_tasks` dict).
- This can happen if a previous request crashed without cleanup. Refreshing the page clears it.

### OAuth redirect mismatch
- Ensure `FRONTEND_URL` matches your domain exactly (including `https://`).
- Add `{FRONTEND_URL}/auth/google/callback` to your Google OAuth authorized redirect URIs.

## Key Design Decisions

- **Two-phase generation** — AI tailoring and PDF compilation are separate. Users can review/edit the AI output before committing to PDF.
- **Background processing** — Profile OCR and job generation run as tracked async tasks with independent DB sessions.
- **Dual extraction** — pdfplumber first (instant), Gemini vision OCR fallback for scanned PDFs.
- **LaTeX over HTML-to-PDF** — Professional typesetting that passes ATS parsing. Custom `resume.cls` handles formatting.
- **No build step frontend** — Vue 3 CDN global build. Just static files served by FastAPI. No Node.js needed.
- **AI chat agents** — Google ADK powers the resume editing chat with tool-calling (read/edit via JSON Patch).

## Contributing

Contributions are welcome! Please open an issue first to discuss what you'd like to change.

## License

MIT License. See [LICENSE](LICENSE).

---

Built by [Yash Patel](https://linkedin.com/in/yashptel)
