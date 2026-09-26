from app.core.llm_provider import get_cached_chat_model
from langchain_core.messages import SystemMessage, HumanMessage
from app.core.config import settings

def _llm():
    # Built on first use, not at import. Importing this module must
    # not require provider credentials.
    return get_cached_chat_model(temperature=0)

def compare_candidates(candidate_a: dict, candidate_b: dict) -> str:
    sa = candidate_a["score"]
    sb = candidate_b["score"]
    pa = candidate_a.get("profile")
    pb = candidate_b.get("profile")
    prompt = f"""Compare these two candidates head-to-head.

CANDIDATE A: {sa.candidate_name}
Score: {sa.weighted_total}/10 | Verdict: {sa.hire_recommendation}
Skills: {', '.join(sa.matched_skills)}
Missing: {', '.join(sa.missing_skills)}
Experience: {pa.experience_years if pa else 'N/A'} years
Reasoning: {sa.shortlist_reasoning}

CANDIDATE B: {sb.candidate_name}
Score: {sb.weighted_total}/10 | Verdict: {sb.hire_recommendation}
Skills: {', '.join(sb.matched_skills)}
Missing: {', '.join(sb.missing_skills)}
Experience: {pb.experience_years if pb else 'N/A'} years
Reasoning: {sb.shortlist_reasoning}

Provide:
1. Who is stronger and why (2-3 sentences)
2. What A has that B doesn't
3. What B has that A doesn't
4. Final recommendation for HR
Keep it concise and practical."""
    response = _llm().invoke([
        SystemMessage(content="You are an expert HR consultant giving clear candidate comparisons."),
        HumanMessage(content=prompt)
    ])
    return response.content.strip()
