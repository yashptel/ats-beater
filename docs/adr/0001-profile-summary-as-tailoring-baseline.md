# Profile Summary is the baseline; Custom Summary is AI-tailored per job

We have two summary fields: `ResumeInfo.summary` (Profile Summary, user-authored)
and `CustomResumeInfo.summary` (Custom Summary, on the tailored PDF). When
Profile Summary is set, the tailoring prompt receives it as input and refines it
for the target JD — same pattern as experience and projects, where the profile
is the source of truth and the AI tailors per job. When Profile Summary is null,
the AI may still generate a Custom Summary if it materially helps the resume; a
null Profile Summary means "the user hasn't written one," not "suppress the
summary on tailored resumes."

## Considered Options

- **Verbatim copy** — if Profile Summary is set, copy as-is to Custom Summary
  with no AI rewrite. Rejected: removes a degree of JD tailoring users expect
  from this product.
- **Two unrelated fields** — Profile Summary purely cosmetic; AI ignores it.
  Rejected: nothing else in the profile is decoupled from tailoring, so this
  would be a surprising special case.
- **Hard opt-out on null** — null Profile Summary forces null Custom Summary.
  Rejected: most users will never write a profile summary, and this would
  silently suppress a section that often improves their tailored resume.

## Consequences

- The parser (`STRUCTURED_RESUME_SYSTEM_PROMPT`) must extract any existing
  summary verbatim from uploaded PDFs and never fabricate one.
- The tailoring prompt (`CUSTOM_RESUME_SYSTEM_PROMPT`) must explicitly handle
  both the "baseline present, refine" and "baseline absent, may generate" paths.
- The enhance flow (`ENHANCED_RESUME_SYSTEM_PROMPT`) must preserve null when the
  user hasn't written a summary — refining null to a fabricated string would
  break the user's stated intent.
- Removing the Profile Summary in the UI sets the field to null, not empty
  string; the tailoring AI must continue to treat null as "may generate."
