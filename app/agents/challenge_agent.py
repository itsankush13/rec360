from app.core.llm_provider import get_cached_chat_model
from langchain_core.messages import HumanMessage, SystemMessage
from app.core.config import settings
from app.models.candidate import CandidateProfile, CandidateScore
import json
import re

def _llm():
    # Built on first use, not at import. Importing this module must
    # not require provider credentials.
    return get_cached_chat_model(temperature=0)

CHALLENGE_SYSTEM_PROMPT = """You are a rigorous hiring assessment challenge agent.
Review the candidate profile and score, looking for unsupported conclusions, inconsistent dimension scores,
missing or weak evidence, and unusually high or low scores relative to matched skills.
Return ONLY valid JSON in this shape:
{
  "challenge_detected": boolean,
  "risk_level": "LOW|MEDIUM|HIGH",
  "issues": ["specific issues"],
  "recommendations": ["specific review recommendations"],
  "evidence_quality": "STRONG|MIXED|WEAK"
}"""


def challenge_score(score: CandidateScore, profile: CandidateProfile) -> dict:
    response = _llm().invoke([
        SystemMessage(content=CHALLENGE_SYSTEM_PROMPT),
        HumanMessage(content=json.dumps({
            "score": score.model_dump(),
            "profile": {
                "name": profile.name,
                "experience_years": profile.experience_years,
                "skills": profile.skills,
                "projects": profile.projects,
                "certifications": profile.certifications,
                "resume_evidence": profile.raw_text[:2500],
            },
        })),
    ])
    text = re.sub(r"```(?:json)?", "", response.content or "", flags=re.IGNORECASE).strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return _fallback_challenge(score, profile)
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return _fallback_challenge(score, profile)


def _fallback_challenge(score: CandidateScore, profile: CandidateProfile) -> dict:
    issues = []
    if not score.matched_skills:
        issues.append("No matched required skills were extracted.")
    if not profile.projects and not profile.segmented_sections.get("experience"):
        issues.append("Limited resume evidence is available for the assessment.")
    if score.weighted_total >= 8 and len(score.matched_skills) < 2:
        issues.append("High overall score is not supported by the matched-skill count.")
    return {
        "challenge_detected": bool(issues),
        "risk_level": "MEDIUM" if issues else "LOW",
        "issues": issues,
        "recommendations": ["Review the cited resume evidence before making a final decision."] if issues else [],
        "evidence_quality": "WEAK" if issues else "MIXED",
    }