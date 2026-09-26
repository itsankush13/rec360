from app.core.llm_provider import get_cached_chat_model
from langchain_core.messages import SystemMessage, HumanMessage
from app.core.config import settings
import json, re

def _llm():
    # Built on first use, not at import. Importing this module must
    # not require provider credentials.
    return get_cached_chat_model(temperature=0)

BIAS_SYSTEM_PROMPT = """You are a strict fairness auditor for AI hiring systems.
Carefully review the candidate's resume text AND scoring rationale for bias indicators.

AUTOMATICALLY flag as bias_detected=true if ANY of these appear in the resume or rationale:
- Age mentioned (e.g. "21 years old", "DOB", "Age:", birth year that reveals age)
- Gender mentioned (e.g. "girl", "boy", "she", "he", "female", "male", "Mrs", "Mr")  
- Religion, nationality, or ethnicity mentioned explicitly
- Photo referenced
- Marital status mentioned
- Scoring language that references gender/age/name origin

Return ONLY valid JSON:
{
  "bias_detected": boolean,
  "bias_types": ["list — e.g. age_disclosure, gender_disclosure, name_origin_bias"],
  "bias_risk_level": "LOW|MEDIUM|HIGH",
  "recommendations": ["list of specific recommendations"],
  "fair_scoring_confidence": number 0-1
}"""

def audit_for_bias(scoring_rationale: str, candidate_name: str,
                   resume_text: str = "") -> dict:
    response = _llm().invoke([
        SystemMessage(content=BIAS_SYSTEM_PROMPT),
        HumanMessage(content=f"""
Candidate Name: {candidate_name}
Resume Text (first 800 chars): {resume_text[:800]}
Scoring Rationale: {scoring_rationale}

Check BOTH the resume text and rationale for any bias indicators.
""")
    ])
    text = response.content.strip()
    text = re.sub(r"```json|```", "", text).strip()
    return json.loads(text)