from app.core.llm_provider import get_cached_chat_model
from langchain_core.messages import SystemMessage, HumanMessage
from app.core.config import settings

def _llm():
    # Built on first use, not at import. Importing this module must
    # not require provider credentials.
    return get_cached_chat_model(temperature=0.5, reasoning_format="hidden")

def generate_hiring_summary(results: list, jd_structured: dict, company: str = "Our Company") -> str:
    if not results:
        return "No candidates are available yet. Run the screening pipeline before generating a hiring summary."

    role = jd_structured.get("role_title", "the role")
    total = len(results)
    shortlisted = [r for r in results if r["score"].hire_recommendation in ["HIRE", "STRONG HIRE"]]
    candidates_summary = "\n".join([
        f"- {r['score'].candidate_name}: {r['score'].weighted_total}/10 — {r['score'].hire_recommendation}"
        for r in results
    ])
    prompt = f"""Write a professional executive summary email for a hiring manager.

Role: {role} at {company}
Total Screened: {total}
Shortlisted: {len(shortlisted)}
Top candidate: {results[0]['score'].candidate_name} ({results[0]['score'].weighted_total}/10)
Top strengths: {', '.join(results[0]['score'].matched_skills[:5])}

All candidates:
{candidates_summary}

Write a concise 150-word email that:
1. States total screened and shortlisted
2. Highlights top 2 candidates with key strengths
3. Recommends next steps
Professional tone suitable for C-suite."""
    response = _llm().invoke([
        SystemMessage(content="You write concise executive HR summary emails."),
        HumanMessage(content=prompt)
    ])
    return response.content.strip()
