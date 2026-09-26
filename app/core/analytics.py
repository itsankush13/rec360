"""
Comparison, what-if analysis, and KPI aggregates.

All three are read-only derivations over data Phases C–F already wrote.
Nothing here scores, persists, or calls a model.

Three design points that matter more than the arithmetic:

**What-if persists nothing.** The requirement is explicit: preview ranking
changes "without changing approved results". Because
`EvaluationCriterion.raw_score` is immutable, reweighting is pure arithmetic
over stored values — no re-scoring, no LLM, no writes. That makes the
non-destructiveness structural rather than a promise.

**Comparison refuses across rubric versions.** Two candidates scored under
different rubrics are not comparable, and a side-by-side table would imply
they were. Every evaluation pins `rubric_version_id`, so this is detectable,
and it returns an error rather than a plausible-looking lie.

**KPI efficiency figures rest on assumptions, not measurements.**
`web/DATA.md` derives recruiter hours returned from 6.9 minutes saved per CV
against an 8.0-minute manual baseline at $42.00/hour. Those three numbers are
the client's estimates. They are therefore inputs to this module, defaulted
but overridable, and every derived figure is returned alongside the
assumption that produced it. A dashboard that asserts a dollar saving without
showing its baseline is asserting something the system has never verified —
and DATA.md's own language rules forbid exactly that.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field

from app.db.models import (
    ChallengeSeverity, ConfidenceBand, CriterionOutcome, EligibilityStatus,
    JobStatus, Recommendation,
)

# Defaults from web/DATA.md. Assumptions, not measurements — see module
# docstring. Overridable per request.
DEFAULT_MANUAL_MINUTES_PER_CV = 8.0
DEFAULT_ASSISTED_MINUTES_PER_CV = 1.1
DEFAULT_HOURLY_RATE = 42.00
DEFAULT_CURRENCY = "USD"

# Below this many candidates, distribution statistics are not reported. Same
# threshold the Challenge Agent and Phase F benchmarks use, for the same
# reason: a median across three people is false precision.
MIN_FOR_DISTRIBUTION = 4

# A what-if weight set must balance to 100, exactly as Phase B requires of a
# real rubric. Previewing an unbalanced rubric would produce scores on an
# unknown scale.
WEIGHT_TOLERANCE = 0.01


class AnalyticsError(Exception):
    """Caller-fixable; the API maps this to 4xx."""

    def __init__(self, message: str, errors: list[str] | None = None):
        super().__init__(message)
        self.message = message
        self.errors = errors or []


# ---------------------------------------------------------------------------
# Candidate comparison
# ---------------------------------------------------------------------------

def compare(evaluations) -> dict:
    """
    Side-by-side comparison on shared criteria.

    Requires at least two evaluations, all scored under the same rubric
    version. The output is criterion-major (one row per criterion, one cell
    per candidate) because that is how the screen reads it — comparing
    candidates *on a requirement* rather than listing each candidate's
    scores separately.
    """
    if len(evaluations) < 2:
        raise AnalyticsError("Comparison needs at least two assessed candidates.")

    versions = {e.rubric_version_id for e in evaluations}
    if len(versions) > 1:
        raise AnalyticsError(
            "These candidates were scored under different rubric versions, so "
            "their scores are not comparable. Re-evaluate them against the same "
            "version first.",
            errors=sorted(versions),
        )

    # Criterion order comes from the rubric's own display order, taken from
    # the first evaluation — they all share a rubric version, so the set is
    # identical.
    ordered = sorted(evaluations[0].criteria, key=lambda c: c.display_order)

    candidates = [
        {
            "candidate_id": e.candidate_id,
            "evaluation_id": e.id,
            "overall_score": round(e.overall_score, 2),
            "overall_confidence": round(e.overall_confidence, 3),
            "confidence_band": e.confidence_band.value,
            "mandatory_score": round(e.mandatory_score, 2),
            "recommendation": e.recommendation.value,
            "eligibility_status": e.eligibility_status.value,
            "experience_years_total": e.experience_years_total,
            "experience_years_relevant": e.experience_years_relevant,
        }
        for e in evaluations
    ]

    rows: list[dict] = []
    for template in ordered:
        cells = []
        for evaluation in evaluations:
            criterion = next(
                (c for c in evaluation.criteria
                 if c.criterion_key == template.criterion_key), None
            )
            if criterion is None:
                cells.append({
                    "candidate_id": evaluation.candidate_id,
                    "score": None,
                    "outcome": None,
                    "note": "Not scored for this candidate.",
                })
                continue
            cells.append({
                "candidate_id": evaluation.candidate_id,
                "score": round(criterion.raw_score, 2),
                "outcome": criterion.outcome.value,
                "confidence": round(criterion.confidence, 3),
                "evidence_count": criterion.evidence_count,
                "matched_terms": (criterion.matched_terms or [])[:6],
            })

        scores = [c["score"] for c in cells if c["score"] is not None]
        rows.append({
            "criterion_key": template.criterion_key,
            "label": template.label,
            "category": template.category.value,
            "requirement_type": template.requirement_type.value,
            "weight": template.weight,
            "cells": cells,
            # Who wins this criterion, and whether it is actually a
            # difference worth showing. A 2-point gap is noise.
            "spread": round(max(scores) - min(scores), 2) if len(scores) > 1 else 0.0,
            "is_differentiator": bool(len(scores) > 1 and (max(scores) - min(scores)) >= 20),
        })

    differentiators = [r for r in rows if r["is_differentiator"]]
    return {
        "rubric_version_id": evaluations[0].rubric_version_id,
        "candidates": candidates,
        "criteria": rows,
        # Highest-weight genuine differences first — what a hiring manager
        # should look at to tell these people apart.
        "key_differences": sorted(
            differentiators, key=lambda r: (-r["weight"], -r["spread"])
        )[:5],
        "summary": (
            f"Comparing {len(candidates)} candidates across {len(rows)} criteria; "
            f"{len(differentiators)} show a material difference."
        ),
    }


# ---------------------------------------------------------------------------
# What-if analysis
# ---------------------------------------------------------------------------

@dataclass
class WhatIfRow:
    candidate_id: str
    evaluation_id: str
    current_score: float
    projected_score: float
    current_rank: int = 0
    projected_rank: int = 0
    recommendation: str = ""
    eligibility_status: str = ""

    @property
    def score_change(self) -> float:
        return round(self.projected_score - self.current_score, 2)

    @property
    def rank_change(self) -> int:
        # Positive means moved up the list.
        return self.current_rank - self.projected_rank

    def to_dict(self) -> dict:
        return {
            "candidate_id": self.candidate_id,
            "evaluation_id": self.evaluation_id,
            "current_score": round(self.current_score, 2),
            "projected_score": round(self.projected_score, 2),
            "score_change": self.score_change,
            "current_rank": self.current_rank,
            "projected_rank": self.projected_rank,
            "rank_change": self.rank_change,
            "recommendation": self.recommendation,
            "eligibility_status": self.eligibility_status,
        }


def validate_weights(weights: dict[str, float], known_keys: set[str]) -> None:
    """
    A proposed weight set must reference real criteria and total 100 — the
    same invariant Phase B enforces on a real rubric. Previewing an
    unbalanced set would put the projected scores on an unknown scale, which
    is worse than refusing.
    """
    if not weights:
        raise AnalyticsError("Provide at least one criterion weight to preview.")

    unknown = sorted(set(weights) - known_keys)
    if unknown:
        raise AnalyticsError(
            "Some criterion keys are not in this rubric version.", errors=unknown
        )

    negative = sorted(k for k, v in weights.items() if v < 0)
    if negative:
        raise AnalyticsError("Weights cannot be negative.", errors=negative)

    total = sum(weights.values())
    if abs(total - 100.0) > WEIGHT_TOLERANCE:
        raise AnalyticsError(
            f"Proposed weights total {total:g}, not 100. Projected scores would "
            "be on a different scale from the approved ones and could not be "
            "compared.",
            errors=[f"weight_total={total:g}"],
        )


def what_if(evaluations, weights: dict[str, float]) -> dict:
    """
    Recompute the ranking under a proposed weight set.

    Pure arithmetic over stored `EvaluationCriterion.raw_score` values.
    Nothing is written, no evaluation is created, no rubric is touched, and
    no model is called — the per-criterion scores are immutable, so
    reweighting them is arithmetic.

    Candidates whose eligibility is DISQUALIFIED keep that status: a
    disqualification comes from a rule, not a weight, so no reweighting can
    make an ineligible candidate eligible. Showing otherwise would be the
    single most misleading thing this screen could do.
    """
    if not evaluations:
        raise AnalyticsError("There are no assessed candidates to preview.")

    known = {c.criterion_key for c in evaluations[0].criteria}
    validate_weights(weights, known)

    rows: list[WhatIfRow] = []
    for evaluation in evaluations:
        projected = 0.0
        for criterion in evaluation.criteria:
            weight = weights.get(criterion.criterion_key)
            if weight is None or criterion.max_score <= 0:
                continue
            projected += criterion.raw_score / criterion.max_score * weight
        rows.append(WhatIfRow(
            candidate_id=evaluation.candidate_id,
            evaluation_id=evaluation.id,
            current_score=evaluation.overall_score,
            projected_score=round(projected, 2),
            recommendation=evaluation.recommendation.value,
            eligibility_status=evaluation.eligibility_status.value,
        ))

    for rank, row in enumerate(
        sorted(rows, key=lambda r: -r.current_score), start=1
    ):
        row.current_rank = rank
    for rank, row in enumerate(
        sorted(rows, key=lambda r: -r.projected_score), start=1
    ):
        row.projected_rank = rank

    ordered = sorted(rows, key=lambda r: r.projected_rank)
    movers = [r for r in ordered if r.rank_change != 0]

    return {
        "persisted": False,
        "notice": (
            "This is a preview only. No approved result, rubric or ranking has "
            "been changed."
        ),
        "proposed_weights": weights,
        "candidates": [r.to_dict() for r in ordered],
        "movement": {
            "candidates_previewed": len(ordered),
            "positions_changed": len(movers),
            "biggest_riser": max(
                (r.to_dict() for r in movers), key=lambda r: r["rank_change"], default=None
            ),
            "biggest_faller": min(
                (r.to_dict() for r in movers), key=lambda r: r["rank_change"], default=None
            ),
            "statement": (
                f"{len(movers)} of {len(ordered)} candidates change position "
                "under these weights."
            ),
        },
        # Restated because it is the requirement, and because a screen that
        # looks like an editor invites the belief that it is one.
        "eligibility_note": (
            "Eligibility is decided by disqualification rules, not weights, so "
            "it is unchanged by this preview."
        ),
    }


# ---------------------------------------------------------------------------
# KPI aggregates
# ---------------------------------------------------------------------------

@dataclass
class EfficiencyAssumptions:
    """
    Inputs, not findings. Defaults come from web/DATA.md and are the
    client's own estimates; they are returned with every result so no
    derived figure appears without the assumption behind it.
    """
    manual_minutes_per_cv: float = DEFAULT_MANUAL_MINUTES_PER_CV
    assisted_minutes_per_cv: float = DEFAULT_ASSISTED_MINUTES_PER_CV
    hourly_rate: float = DEFAULT_HOURLY_RATE
    currency: str = DEFAULT_CURRENCY

    @property
    def minutes_saved_per_cv(self) -> float:
        return round(self.manual_minutes_per_cv - self.assisted_minutes_per_cv, 2)

    def to_dict(self) -> dict:
        return {
            "manual_minutes_per_cv": self.manual_minutes_per_cv,
            "assisted_minutes_per_cv": self.assisted_minutes_per_cv,
            "minutes_saved_per_cv": self.minutes_saved_per_cv,
            "hourly_rate": self.hourly_rate,
            "currency": self.currency,
            "note": (
                "These are configurable planning assumptions supplied with the "
                "engagement, not measurements taken by this system. Efficiency "
                "figures below are derived from them."
            ),
        }


def _pct(numerator: int, denominator: int) -> dict | None:
    """
    A percentage always carries its denominator — web/DATA.md forbids one
    without. Returns None rather than dividing by zero.
    """
    if denominator <= 0:
        return None
    return {
        "value": round(numerator / denominator * 100.0, 1),
        "of": denominator,
        "count": numerator,
        "statement": f"{numerator} of {denominator}",
    }


def kpis(
    *,
    jobs,
    evaluations,
    challenge_findings,
    override_count: int,
    campaign_count: int,
    assumptions: EfficiencyAssumptions | None = None,
) -> dict:
    """
    Assemble the HR KPI dashboard's six groups: workload, throughput,
    efficiency, quality, exceptions, outcomes.

    Every figure is either a raw count or a derivation with its denominator
    or assumption attached. Nothing is presented as a bare percentage.
    """
    assumptions = assumptions or EfficiencyAssumptions()

    total_files = len(jobs)
    completed = [j for j in jobs if j.status == JobStatus.COMPLETED]
    duplicates = [j for j in jobs if j.status == JobStatus.DUPLICATE]
    failed = [j for j in jobs if j.status == JobStatus.FAILED]
    flagged = [j for j in jobs if getattr(j, "requires_review", False)]

    assessed = [e for e in evaluations]
    scores = [e.overall_score for e in assessed]

    # Workload
    workload = {
        "campaigns": campaign_count,
        "cvs_received": total_files,
        "cvs_read": len(completed) + len(duplicates),
        "candidates_assessed": len(assessed),
        "files_held": len(failed),
    }

    # Throughput
    durations = [
        j.duration_ms for j in completed
        if getattr(j, "duration_ms", None)
    ]
    throughput = {
        "assessments_completed": len(assessed),
        "median_seconds_per_cv": (
            round(statistics.median(durations) / 1000.0, 2) if durations else None
        ),
        "processed_without_a_problem": _pct(
            len(completed) + len(duplicates), total_files
        ),
    }

    # Efficiency — derived, with assumptions attached
    cvs = len(completed) + len(duplicates)
    manual_hours = cvs * assumptions.manual_minutes_per_cv / 60.0
    assisted_hours = cvs * assumptions.assisted_minutes_per_cv / 60.0
    hours_returned = manual_hours - assisted_hours
    efficiency = {
        "assumptions": assumptions.to_dict(),
        "cvs_included": cvs,
        "manual_equivalent_hours": round(manual_hours, 1),
        "actual_recruiter_hours": round(assisted_hours, 1),
        "recruiter_hours_returned": round(hours_returned, 1),
        "screening_time_not_spent": {
            "amount": round(hours_returned * assumptions.hourly_rate, 2),
            "currency": assumptions.currency,
            "derivation": (
                f"{round(hours_returned, 1)} hours x "
                f"{assumptions.hourly_rate:.2f} {assumptions.currency}/hour"
            ),
        },
        "baseline": (
            f"Measured against {assumptions.manual_minutes_per_cv:g} minutes per CV "
            "of manual screening."
        ),
    }

    # Quality
    criteria_total = sum(len(e.criteria) for e in assessed)
    criteria_with_evidence = sum(
        1 for e in assessed for c in e.criteria if c.evidence_count > 0
    )
    scored_criteria = sum(
        1 for e in assessed for c in e.criteria if c.weight > 0 and c.raw_score > 0
    )
    scored_with_evidence = sum(
        1 for e in assessed for c in e.criteria
        if c.weight > 0 and c.raw_score > 0 and c.evidence_count > 0
    )
    high_findings = [
        f for f in challenge_findings if f.severity == ChallengeSeverity.HIGH
    ]
    low_confidence = [
        e for e in assessed if e.confidence_band == ConfidenceBand.LOW
    ]
    quality = {
        # The honest version of DATA.md's "evidence coverage 100%": the share
        # of criteria that earned a score and cite a CV line. Criteria scoring
        # zero have nothing to cite, so including them would flatter the number.
        "evidence_coverage": _pct(scored_with_evidence, scored_criteria),
        "criteria_cited": _pct(criteria_with_evidence, criteria_total),
        "assessments_the_reviewer_questioned": _pct(
            len({f.evaluation_id for f in high_findings if f.evaluation_id}),
            len(assessed),
        ),
        "low_confidence_assessments": _pct(len(low_confidence), len(assessed)),
        "assessments_the_team_overruled": _pct(override_count, len(assessed)),
    }

    # Exceptions
    reasons: dict[str, int] = {}
    for job in failed:
        code = job.error_code.value if job.error_code else "UNKNOWN"
        reasons[code] = reasons.get(code, 0) + 1
    # Screened, not held: a job that completed (or merged as a duplicate)
    # but still carries a flag — a scanned CV read with little confidence, a
    # CV with no name/contact — for a person to double-check, never a reason
    # it was excluded from screening. Kept separate from `by_reason` above,
    # which is only ever files that never got screened at all.
    screened_flags: dict[str, int] = {}
    for job in flagged:
        if job.status == JobStatus.FAILED:
            continue
        code = job.error_code.value if job.error_code else "FLAGGED"
        screened_flags[code] = screened_flags.get(code, 0) + 1
    exceptions = {
        "files_held": len(failed),
        "duplicates_found": len(duplicates),
        "flagged_for_review": len(flagged),
        "by_reason": reasons,
        "screened_by_reason": screened_flags,
        "retryable": sum(
            1 for j in failed if getattr(j, "max_attempts", 0) > 0
        ),
    }

    # Outcomes
    by_recommendation = {r.value: 0 for r in Recommendation}
    for evaluation in assessed:
        by_recommendation[evaluation.recommendation.value] += 1
    ineligible = sum(
        1 for e in assessed
        if e.eligibility_status == EligibilityStatus.DISQUALIFIED
    )
    review_required = sum(
        1 for e in assessed
        if e.eligibility_status == EligibilityStatus.REVIEW_REQUIRED
    )
    outcomes = {
        "by_recommendation": by_recommendation,
        "ineligible": ineligible,
        "eligibility_review_required": review_required,
        "score_distribution": (
            {
                "mean": round(statistics.fmean(scores), 2),
                "median": round(statistics.median(scores), 2),
                "lowest": round(min(scores), 2),
                "highest": round(max(scores), 2),
                "candidates_assessed": len(scores),
            }
            if len(scores) >= MIN_FOR_DISTRIBUTION else None
        ),
    }

    return {
        "workload": workload,
        "throughput": throughput,
        "efficiency": efficiency,
        "quality": quality,
        "exceptions": exceptions,
        "outcomes": outcomes,
        "disclaimer": (
            "These figures describe screening activity. AI recommends; a person "
            "decides."
        ),
    }
