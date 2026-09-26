"""
B07 — per-JD, LLM-tailored weight suggestion for a rubric's active criteria.

Mirrors `app.agents.jd_agent`'s shape: built on first use (importing this
module must not require provider credentials), same markdown-fence
stripping, same `sanitize_input` trust boundary on free-text JD input.
"""
from app.core.llm_provider import get_cached_chat_model
from langchain_core.messages import SystemMessage, HumanMessage
from app.core.security import sanitize_input
import json, re


def _llm():
    return get_cached_chat_model(temperature=0)


WEIGHT_SUGGESTION_SYSTEM_PROMPT = """You are an expert HR analyst. Given a role title, a job \
description, and a list of scoring criteria, assign each criterion a weight from 0 to 100 so \
that all weights sum to exactly 100.

Weight MANDATORY criteria more heavily by default — real hiring practice puts nearly all \
weight on mandatory criteria — unless the job description clearly justifies a different \
balance.

Return ONLY valid JSON mapping each criterion_key to its weight, no markdown, no explanation:
{"criterion_key_1": weight, "criterion_key_2": weight, ...}"""


def suggest_weights(role_title: str, job_description: str, criteria: list[dict]) -> dict[str, float]:
    clean_text, warnings = sanitize_input(job_description or "")
    if warnings:
        print(f"[Security] JD warnings: {warnings}")

    criteria_lines = "\n".join(
        f"- criterion_key={c['criterion_key']!r}, label={c['label']!r}, "
        f"category={c['category']!r}, requirement_type={c['requirement_type']!r}"
        for c in criteria
    )
    human_content = (
        f"Role title: {role_title}\n\n"
        f"Job description:\n{clean_text}\n\n"
        f"Criteria:\n{criteria_lines}"
    )

    response = _llm().invoke([
        SystemMessage(content=WEIGHT_SUGGESTION_SYSTEM_PROMPT),
        HumanMessage(content=human_content),
    ])

    text = response.content.strip()
    text = re.sub(r"```json|```", "", text).strip()
    return json.loads(text)
