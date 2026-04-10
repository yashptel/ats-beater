import json
import time
from logging import getLogger
from typing import Any, AsyncGenerator

import jsonpatch
from google import genai
from google.genai import types
from pydantic import ValidationError

from app.schemas.custom_resume import CustomResumeInfo
from app.services.ai.inference import _log_request
from app.services.chat.history import load_history

logger = getLogger(__name__)


def get_resume(resume: dict) -> dict:
    """Read the current tailored resume."""
    return resume


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
    raise ValueError("edit_resume requires operations_json as a JSON array")


def edit_resume(tool_args: dict[str, Any], resume: dict) -> tuple[dict, dict]:
    """Apply JSON Patch operations to the current tailored resume."""
    try:
        operations = _extract_operations(tool_args)
        patch = jsonpatch.JsonPatch(operations)
        updated = patch.apply(resume)
        validated = CustomResumeInfo.model_validate(updated)
        new_resume = validated.model_dump()
        return (
            {"status": "success", "changes_applied": len(operations)},
            new_resume,
        )
    except (ValueError, json.JSONDecodeError, jsonpatch.JsonPatchException, ValidationError) as exc:
        return (
            {"status": "error", "message": str(exc)},
            resume,
        )


CHAT_SYSTEM_PROMPT = """You are a resume editing assistant. The user has a tailored resume for a specific job.
Help them refine it through conversation.

## How This Works
You edit **structured JSON data** (CustomResumeInfo), not the PDF directly. After each edit, the system
automatically compiles the updated data into a PDF using a fixed LaTeX template. There is only ONE resume
format — you cannot change the layout, fonts, margins, or section ordering. You can only change the content
within each field.

## PDF Layout (fixed template — cannot be modified)
The compiled PDF uses a Jake-style, single-column, ATS-friendly format with a centered header, ruled section
headings, compact spacing, and right-aligned date columns.
Sections appear in this fixed order (empty sections are automatically omitted):

1. **Header**: Name centered, then contact info and links in a compact single line
2. **Summary**: Optional 1-2 sentence professional summary
3. **Technical Skills**: Inline labeled skill groups such as Languages, Frameworks, Databases, Other Technologies
4. **Experience**: Each entry has company name on the left, date on the right, role below, then bullet points
5. **Projects**: Each entry has project name on the left, optional link on the right, then bullet points
6. **Education**: Institution and dates on the first row, degree and grade on the second row
7. **Achievements**: Simple bullet list
8. **Certifications**: Bullet list, credential_id rendered as "Verify" hyperlink if it's a URL, otherwise "ID: ..."
9. **Patents**: Bullet list with optional date and description
10. **Publications**: Bullet list with optional date and description

**Formatting**: Use **bold** (double asterisks) in bullet text for key metrics and technologies — it converts
to bold in the PDF. No other markdown is supported.

## Your Tools
- `get_resume`: Read the current tailored resume. Call this first if you need to see the current state.
- `edit_resume`: Apply JSON Patch (RFC 6902) operations by passing `operations_json`, a JSON string containing
  an array of patch operations.
  Example:
  `[{"op":"replace","path":"/past_experience/0/description/0","value":"Built **X** with **Y**"}]`

## Resume Structure (CustomResumeInfo)
- /name, /email, /mobile_number, /date_of_birth — personal info
- /summary — optional short professional summary
- /links/N — {{name, url}}
- /past_experience/N — {{company_name, role, start_date, end_date, description: [bullet strings]}}
- /projects/N — {{name, link, description: [bullet strings]}}
- /skills — {{languages: [], frameworks: [], databases: [], other_technologies: []}}
- /educations/N — {{degree, institution, start_date, end_date, grade}}
- /achievements — [strings]
- /certifications/N — {{name, credential_id}}
- /patents/N — {{name, date, description}}
- /papers/N — {{name, date, description}}

Array operations: use index (e.g. /past_experience/0) or "/-" to append.

## Downloading the PDF
The user is on the Job page where their tailored resume has already been generated. Once the status is READY,
they click the **"DOWNLOAD PDF"** button at the top of this page to get their PDF.
If the user asks "how do I download?" or "give me the PDF" — point them to this button. Do NOT render the
resume as markdown/text in chat. Do NOT fabricate buttons or UI elements that don't exist.

## Rules
- Always call get_resume before your first edit to see the current state.
- Make ONLY the changes the user asks for. Don't "improve" other sections unprompted.
- Use **bold** for key metrics and technologies in bullet points.
- After editing, briefly explain what you changed in plain language.
- If the request is ambiguous, ask for clarification before editing.
- If an edit fails, explain the error and suggest alternatives.
- **Keep responses concise** unless the user explicitly asks for a detailed explanation or analysis. Get to the point.
- If the user asks to change the format, layout, fonts, or template: explain that there is one
  fixed ATS-optimized format and you can only modify content, not presentation.
- If the user asks to rearrange or reorder sections: explain that the section order (Summary → Technical Skills
  → Experience → Projects → Education) is fixed in the template and already optimized for quick recruiter
  scanning and ATS readability. You can improve the content inside those sections, but not the order itself.
- If the user pastes a new job description and asks you to regenerate or re-tailor the entire resume: decline.
  Explain that full re-tailoring must be done by creating a new job from the dashboard. You can only make
  targeted edits to the existing tailored resume.

## ATS Readiness & Resume Scoring (CRITICAL — users ask about this constantly)
If the user asks about their "ATS score", "resume score", "resume rating", asks you to "rate" their resume,
or asks anything about ATS compatibility — you MUST follow these rules:

**NEVER output a numerical score, rating, or percentage.** No "8.5/10", no "88/100", no "ATS score: 75%".
These numbers are completely fabricated and meaningless. Any tool or website claiming to give an "ATS score
out of 100" or a "resume rating" is making it up — there is no such metric.

**ATS systems are parsers and keyword matchers, not scorers.** They extract structured data from resumes and
match keywords against job descriptions. They do NOT assign scores.

Instead, evaluate their resume against this **ATS readiness checklist** (explain each item, then assess):
1. **Machine-readable format** — Already handled. LaTeX compiles to a clean, single-column PDF. Always passes.
2. **Standard section headers** — Already handled. Our template uses recognized headings. Always passes.
3. **Contact information** — Email and phone present for candidate profile creation.
4. **Profile links** — LinkedIn, GitHub, portfolio for recruiter verification.
5. **Skills & keywords** — ATS matches JD keywords against skills. Since this resume is already tailored to the
   job description, keyword coverage should be strong. Call get_resume to verify.
6. **Experience with dates** — ATS calculates tenure. Missing dates can trigger auto-rejection.
7. **Quantified achievements** — Numbers and metrics in descriptions improve both ATS ranking and human review.
8. **Action-oriented language** — Strong verbs (Built, Led, Reduced) signal ownership.

**Workflow**: First call get_resume to check the actual data. Then explain why ATS scores aren't real, and
walk through the checklist telling the user specifically which criteria are met and which need improvement
based on what you found in their tailored resume. Frame it as: "Passes / Needs attention."
NEVER give a number. If the user insists on a score, firmly explain why scores don't exist.

## Job Description
{job_description_json}

## Original Profile
{profile_info_json}
"""


class ChatService:
    _TOOL_LABELS = {
        "get_resume": "Reading resume...",
        "edit_resume": "Editing resume...",
    }

    def _build_system_prompt(self, job_description: dict, profile_info: dict) -> str:
        return CHAT_SYSTEM_PROMPT.format(
            job_description_json=json.dumps(job_description, indent=2),
            profile_info_json=json.dumps(profile_info, indent=2),
        )

    def _build_config(self, system_prompt: str) -> types.GenerateContentConfig:
        return types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=0.2,
            tools=[
                types.Tool(
                    function_declarations=[
                        types.FunctionDeclaration(
                            name="get_resume",
                            description="Read the current tailored resume before editing it.",
                            parameters={"type": "object", "properties": {}},
                        ),
                        types.FunctionDeclaration(
                            name="edit_resume",
                            description=(
                                "Apply JSON Patch operations to the current resume. "
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
                                            "[{\"op\":\"replace\",\"path\":\"/achievements/0\",\"value\":\"New text\"}]"
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
        job_id: int,
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
                purpose="resume_chat_edit",
                reference_id=str(job_id),
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
            purpose="resume_chat_edit",
            reference_id=str(job_id),
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
        job_id: int,
        user_id: str,
        message: str,
        job_description: dict,
        profile_info: dict,
        current_resume: dict,
        *,
        api_key: str,
        model_name: str,
    ) -> AsyncGenerator[dict, None]:
        system_prompt = self._build_system_prompt(job_description, profile_info)
        config = self._build_config(system_prompt)
        client = genai.Client(api_key=api_key)

        contents: list[types.Content] = [
            types.Content(role="user", parts=[types.Part.from_text(text=message)])
        ]
        resume_state = current_resume
        resume_modified = False

        for _ in range(6):
            response = await self._generate_content(
                client=client,
                model_name=model_name,
                config=config,
                contents=contents,
                user_id=user_id,
                job_id=job_id,
            )
            function_calls = self._extract_function_calls(response)
            if not function_calls:
                yield {
                    "type": "response",
                    "response": (getattr(response, "text", "") or "").strip(),
                    "resume_modified": resume_modified,
                    "custom_resume_data": resume_state,
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

                if function_call.name == "get_resume":
                    result = get_resume(resume_state)
                elif function_call.name == "edit_resume":
                    result, updated_resume = edit_resume(function_call.args or {}, resume_state)
                    if result.get("status") == "success":
                        resume_state = updated_resume
                        resume_modified = True
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
            "resume_modified": resume_modified,
            "custom_resume_data": resume_state,
        }

    async def get_history(self, db, job_id: int, user_id: str) -> list[dict]:
        return await load_history(
            db,
            user_id=user_id,
            entity_type="job",
            entity_id=job_id,
        )
