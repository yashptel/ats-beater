import time
from logging import getLogger
from typing import Any, AsyncGenerator

import jsonpatch
from pydantic import ValidationError
from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import DatabaseSessionService
from google.adk.tools import ToolContext
from google.genai import types

from app.config import get_settings
from app.schemas.resume import ResumeInfo
from app.services.ai.inference import _log_request

logger = getLogger(__name__)

APP_NAME = "ats-beater-profile-chat"

# ── Agent tools (module-level functions) ────────────────────────────────


def get_profile(tool_context: ToolContext) -> dict:
    """Read the current profile data. Call this to see the profile before making changes."""
    return tool_context.state.get("profile", {})


def edit_profile(operations: list[dict], tool_context: ToolContext) -> dict:
    """Apply changes to the profile using JSON Patch (RFC 6902).

    Args:
        operations: List of patch ops. Each has: op ("replace"/"add"/"remove"),
                    path (JSON pointer like "/past_experience/0/description"),
                    value (new value, not needed for "remove").
    """
    current = tool_context.state.get("profile", {})
    try:
        patch = jsonpatch.JsonPatch(operations)
        updated = patch.apply(current)
        validated = ResumeInfo.model_validate(updated)
        tool_context.state["profile"] = validated.model_dump()
        return {"status": "success", "changes_applied": len(operations)}
    except (jsonpatch.JsonPatchException, ValidationError) as e:
        return {"status": "error", "message": str(e)}


# ── System prompt ──────────────────────────────────────────────────────

PROFILE_CHAT_SYSTEM_PROMPT = """You are a profile editing assistant. The user wants to update their resume profile through conversation.
Help them refine it naturally.

## How This Product Works (CRITICAL — users ask about downloads/PDFs constantly)
This is a resume tailoring service called **ATS Beater**. The user is currently viewing their **Profile** page.
Here is the full product flow — you MUST understand this to guide users correctly:

**Profile (you are here):** The user uploads their resume PDF. We extract their info into a structured
profile (the data you can see and edit). This is their "master" resume data — not a downloadable resume.
The profile is reusable across multiple job applications.

**Jobs (separate page, via the sidebar):** The user goes to the **Jobs** section, pastes a **job description**,
and our AI generates a **tailored resume** optimized for that specific role. The tailored resume is then
compiled into an ATS-optimized PDF using LaTeX. THAT is where the downloadable PDF lives.

**Roast (separate page, via the sidebar):** A free feature where users can get their resume "roasted" — a
comedic + serious analysis of their resume with an ATS readiness checklist. No PDF is generated here.

**Credits:** Generating tailored resumes costs credits. Users get 3 free per day. Additional credit packs
can be purchased. Roasts are free.

### Handling download/PDF questions
**If the user asks "how do I download?", "give me PDF", "is this downloadable?", "provide me a resume",
or anything about getting a final resume document — you MUST explain the flow:**
"Your profile is your master data — it's not a downloadable document. To get a PDF resume, go to the
**Jobs** section from the sidebar, paste the job description you're targeting, and click **Generate Resume**.
The system will create an ATS-optimized PDF tailored for that specific role. You can then download it from there."

**NEVER say "click the Download button" or "look for the Export button" — those buttons do NOT exist on
the profile page. NEVER fabricate UI elements that don't exist.**

**If the user says they don't have a job/JD yet:** Explain that they can still refine their profile here,
and when they're ready to apply, they paste a job description in the Jobs section to get a tailored PDF.
Also mention they can try the free **Roast** feature to get feedback on their resume's ATS readiness.

## Your Tools
- get_profile: Read the current profile data. Call this first if you need to see the current state.
- edit_profile: Apply changes using JSON Patch (RFC 6902) operations.
  Supported ops: "replace", "add", "remove"
  Example: [{"op": "replace", "path": "/name", "value": "Jane Doe"}]

## Profile Structure (ResumeInfo)
- /name, /email, /mobile_number, /date_of_birth — personal info
- /links/N — {name, url}
- /past_experience/N — {company_name, department, location, role, start_date, end_date, description}
  Note: description is a single string, not an array of bullets.
- /projects/N — {name, link, description}
  Note: description is a single string, not an array of bullets.
- /skills/N — {name, category}
  Skills are a flat list. Each skill has a name and a category (e.g. "Programming", "Frameworks", "Cloud/Infra", "Data", "AI", "Soft Skills").
- /educations/N — {degree, institution, start_date, end_date, grade}
- /achievements/N — {name, description}
- /certifications/N — {name, credential_id}
- /patents/N — {name, date, description}
- /papers/N — {name, date, description}

Array operations: use index (e.g. /skills/0) or "/-" to append.

## Rules
- Always call get_profile before your first edit to see the current state.
- Make ONLY the changes the user asks for. Don't "improve" other sections unprompted.
- After editing, briefly explain what you changed in plain language.
- If the request is ambiguous, ask for clarification before editing.
- If an edit fails, explain the error and suggest alternatives.
- **Keep responses concise** unless the user explicitly asks for a detailed explanation or analysis. Get to the point.

## ATS Readiness & Resume Scoring (CRITICAL — users ask about this constantly)
If the user asks about their "ATS score", "resume score", "resume rating", asks you to "rate" their resume,
or asks anything about ATS compatibility — you MUST follow these rules:

**NEVER output a numerical score, rating, or percentage.** No "8.5/10", no "88/100", no "ATS score: 75%".
These numbers are completely fabricated and meaningless. Any tool or website claiming to give an "ATS score
out of 100" or a "resume rating" is making it up — there is no such metric.

**ATS systems are parsers and keyword matchers, not scorers.** They extract structured data from resumes and
match keywords against job descriptions. They do NOT assign scores.

Instead, evaluate their profile against this **ATS readiness checklist** (explain each item, then assess):
1. **Machine-readable format** — Already handled. LaTeX compiles to a clean, single-column PDF. Always passes.
2. **Standard section headers** — Already handled. Our template uses recognized headings (Experience, Education,
   Skills, Projects). Always passes.
3. **Contact information** — Email and phone present so ATS can create their candidate profile.
4. **Profile links** — LinkedIn, GitHub, portfolio help recruiters verify their background.
5. **Skills & keywords** — ATS matches job description keywords against skills. More relevant skills with proper
   categorization (Programming, Frameworks, Tools, etc.) = more keyword hits.
6. **Experience with dates** — ATS calculates tenure from dates. Missing dates can trigger auto-rejection when
   JDs require "minimum X years of experience."
7. **Quantified achievements** — Numbers, percentages, and scale in descriptions ("reduced latency by 40%",
   "served 10K users") help both ATS ranking and human review.
8. **Action-oriented language** — Descriptions starting with strong verbs (Built, Led, Designed, Reduced) signal
   ownership and impact.

**Workflow**: First call get_profile to check the actual data. Then explain why ATS scores aren't real, and
walk through the checklist telling the user specifically which criteria are met and which need improvement
based on what you found in their profile. Frame it as: "Passes / Needs attention."
NEVER give a number. If the user insists on a score, firmly explain why scores don't exist.
"""


# ── ProfileChatService ─────────────────────────────────────────────────


class ProfileChatService:
    def __init__(self):
        settings = get_settings()
        self.session_service = DatabaseSessionService(
            db_url=settings.DATABASE_URL
        )
        self.flash_model = settings.GEMINI_FLASH_MODEL

    def _build_agent(self, user_id: str, profile_id: int) -> Agent:
        model_name = self.flash_model
        _profile_id = profile_id
        _user_id = user_id

        async def _after_model_callback(callback_context, llm_response):
            """Log LLM call metrics to llm_requests table."""
            usage = llm_response.usage_metadata
            await _log_request(
                model_name=model_name,
                user_id=_user_id,
                purpose="profile_chat_edit",
                reference_id=str(_profile_id),
                input_tokens=getattr(usage, "prompt_token_count", 0) if usage else 0,
                output_tokens=getattr(usage, "candidates_token_count", 0) if usage else 0,
                total_tokens=getattr(usage, "total_token_count", 0) if usage else 0,
                cached_tokens=getattr(usage, "cached_content_token_count", 0) if usage else 0,
                response_time_ms=0,
                success=True,
                error_message=None,
            )
            return llm_response

        return Agent(
            model=self.flash_model,
            name="profile_editor",
            instruction=PROFILE_CHAT_SYSTEM_PROMPT,
            tools=[get_profile, edit_profile],
            after_model_callback=_after_model_callback,
        )

    async def chat(
        self,
        profile_id: int,
        user_id: str,
        message: str,
        current_profile: dict,
    ) -> dict[str, Any]:
        session_id = f"profile_chat_{profile_id}"

        agent = self._build_agent(user_id, profile_id)
        runner = Runner(
            agent=agent,
            app_name=APP_NAME,
            session_service=self.session_service,
        )

        # Get or create session
        session = await self.session_service.get_session(
            app_name=APP_NAME, user_id=user_id, session_id=session_id,
        )
        if not session:
            session = await self.session_service.create_session(
                app_name=APP_NAME,
                user_id=user_id,
                session_id=session_id,
                state={"profile": current_profile},
            )

        new_message = types.Content(
            role="user", parts=[types.Part.from_text(text=message)]
        )

        response_text = ""
        resume_modified = False
        t0 = time.monotonic()

        async for event in runner.run_async(
            user_id=user_id, session_id=session_id, new_message=new_message,
        ):
            if event.actions and event.actions.state_delta:
                if "profile" in event.actions.state_delta:
                    resume_modified = True
            if event.is_final_response() and event.content:
                for part in event.content.parts:
                    if part.text:
                        response_text += part.text

        elapsed_ms = int((time.monotonic() - t0) * 1000)
        logger.info(f"Profile chat turn for profile {profile_id}: {elapsed_ms}ms, modified={resume_modified}")

        # Get updated profile from session state
        updated_session = await self.session_service.get_session(
            app_name=APP_NAME, user_id=user_id, session_id=session_id,
        )
        updated_profile = updated_session.state.get("profile") if updated_session else None

        return {
            "response": response_text,
            "resume_modified": resume_modified,
            "resume_info": updated_profile,
        }

    _TOOL_LABELS = {
        "get_profile": "Reading profile...",
        "edit_profile": "Editing profile...",
    }

    async def chat_stream(
        self,
        profile_id: int,
        user_id: str,
        message: str,
        current_profile: dict,
    ) -> AsyncGenerator[dict, None]:
        """Like chat() but yields SSE-friendly events as they happen."""
        session_id = f"profile_chat_{profile_id}"

        agent = self._build_agent(user_id, profile_id)
        runner = Runner(
            agent=agent,
            app_name=APP_NAME,
            session_service=self.session_service,
        )

        session = await self.session_service.get_session(
            app_name=APP_NAME, user_id=user_id, session_id=session_id,
        )
        if not session:
            session = await self.session_service.create_session(
                app_name=APP_NAME,
                user_id=user_id,
                session_id=session_id,
                state={"profile": current_profile},
            )

        new_message = types.Content(
            role="user", parts=[types.Part.from_text(text=message)]
        )

        response_text = ""
        resume_modified = False
        t0 = time.monotonic()

        async for event in runner.run_async(
            user_id=user_id, session_id=session_id, new_message=new_message,
        ):
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if part.function_call:
                        label = self._TOOL_LABELS.get(part.function_call.name, part.function_call.name)
                        yield {"type": "tool_call", "name": part.function_call.name, "label": label}

            if event.actions and event.actions.state_delta:
                if "profile" in event.actions.state_delta:
                    resume_modified = True

            if event.is_final_response() and event.content:
                for part in event.content.parts:
                    if part.text:
                        response_text += part.text

        elapsed_ms = int((time.monotonic() - t0) * 1000)
        logger.info(f"Profile chat turn for profile {profile_id}: {elapsed_ms}ms, modified={resume_modified}")

        updated_session = await self.session_service.get_session(
            app_name=APP_NAME, user_id=user_id, session_id=session_id,
        )
        updated_profile = updated_session.state.get("profile") if updated_session else None

        yield {
            "type": "response",
            "response": response_text,
            "resume_modified": resume_modified,
            "resume_info": updated_profile,
        }

    async def get_history(self, profile_id: int, user_id: str) -> list[dict]:
        session_id = f"profile_chat_{profile_id}"
        session = await self.session_service.get_session(
            app_name=APP_NAME, user_id=user_id, session_id=session_id,
        )
        if not session:
            return []

        messages = []
        for event in session.events:
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if part.function_call:
                        label = self._TOOL_LABELS.get(part.function_call.name, part.function_call.name)
                        messages.append({
                            "type": "tool_call",
                            "name": part.function_call.name,
                            "label": label,
                            "timestamp": event.timestamp,
                        })
                    elif part.text:
                        messages.append({
                            "role": event.content.role,
                            "content": part.text,
                            "timestamp": event.timestamp,
                        })
        return messages
