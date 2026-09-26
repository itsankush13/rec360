"""
Candidate 360 completion — category rollups, next action, validation
questions, interview focus, and campaign benchmarks.

These are the five Candidate 360 sections Phases D and E left open. All of
them are derived from data those phases already produce, which is why none
of this re-scores anything.

Two deliberate choices worth stating:

**Nothing here is model-generated.** The recommended next action, the
validation questions and the interview focus areas all fall out of Phase D's
own findings: a criterion marked INSUFFICIENT_EVIDENCE *is* a question to
ask; an indeterminate eligibility finding *is* a thing to confirm; a
timeline contradiction *is* something to probe. Asking an LLM to invent
questions when the gaps are already enumerated would add variance and
subtract traceability. `app/core/interview_generator.py` remains available
to elaborate on these, optionally and boundedly, but never to originate them.

**A category with no criteria scores None, not zero.** "Not assessed" and
"assessed and scored zero" are different claims about a candidate, and
collapsing them would misrepresent a rubric that simply has no
certification criteria.
"""
from __future__ import annotations

import statistics

from app.db.models import (
    ChallengeSeverity, ConfidenceBand, CriterionOutcome, EligibilityStatus,
    NextAction, Recommendation, RequirementCategory,
)

# Categories rolled up into their own named field on the evaluation, because
# the client's Candidate 360 asks for these four by name.
_NAMED_ROLLUPS = {
    "skills_score": (RequirementCategory.SKILL,),
    "experience_score": (RequirementCategory.EXPERIENCE,),
    "education_score": (RequirementCategory.QUALIFICATION,),
    "certification_score": (RequirementCategory.CERTIFICATION,),
}

# How many questions and focus areas to surface. More than this is noise on
# a screen a recruiter reads before an interview.
MAX_QUESTIONS = 8
MAX_FOCUS_AREAS = 6


# ---------------------------------------------------------------------------
# Category rollups
# ---------------------------------------------------------------------------

def category_rollups(results) -> dict:
    """
    Roll per-criterion scores up by requirement category.

    Weight-weighted within each category and expressed 0-100, so a category
    figure means "how well this candidate did on the criteria of this kind",
    independent of how much of the rubric those criteria happened to occupy.

    Deliberately NOT `sum(weighted_score)` — that would express the category
    as a share of the whole rubric, so a candidate scoring perfectly on
    20 points of skills criteria would read as 20/100 on skills. The
    denominator is the category's own weight.
    """
    buckets: dict[str, list] = {}
    for result in results:
        if result.weight <= 0:
            continue
        buckets.setdefault(result.category.value, []).append(result)

    rollups: dict[str, dict] = {}
    for category, members in buckets.items():
        weight_total = sum(m.weight for m in members)
        if weight_total <= 0:
            continue
        score = sum(m.weighted_score for m in members) / weight_total * 100.0
        confidence = sum(m.confidence * m.weight for m in members) / weight_total
        rollups[category] = {
            "score": round(score, 2),
            "confidence": round(confidence, 3),
            "weight": round(weight_total, 2),
            "criterion_count": len(members),
            "confirmed": sum(
                1 for m in members if m.outcome == CriterionOutcome.CONFIRMED_MATCH
            ),
        }
    return rollups


def named_rollups(rollups: dict) -> dict:
    """
    Map the category rollups onto the four fields the client asked for by
    name. Absent categories stay None.
    """
    out: dict[str, float | None] = {}
    for field, categories in _NAMED_ROLLUPS.items():
        values = [rollups[c.value] for c in categories if c.value in rollups]
        if not values:
            out[field] = None
            continue
        weight_total = sum(v["weight"] for v in values)
        if weight_total <= 0:
            out[field] = None
            continue
        out[field] = round(
            sum(v["score"] * v["weight"] for v in values) / weight_total, 2
        )
    return out


# ---------------------------------------------------------------------------
# Recommended next action
# ---------------------------------------------------------------------------

def next_action(
    *,
    eligibility_status: EligibilityStatus,
    recommendation: Recommendation,
    confidence_band: ConfidenceBand,
    has_indeterminate: bool,
    high_severity_findings: int,
    insufficient_criteria: int,
) -> tuple[NextAction, str]:
    """
    Decide what a recruiter should do next, and say why.

    Ordered by precedence, strictest first. Every branch returns a reason,
    because a next action a recruiter cannot interrogate is just another
    opaque recommendation.
    """
    if eligibility_status == EligibilityStatus.DISQUALIFIED:
        return NextAction.REJECT, (
            "A mandatory eligibility rule was not met. This is a rule-based "
            "outcome, not a score-based one, and the AI assessment cannot "
            "overturn it."
        )

    if has_indeterminate:
        return NextAction.CONFIRM_ELIGIBILITY, (
            "One or more mandatory conditions could not be verified from the CV. "
            "Confirm these with the candidate before assessing them further — "
            "they have not been failed, only left unproven."
        )

    if high_severity_findings:
        return NextAction.MANUAL_REVIEW, (
            f"The review agent raised {high_severity_findings} high-severity "
            "concern(s) about this assessment. Read those before relying on the "
            "score."
        )

    if confidence_band == ConfidenceBand.LOW:
        return NextAction.MANUAL_REVIEW, (
            "Confidence in this assessment is low, usually because the CV gave "
            "little to work with. The score reflects the document more than the "
            "candidate."
        )

    if insufficient_criteria >= 2:
        return NextAction.REQUEST_EVIDENCE, (
            f"{insufficient_criteria} criteria could not be assessed from the CV. "
            "Ask the candidate to supply the missing detail."
        )

    if recommendation in (Recommendation.STRONG_FIT, Recommendation.POTENTIAL_FIT):
        return NextAction.INTERVIEW, (
            "The mandatory criteria are met with sufficient confidence and no "
            "material concerns were raised."
        )

    if recommendation == Recommendation.NOT_RECOMMENDED:
        return NextAction.REJECT, (
            "The scored criteria are met poorly and the evidence for that is "
            "sound. A person should still confirm before rejecting."
        )

    return NextAction.MANUAL_REVIEW, (
        "This candidate sits between the automatic bands and needs a human read."
    )


# ---------------------------------------------------------------------------
# Validation questions and interview focus
# ---------------------------------------------------------------------------

def validation_questions(results, eligibility_findings, profile) -> list[dict]:
    """
    Questions a recruiter should ask to close the gaps this assessment found.

    Each one is traceable to the finding that produced it, which is the
    difference between a useful prompt and a generated pleasantry.
    """
    questions: list[dict] = []

    # Unverifiable mandatory conditions first — these block a decision.
    for finding in eligibility_findings:
        if not getattr(finding, "indeterminate", False):
            continue
        questions.append({
            "question": (
                f"Can you confirm whether you meet this requirement: "
                f"{_trim(getattr(finding, 'label', ''))}?"
            ),
            "why": "This mandatory condition could not be verified from the CV.",
            "source": "eligibility",
            "reference": getattr(finding, "code", ""),
            "priority": "HIGH",
        })

    # Then criteria the CV simply did not speak to.
    insufficient = sorted(
        (r for r in results
         if r.outcome == CriterionOutcome.INSUFFICIENT_EVIDENCE and r.weight > 0),
        key=lambda r: -r.weight,
    )
    for result in insufficient:
        questions.append({
            "question": (
                f"The CV does not make this clear — can you describe your "
                f"experience with {_trim(result.label)}?"
            ),
            "why": "This criterion could not be assessed from the CV as written.",
            "source": "criterion",
            "reference": result.criterion_key,
            "priority": "HIGH" if result.weight >= 15 else "MEDIUM",
        })

    # Contradictions need a direct question, carefully worded.
    for result in (r for r in results
                   if r.outcome == CriterionOutcome.CONTRADICTORY_EVIDENCE):
        questions.append({
            "question": (
                f"The CV appears to indicate limited experience here — can you "
                f"clarify your background in {_trim(result.label)}?"
            ),
            "why": "The CV appears to contradict this requirement rather than omit it.",
            "source": "criterion",
            "reference": result.criterion_key,
            "priority": "HIGH",
        })

    # Timeline questions from the experience engine's own findings.
    for entry in (getattr(profile, "contradictions", None) or []):
        kind = str(entry.get("type", ""))
        if kind == "EMPLOYMENT_GAP":
            questions.append({
                "question": "Could you talk me through the gap in your employment history?",
                "why": entry.get("detail", ""),
                "source": "experience", "reference": kind, "priority": "MEDIUM",
            })
        elif kind in ("EXPERIENCE_CLAIM_MISMATCH", "UNVERIFIED_EXPERIENCE_CLAIM"):
            questions.append({
                "question": (
                    "Can you confirm your total years of relevant experience, and "
                    "the dates of each role?"
                ),
                "why": entry.get("detail", ""),
                "source": "experience", "reference": kind, "priority": "HIGH",
            })
        elif kind == "STALE_EXPERIENCE":
            questions.append({
                "question": "What have you been doing since your most recent role?",
                "why": entry.get("detail", ""),
                "source": "experience", "reference": kind, "priority": "MEDIUM",
            })

    # Deduplicate on the question text, keep the highest priority.
    seen: dict[str, dict] = {}
    for question in questions:
        key = question["question"]
        if key not in seen or question["priority"] == "HIGH":
            seen[key] = question
    ordered = sorted(
        seen.values(), key=lambda q: 0 if q["priority"] == "HIGH" else 1
    )
    return ordered[:MAX_QUESTIONS]


def interview_focus(results, rollups) -> list[dict]:
    """
    What an interview should probe, weighted by what the rubric cares about
    and what the assessment could not settle.
    """
    focus: list[dict] = []

    # Partial and adjacent matches are the most useful interview territory:
    # something is there, but not clearly the thing that was asked for.
    for result in sorted(
        (r for r in results
         if r.outcome == CriterionOutcome.PARTIAL_MATCH and r.weight > 0),
        key=lambda r: -r.weight,
    ):
        focus.append({
            "area": _trim(result.label),
            "reason": (
                "Partially evidenced — probe depth rather than presence."
                if result.matched_terms else
                "Evidenced only through a related skill; establish whether it transfers."
            ),
            "criterion_key": result.criterion_key,
            "weight": result.weight,
        })

    # Then heavy criteria confirmed on low confidence.
    for result in sorted(
        (r for r in results
         if r.outcome == CriterionOutcome.CONFIRMED_MATCH
         and r.confidence_band == ConfidenceBand.LOW and r.weight > 0),
        key=lambda r: -r.weight,
    ):
        focus.append({
            "area": _trim(result.label),
            "reason": "Recorded as met, but the supporting evidence is thin.",
            "criterion_key": result.criterion_key,
            "weight": result.weight,
        })

    # And the weakest category overall, as a framing note.
    if rollups:
        weakest = min(rollups.items(), key=lambda kv: kv[1]["score"])
        category, detail = weakest
        if detail["score"] < 60:
            focus.append({
                "area": f"{category.replace('_', ' ').title()} overall",
                "reason": (
                    f"Weakest category at {detail['score']:.0f} of 100 across "
                    f"{detail['criterion_count']} criteria."
                ),
                "criterion_key": "",
                "weight": detail["weight"],
            })

    return focus[:MAX_FOCUS_AREAS]


def _trim(text: str, limit: int = 110) -> str:
    text = (text or "").strip().rstrip(".")
    return text if len(text) <= limit else text[:limit].rstrip() + "…"


# ---------------------------------------------------------------------------
# Campaign benchmarks
# ---------------------------------------------------------------------------

def benchmarks(scores: list[float]) -> dict | None:
    """
    Distribution of a campaign's scores, for the "comparison with campaign
    benchmarks" section.

    Returns None below four candidates. A median across two people is
    arithmetically valid and practically meaningless, and presenting it as a
    benchmark would be false precision — the same reason the Challenge Agent
    refuses to call outliers on a tiny run.
    """
    usable = [s for s in scores if s is not None]
    if len(usable) < 4:
        return None

    ordered = sorted(usable)
    return {
        "candidates_assessed": len(ordered),
        "mean": round(statistics.fmean(ordered), 2),
        "median": round(statistics.median(ordered), 2),
        "lowest": round(ordered[0], 2),
        "highest": round(ordered[-1], 2),
        "top_quartile_from": round(
            statistics.quantiles(ordered, n=4)[2], 2
        ) if len(ordered) >= 4 else None,
    }


def percentile_of(score: float, scores: list[float]) -> dict | None:
    """
    Where one candidate sits in the campaign.

    Always reported with its denominator — `web/DATA.md` forbids a
    percentage without one, and "top 10%" of nine candidates is a
    meaningfully different statement from "top 10%" of nine hundred.
    """
    usable = sorted(s for s in scores if s is not None)
    if len(usable) < 4:
        return None

    at_or_below = sum(1 for s in usable if s <= score)
    percentile = at_or_below / len(usable) * 100.0
    rank = sum(1 for s in usable if s > score) + 1
    return {
        "percentile": round(percentile, 1),
        "rank": rank,
        "out_of": len(usable),
        "vs_median": round(score - statistics.median(usable), 2),
        "statement": (
            f"Ranks {rank} of {len(usable)} assessed candidates in this campaign."
        ),
    }


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------

def enrich(evaluation, results, eligibility_findings, profile, challenge_findings=None) -> None:
    """
    Populate the Phase F fields on an evaluation, in place, before it is
    committed. Reads Phase D/E output only — computes no new scores.
    """
    rollups = category_rollups(results)
    evaluation.category_scores = rollups
    for field, value in named_rollups(rollups).items():
        setattr(evaluation, field, value)

    high_severity = sum(
        1 for f in (challenge_findings or [])
        if getattr(f, "severity", None) == ChallengeSeverity.HIGH
    )
    action, reason = next_action(
        eligibility_status=evaluation.eligibility_status,
        recommendation=evaluation.recommendation,
        confidence_band=evaluation.confidence_band,
        has_indeterminate=any(
            getattr(f, "indeterminate", False) for f in eligibility_findings
        ),
        high_severity_findings=high_severity,
        insufficient_criteria=sum(
            1 for r in results
            if r.outcome == CriterionOutcome.INSUFFICIENT_EVIDENCE and r.weight > 0
        ),
    )
    evaluation.next_action = action.value
    evaluation.next_action_reason = reason
    evaluation.validation_questions = validation_questions(
        results, eligibility_findings, profile
    )
    evaluation.interview_focus = interview_focus(results, rollups)
