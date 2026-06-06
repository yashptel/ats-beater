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
from app.services.ai.user_settings import (
    PROVIDER_OPENAI,
    local_endpoints_allowed,
    validate_base_url,
)
from app.services.chat.history import load_history
from app.services.chat.openai_chat import stream_tool_chat, to_openai_tools

logger = getLogger(__name__)

OPENAI_CHAT_TOOLS = to_openai_tools(
    [
        {
            "name": "get_resume",
            "description": "Read the current tailored resume before editing it.",
            "parameters": {"type": "object", "properties": {}},
        },
        {
            "name": "edit_resume",
            "description": (
                "Apply JSON Patch operations to the current resume. "
                "Pass operations_json as a JSON array string."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "operations_json": {
                        "type": "string",
                        "description": (
                            "A JSON string containing an array of RFC 6902 patch operations. "
                            "Example: [{\"op\":\"replace\",\"path\":\"/achievements/0\",\"value\":\"New text\"}]"
                        ),
                    }
                },
                "required": ["operations_json"],
            },
        },
    ]
)


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
    except (
        ValueError,
        TypeError,
        KeyError,
        json.JSONDecodeError,
        jsonpatch.JsonPatchException,
        ValidationError,
    ) as exc:
        return (
            {"status": "error", "message": str(exc)},
            resume,
        )


CHAT_SYSTEM_PROMPT = """You are a job-search assistant for a specific job application. The user has a
tailored resume for the job. Help them — through conversation — refine the
resume, draft polished answers to interview questions about this role, and
draft referral messages they can send to land an interview.

## How This Works
You edit **structured JSON data** (CustomResumeInfo), not the PDF directly. After each edit, the system
automatically compiles the updated data into a PDF using the job's selected LaTeX template. Users can switch
between the app's fixed templates from the Job page UI, but chat edits are content-only. You can only change
the content within each field.

## PDF Layout (selected fixed template — chat cannot modify it)
The compiled PDF uses one of the app's fixed ATS-friendly templates. Depending on the selected template,
spacing, fonts, section heading style, and density may differ. Sections appear in this fixed order
(empty sections are automatically omitted):

1. **Header**: Name centered, then contact info and links in a compact single line
2. **Summary**: Optional 1-2 sentence professional summary
3. **Technical Skills**: Inline labeled skill groups such as Languages, Frameworks, Databases, Other Technologies
4. **Experience**: Each entry has company name on the left, date on the right, role below, then bullet points
5. **Projects**: Each entry has the project name on the left, linked when a valid project URL exists, then bullet points
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
  `[{{"op":"replace","path":"/past_experience/0/description/0","value":"Built **X** with **Y**"}}]`

## Resume Structure (CustomResumeInfo)
- /name, /email, /mobile_number, /date_of_birth — personal info
- /location — optional candidate location
- /summary — optional short professional summary
  To remove it, delete `/summary` or set it to null.
- /links/N — {{name, url}}
- /past_experience/N — {{company_name, department, location, role, start_date, end_date, description: [bullet strings]}}
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
- If the user asks to change the format, layout, fonts, or template: explain that template changes are handled
  by the template selector on the Job page. You can improve the content, but you cannot change templates in chat.
- If the user asks to rearrange or reorder sections: explain that the section order (Summary → Technical Skills
  → Experience → Projects → Education) is fixed in the template and already optimized for quick recruiter
  scanning and ATS readability. You can improve the content inside those sections, but not the order itself.
- If the user pastes a new job description and asks you to regenerate or re-tailor the entire resume: decline.
  Explain that full re-tailoring must be done by creating a new job from the dashboard. You can only make
  targeted edits to the existing tailored resume.

## Interview Answer Drafting

When the user asks you to draft, write, prepare, or help with an answer to an
interview question (examples: "Why do you want to work here?", "Tell me about
yourself", "What's your biggest weakness?", "Why are you leaving?", "Tell me
about a hard problem you solved", "Conflict with a manager", "A time you
failed", "Why this role?"), produce a polished, ready-to-rehearse answer
grounded in the candidate's profile and tailored to this specific job's JD.

### Truthfulness (ABSOLUTE)
- NEVER invent a project, story, achievement, or number not present in the
  candidate's profile.
- Anchor every claim to a specific role, project, or skill in the profile.
- Reference the JD's requirements where you can do so honestly.
- If the profile lacks a story for the question being asked (for example,
  the user wants "tell me about a conflict with a manager" and nothing in
  the profile speaks to that), DO NOT fabricate one. Say: "Your profile
  doesn't yet have a story for X — share it in 1-2 lines and I'll structure
  it into an answer."

### Style and length
- Spoken style. Short sentences. No bullet points, no headers, no markdown
  inside the answer itself.
- Short questions (Why this company / Why this role / Biggest weakness /
  Why leaving): 2-4 sentences.
- Behavioural questions ("Tell me about a time you…", "Describe a hard
  problem…", "Conflict…", "Failed project…", "Led a team…"): 6-9 sentences.
- Don't open with "I am…" or "I would say…" — just start the answer.

### Output shape
- Non-behavioural questions: return the polished answer only.
- Behavioural questions: return the polished answer first, then a tiny
  STAR breakdown underneath in this exact form:

  **STAR breakdown**
  - **Situation:** one line
  - **Task:** one line
  - **Action:** one line
  - **Result:** one line (use real numbers from the profile if present)

The STAR breakdown is a rehearsal aid — it lives outside the spoken answer.
Never weave Situation/Task/Action/Result labels into the answer itself.

## Referral Message Drafting

When the user asks you to write, draft, or help with a referral message,
referral email, or outreach for this job (examples: "Draft a referral
message to my contact at this company", "Email to the recruiter for this
role", "DM to my friend at Stripe about this job", "Help me ask for a
warm intro"), draft a single ready-to-send message grounded in the
candidate's profile and tailored to this specific job's JD.

### Infer before drafting
Read the user's request and infer:
1. CHANNEL — email (has Subject), LinkedIn DM, plain message / SMS, or
   Slack. Inferred from words like "email", "DM", "LinkedIn", "message".
2. RECIPIENT — someone the user knows at the company (warm), a recruiter
   (cold), a hiring manager (cold), or generic / unknown.
3. TONE — professional default; friendlier if the user says it's a friend
   or someone they already know well.

If channel and recipient are both ambiguous AND the message would land
very differently across them (warm intro to a friend vs cold email to a
recruiter), ask exactly ONE clarifying question before drafting. Otherwise
draft with your best inference.

### Truthfulness (ABSOLUTE)
- Mention only experience, skills, and achievements actually in the
  candidate's profile.
- Reference the specific job title and (when present in the JD) the
  company name.
- Tailor ONE sentence to why the candidate fits this specific role —
  pull from the most relevant role or project in the profile.

### Style
- No buzzwords. No "I am writing to express my interest in…". No
  "passionate about…" / "deeply motivated by…" filler.
- Concrete, low-pressure ask at the end: "would you be open to passing
  this along", "would you consider referring me for this role", "happy
  to chat for 10 minutes if helpful". Never demand or guilt.
- Short. Email body 3-5 short paragraphs, ~150 words. LinkedIn DM /
  plain message 2-3 short paragraphs, ~100 words.

### Output shape
- Email: first line `Subject: <subject>`, then a blank line, then the body.
- LinkedIn DM / plain message / Slack: just the message body, no subject.
- Don't surround the message in code fences. Don't add a "Here's the draft:"
  preamble — the chat already shows it's your reply.

### If the user doesn't specify recipient or channel
Ask one question: "Quick check — is this for someone you know at the
company, a recruiter, or the hiring manager? And what channel — email or
LinkedIn?" Then draft.

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

    def _execute_tool(self, name: str, args: dict, resume_state: dict):
        """Run a chat tool with resume validation. Shared by both provider loops.

        Returns (result, new_state, modified)."""
        if name == "get_resume":
            return get_resume(resume_state), resume_state, False
        if name == "edit_resume":
            result, updated = edit_resume(args or {}, resume_state)
            if result.get("status") == "success":
                return result, updated, True
            return result, resume_state, False
        return {"status": "error", "message": "Unknown tool"}, resume_state, False

    def _make_openai_client(self, ai_settings):
        from openai import AsyncOpenAI

        return AsyncOpenAI(
            api_key=ai_settings.api_key, base_url=ai_settings.base_url, timeout=60.0
        )

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
        ai_settings,
    ) -> AsyncGenerator[dict, None]:
        system_prompt = self._build_system_prompt(job_description, profile_info)

        if ai_settings.provider == PROVIDER_OPENAI:
            validate_base_url(ai_settings.base_url or "", allow_local=local_endpoints_allowed())
            client = self._make_openai_client(ai_settings)
            async for event in stream_tool_chat(
                client=client,
                model=ai_settings.model_name,
                system_prompt=system_prompt,
                message=message,
                tools=OPENAI_CHAT_TOOLS,
                tool_labels=self._TOOL_LABELS,
                execute_tool=self._execute_tool,
                initial_state=current_resume,
                state_key="custom_resume_data",
                reasoning_effort=ai_settings.reasoning_effort,
                user_id=user_id,
                purpose="resume_chat_edit",
                reference_id=str(job_id),
                fallback_message="I couldn't complete that edit cleanly. Please try a more specific request.",
            ):
                yield event
            return

        model_name = ai_settings.model_name
        config = self._build_config(system_prompt)
        client = genai.Client(api_key=ai_settings.api_key)

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
