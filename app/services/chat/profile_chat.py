import json
import time
from logging import getLogger
from typing import Any, AsyncGenerator

import jsonpatch
from google import genai
from google.genai import types
from pydantic import ValidationError

from app.schemas.resume import ResumeInfo
from app.services.ai.inference import _log_request
from app.services.chat.history import load_history

logger = getLogger(__name__)


def get_profile(profile: dict) -> dict:
    """Read the current profile data."""
    return profile


def _extract_operations(tool_args: dict[str, Any]) -> list[dict]:
    if isinstance(tool_args.get("operations"), list):
        return tool_args["operations"]

    raw_operations = tool_args.get("operations_json")
    if isinstance(raw_operations, list):
        return raw_operations
    if isinstance(raw_operations, str):
        parsed = json.loads(raw_operations)
        if isinstance(parsed, list):
            return parsed
    raise ValueError("edit_profile requires operations_json as a JSON array")


def edit_profile(tool_args: dict[str, Any], profile: dict) -> tuple[dict, dict]:
    """Apply JSON Patch operations to the current profile."""
    try:
        operations = _extract_operations(tool_args)
        patch = jsonpatch.JsonPatch(operations)
        updated = patch.apply(profile)
        validated = ResumeInfo.model_validate(updated)
        new_profile = validated.model_dump()
        return (
            {"status": "success", "changes_applied": len(operations)},
            new_profile,
        )
    except (ValueError, json.JSONDecodeError, jsonpatch.JsonPatchException, ValidationError) as exc:
        return (
            {"status": "error", "message": str(exc)},
            profile,
        )


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

**Credits:** Legacy credits and purchases still exist in the product, but profile editing here is about your
structured profile data.

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
- `get_profile`: Read the current profile data. Call this first if you need to see the current state.
- `edit_profile`: Apply JSON Patch operations by passing `operations_json`, a JSON string containing an
  RFC 6902 patch array.
  Example:
  `[{"op":"replace","path":"/name","value":"Jane Doe"}]`

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


class ProfileChatService:
    _TOOL_LABELS = {
        "get_profile": "Reading profile...",
        "edit_profile": "Editing profile...",
    }

    def _build_config(self) -> types.GenerateContentConfig:
        return types.GenerateContentConfig(
            system_instruction=PROFILE_CHAT_SYSTEM_PROMPT,
            temperature=0.2,
            tools=[
                types.Tool(
                    function_declarations=[
                        types.FunctionDeclaration(
                            name="get_profile",
                            description="Read the current profile before editing it.",
                            parameters={"type": "object", "properties": {}},
                        ),
                        types.FunctionDeclaration(
                            name="edit_profile",
                            description=(
                                "Apply JSON Patch operations to the current profile. "
                                "Pass operations_json as a JSON array string."
                            ),
                            parameters={
                                "type": "object",
                                "properties": {
                                    "operations_json": {
                                        "type": "string",
                                        "description": (
                                            "A JSON string containing an array of RFC 6902 patch "
                                            "operations. Example: "
                                            "[{\"op\":\"replace\",\"path\":\"/skills/0/name\",\"value\":\"Python\"}]"
                                        ),
                                    }
                                },
                                "required": ["operations_json"],
                            },
                        ),
                    ]
                )
            ],
            automatic_function_calling=types.AutomaticFunctionCallingConfig(
                disable=True
            ),
            thinking_config=types.ThinkingConfig(thinking_level="LOW"),
        )

    def _extract_function_calls(self, response) -> list[Any]:
        function_calls = list(getattr(response, "function_calls", []) or [])
        if function_calls:
            return function_calls

        candidates = getattr(response, "candidates", None) or []
        if not candidates:
            return []
        parts = getattr(candidates[0].content, "parts", None) or []
        return [part.function_call for part in parts if getattr(part, "function_call", None)]

    def _extract_model_content(self, response):
        candidates = getattr(response, "candidates", None) or []
        if not candidates:
            return None
        return getattr(candidates[0], "content", None)

    async def _generate_content(
        self,
        *,
        client: genai.Client,
        model_name: str,
        config: types.GenerateContentConfig,
        contents: list[types.Content],
        user_id: str,
        profile_id: int,
    ):
        t0 = time.monotonic()
        try:
            response = await client.aio.models.generate_content(
                model=model_name,
                contents=contents,
                config=config,
            )
        except Exception as exc:
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            await _log_request(
                model_name=model_name,
                user_id=user_id,
                purpose="profile_chat_edit",
                reference_id=str(profile_id),
                input_tokens=0,
                output_tokens=0,
                total_tokens=0,
                cached_tokens=0,
                response_time_ms=elapsed_ms,
                success=False,
                error_message=str(exc)[:500],
            )
            raise

        elapsed_ms = int((time.monotonic() - t0) * 1000)
        usage = getattr(response, "usage_metadata", None)
        await _log_request(
            model_name=model_name,
            user_id=user_id,
            purpose="profile_chat_edit",
            reference_id=str(profile_id),
            input_tokens=getattr(usage, "prompt_token_count", 0) if usage else 0,
            output_tokens=getattr(usage, "candidates_token_count", 0) if usage else 0,
            total_tokens=getattr(usage, "total_token_count", 0) if usage else 0,
            cached_tokens=getattr(usage, "cached_content_token_count", 0) if usage else 0,
            response_time_ms=elapsed_ms,
            success=True,
            error_message=None,
        )
        return response

    async def chat_stream(
        self,
        profile_id: int,
        user_id: str,
        message: str,
        current_profile: dict,
        *,
        api_key: str,
        model_name: str,
    ) -> AsyncGenerator[dict, None]:
        config = self._build_config()
        client = genai.Client(api_key=api_key)

        contents: list[types.Content] = [
            types.Content(role="user", parts=[types.Part.from_text(text=message)])
        ]
        profile_state = current_profile
        profile_modified = False

        for _ in range(6):
            response = await self._generate_content(
                client=client,
                model_name=model_name,
                config=config,
                contents=contents,
                user_id=user_id,
                profile_id=profile_id,
            )
            function_calls = self._extract_function_calls(response)
            if not function_calls:
                yield {
                    "type": "response",
                    "response": (getattr(response, "text", "") or "").strip(),
                    "resume_modified": profile_modified,
                    "resume_info": profile_state,
                }
                return

            model_content = self._extract_model_content(response)
            if model_content:
                contents.append(model_content)

            function_responses = []
            for function_call in function_calls:
                label = self._TOOL_LABELS.get(function_call.name, function_call.name)
                yield {
                    "type": "tool_call",
                    "name": function_call.name,
                    "label": label,
                }

                if function_call.name == "get_profile":
                    result = get_profile(profile_state)
                elif function_call.name == "edit_profile":
                    result, updated_profile = edit_profile(function_call.args or {}, profile_state)
                    if result.get("status") == "success":
                        profile_state = updated_profile
                        profile_modified = True
                else:
                    result = {"status": "error", "message": "Unknown tool"}

                function_responses.append(
                    types.Part.from_function_response(
                        name=function_call.name,
                        response={"result": result},
                    )
                )

            contents.append(types.Content(role="user", parts=function_responses))

        yield {
            "type": "response",
            "response": "I couldn't complete that edit cleanly. Please try a more specific request.",
            "resume_modified": profile_modified,
            "resume_info": profile_state,
        }

    async def get_history(self, db, profile_id: int, user_id: str) -> list[dict]:
        return await load_history(
            db,
            user_id=user_id,
            entity_type="profile",
            entity_id=profile_id,
        )
