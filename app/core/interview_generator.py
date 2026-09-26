from app.core.llm_provider import get_cached_chat_model
from langchain_core.messages import SystemMessage, HumanMessage
from app.core.config import settings
import json, re

def _llm():
    # Built on first use, not at import. Importing this module must
    # not require provider credentials.
    return get_cached_chat_model(temperature=0.7)

def generate_interview_questions(candidate_result: dict, jd_structured: dict, num_questions: int = 8) -> dict:
    s = candidate_result["score"]
    profile = candidate_result.get("profile")
    prompt = f"""Generate {num_questions} personalized interview questions for this candidate.

CANDIDATE: {s.candidate_name}
Score: {s.weighted_total}/10
Matched Skills: {', '.join(s.matched_skills)}
Missing Skills: {', '.join(s.missing_skills)}
Experience: {profile.experience_years if profile else 'N/A'} years
Assessment: {s.shortlist_reasoning}
JOB ROLE: {jd_structured.get('role_title', 'the role')}
Required Skills: {', '.join(jd_structured.get('required_skills', []))}

Return ONLY valid JSON, no markdown:
{{
  "technical":   ["q1", "q2"],
  "gap_probe":   ["q1", "q2"],
  "behavioural": ["q1", "q2"],
  "culture_fit": ["q1"],
  "motivation":  ["q1"]
}}"""
    response = _llm().invoke([
        SystemMessage(content="You generate specific interview questions. Return only valid JSON."),
        HumanMessage(content=prompt)
    ])
    text = re.sub(r"```json|```", "", response.content.strip()).strip()
    return json.loads(text)
