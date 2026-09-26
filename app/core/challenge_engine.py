"""
Challenge Agent — deterministic review of a scoring run.

`app/agents/challenge_agent.py` already asked a model for one `risk_level`
and a flat issues list, and the answer was discarded. That shape cannot
satisfy the client's requirement, which names six specific checks and needs
them attached to the criterion they concern so a recruiter can act on them.

Every check here is structural: it compares scores, evidence counts, weights
and run distributions. None of them needs an LLM, and asking one whether its
own conclusion was supported would be close to worthless. Determinism also
means a finding is reproducible, which is the point of a challenge layer —
a client can be shown exactly why a concern was raised.

The hard rule: **this module never changes a score, an outcome, or an
eligibility verdict.** It reads finished evaluations and writes findings.
That separation is what keeps it a reviewer rather than a second scorer with
no rubric behind it.

The six checks, and what each one actually keys off:

  UNSUPPORTED_CONCLUSION   a model adjustment the evidence doesn't carry, or
                           a confirmed match with nothing cited. Detectable
                           only because Phase D kept `deterministic_score`
                           alongside `raw_score`.
  INCONSISTENT_SCORING     the same criterion scored very differently for
                           candidates whose evidence looks equivalent.
  MISSING_EVIDENCE         a weighted criterion earned credit with no cited
                           excerpt at all.
  WEAK_EVIDENCE            evidence exists but is thin, low-relevance, or
                           the criterion was marked `evidence_required` and
                           only adjacency was found.
  CONTRADICTION            the CV argues against a criterion, or the stated
                           experience contradicts the parsed timeline.
  WEIGHTING_ANOMALY        one criterion dominates the result, or mandatory
                           criteria carry less weight than preferred ones.
  OUTLIER_RECOMMENDATION   a recommendation far from the run's distribution,
                           or a strong recommendation on low confidence.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field

from app.db.models import (
    ChallengeCheck, ChallengeScope, ChallengeSeverity, ConfidenceBand,
    CriterionOutcome, EvaluationStatus, Recommendation, RequirementType,
)

ENGINE_VERSION = "phase-e-1.0.0"

# A model adjustment larger than this, on a criterion whose cited evidence
# did not change, is worth flagging. Phase D caps adjustments at 15 points.
UNSUPPORTED_ADJUSTMENT_POINTS = 8.0

# A criterion carrying at least this much weight is material enough that
# thin evidence on it matters.
MATERIAL_WEIGHT = 10.0

# One criterion holding more than this share of the total weight means the
# rubric is effectively a single-criterion test.
DOMINANT_WEIGHT_SHARE = 0.5

# Evidence relevance at or below this is an adjacency-only match.
WEAK_RELEVANCE = 0.6

# How far from the run's mean score a candidate must sit to be an outlier.
OUTLIER_SIGMA = 2.0

# Two candidates scoring at least this far apart on the same criterion, with
# comparable matched-term counts, is a consistency concern.
INCONSISTENT_SCORE_GAP = 40.0


@dataclass
class Finding:
    check: ChallengeCheck
    severity: ChallengeSeverity
    scope: ChallengeScope
    title: str
    detail: str
    recommendation: str = ""
    evaluation_id: str | None = None
    criterion_id: str | None = None
    criterion_key: str = ""
    observed: dict | None = None
    display_order: int = 0


@dataclass
class ChallengeReport:
    findings: list[Finding] = field(default_factory=list)

    @property
    def risk_level(self) -> ChallengeSeverity:
        """Highest severity present — kept for the legacy `risk_level` field."""
        order = [
            ChallengeSeverity.HIGH, ChallengeSeverity.MEDIUM,
            ChallengeSeverity.LOW, ChallengeSeverity.INFO,
        ]
        for severity in order:
            if any(f.severity == severity for f in self.findings):
                return severity
        return ChallengeSeverity.INFO

    def for_evaluation(self, evaluation_id: str) -> list[Finding]:
        return [f for f in self.findings if f.evaluation_id == evaluation_id]

    def counts_by_severity(self) -> dict[str, int]:
        counts = {s.value: 0 for s in ChallengeSeverity}
        for finding in self.findings:
            counts[finding.severity.value] += 1
        return counts


# ---------------------------------------------------------------------------
# Per-criterion checks
# ---------------------------------------------------------------------------

def _check_unsupported(evaluation, criterion) -> list[Finding]:
    findings: list[Finding] = []

    # A model adjustment that moved the score materially. The evidence the
    # model was shown is the same evidence the deterministic pass used, so a
    # large delta means the model reached further than the excerpts support.
    drift = criterion.raw_score - criterion.deterministic_score
    if criterion.llm_adjusted and abs(drift) >= UNSUPPORTED_ADJUSTMENT_POINTS:
        findings.append(Finding(
            check=ChallengeCheck.UNSUPPORTED_CONCLUSION,
            severity=ChallengeSeverity.HIGH if drift > 0 else ChallengeSeverity.MEDIUM,
            scope=ChallengeScope.CRITERION,
            title="Model adjustment moved this score materially",
            detail=(
                f"'{criterion.label[:120]}' was scored {criterion.deterministic_score:.0f} "
                f"from the CV evidence, then adjusted to {criterion.raw_score:.0f} "
                f"({drift:+.0f}). The adjustment was made from the same excerpts, so it "
                "adds no new evidence."
            ),
            recommendation="Read the cited excerpts and confirm the adjusted score is warranted.",
            evaluation_id=evaluation.id,
            criterion_id=criterion.id,
            criterion_key=criterion.criterion_key,
            observed={
                "deterministic_score": criterion.deterministic_score,
                "final_score": criterion.raw_score,
                "adjustment": round(drift, 2),
            },
        ))

    # A confirmed match has to point at something.
    if (
        criterion.outcome == CriterionOutcome.CONFIRMED_MATCH
        and criterion.evidence_count == 0
    ):
        findings.append(Finding(
            check=ChallengeCheck.UNSUPPORTED_CONCLUSION,
            severity=ChallengeSeverity.HIGH,
            scope=ChallengeScope.CRITERION,
            title="Confirmed match with nothing cited",
            detail=(
                f"'{criterion.label[:120]}' is recorded as a confirmed match but no CV "
                "excerpt is attached to it."
            ),
            recommendation="Treat this criterion as unverified until an excerpt is found.",
            evaluation_id=evaluation.id,
            criterion_id=criterion.id,
            criterion_key=criterion.criterion_key,
            observed={"outcome": criterion.outcome.value, "evidence_count": 0},
        ))
    return findings


def _check_evidence(evaluation, criterion) -> list[Finding]:
    findings: list[Finding] = []
    if criterion.weight <= 0:
        return findings

    earned_credit = criterion.raw_score > 0
    scored_outcomes = (
        CriterionOutcome.CONFIRMED_MATCH, CriterionOutcome.PARTIAL_MATCH,
    )

    if earned_credit and criterion.evidence_count == 0:
        findings.append(Finding(
            check=ChallengeCheck.MISSING_EVIDENCE,
            severity=(
                ChallengeSeverity.HIGH if criterion.weight >= MATERIAL_WEIGHT
                else ChallengeSeverity.MEDIUM
            ),
            scope=ChallengeScope.CRITERION,
            title="Score awarded with no cited excerpt",
            detail=(
                f"'{criterion.label[:120]}' scored {criterion.raw_score:.0f} and carries "
                f"{criterion.weight:.0f} of the 100 available weight, but no CV excerpt "
                "is attached."
            ),
            recommendation="Verify this against the CV before relying on the overall score.",
            evaluation_id=evaluation.id,
            criterion_id=criterion.id,
            criterion_key=criterion.criterion_key,
            observed={"score": criterion.raw_score, "weight": criterion.weight},
        ))
        return findings

    # Weak rather than missing: something was cited, but only adjacency, or
    # the scorer's own confidence is low on a criterion that matters.
    if (
        criterion.outcome in scored_outcomes
        and criterion.weight >= MATERIAL_WEIGHT
        and criterion.confidence_band == ConfidenceBand.LOW
    ):
        findings.append(Finding(
            check=ChallengeCheck.WEAK_EVIDENCE,
            severity=ChallengeSeverity.MEDIUM,
            scope=ChallengeScope.CRITERION,
            title="Material criterion rests on low-confidence evidence",
            detail=(
                f"'{criterion.label[:120]}' carries {criterion.weight:.0f} weight and "
                f"scored {criterion.raw_score:.0f}, but confidence in that judgement is "
                f"only {criterion.confidence:.0%}."
            ),
            recommendation="Ask the candidate to confirm this directly.",
            evaluation_id=evaluation.id,
            criterion_id=criterion.id,
            criterion_key=criterion.criterion_key,
            observed={
                "weight": criterion.weight,
                "confidence": round(criterion.confidence, 3),
            },
        ))

    # Credit earned purely by adjacency, where the rubric asked for evidence.
    equivalents = criterion.equivalent_terms or []
    adjacency_only = (
        earned_credit
        and not (criterion.matched_terms or [])
        and any("related" in str(entry) for entry in equivalents)
    )
    if adjacency_only:
        findings.append(Finding(
            check=ChallengeCheck.WEAK_EVIDENCE,
            severity=ChallengeSeverity.MEDIUM,
            scope=ChallengeScope.CRITERION,
            title="Credit given for a related skill, not the one asked for",
            detail=(
                f"'{criterion.label[:120]}' scored {criterion.raw_score:.0f} on the "
                f"strength of a related skill only ({', '.join(str(e) for e in equivalents[:3])}). "
                "The requirement itself is not evidenced."
            ),
            recommendation=(
                "Decide whether the related experience is acceptable for this role."
            ),
            evaluation_id=evaluation.id,
            criterion_id=criterion.id,
            criterion_key=criterion.criterion_key,
            observed={"equivalent_terms": [str(e) for e in equivalents[:5]]},
        ))
    return findings


def _check_contradiction(evaluation, criterion) -> list[Finding]:
    if criterion.outcome != CriterionOutcome.CONTRADICTORY_EVIDENCE:
        return []
    return [Finding(
        check=ChallengeCheck.CONTRADICTION,
        severity=(
            ChallengeSeverity.HIGH if criterion.requirement_type == RequirementType.MANDATORY
            else ChallengeSeverity.MEDIUM
        ),
        scope=ChallengeScope.CRITERION,
        title="The CV contradicts this requirement",
        detail=(
            f"'{criterion.label[:120]}' is contradicted by the CV rather than simply "
            "absent from it."
        ),
        recommendation="Read the cited excerpt; this may be a wording issue or a real gap.",
        evaluation_id=evaluation.id,
        criterion_id=criterion.id,
        criterion_key=criterion.criterion_key,
        observed={"outcome": criterion.outcome.value},
    )]


# ---------------------------------------------------------------------------
# Per-evaluation checks
# ---------------------------------------------------------------------------

_EXPERIENCE_SEVERITY = {
    "HIGH": ChallengeSeverity.HIGH,
    "MEDIUM": ChallengeSeverity.MEDIUM,
    "LOW": ChallengeSeverity.LOW,
}


def _check_evaluation(evaluation) -> list[Finding]:
    findings: list[Finding] = []

    # Experience contradictions the Phase D engine already found. Surfaced
    # here rather than re-derived, so the two never disagree.
    for entry in (evaluation.contradictions or []):
        findings.append(Finding(
            check=ChallengeCheck.CONTRADICTION,
            severity=_EXPERIENCE_SEVERITY.get(
                str(entry.get("severity", "LOW")).upper(), ChallengeSeverity.LOW
            ),
            scope=ChallengeScope.EVALUATION,
            title="Inconsistency in the stated work history",
            detail=str(entry.get("detail", ""))[:1000],
            recommendation="Confirm the dates and duration with the candidate.",
            evaluation_id=evaluation.id,
            observed={"type": entry.get("type")},
        ))

    # A strong recommendation the confidence does not support.
    if (
        evaluation.recommendation == Recommendation.STRONG_FIT
        and evaluation.confidence_band != ConfidenceBand.HIGH
    ):
        findings.append(Finding(
            check=ChallengeCheck.OUTLIER_RECOMMENDATION,
            severity=ChallengeSeverity.MEDIUM,
            scope=ChallengeScope.EVALUATION,
            title="Strong recommendation on less than high confidence",
            detail=(
                f"Recorded as a strong fit at {evaluation.overall_score:.1f} of 100, but "
                f"overall confidence is {evaluation.overall_confidence:.0%}."
            ),
            recommendation="Review the evidence before shortlisting on this basis.",
            evaluation_id=evaluation.id,
            observed={
                "overall_score": evaluation.overall_score,
                "confidence": round(evaluation.overall_confidence, 3),
            },
        ))

    # A high overall score carried by preferred criteria while the mandatory
    # ones lag. The weighting makes this possible and it is easy to miss.
    if (
        evaluation.overall_score >= 70
        and evaluation.mandatory_score > 0
        and evaluation.mandatory_score < evaluation.overall_score - 20
    ):
        findings.append(Finding(
            check=ChallengeCheck.UNSUPPORTED_CONCLUSION,
            severity=ChallengeSeverity.HIGH,
            scope=ChallengeScope.EVALUATION,
            title="Overall score is carried by preferred criteria",
            detail=(
                f"Overall {evaluation.overall_score:.1f} of 100 but only "
                f"{evaluation.mandatory_score:.1f} on the mandatory criteria. The "
                "ranking position overstates how well the essential requirements are met."
            ),
            recommendation="Judge this candidate on the mandatory criteria first.",
            evaluation_id=evaluation.id,
            observed={
                "overall_score": evaluation.overall_score,
                "mandatory_score": evaluation.mandatory_score,
            },
        ))
    return findings


# ---------------------------------------------------------------------------
# Rubric and run-level checks
# ---------------------------------------------------------------------------

def _check_weighting(run_id: str, criteria_sample) -> list[Finding]:
    """
    Weighting anomalies are a property of the rubric, not of a candidate, so
    they attach to the run. Any evaluation's criteria list describes the same
    rubric version, so one sample is enough.
    """
    findings: list[Finding] = []
    active = [c for c in criteria_sample if c.weight > 0]
    if not active:
        return findings

    total = sum(c.weight for c in active)
    if total <= 0:
        return findings

    heaviest = max(active, key=lambda c: c.weight)
    share = heaviest.weight / total
    if share > DOMINANT_WEIGHT_SHARE:
        findings.append(Finding(
            check=ChallengeCheck.WEIGHTING_ANOMALY,
            severity=ChallengeSeverity.MEDIUM,
            scope=ChallengeScope.RUN,
            title="One criterion dominates the score",
            detail=(
                f"'{heaviest.label[:120]}' carries {heaviest.weight:.0f} of "
                f"{total:.0f} weight ({share:.0%}). The ranking is close to a single-"
                "criterion sort."
            ),
            recommendation="Confirm this weighting is intended before acting on the ranking.",
            criterion_key=heaviest.criterion_key,
            observed={"criterion_weight": heaviest.weight, "total_weight": total,
                      "share": round(share, 3)},
        ))

    mandatory = sum(
        c.weight for c in active if c.requirement_type == RequirementType.MANDATORY
    )
    preferred = sum(
        c.weight for c in active if c.requirement_type == RequirementType.PREFERRED
    )
    if preferred > mandatory and mandatory > 0:
        findings.append(Finding(
            check=ChallengeCheck.WEIGHTING_ANOMALY,
            severity=ChallengeSeverity.HIGH,
            scope=ChallengeScope.RUN,
            title="Preferred criteria outweigh mandatory ones",
            detail=(
                f"Mandatory criteria carry {mandatory:.0f} weight against "
                f"{preferred:.0f} for preferred criteria. A candidate can rank highly "
                "while meeting the essentials poorly."
            ),
            recommendation="Reweight the rubric, or read mandatory scores separately.",
            observed={"mandatory_weight": mandatory, "preferred_weight": preferred},
        ))

    unweighted_mandatory = [
        c for c in criteria_sample
        if c.requirement_type == RequirementType.MANDATORY and c.weight <= 0
    ]
    if unweighted_mandatory:
        findings.append(Finding(
            check=ChallengeCheck.WEIGHTING_ANOMALY,
            severity=ChallengeSeverity.MEDIUM,
            scope=ChallengeScope.RUN,
            title="Mandatory criteria carry no weight",
            detail=(
                f"{len(unweighted_mandatory)} criterion/criteria marked mandatory have "
                "zero weight, so they do not affect the score at all: "
                + ", ".join(c.label[:60] for c in unweighted_mandatory[:3])
            ),
            recommendation=(
                "Either give them weight or enforce them as disqualification rules."
            ),
            observed={"count": len(unweighted_mandatory)},
        ))
    return findings


def _check_outliers(evaluations) -> list[Finding]:
    """Scores far from the run's distribution."""
    findings: list[Finding] = []
    scored = [e for e in evaluations if e.status == EvaluationStatus.COMPLETED]
    if len(scored) < 4:
        # A handful of candidates has no meaningful distribution, and
        # claiming one would be false precision.
        return findings

    values = [e.overall_score for e in scored]
    mean = statistics.fmean(values)
    try:
        deviation = statistics.stdev(values)
    except statistics.StatisticsError:
        return findings
    if deviation < 1e-6:
        return findings

    for evaluation in scored:
        sigma = (evaluation.overall_score - mean) / deviation
        if abs(sigma) < OUTLIER_SIGMA:
            continue
        high = sigma > 0
        findings.append(Finding(
            check=ChallengeCheck.OUTLIER_RECOMMENDATION,
            severity=ChallengeSeverity.LOW,
            scope=ChallengeScope.EVALUATION,
            title=(
                "Unusually high score for this campaign" if high
                else "Unusually low score for this campaign"
            ),
            detail=(
                f"Scored {evaluation.overall_score:.1f} against a run mean of "
                f"{mean:.1f} across {len(scored)} assessed candidates. "
                + ("Worth confirming the evidence supports it."
                   if high else "Worth confirming the CV was read correctly.")
            ),
            recommendation="Spot-check this assessment against the CV.",
            evaluation_id=evaluation.id,
            observed={
                "overall_score": evaluation.overall_score,
                "run_mean": round(mean, 2),
                "candidates_assessed": len(scored),
            },
        ))
    return findings


def _check_consistency(evaluations) -> list[Finding]:
    """
    The same criterion scored very differently for candidates whose evidence
    looks comparable. Compared on matched-term count rather than on the
    excerpt text: two candidates with the same number of confirmed terms on
    one criterion should not be 40 points apart on it.
    """
    findings: list[Finding] = []
    scored = [e for e in evaluations if e.status == EvaluationStatus.COMPLETED]
    if len(scored) < 2:
        return findings

    by_key: dict[str, list[tuple]] = {}
    for evaluation in scored:
        for criterion in evaluation.criteria:
            if criterion.weight <= 0:
                continue
            by_key.setdefault(criterion.criterion_key, []).append(
                (evaluation, criterion, len(criterion.matched_terms or []))
            )

    for key, entries in by_key.items():
        # Group by matched-term count: comparable evidence.
        buckets: dict[int, list[tuple]] = {}
        for entry in entries:
            buckets.setdefault(entry[2], []).append(entry)

        for term_count, bucket in buckets.items():
            if len(bucket) < 2:
                continue
            scores = [c.raw_score for _, c, _ in bucket]
            gap = max(scores) - min(scores)
            if gap < INCONSISTENT_SCORE_GAP:
                continue
            lowest = min(bucket, key=lambda e: e[1].raw_score)
            highest = max(bucket, key=lambda e: e[1].raw_score)
            findings.append(Finding(
                check=ChallengeCheck.INCONSISTENT_SCORING,
                severity=ChallengeSeverity.MEDIUM,
                scope=ChallengeScope.CRITERION,
                title="Comparable evidence scored inconsistently",
                detail=(
                    f"On '{highest[1].label[:100]}', two candidates each with "
                    f"{term_count} matched term(s) scored "
                    f"{highest[1].raw_score:.0f} and {lowest[1].raw_score:.0f} — "
                    f"a {gap:.0f}-point gap."
                ),
                recommendation="Compare the two CVs on this criterion directly.",
                evaluation_id=lowest[0].id,
                criterion_id=lowest[1].id,
                criterion_key=key,
                observed={
                    "matched_term_count": term_count,
                    "score_gap": round(gap, 2),
                    "higher_score": highest[1].raw_score,
                    "lower_score": lowest[1].raw_score,
                },
            ))
    return findings


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def review(evaluations) -> ChallengeReport:
    """
    Review a run's evaluations and return findings. Pure: reads the rows,
    changes nothing.
    """
    report = ChallengeReport()
    completed = [e for e in evaluations if e.status == EvaluationStatus.COMPLETED]

    for evaluation in completed:
        for criterion in evaluation.criteria:
            report.findings.extend(_check_unsupported(evaluation, criterion))
            report.findings.extend(_check_evidence(evaluation, criterion))
            report.findings.extend(_check_contradiction(evaluation, criterion))
        report.findings.extend(_check_evaluation(evaluation))

    if completed:
        report.findings.extend(
            _check_weighting(completed[0].run_id, completed[0].criteria)
        )
    report.findings.extend(_check_outliers(completed))
    report.findings.extend(_check_consistency(completed))

    # Stable ordering: worst first, so the UI's first row is the one that
    # matters most.
    severity_rank = {
        ChallengeSeverity.HIGH: 0, ChallengeSeverity.MEDIUM: 1,
        ChallengeSeverity.LOW: 2, ChallengeSeverity.INFO: 3,
    }
    report.findings.sort(
        key=lambda f: (severity_rank[f.severity], f.check.value, f.criterion_key)
    )
    for order, finding in enumerate(report.findings):
        finding.display_order = order
    return report
