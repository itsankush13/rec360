from app.core.llm_provider import get_cached_chat_model
from langchain_core.messages import SystemMessage, HumanMessage
from app.core.config import settings
from app.core.security import sanitize_input
import json, re

def _llm():
    # Built on first use, not at import. Importing this module must
    # not require provider credentials.
    return get_cached_chat_model(temperature=0)

JD_SYSTEM_PROMPT = """You are an expert HR analyst. Extract structured hiring requirements from a Job Description.
Return ONLY valid JSON. No markdown, no explanation.

JSON structure:
{
  "role_title": "string",
  "required_skills": ["list of skills"],
  "preferred_skills": ["list of skills"],
  "min_experience_years": number,
  "education_requirement": "string",
  "key_responsibilities": ["list"],
  "seniority_level": "Junior|Mid|Senior|Lead|Principal"
}"""

def parse_jd(jd_text: str) -> dict:
    clean_text, warnings = sanitize_input(jd_text)
    if warnings:
        print(f"[Security] JD warnings: {warnings}")

    response = _llm().invoke([
        SystemMessage(content=JD_SYSTEM_PROMPT),
        HumanMessage(content=f"Job Description:\n{clean_text}")
    ])
    
    text = response.content.strip()
    # Strip markdown fences if present
    text = re.sub(r"```json|```", "", text).strip()
    return json.loads(text)


GENERATE_SYSTEM_PROMPT = """You are an expert HR analyst writing a Job Description for this \
company, not a generic internet template. Use any company baseline or prior JDs given to you as \
the starting point and adapt them; use any explicit overrides exactly as given. Return ONLY \
valid JSON. No markdown, no explanation.

JSON structure:
{
  "jd_text": "the full job description as prose, ready to show a recruiter",
  "role_title": "string",
  "required_skills": ["list of skills"],
  "preferred_skills": ["list of skills"],
  "min_experience_years": number,
  "education_requirement": "string",
  "key_responsibilities": ["list"],
  "seniority_level": "Junior|Mid|Senior|Lead|Principal"
}"""


def generate_jd(
    role_title: str,
    grade: str | None = None,
    min_experience_years: int | None = None,
    required_skills: list[str] | None = None,
    key_responsibilities: list[str] | None = None,
    remuneration: str | None = None,
    reference_template: dict | None = None,
    similar_examples: list[str] | None = None,
) -> dict:
    """
    The inverse of `parse_jd`: given a role and whatever is already known
    about it, produce a JD. Returns the same structured fields `parse_jd`
    would extract back out, plus `jd_text` — the two stay in sync by
    construction rather than by a second round-trip through the extractor.
    """
    context_lines = [f"Role title: {role_title}"]
    if grade:
        context_lines.append(f"Grade/level: {grade}")
    if min_experience_years is not None:
        context_lines.append(f"Minimum experience: {min_experience_years} years")
    if required_skills:
        context_lines.append(f"Required skills to include: {', '.join(required_skills)}")
    if key_responsibilities:
        context_lines.append(f"Responsibilities to include: {', '.join(key_responsibilities)}")
    if remuneration:
        context_lines.append(f"Remuneration to state: {remuneration}")
    if reference_template:
        context_lines.append(
            "Company baseline for this role (adapt, do not copy verbatim): "
            f"{json.dumps(reference_template)}"
        )
    for i, example in enumerate(similar_examples or [], start=1):
        context_lines.append(f"Prior JD this company used for a similar role (#{i}):\n{example}")

    response = _llm().invoke([
        SystemMessage(content=GENERATE_SYSTEM_PROMPT),
        HumanMessage(content="\n\n".join(context_lines)),
    ])

    text = response.content.strip()
    text = re.sub(r"```json|```", "", text).strip()
    return json.loads(text)