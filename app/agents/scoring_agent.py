from app.core import llm_provider
from langchain_core.messages import SystemMessage, HumanMessage
from app.core.config import settings
from app.models.candidate import CandidateProfile, CandidateScore, ScoringDimension
import json, re


SCORE_SYSTEM_PROMPT = """You are an expert technical recruiter. Score a candidate against a job description.

Return ONLY valid JSON with these exact dimension scores (0-10 each) and one-line justifications:
{
  "skills_match": {"score": number, "justification": "string"},
  "experience_relevance": {"score": number, "justification": "string"},
  "education_certs": {"score": number, "justification": "string"},
  "project_portfolio": {"score": number, "justification": "string"},
  "communication_quality": {"score": number, "justification": "string"},
  "matched_skills": ["list of matched skills"],
  "missing_skills": ["list of missing required skills"],
  "shortlist_reasoning": "2-3 sentence overall assessment",
  "llm_confidence": number between 0 and 1
}

Weights: skills_match=30%, experience_relevance=25%, education_certs=15%, project_portfolio=20%, communication_quality=10%
Be strict and objective. Base scores ONLY on evidence in the resume."""

def score_candidate(
    candidate: CandidateProfile,
    jd_structured: dict,
    semantic_similarity: float = 0.0,
    bm25_score: float = 0.0,
) -> CandidateScore:
    
    llm = llm_provider.get_chat_model(
        max_tokens=1800,
        reasoning_format="hidden",
        model_kwargs={"response_format": {"type": "json_object"}},
    )

    prompt = f"""
JOB REQUIREMENTS:
{json.dumps(jd_structured, indent=2)}

CANDIDATE PROFILE:
Name: {candidate.name}
Experience: {candidate.experience_years} years
Education: {candidate.education}
Skills: {', '.join(candidate.skills)}
Projects: {'; '.join(candidate.projects[:3])}
Certifications: {', '.join(candidate.certifications)}

Resume Sections:
{candidate.segmented_sections.get('experience', '')[:2000]}
"""
    
    messages = [
        SystemMessage(content=SCORE_SYSTEM_PROMPT),
        HumanMessage(content=prompt)
    ]

    response = llm.invoke(messages)
    try:
        scored = _parse_json_response(response.content)
    except json.JSONDecodeError:
        retry_prompt = f"""Return ONLY one compact valid JSON object. Do not use markdown or explanations.

JOB REQUIREMENTS:
{json.dumps(jd_structured)}

CANDIDATE:
Name: {candidate.name}
Experience: {candidate.experience_years}
Education: {candidate.education}
Skills: {', '.join(candidate.skills)}
Resume evidence: {candidate.segmented_sections.get('experience', '')[:1200]}

Use these keys: skills_match, experience_relevance, education_certs, project_portfolio,
communication_quality (each an object with score and justification), matched_skills,
missing_skills, shortlist_reasoning, llm_confidence."""
        retry_response = llm.invoke([
            SystemMessage(content=SCORE_SYSTEM_PROMPT),
            HumanMessage(content=retry_prompt),
        ])
        try:
            scored = _parse_json_response(retry_response.content)
        except json.JSONDecodeError:
            scored = _fallback_scored(candidate, jd_structured)

    weights = {
        "skills_match": 0.30,
        "experience_relevance": 0.25,
        "education_certs": 0.15,
        "project_portfolio": 0.20,
        "communication_quality": 0.10,
    }
    
    dimensions = []
    weighted_total = 0.0
    for key, weight in weights.items():
        dim_data = scored.get(key, {"score": 0, "justification": "Not evaluated"})
        s = float(dim_data["score"])
        dimensions.append(ScoringDimension(
            name=key.replace("_", " ").title(),
            score=s,
            weight=weight,
            justification=dim_data["justification"]
        ))
        weighted_total += s * weight

    # Ensemble score: combine LLM + semantic + BM25
    # Normalize bm25 to 0-10 range (cap at 50 raw score)
    bm25_normalized = min(bm25_score / 5.0, 10.0)
    semantic_score = semantic_similarity * 10  # 0-1 → 0-10
    
    ensemble_score = (
        0.50 * weighted_total +
        0.30 * semantic_score +
        0.20 * bm25_normalized
    )
    
    # Confidence = average of LLM confidence + extraction completeness
    extraction_completeness = min(len(candidate.skills) / 10.0, 1.0)
    confidence = (scored.get("llm_confidence", 0.7) + extraction_completeness) / 2
    
    # Hire recommendation
    if ensemble_score >= 7.5:
        rec = "STRONG HIRE"
    elif ensemble_score >= 6.0:
        rec = "HIRE"
    elif ensemble_score >= 4.5:
        rec = "MAYBE"
    else:
        rec = "NO HIRE"

    matched_skills = scored.get("matched_skills", [])
    missing_skills = scored.get("missing_skills", [])

    # Hiring match % — calculated BEFORE building the object
    skill_coverage = len(matched_skills) / max(
        len(jd_structured.get("required_skills", [])), 1)
    hiring_match = (
        0.5 * semantic_similarity +
        0.3 * skill_coverage +
        0.2 * (ensemble_score / 10)
    ) * 100

    return CandidateScore(
        candidate_name=candidate.name,
        file_name="",
        dimensions=dimensions,
        weighted_total=round(ensemble_score, 2),
        confidence=round(confidence, 2),
        hire_recommendation=rec,
        matched_skills=matched_skills,
        missing_skills=missing_skills,
        semantic_similarity=round(semantic_similarity, 3),
        bm25_score=round(bm25_score, 2),
        bias_masked=True,
        shortlist_reasoning=scored.get("shortlist_reasoning", ""),
        hiring_match_pct=round(min(hiring_match, 100), 1),
    )


def _parse_json_response(content: str) -> dict:
    """Parse a JSON object from a model response, including fenced output."""
    text = re.sub(r"```(?:json)?", "", content or "", flags=re.IGNORECASE).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise json.JSONDecodeError("No JSON object found", text, 0)
    return json.loads(text[start:end + 1])


def _fallback_scored(candidate: CandidateProfile, jd_structured: dict) -> dict:
    """Return a usable evidence-based score when the model response is unusable."""
    candidate_skills = {skill.casefold() for skill in candidate.skills}
    required_skills = jd_structured.get("required_skills", [])
    matched = [skill for skill in required_skills if skill.casefold() in candidate_skills]
    missing = [skill for skill in required_skills if skill.casefold() not in candidate_skills]
    skill_score = 10 * len(matched) / max(len(required_skills), 1)
    experience_target = float(jd_structured.get("min_experience_years") or 0)
    experience_score = 10 if candidate.experience_years >= experience_target else (
        10 * candidate.experience_years / max(experience_target, 1)
    )
    return {
        "skills_match": {"score": skill_score, "justification": "Calculated from extracted required-skill coverage."},
        "experience_relevance": {"score": experience_score, "justification": "Calculated from stated experience and job minimum."},
        "education_certs": {"score": 5, "justification": "Model response unavailable; neutral score used."},
        "project_portfolio": {"score": 5 if candidate.projects else 0, "justification": "Calculated from extracted project evidence."},
        "communication_quality": {"score": 5, "justification": "Model response unavailable; neutral score used."},
        "matched_skills": matched,
        "missing_skills": missing,
        "shortlist_reasoning": "Scored using extracted resume evidence because the AI response was not valid JSON.",
        "llm_confidence": 0.4,
    }

# ===========================================================================
# Phase D — rubric-aware refinement
#
# Everything above is unchanged and still used by app/core/pipeline.py and
# the Streamlit app. It scores five hardcoded dimensions and knows nothing
# about rubrics; it is left exactly as it was so those callers keep working.
#
# What follows is the Phase D path. The important inversion: the model is no
# longer the scorer. `app/core/criterion_scorer.py` produces the score from
# rubric weights, taxonomy matches and the parsed experience timeline, and
# the model is only allowed to *adjust* it, within a band, where evidence
# already exists. That ordering is what makes the result defensible:
#
#   * scores stay reproducible if the model is unavailable
#   * a criterion with no evidence cannot be talked up
#   * eligibility never enters the prompt at all
#
# `deterministic_score` and `raw_score` are both persisted, so any adjustment
# the model made is visible after the fact — which is what Phase E's
# Challenge Agent needs to flag unsupported conclusions.
# ===========================================================================

# The model may move a criterion by at most this many points either way.
LLM_ADJUSTMENT_BAND = 15.0

# Criteria with no evidence at all are excluded from the prompt entirely.
# An LLM asked to reconsider "not demonstrated" reliably invents a reason to
# award partial credit, which is the exact failure mode the client's
# "unsupported conclusions" check exists to catch.
_REFINABLE_OUTCOMES = {"CONFIRMED_MATCH", "PARTIAL_MATCH", "CONTRADICTORY_EVIDENCE"}

REFINE_SYSTEM_PROMPT = """You are auditing a rule-based CV screening score, not producing one.

For each criterion you are given: the requirement, the score a deterministic
engine assigned, and the exact CV excerpts it used. Decide whether the
excerpts justify that score.

Return ONLY valid JSON:
{
  "criteria": [
    {"criterion_key": "string", "adjustment": number, "reason": "one short sentence"}
  ]
}

Rules you must follow:
- "adjustment" is a DELTA in points, between -15 and +15. Use 0 when the score is fair.
- Justify every non-zero adjustment by referring to the supplied excerpts only.
- Never award credit for a skill that is not in the excerpts.
- Judge only what the excerpts show. Do not infer seniority, employer quality,
  education prestige, nationality, gender or age. Do not comment on the person.
- If the excerpts are too thin to judge, use 0.
Be conservative: 0 is the correct answer for most criteria."""


def refine_criterion_scores(results, index, campaign=None, version=None) -> None:
    """
    Adjust `results` in place, within bounds. Never raises.

    `results` is a list of `criterion_scorer.CriterionResult`. Only criteria
    that already have evidence are sent. Every returned adjustment is clamped
    to the band and re-clamped to the criterion's own 0..max_score range, so
    a malformed or adversarial response cannot produce an out-of-range score.
    """
    import json as _json

    llm = llm_provider.get_chat_model(
        max_tokens=1800,
        reasoning_format="hidden",
        model_kwargs={"response_format": {"type": "json_object"}},
    )

    refinable = [
        r for r in results
        if r.evidence and r.outcome.value in _REFINABLE_OUTCOMES and r.weight > 0
    ]
    if not refinable:
        return

    payload = {
        "role": getattr(campaign, "job_title", "") if campaign else "",
        "criteria": [
            {
                "criterion_key": r.criterion_key,
                "requirement": r.label,
                "deterministic_score": r.deterministic_score,
                "max_score": r.max_score,
                "outcome": r.outcome.value,
                "matched_terms": r.matched_terms[:8],
                "missing_terms": r.missing_terms[:8],
                "cv_excerpts": [
                    {
                        "text": e.excerpt[:400],
                        "section": e.section,
                        "page": e.page_number,
                    }
                    for e in r.evidence[:3]
                ],
            }
            for r in refinable
        ],
    }

    response = llm.invoke([
        SystemMessage(content=REFINE_SYSTEM_PROMPT),
        HumanMessage(content=_json.dumps(payload, indent=2)),
    ])
    parsed = _parse_json_response(response.content)

    adjustments = {}
    for entry in parsed.get("criteria", []) or []:
        key = entry.get("criterion_key")
        if not key:
            continue
        try:
            delta = float(entry.get("adjustment", 0) or 0)
        except (TypeError, ValueError):
            continue
        adjustments[key] = (delta, str(entry.get("reason", "") or "").strip())

    by_key = {r.criterion_key: r for r in refinable}
    for key, (delta, reason) in adjustments.items():
        result = by_key.get(key)
        if result is None or delta == 0:
            continue

        clamped = max(-LLM_ADJUSTMENT_BAND, min(LLM_ADJUSTMENT_BAND, delta))
        new_score = max(0.0, min(result.max_score, result.deterministic_score + clamped))
        if abs(new_score - result.raw_score) < 0.01:
            continue

        result.raw_score = round(new_score, 2)
        result.weighted_score = round(
            (result.raw_score / result.max_score if result.max_score else 0.0) * result.weight, 3
        )
        result.llm_adjusted = True
        if reason:
            result.rationale = (
                f"{result.rationale} Model review adjusted this by "
                f"{clamped:+.1f} points: {reason}"
            ).strip()
