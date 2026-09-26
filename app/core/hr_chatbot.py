from app.core.llm_provider import get_cached_chat_model
from langchain_core.messages import SystemMessage, HumanMessage
from app.core.config import settings

def _llm():
    # Built on first use, not at import. Importing this module must
    # not require provider credentials.
    return get_cached_chat_model(temperature=0.3)

HR_CHATBOT_SYSTEM = """You are an intelligent HR assistant with access to a candidate database.
Answer questions about candidates based only on the data provided.
Be specific — mention candidate names and actual scores. Use bullet points for lists."""

def build_candidate_context(results: list) -> str:
    context = "CANDIDATE DATABASE:\n\n"
    for i, r in enumerate(results, 1):
        s = r["score"]
        profile = r.get("profile")
        jd_matches = r.get("jd_matches", [])
        best_role = jd_matches[0]["role_name"] if jd_matches else "N/A"
        context += f"""Candidate #{i}: {s.candidate_name}
- Score: {s.weighted_total}/10
- Hiring Match: {getattr(s, 'hiring_match_pct', 0)}%
- Verdict: {s.hire_recommendation}
- Confidence: {int(s.confidence*100)}%
- Best-Fit Role: {best_role}
- Matched Skills: {', '.join(s.matched_skills) if s.matched_skills else 'None'}
- Missing Skills: {', '.join(s.missing_skills) if s.missing_skills else 'None'}
- Experience: {profile.experience_years if profile else 'N/A'} years
- AI Reasoning: {s.shortlist_reasoning}
- Dimensions: {', '.join([f"{d.name}:{d.score}" for d in s.dimensions])}

"""
    return context

def ask_hr_chatbot(question: str, results: list, chat_history: list) -> str:
    if not results:
        return "No candidates screened yet. Please run the pipeline first."
    context = build_candidate_context(results)
    messages = [SystemMessage(content=HR_CHATBOT_SYSTEM)]
    messages.append(HumanMessage(content=f"{context}\nAnswer HR questions based on this data."))
    messages.append(SystemMessage(content="Understood. Ask me anything about these candidates."))
    for msg in chat_history[-6:]:
        if msg["role"] == "user":
            messages.append(HumanMessage(content=msg["content"]))
        else:
            messages.append(SystemMessage(content=msg["content"]))
    messages.append(HumanMessage(content=question))
    response = _llm().invoke(messages)
    return response.content.strip()
