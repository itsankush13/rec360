"""
AI-first campaign entry point — extract structured hiring intent from a
recruiter's free-text request ("Hire a Senior Data Engineer with 5+ years of
Python, SQL and AWS experience").

Mirrors app.agents.jd_agent's shape exactly: built on first use (importing
this module must not require provider credentials), same markdown-fence
stripping, same sanitize_input trust boundary on free-text input. This
agent's output feeds jd_generation_service.generate_for_campaign the same
way a recruiter's own step-1 form answers would — it does not replace JD
generation or requirement extraction, it only supplies their inputs from
one sentence instead of a multi-field form.
"""
from app.core.llm_provider import get_cached_chat_model
from langchain_core.messages import SystemMessage, HumanMessage
from app.core.security import sanitize_input
import json, re


def _llm():
    return get_cached_chat_model(temperature=0)


SYSTEM_PROMPT = """You are an expert HR analyst. A recruiter has described who they need to \
hire in one informal sentence or paragraph. Extract structured hiring intent from it.
Return ONLY valid JSON. No markdown, no explanation. If a field is not mentioned, use null \
(or an empty list for list fields) — never invent a value that was not stated or clearly \
implied by the request.

JSON structure:
{
  "role_title": "string — the job title. Always required; infer a reasonable one if not explicit",
  "seniority_level": "Junior|Mid|Senior|Lead|Principal, or null",
  "min_experience_years": number or null,
  "required_skills": ["list of must-have skills/technologies"],
  "preferred_skills": ["list of nice-to-have skills/technologies"],
  "education_requirement": "string or null",
  "key_responsibilities": ["list, only if stated or clearly implied"],
  "location": "string or null",
  "work_arrangement": "remote|hybrid|onsite, or null",
  "vacancies": number or null,
  "business_unit": "string or null",
  "remuneration": "string or null"
}"""


class HiringRequestParseError(ValueError):
    """The model's response was not usable JSON, or named no identifiable role."""


def extract_hiring_intent(request_text: str) -> dict:
    clean_text, warnings = sanitize_input(request_text)
    if warnings:
        print(f"[Security] hiring request warnings: {warnings}")

    response = _llm().invoke([
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=f"Recruiter's request:\n{clean_text}"),
    ])

    text = response.content.strip()
    text = re.sub(r"```json|```", "", text).strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise HiringRequestParseError(f"AI returned unparseable output: {exc}") from exc

    if not isinstance(parsed, dict) or not str(parsed.get("role_title") or "").strip():
        raise HiringRequestParseError("AI could not identify a role to hire for from this request")

    return parsed
