"""
Evaluation orchestration.

This is the service that finally connects Phase B to scoring. An
`EvaluationRun` pins a rubric version, walks the campaign's candidates,
scores each one criterion by criterion against `rubric_weights`, applies the
deterministic eligibility engine, and writes immutable results.

Immutability, concretely: nothing here ever updates an `Evaluation`'s score,
outcome, evidence or findings after commit. Re-scoring a candidate creates a
new run and new rows, and the previous evaluation is marked `is_current =
False` with `superseded_by_evaluation_id` set. Both are then readable
forever, which is what lets a client ask "what did we decide in March, and
against which rubric?" and get an answer.

Ordering inside one candidate's evaluation matters and is deliberate:

    1. build the evidence index from the retained document
    2. parse the experience timeline
    3. score every criterion deterministically
    4. optionally let the model adjust criterion scores within a bounded band
    5. run the eligibility engine on the *final* criterion scores
    6. aggregate

The eligibility engine runs last so that `MIN_CRITERION_SCORE` rules see the
score that will actually be reported. It still cannot be influenced by the
model in any other way: it reads structured facts, and a `HARD_FAIL` verdict
is not something a high AI score can overturn.
"""
from __future__ import annotations

import logging
import secrets
import time
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import (
    candidate_360, challenge_engine, criterion_scorer, document_quality,
    eligibility_engine, evidence_index, experience_engine, llm_usage,
)
from app.core.criterion_scorer import band_for
from app.db.models import (
    AuditAction, Campaign, CampaignStatus, Candidate, CandidateDocument, ChallengeFinding,
    ChallengeSeverity, ConfidenceBand,
    CriterionOutcome, EligibilityFinding, EligibilityStatus, Evaluation,
    EvaluationCriterion, EvaluationEvidence, EvaluationRun, EvaluationStatus,
    JobStatus, ProcessingBatch, ProcessingJob, Recommendation, RequirementType,
    Rubric, RubricVersion, RunStatus, RunTrigger, ScoringMode,
)
from app.services import disposition_service, rubric_service

logger = logging.getLogger(__name__)

# Same shape and same collision-checked generation as
# campaign_service._next_short_id (RC + creation date + a random number) —
# "assessment run cdc651b4" was a raw UUID fragment with no meaning at all;
# this makes it as readable as a campaign's own short id.
_RUN_SHORT_ID_PREFIX = "RC"
_RUN_SHORT_ID_RANDOM_DIGITS = 5
_RUN_SHORT_ID_MAX_ATTEMPTS = 50


def _next_run_short_id(db: Session) -> str:
    date_part = datetime.now(timezone.utc).strftime("%Y%m%d")
    ceiling = 10 ** _RUN_SHORT_ID_RANDOM_DIGITS
    for _ in range(_RUN_SHORT_ID_MAX_ATTEMPTS):
        candidate = (
            f"{_RUN_SHORT_ID_PREFIX}{date_part}-"
            f"{secrets.randbelow(ceiling):0{_RUN_SHORT_ID_RANDOM_DIGITS}d}"
        )
        taken = db.scalar(select(EvaluationRun.short_id).where(EvaluationRun.short_id == candidate))
        if taken is None:
            return candidate
    raise RuntimeError("Could not generate a unique assessment run short id.")

# Stamped on every run and evaluation. Bump this whenever scoring logic
# changes in a way that would move scores, so historical results stay
# attributable to the logic that produced them.
ENGINE_VERSION = "phase-d-1.0.0"

# Recommendation bands over the 0-100 overall score.
STRONG_FIT_SCORE = 75.0
POTENTIAL_FIT_SCORE = 55.0
NOT_RECOMMENDED_SCORE = 35.0

# A mandatory-criteria score below this cannot be a Strong Fit however well
# the preferred criteria scored — the weighting would otherwise let a
# candidate coast in on nice-to-haves.
STRONG_FIT_MANDATORY_FLOOR = 70.0

# Below this overall confidence, no automatic recommendation is made at all.
# The client's first requirement is that AI output is never presented as an
# autonomous decision; a low-confidence recommendation is exactly the kind
# of thing that gets acted on as though it were one.
MIN_CONFIDENCE_FOR_RECOMMENDATION = 0.45


class EvaluationError(Exception):
    """Raised for caller-fixable problems; the API maps this to 4xx."""

    def __init__(self, message: str, errors: list[str] | None = None):
        super().__init__(message)
        self.message = message
        self.errors = errors or []


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    """Same fix as processing_service._aware — SQLite returns naive datetimes."""
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Resolution helpers
# ---------------------------------------------------------------------------

def _require_campaign(db: Session, campaign_id: str) -> Campaign:
    campaign = db.get(Campaign, campaign_id)
    if campaign is None:
        raise EvaluationError(f"Campaign '{campaign_id}' does not exist.")
    return campaign


def resolve_rubric_version(
    db: Session,
    campaign_id: str,
    *,
    batch: ProcessingBatch | None = None,
    rubric_version_id: str | None = None,
) -> RubricVersion:
    """
    Decide which rubric version a run scores against.

    Precedence: an explicit id, then the batch's pinned version, then the
    campaign's active version. The batch's pin wins over "whatever is
    approved now" on purpose — a batch uploaded under v1 is scored under v1
    unless someone explicitly asks for a re-evaluation under v2.
    """
    if rubric_version_id:
        version = db.get(RubricVersion, rubric_version_id)
        if version is None:
            raise EvaluationError(f"Rubric version '{rubric_version_id}' does not exist.")
    elif batch is not None and batch.rubric_version_id:
        version = db.get(RubricVersion, batch.rubric_version_id)
        if version is None:
            raise EvaluationError(
                f"Batch '{batch.id}' pins rubric version '{batch.rubric_version_id}', "
                "which no longer exists."
            )
    else:
        version = rubric_service.get_active_version(db, campaign_id)
        if version is None:
            raise EvaluationError(
                "This campaign has no approved rubric version. Approve a rubric "
                "before evaluating candidates."
            )

    # Confirm the version belongs to this campaign — an id from another
    # campaign would otherwise silently score against the wrong rubric.
    rubric = db.get(Rubric, version.rubric_id)
    if rubric is None or rubric.campaign_id != campaign_id:
        raise EvaluationError(
            f"Rubric version {version.version_number} does not belong to campaign "
            f"'{campaign_id}'."
        )

    if not version.is_usable_for_evaluation:
        raise EvaluationError(
            f"Rubric version {version.version_number} is {version.status.value}. "
            "Only APPROVED or LOCKED versions can be used for evaluation."
        )

    active_weights = [w for w in version.weights if w.active]
    if not active_weights:
        raise EvaluationError(
            f"Rubric version {version.version_number} has no active criteria to score."
        )
    if not version.is_balanced:
        # Should be unreachable: Phase B refuses to approve an unbalanced
        # version. Checked anyway, because an out-of-100 denominator would
        # silently distort every score in the run.
        raise EvaluationError(
            f"Rubric version {version.version_number} has active weights summing to "
            f"{version.weight_total}, not 100. Scores would be meaningless.",
            errors=[f"weight_total={version.weight_total}"],
        )
    return version


def _candidates_for_batch(db: Session, batch_id: str) -> list[str]:
    """
    Candidates from a batch: the jobs that produced usable documents.

    DUPLICATE jobs are included via their `candidate_id` — a duplicate
    attaches its document to an existing candidate, who still needs scoring.
    FAILED jobs have no candidate and are skipped; they are already visible
    as exceptions in the Control Tower.
    """
    rows = db.scalars(
        select(ProcessingJob.candidate_id)
        .where(
            ProcessingJob.batch_id == batch_id,
            ProcessingJob.candidate_id.is_not(None),
            ProcessingJob.status.in_([JobStatus.COMPLETED, JobStatus.DUPLICATE]),
        )
    ).all()
    seen: list[str] = []
    for candidate_id in rows:
        if candidate_id and candidate_id not in seen:
            seen.append(candidate_id)
    return seen


def _latest_document(db: Session, candidate_id: str) -> CandidateDocument | None:
    """
    The document to score. The most recent one wins: an updated CV supersedes
    the original, and scoring the older file would report stale findings.
    """
    return db.scalars(
        select(CandidateDocument)
        .where(
            CandidateDocument.candidate_id == candidate_id,
            CandidateDocument.text_char_count > 0,
        )
        .order_by(CandidateDocument.created_at.desc())
    ).first()


def current_evaluation(db: Session, candidate_id: str) -> Evaluation | None:
    return db.scalars(
        select(Evaluation)
        .where(Evaluation.candidate_id == candidate_id, Evaluation.is_current.is_(True))
        .order_by(Evaluation.created_at.desc())
    ).first()


def ranked_evaluations(
    db: Session, campaign_id: str, *, include_ineligible: bool = False,
    limit: int | None = None,
) -> list[Evaluation]:
    """
    The campaign's current, completed evaluations in leaderboard order.

    The one place this ordering is defined — the leaderboard API and B15's
    rank-at-decision-time snapshot both read it from here, so neither can
    drift from the other.
    """
    statement = select(Evaluation).where(
        Evaluation.campaign_id == campaign_id,
        Evaluation.is_current.is_(True),
        Evaluation.status == EvaluationStatus.COMPLETED,
    )
    if not include_ineligible:
        statement = statement.where(
            Evaluation.eligibility_status != EligibilityStatus.DISQUALIFIED
        )
    statement = statement.order_by(Evaluation.overall_score.desc(), Evaluation.created_at)
    if limit is not None:
        statement = statement.limit(limit)
    return list(db.scalars(statement).all())


def rank_of(
    db: Session, campaign_id: str, candidate_id: str, *, include_ineligible: bool = True,
) -> int | None:
    """
    Where this candidate sits on the leaderboard right now, 1-based.

    `include_ineligible` defaults to True here (unlike the leaderboard
    itself): B15 wants a rank recorded for whoever a recruiter waitlists,
    even one the leaderboard hides by default. None means not currently
    evaluated at all, not "last place".
    """
    for position, evaluation in enumerate(
        ranked_evaluations(db, campaign_id, include_ineligible=include_ineligible), start=1,
    ):
        if evaluation.candidate_id == candidate_id:
            return position
    return None


# ---------------------------------------------------------------------------
# Run creation
# ---------------------------------------------------------------------------

def create_run(
    db: Session,
    campaign_id: str,
    *,
    batch_id: str | None = None,
    rubric_version_id: str | None = None,
    candidate_ids: list[str] | None = None,
    trigger: RunTrigger = RunTrigger.MANUAL,
    scoring_mode: ScoringMode = ScoringMode.DETERMINISTIC,
    only_unevaluated: bool = False,
    created_by: str = "",
    notes: str = "",
) -> EvaluationRun:
    """
    Create a run and select its candidate set. Nothing is scored yet — call
    `execute_run` for that, so a caller can create a run in a request and
    drain it on a worker.
    """
    _require_campaign(db, campaign_id)

    batch = None
    if batch_id:
        batch = db.get(ProcessingBatch, batch_id)
        if batch is None:
            raise EvaluationError(f"Batch '{batch_id}' does not exist.")
        if batch.campaign_id != campaign_id:
            raise EvaluationError(f"Batch '{batch_id}' belongs to a different campaign.")

    version = resolve_rubric_version(
        db, campaign_id, batch=batch, rubric_version_id=rubric_version_id
    )

    if candidate_ids:
        selected = list(dict.fromkeys(candidate_ids))
        known = set(db.scalars(
            select(Candidate.id).where(
                Candidate.campaign_id == campaign_id, Candidate.id.in_(selected)
            )
        ).all())
        unknown = [c for c in selected if c not in known]
        if unknown:
            raise EvaluationError(
                "Some candidate ids are not in this campaign.", errors=unknown
            )
    elif batch is not None:
        selected = _candidates_for_batch(db, batch.id)
    else:
        selected = list(db.scalars(
            select(Candidate.id)
            .where(Candidate.campaign_id == campaign_id)
            .order_by(Candidate.created_at)
        ).all())

    if only_unevaluated:
        selected = [
            candidate_id for candidate_id in selected
            if _needs_evaluation(db, candidate_id, version.id)
        ]

    run = EvaluationRun(
        short_id=_next_run_short_id(db),
        campaign_id=campaign_id,
        rubric_version_id=version.id,
        batch_id=batch.id if batch else None,
        trigger=trigger,
        scoring_mode=scoring_mode,
        engine_version=ENGINE_VERSION,
        status=RunStatus.PENDING,
        total_candidates=len(selected),
        created_by=created_by,
        notes=notes,
    )
    db.add(run)
    db.flush()

    # The selection is materialised as SKIPPED evaluation placeholders only
    # when it is empty, so an empty run is still explicable rather than
    # looking like a bug.
    if not selected:
        run.status = RunStatus.COMPLETED
        run.started_at = run.completed_at = _now()
        run.notes = (run.notes + " No candidates matched this run's selection.").strip()
        db.flush()

    run._selected_candidate_ids = selected  # type: ignore[attr-defined]
    return run


def _needs_evaluation(db: Session, candidate_id: str, rubric_version_id: str) -> bool:
    """True when this candidate has no current evaluation under this version."""
    existing = current_evaluation(db, candidate_id)
    return existing is None or existing.rubric_version_id != rubric_version_id


def selected_candidate_ids(db: Session, run: EvaluationRun) -> list[str]:
    """
    Recover a run's candidate set.

    `create_run` stashes it on the instance for the common
    create-then-execute-in-one-request path. A run picked up later by a
    worker won't have that, so it is recomputed from the run's own
    parameters, which is why they are all persisted.
    """
    stashed = getattr(run, "_selected_candidate_ids", None)
    if stashed is not None:
        return stashed
    if run.batch_id:
        return _candidates_for_batch(db, run.batch_id)
    return list(db.scalars(
        select(Candidate.id)
        .where(Candidate.campaign_id == run.campaign_id)
        .order_by(Candidate.created_at)
    ).all())


# ---------------------------------------------------------------------------
# Scoring one candidate
# ---------------------------------------------------------------------------

def _campaign_terms(weights) -> list[str]:
    """
    The union of terms across the rubric's criteria — used to decide which
    employment history is *relevant* rather than merely present.
    """
    from app.core import skill_taxonomy
    terms: list[str] = []
    for weight in weights:
        for term in skill_taxonomy.extract_terms(weight.label, limit=6):
            if term not in terms:
                terms.append(term)
    return terms


def _aggregate(results, profile, index, eligibility, document=None) -> dict:
    """
    Roll criterion results into the candidate-level numbers.

    Overall score is the sum of weighted contributions. Because Phase B
    guarantees active weights sum to 100 and each contribution is
    `(raw/max) * weight`, the total is already on a 0-100 scale — there is no
    second normalisation, which is where double-scaling bugs come from.
    """
    scored = [r for r in results if r.weight > 0]
    overall = round(sum(r.weighted_score for r in scored), 2)

    def _subset_score(predicate) -> float:
        subset = [r for r in scored if predicate(r)]
        total_weight = sum(r.weight for r in subset)
        if total_weight <= 0:
            return 0.0
        return round(
            sum(r.weighted_score for r in subset) / total_weight * 100.0, 2
        )

    mandatory = _subset_score(lambda r: r.requirement_type == RequirementType.MANDATORY)
    preferred = _subset_score(lambda r: r.requirement_type == RequirementType.PREFERRED)

    # Confidence is weighted by the criteria's own weights: being unsure
    # about a 30-point criterion matters more than about a 2-point one.
    weight_total = sum(r.weight for r in scored)
    if weight_total > 0:
        confidence = sum(r.confidence * r.weight for r in scored) / weight_total
    elif results:
        confidence = sum(r.confidence for r in results) / len(results)
    else:
        confidence = 0.0

    # Extraction quality caps confidence. A perfect-looking score off a
    # 300-character CV is not a confident result.
    richness = criterion_scorer._richness(getattr(index, "text", ""))
    confidence = min(confidence, 0.35 + 0.65 * richness)

    # So does an unparseable timeline, when experience is being scored.
    if any(r.category.value == "EXPERIENCE" for r in scored) and profile is not None:
        if not getattr(profile, "timeline_found", False):
            confidence = min(confidence, 0.5)

    # And so does an indeterminate eligibility check — an unverified
    # mandatory requirement is a hole in the evidence, not a detail.
    if eligibility.review_items:
        confidence = min(confidence, 0.7)

    # And so does text recovered from images. The score is untouched: what
    # is in doubt is how well we read the CV, not how good the candidate is.
    ceiling = document_quality.confidence_ceiling(document)
    if ceiling is not None:
        confidence = min(confidence, ceiling)

    return {
        "overall_score": overall,
        "mandatory_score": mandatory,
        "preferred_score": preferred,
        "overall_confidence": round(max(0.0, min(1.0, confidence)), 3),
    }


def _recommend(
    overall_score: float,
    mandatory_score: float,
    confidence: float,
    eligibility: eligibility_engine.EligibilityOutcome,
) -> Recommendation:
    """
    Map the numbers onto the client's four bands.

    Eligibility dominates. A disqualified candidate is Not Recommended
    whatever they scored, and an indeterminate check forces Review Required —
    the system does not get to guess its way past a mandatory requirement it
    could not verify.
    """
    if eligibility.status == EligibilityStatus.DISQUALIFIED:
        return Recommendation.NOT_RECOMMENDED
    if eligibility.status == EligibilityStatus.REVIEW_REQUIRED:
        return Recommendation.REVIEW_REQUIRED
    if confidence < MIN_CONFIDENCE_FOR_RECOMMENDATION:
        return Recommendation.REVIEW_REQUIRED

    if overall_score >= STRONG_FIT_SCORE and mandatory_score >= STRONG_FIT_MANDATORY_FLOOR:
        return Recommendation.STRONG_FIT
    if overall_score >= POTENTIAL_FIT_SCORE:
        return Recommendation.POTENTIAL_FIT
    if overall_score < NOT_RECOMMENDED_SCORE:
        return Recommendation.NOT_RECOMMENDED
    return Recommendation.REVIEW_REQUIRED


def _narrative(candidate, results, aggregate, eligibility, profile) -> str:
    """
    A short factual summary. Deliberately assembled from the numbers rather
    than generated: it must never read as a hiring decision, and it must say
    the same thing the structured fields say.
    """
    name = (getattr(candidate, "full_name", "") or "This candidate").strip()
    # Informational requirements are seeded as zero-weight criteria so they
    # still display (see rubric_service.seed_from_requirements) but were
    # never meant to be scored — counting them in "confirmed on X of Y"
    # inflates Y with criteria nobody is being judged against. Scope the
    # count to what was actually scored, same as _aggregate() above.
    scored_results = [r for r in results if r.weight > 0]
    confirmed = [r for r in scored_results if r.outcome == CriterionOutcome.CONFIRMED_MATCH]
    missing = [r for r in scored_results if r.outcome == CriterionOutcome.NOT_DEMONSTRATED]

    parts = [
        f"{name} scores {aggregate['overall_score']:.1f} of 100 against this rubric "
        f"({aggregate['mandatory_score']:.1f} on mandatory criteria), with "
        f"{aggregate['overall_confidence']:.0%} confidence."
    ]
    if confirmed:
        parts.append(
            f"Confirmed on {len(confirmed)} of {len(scored_results)} scored criteria, "
            f"including {', '.join(r.label[:60] for r in confirmed[:3])}."
        )
    if missing:
        parts.append(
            f"Not demonstrated: {', '.join(r.label[:60] for r in missing[:3])}."
        )
    if eligibility.status == EligibilityStatus.DISQUALIFIED:
        parts.append(
            "Ineligible against the campaign's mandatory rules: "
            + " ".join(f.message for f in eligibility.hard_failures[:2])
        )
    elif eligibility.review_items:
        parts.append(
            f"{len(eligibility.review_items)} eligibility check(s) could not be "
            "confirmed from the CV and need recruiter verification."
        )
    if profile is not None and getattr(profile, "contradictions", None):
        parts.append(
            f"{len(profile.contradictions)} inconsistency/ies found in the stated "
            "experience history."
        )
    parts.append(
        "This is a decision-support summary, not a hiring decision."
    )
    return " ".join(parts)


def _missing_information(index, profile, results) -> list[str]:
    """What the CV does not tell us — the client asks for this explicitly."""
    items: list[str] = []
    if index is None or not getattr(index, "text", ""):
        return ["No readable CV text was available for this candidate."]

    for section, label in (
        ("EXPERIENCE", "employment history"),
        ("EDUCATION", "education"),
        ("SKILLS", "a skills summary"),
    ):
        if not index.has_section(section):
            items.append(f"The CV has no identifiable {label} section.")

    if profile is not None and not getattr(profile, "timeline_found", False):
        items.append(
            "No dated employment history could be parsed, so years of experience "
            "could not be verified."
        )
    if profile is not None and getattr(profile, "gaps", None):
        for gap in profile.gaps:
            if gap.months >= 6:
                items.append(
                    f"An unexplained {gap.months}-month gap between "
                    f"{gap.start.isoformat()} and {gap.end.isoformat()}."
                )

    insufficient = [
        r for r in results
        if r.outcome == CriterionOutcome.INSUFFICIENT_EVIDENCE and r.weight > 0
    ]
    for result in insufficient[:5]:
        items.append(f"Insufficient evidence to assess: {result.label[:100]}")
    return items


def evaluate_candidate(
    db: Session,
    run: EvaluationRun,
    candidate: Candidate,
    version: RubricVersion,
    *,
    campaign: Campaign | None = None,
    campaign_terms: list[str] | None = None,
) -> Evaluation:
    """
    Score one candidate and persist an immutable Evaluation.

    Always returns an Evaluation row, including on failure — a candidate that
    could not be scored has to be visible as such, not absent from the run.
    """
    started = _now()
    weights = [w for w in version.weights if w.active]
    rules = [r for r in version.disqualification_rules if r.active]
    campaign = campaign or db.get(Campaign, run.campaign_id)

    evaluation = Evaluation(
        run_id=run.id,
        campaign_id=run.campaign_id,
        candidate_id=candidate.id,
        rubric_version_id=version.id,
        scoring_mode=run.scoring_mode,
        engine_version=ENGINE_VERSION,
    )

    document = _latest_document(db, candidate.id)
    if document is None:
        evaluation.status = EvaluationStatus.SKIPPED
        evaluation.error_message = (
            "No document with extracted text is attached to this candidate, so "
            "there is nothing to score."
        )
        evaluation.eligibility_status = EligibilityStatus.REVIEW_REQUIRED
        evaluation.recommendation = Recommendation.REVIEW_REQUIRED
        evaluation.confidence_band = ConfidenceBand.LOW
        evaluation.missing_information = [evaluation.error_message]
        evaluation.duration_ms = int((_now() - started).total_seconds() * 1000)
        db.add(evaluation)
        db.flush()
        return evaluation

    evaluation.document_id = document.id

    try:
        index = evidence_index.build_index(document)
        terms = campaign_terms if campaign_terms is not None else _campaign_terms(weights)
        profile = experience_engine.analyse(index, campaign_terms=terms)

        results = [
            criterion_scorer.score_criterion(weight, index, profile, order=order)
            for order, weight in enumerate(weights)
        ]
        # Carry requirement_type through for the mandatory/preferred split.
        for result, weight in zip(results, weights):
            result.requirement_type = weight.requirement_type  # type: ignore[attr-defined]

        if run.scoring_mode == ScoringMode.LLM_ASSISTED:
            _apply_llm_refinement(results, index, campaign, version)

        facts = eligibility_engine.CandidateFacts(
            text=index.text,
            index=index,
            experience=profile,
            criterion_scores={r.criterion_key: r.raw_score for r in results},
            criterion_keys_by_requirement={
                w.requirement_id: w.criterion_key for w in weights if w.requirement_id
            },
            candidate_location=candidate.location or "",
            campaign_location=(campaign.location if campaign else "") or "",
        )
        eligibility = eligibility_engine.evaluate(rules, facts)

        aggregate = _aggregate(results, profile, index, eligibility, document)

        evaluation.overall_score = aggregate["overall_score"]
        evaluation.mandatory_score = aggregate["mandatory_score"]
        evaluation.preferred_score = aggregate["preferred_score"]
        evaluation.overall_confidence = aggregate["overall_confidence"]
        evaluation.confidence_band = band_for(evaluation.overall_confidence)
        evaluation.eligibility_status = eligibility.status
        evaluation.recommendation = _recommend(
            evaluation.overall_score, evaluation.mandatory_score,
            evaluation.overall_confidence, eligibility,
        )

        evaluation.experience_years_total = profile.total_years
        evaluation.experience_years_relevant = profile.relevant_years
        evaluation.experience_profile = profile.to_dict()
        evaluation.contradictions = profile.contradictions

        evaluation.strengths = [
            {"criterion_key": r.criterion_key, "label": r.label, "score": r.raw_score,
             "weight": r.weight}
            for r in sorted(results, key=lambda r: -r.weighted_score)
            if r.outcome == CriterionOutcome.CONFIRMED_MATCH and r.weight > 0
        ][:6]
        evaluation.gaps = [
            {"criterion_key": r.criterion_key, "label": r.label, "score": r.raw_score,
             "weight": r.weight, "outcome": r.outcome.value}
            for r in sorted(results, key=lambda r: -r.weight)
            if r.outcome in (
                CriterionOutcome.NOT_DEMONSTRATED,
                CriterionOutcome.CONTRADICTORY_EVIDENCE,
            ) and r.weight > 0
        ][:6]
        evaluation.missing_information = _missing_information(index, profile, results)
        readability = document_quality.missing_information_note(document)
        if readability:
            evaluation.missing_information = [readability] + evaluation.missing_information
        evaluation.narrative = _narrative(
            candidate, results, aggregate, eligibility, profile
        )
        evaluation.status = EvaluationStatus.COMPLETED

        # Phase F: category rollups, next action, validation questions and
        # interview focus. Derived from what is already computed above —
        # no new scoring. Challenge findings aren't available yet (three of
        # those checks are comparative and need the whole run), so the next
        # action is refined once more after the review pass.
        candidate_360.enrich(evaluation, results, eligibility.findings, profile)

        db.add(evaluation)
        db.flush()

        _persist_criteria(db, evaluation, results, document.id)
        _persist_eligibility(db, evaluation, eligibility)

    except Exception as exc:  # one bad CV must not sink the run
        logger.exception("Evaluation failed for candidate %s", candidate.id)
        evaluation.status = EvaluationStatus.FAILED
        evaluation.error_message = f"{exc.__class__.__name__}: {exc}"
        evaluation.eligibility_status = EligibilityStatus.REVIEW_REQUIRED
        evaluation.recommendation = Recommendation.REVIEW_REQUIRED
        evaluation.confidence_band = ConfidenceBand.LOW
        db.add(evaluation)
        db.flush()

    evaluation.duration_ms = int((_now() - started).total_seconds() * 1000)
    db.flush()
    return evaluation


def _persist_criteria(db: Session, evaluation: Evaluation, results, document_id: str) -> None:
    for result in results:
        criterion = EvaluationCriterion(
            evaluation_id=evaluation.id,
            rubric_weight_id=result.rubric_weight_id,
            criterion_key=result.criterion_key,
            label=result.label,
            category=result.category,
            requirement_type=getattr(result, "requirement_type", RequirementType.MANDATORY),
            weight=result.weight,
            max_score=result.max_score,
            scoring_method=result.scoring_method,
            deterministic_score=result.deterministic_score,
            raw_score=result.raw_score,
            weighted_score=result.weighted_score,
            llm_adjusted=result.llm_adjusted,
            outcome=result.outcome,
            confidence=result.confidence,
            confidence_band=result.confidence_band,
            matched_terms=result.matched_terms or [],
            equivalent_terms=result.equivalent_terms or [],
            missing_terms=result.missing_terms or [],
            rationale=result.rationale,
            evidence_count=len(result.evidence),
            display_order=result.display_order,
        )
        db.add(criterion)
        db.flush()

        for item in result.evidence:
            db.add(EvaluationEvidence(
                evaluation_id=evaluation.id,
                criterion_id=criterion.id,
                document_id=document_id,
                excerpt=item.excerpt,
                page_number=item.page_number,
                section=item.section,
                char_start=item.char_start,
                char_end=item.char_end,
                match_type=item.match_type,
                matched_term=item.matched_term[:255],
                relevance=item.relevance,
            ))
    db.flush()


def _persist_eligibility(
    db: Session, evaluation: Evaluation, outcome: eligibility_engine.EligibilityOutcome
) -> None:
    for finding in outcome.findings:
        db.add(EligibilityFinding(
            evaluation_id=evaluation.id,
            rule_id=finding.rule_id,
            code=finding.code,
            label=finding.label,
            rule_type=finding.rule_type,
            operator=finding.operator,
            threshold=finding.threshold,
            severity=finding.severity,
            triggered=finding.triggered,
            indeterminate=finding.indeterminate,
            observed_value=finding.observed_value[:2000],
            message=finding.message,
            display_order=finding.display_order,
        ))
    db.flush()


def _apply_llm_refinement(results, index, campaign, version) -> None:
    """
    Optional bounded model pass.

    The model may only nudge a criterion within `LLM_ADJUSTMENT_BAND` of the
    deterministic score, and only where evidence exists. It cannot zero a
    confirmed match, promote a criterion with no evidence, or touch
    eligibility. If it is unreachable or returns anything unexpected, the
    deterministic scores stand and the run continues — an LLM outage must not
    fail a screening run.
    """
    try:
        from app.agents.scoring_agent import refine_criterion_scores
    except Exception as exc:
        logger.warning("LLM refinement unavailable (%s); keeping deterministic scores", exc)
        return
    try:
        refine_criterion_scores(results, index, campaign, version)
    except Exception as exc:
        logger.warning("LLM refinement failed (%s); keeping deterministic scores", exc)


# ---------------------------------------------------------------------------
# Run execution
# ---------------------------------------------------------------------------

def execute_run(
    db: Session, run: EvaluationRun, *, delay_seconds: float = 0.0
) -> EvaluationRun:
    """
    Score every candidate in the run's selection.

    Runs inline against the caller's session, matching the Phase C `inline`
    queue backend. Opening a second session here would reintroduce the bug
    Phase C already fixed once.
    """
    if run.status in (RunStatus.COMPLETED, RunStatus.COMPLETED_WITH_ERRORS, RunStatus.CANCELLED):
        return run

    version = db.get(RubricVersion, run.rubric_version_id)
    if version is None:
        raise EvaluationError(
            f"Rubric version '{run.rubric_version_id}' has disappeared; the run "
            "cannot be executed."
        )
    campaign = db.get(Campaign, run.campaign_id)

    run.status = RunStatus.RUNNING
    run.started_at = run.started_at or _now()
    db.flush()

    started_action = (
        AuditAction.REEVALUATION_STARTED
        if run.trigger == RunTrigger.REEVALUATION
        else AuditAction.EVALUATION_RUN_STARTED
    )
    disposition_service.record_audit(
        db, started_action,
        campaign_id=run.campaign_id,
        entity_type="evaluation_run",
        entity_id=run.id,
        summary=(
            "Re-assessment started after a rubric change: "
            if run.trigger == RunTrigger.REEVALUATION
            else "Assessment started: "
        )
        + f"{run.total_candidates} candidate(s), scored against rubric "
          f"version {version.version_number}. "
          "The system recommends; a person decides.",
        after={"candidates": run.total_candidates,
               "rubric_version": version.version_number},
        actor=run.created_by,
    )

    candidate_ids = selected_candidate_ids(db, run)
    run.total_candidates = len(candidate_ids)

    weights = [w for w in version.weights if w.active]
    terms = _campaign_terms(weights)

    # B21: every LLM call made while scoring this run — the bounded scoring
    # refinement pass and the challenge/bias agents below — is billed to
    # this run so /api/developer/metrics can report cost per CV.
    with llm_usage.track(db, campaign_id=run.campaign_id, run_id=run.id, call_type="screening"):
        evaluated = failed = skipped = 0
        for candidate_id in candidate_ids:
            candidate = db.get(Candidate, candidate_id)
            if candidate is None:
                skipped += 1
                continue

            previous = current_evaluation(db, candidate_id)
            evaluation = evaluate_candidate(
                db, run, candidate, version, campaign=campaign, campaign_terms=terms
            )

            if evaluation.status == EvaluationStatus.COMPLETED:
                evaluated += 1
            elif evaluation.status == EvaluationStatus.FAILED:
                failed += 1
            else:
                skipped += 1

            # Supersede the previous result rather than replacing it. The old
            # row keeps its score, criteria, evidence and findings exactly as
            # they were — this is the only mutation performed on a committed
            # evaluation, and it touches navigation fields only.
            if previous is not None and previous.id != evaluation.id:
                previous.is_current = False
                previous.superseded_by_evaluation_id = evaluation.id
            db.flush()

            # Demo pacing is deliberately opt-in and bounded by the request
            # schema. It gives a presenter time to show the pipeline state
            # while preserving the real deterministic + LLM work above.
            run.evaluated_count = evaluated
            run.failed_count = failed
            run.skipped_count = skipped
            db.flush()
            if delay_seconds > 0:
                time.sleep(delay_seconds)

        # Challenge review runs after scoring, not during it. Three of the
        # six checks (inconsistent scoring, outliers, weighting) are
        # comparative and need the whole run in view. It reads the finished
        # rows and writes findings; it never touches a score or an
        # eligibility verdict.
        _persist_challenge_findings(db, run)

    run.evaluated_count = evaluated
    run.failed_count = failed
    run.skipped_count = skipped
    run.completed_at = _now()
    run.status = RunStatus.COMPLETED_WITH_ERRORS if failed else RunStatus.COMPLETED

    # _aware(), not the raw column: SQLite hands back a naive datetime
    # and subtracting it from an aware one raises TypeError.
    started_at = _aware(run.started_at)
    seconds = (
        round((_aware(run.completed_at) - started_at).total_seconds(), 1)
        if started_at else None
    )
    disposition_service.record_audit(
        db, AuditAction.EVALUATION_RUN_COMPLETED,
        campaign_id=run.campaign_id,
        entity_type="evaluation_run",
        entity_id=run.id,
        summary=f"Assessment finished: {evaluated} of "
                f"{run.total_candidates} candidate(s) assessed"
                + (f", {failed} could not be" if failed else "")
                + (f", {skipped} skipped" if skipped else "")
                + (f", in {seconds} seconds" if seconds is not None else "")
                + ".",
        after={"assessed": evaluated, "not_assessed": failed,
               "skipped": skipped, "selected": run.total_candidates,
               "seconds": seconds},
        actor=run.created_by,
    )

    # A campaign whose first results are in belongs in REVIEW.
    if campaign is not None and evaluated and campaign.can_transition_to(CampaignStatus.REVIEW):
        campaign.status = CampaignStatus.REVIEW

    db.flush()
    return run


def _persist_challenge_findings(db: Session, run: EvaluationRun) -> None:
    """
    Write the Challenge Agent's findings for this run.

    Wrapped so a bug in the reviewer cannot lose a completed scoring run —
    the scores are the deliverable, the findings are commentary on them.
    """
    try:
        report = challenge_engine.review(list(run.evaluations))
    except Exception:
        logger.exception("Challenge review failed for run %s; scores are unaffected", run.id)
        return

    for finding in report.findings:
        db.add(ChallengeFinding(
            run_id=run.id,
            evaluation_id=finding.evaluation_id,
            criterion_id=finding.criterion_id,
            criterion_key=finding.criterion_key[:128],
            check=finding.check,
            severity=finding.severity,
            scope=finding.scope,
            title=finding.title[:255],
            detail=finding.detail,
            recommendation=finding.recommendation,
            observed=finding.observed,
            display_order=finding.display_order,
            engine_version=challenge_engine.ENGINE_VERSION,
        ))
    db.flush()

    # A high-severity challenge finding changes what a recruiter should do
    # next, so the derived next action is settled here rather than during
    # scoring. This runs before the caller commits, so nothing already
    # committed is being rewritten.
    for evaluation in run.evaluations:
        if evaluation.status != EvaluationStatus.COMPLETED:
            continue
        high = sum(
            1 for f in report.findings
            if f.evaluation_id == evaluation.id
            and f.severity == ChallengeSeverity.HIGH
        )
        if not high:
            continue
        action, reason = candidate_360.next_action(
            eligibility_status=evaluation.eligibility_status,
            recommendation=evaluation.recommendation,
            confidence_band=evaluation.confidence_band,
            has_indeterminate=any(
                f.indeterminate for f in evaluation.eligibility_findings
            ),
            high_severity_findings=high,
            insufficient_criteria=sum(
                1 for c in evaluation.criteria
                if c.outcome == CriterionOutcome.INSUFFICIENT_EVIDENCE and c.weight > 0
            ),
        )
        evaluation.next_action = action.value
        evaluation.next_action_reason = reason
    db.flush()


def run_and_execute(db: Session, campaign_id: str, **kwargs) -> EvaluationRun:
    """Convenience for the API's common case: create then drain immediately."""
    run = create_run(db, campaign_id, **kwargs)
    if run.total_candidates:
        execute_run(db, run)
    return run


# ---------------------------------------------------------------------------
# Reevaluation — the Phase B hook
# ---------------------------------------------------------------------------

def reevaluation_status(db: Session, campaign_id: str) -> dict:
    """
    What needs re-scoring because the rubric moved underneath it.

    This is the consumer of Phase B's `reevaluation_required` flag. Phase B
    sets it when a new version is approved over an existing approved/locked
    one and deliberately re-scores nothing; this reports the consequence so a
    recruiter can decide. Candidates are grouped by the rubric version their
    current evaluation was produced under, because that — not the flag alone
    — is what actually makes a result stale.
    """
    _require_campaign(db, campaign_id)
    active = rubric_service.get_active_version(db, campaign_id)

    candidates = list(db.scalars(
        select(Candidate).where(Candidate.campaign_id == campaign_id)
    ).all())

    stale: list[dict] = []
    unevaluated: list[dict] = []
    current: list[dict] = []

    for candidate in candidates:
        evaluation = current_evaluation(db, candidate.id)
        entry = {
            "candidate_id": candidate.id,
            "full_name": candidate.full_name,
            "evaluation_id": evaluation.id if evaluation else None,
        }
        if evaluation is None:
            unevaluated.append(entry)
        elif active is not None and evaluation.rubric_version_id != active.id:
            scored_under = db.get(RubricVersion, evaluation.rubric_version_id)
            entry["scored_under_version"] = (
                scored_under.version_number if scored_under else None
            )
            stale.append(entry)
        else:
            current.append(entry)

    return {
        "campaign_id": campaign_id,
        "active_version_number": active.version_number if active else None,
        "active_version_id": active.id if active else None,
        "reevaluation_required": bool(active and active.reevaluation_required),
        "reevaluation_acknowledged_at": _aware(
            active.reevaluation_acknowledged_at
        ).isoformat() if active and active.reevaluation_acknowledged_at else None,
        "supersedes_version_id": active.supersedes_version_id if active else None,
        "counts": {
            "total_candidates": len(candidates),
            "current": len(current),
            "stale": len(stale),
            "unevaluated": len(unevaluated),
        },
        "stale_candidates": stale,
        "unevaluated_candidates": unevaluated,
        # Stated rather than implied: Phase B's contract is that nothing is
        # re-scored without a person asking for it.
        "action_required": (
            "Start a re-evaluation run against the active rubric version to refresh "
            f"{len(stale)} stale result(s)." if stale else
            f"Evaluate {len(unevaluated)} candidate(s) that have no results yet."
            if unevaluated else "All candidates are current against the active rubric."
        ),
    }


def start_reevaluation(
    db: Session, campaign_id: str, *, created_by: str = "", notes: str = ""
) -> EvaluationRun:
    """
    Re-score every candidate whose current result predates the active rubric
    version. Candidates already current are left alone — re-scoring them
    would burn LLM budget to produce the same numbers.
    """
    status = reevaluation_status(db, campaign_id)
    targets = [entry["candidate_id"] for entry in status["stale_candidates"]]
    targets += [entry["candidate_id"] for entry in status["unevaluated_candidates"]]

    if not targets:
        raise EvaluationError(
            "Nothing to re-evaluate: every candidate is already current against "
            "the active rubric version."
        )

    previous_run = db.scalars(
        select(EvaluationRun)
        .where(EvaluationRun.campaign_id == campaign_id)
        .order_by(EvaluationRun.created_at.desc())
    ).first()

    run = create_run(
        db, campaign_id,
        candidate_ids=targets,
        trigger=RunTrigger.REEVALUATION,
        created_by=created_by,
        notes=notes or "Re-evaluation after a rubric version change.",
    )
    if previous_run is not None:
        run.reevaluation_of_run_id = previous_run.id
        db.flush()
    return run
