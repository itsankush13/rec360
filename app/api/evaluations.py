"""
Phase D routes — evaluation runs, results, leaderboard, re-evaluation.

Split across two prefixes for the same reason Phase C is: runs are started
inside a campaign, but once a run exists the UI polls it and reads individual
evaluations by id.

Nothing here exposes a way to modify a committed evaluation. That is not an
oversight — results are immutable, and re-scoring is a new run. The only
write endpoints are "start a run" and "start a re-evaluation".
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import document_quality
from app.db.models import (
    Candidate, CandidateDocument, ChallengeFinding, ChallengeSeverity,
    EligibilityStatus, Evaluation, EvaluationRun, EvaluationStatus,
    Recommendation, RubricVersion,
)
from app.db.session import get_db
from app.schemas.evaluation import (
    ChallengeFindingOut, EvaluationDetail, EvaluationSummary, LeaderboardEntry,
    ReevaluationStatus, RunCreate, RunDetail, RunOut,
)
from app.services import campaign_service, evaluation_service
from app.services.evaluation_service import EvaluationError

campaign_router = APIRouter(prefix="/api/campaigns/{campaign_id}", tags=["evaluations"])
evaluation_router = APIRouter(prefix="/api/evaluations", tags=["evaluations"])


def _require_campaign(db: Session, campaign_id: str):
    campaign = campaign_service.get_campaign(db, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign


def _require_run(db: Session, run_id: str) -> EvaluationRun:
    run = db.get(EvaluationRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Evaluation run not found")
    return run


def _require_evaluation(db: Session, evaluation_id: str) -> Evaluation:
    evaluation = db.get(Evaluation, evaluation_id)
    if evaluation is None:
        raise HTTPException(status_code=404, detail="Evaluation not found")
    return evaluation


def _version_number(db: Session, rubric_version_id: str) -> int | None:
    version = db.get(RubricVersion, rubric_version_id)
    return version.version_number if version else None


def _summary(db: Session, evaluation: Evaluation) -> EvaluationSummary:
    summary = EvaluationSummary.model_validate(evaluation)
    candidate = db.get(Candidate, evaluation.candidate_id)
    summary.candidate_name = candidate.full_name if candidate else ""
    return summary


def _run_out(db: Session, run: EvaluationRun) -> RunOut:
    out = RunOut.model_validate(run)
    out.rubric_version_number = _version_number(db, run.rubric_version_id)
    return out


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------

@campaign_router.post("/evaluations/runs", response_model=RunDetail, status_code=201)
def start_run(campaign_id: str, payload: RunCreate, db: Session = Depends(get_db)):
    """
    Score candidates against an approved rubric version.

    422 when the campaign has no usable rubric — that is a precondition
    failure the caller can fix, not a server fault. Phase B already refuses
    to approve an unbalanced rubric, so reaching this with a bad weight total
    would be a bug, and it is reported as one rather than scored around.
    """
    _require_campaign(db, campaign_id)
    try:
        run = evaluation_service.create_run(
            db, campaign_id,
            batch_id=payload.batch_id,
            rubric_version_id=payload.rubric_version_id,
            candidate_ids=payload.candidate_ids,
            scoring_mode=payload.scoring_mode,
            only_unevaluated=payload.only_unevaluated,
            created_by=payload.created_by,
            notes=payload.notes,
        )
        if payload.execute and run.total_candidates:
            evaluation_service.execute_run(
                db, run, delay_seconds=payload.demo_delay_seconds
            )
    except EvaluationError as exc:
        raise HTTPException(
            status_code=422, detail={"message": exc.message, "errors": exc.errors}
        ) from exc

    db.commit()
    db.refresh(run)
    return _run_detail(db, run)


def _run_detail(db: Session, run: EvaluationRun) -> RunDetail:
    detail = RunDetail.model_validate(run)
    detail.rubric_version_number = _version_number(db, run.rubric_version_id)
    detail.evaluations = [
        _summary(db, evaluation)
        for evaluation in sorted(
            run.evaluations, key=lambda e: (-e.overall_score, e.created_at)
        )
    ]
    return detail


@campaign_router.get("/evaluations/runs", response_model=list[RunOut])
def list_runs(campaign_id: str, db: Session = Depends(get_db)):
    _require_campaign(db, campaign_id)
    runs = db.scalars(
        select(EvaluationRun)
        .where(EvaluationRun.campaign_id == campaign_id)
        .order_by(EvaluationRun.created_at.desc())
    ).all()
    return [_run_out(db, run) for run in runs]


@evaluation_router.get("/runs/{run_id}", response_model=RunDetail)
def get_run(run_id: str, db: Session = Depends(get_db)):
    return _run_detail(db, _require_run(db, run_id))


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------

@campaign_router.get("/evaluations", response_model=list[EvaluationSummary])
def list_evaluations(
    campaign_id: str,
    current_only: bool = Query(
        True,
        description=(
            "Only the latest evaluation per candidate. Set false to see the full "
            "history, including results produced under superseded rubric versions."
        ),
    ),
    recommendation: Recommendation | None = None,
    eligibility_status: EligibilityStatus | None = None,
    db: Session = Depends(get_db),
):
    _require_campaign(db, campaign_id)
    statement = select(Evaluation).where(Evaluation.campaign_id == campaign_id)
    if current_only:
        statement = statement.where(Evaluation.is_current.is_(True))
    if recommendation is not None:
        statement = statement.where(Evaluation.recommendation == recommendation)
    if eligibility_status is not None:
        statement = statement.where(Evaluation.eligibility_status == eligibility_status)

    evaluations = db.scalars(
        statement.order_by(Evaluation.overall_score.desc(), Evaluation.created_at.desc())
    ).all()
    return [_summary(db, evaluation) for evaluation in evaluations]


@campaign_router.get("/leaderboard", response_model=list[LeaderboardEntry])
def leaderboard(
    campaign_id: str,
    include_ineligible: bool = Query(
        False,
        description=(
            "Disqualified candidates are excluded by default so the ranking is "
            "actionable. They remain retrievable, since a disqualification a "
            "recruiter disagrees with has to be reviewable."
        ),
    ),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    """
    Ranked candidates: overall score, criterion-level scores, confidence and
    eligibility, as the client's ranking requirement specifies.
    """
    _require_campaign(db, campaign_id)

    # X12: push the limit into SQL rather than loading every evaluation in
    # the campaign and slicing in Python. At demo scale (a handful of CVs)
    # the two are indistinguishable; at the stated 10,000-CVs-a-month scale
    # this is the difference between fetching ten rows and fetching all of
    # them to show ten.
    evaluations = evaluation_service.ranked_evaluations(
        db, campaign_id, include_ineligible=include_ineligible, limit=limit,
    )

    entries: list[LeaderboardEntry] = []
    for rank, evaluation in enumerate(evaluations, start=1):
        entry = LeaderboardEntry.model_validate(evaluation)
        candidate = db.get(Candidate, evaluation.candidate_id)
        entry.candidate_name = candidate.full_name if candidate else ""
        entry.rank = rank
        entry.criterion_scores = {
            criterion.criterion_key: criterion.raw_score
            for criterion in evaluation.criteria
        }
        entries.append(entry)
    return entries


@evaluation_router.get("/{evaluation_id}", response_model=EvaluationDetail)
def get_evaluation(evaluation_id: str, db: Session = Depends(get_db)):
    """Full Candidate 360 payload for one evaluation."""
    evaluation = _require_evaluation(db, evaluation_id)
    detail = EvaluationDetail.model_validate(evaluation)
    candidate = db.get(Candidate, evaluation.candidate_id)
    detail.candidate_name = candidate.full_name if candidate else ""
    detail.rubric_version_number = _version_number(db, evaluation.rubric_version_id)
    # How much of the CV could actually be read. Absent when it read normally.
    cv = (db.get(CandidateDocument, evaluation.document_id)
          if evaluation.document_id else None)
    detail.document_quality = document_quality.describe(cv)
    detail.cv_available = bool(cv is not None and cv.storage_path)
    # Challenge findings for this candidate, plus the run-scoped ones (a
    # weighting anomaly concerns everyone in the run, not one person).
    detail.challenge_findings = [
        ChallengeFindingOut.model_validate(finding)
        for finding in db.scalars(
            select(ChallengeFinding)
            .where(
                ChallengeFinding.run_id == evaluation.run_id,
                (ChallengeFinding.evaluation_id == evaluation.id)
                | (ChallengeFinding.evaluation_id.is_(None)),
            )
            .order_by(ChallengeFinding.display_order)
        ).all()
    ]
    return detail


@evaluation_router.get("/runs/{run_id}/challenge", response_model=list[ChallengeFindingOut])
def run_challenge_findings(
    run_id: str,
    severity: ChallengeSeverity | None = Query(
        None, description="Filter to one severity."
    ),
    db: Session = Depends(get_db),
):
    """
    Every Challenge Agent finding for a run, worst first.

    Read-only by design. A finding records a concern about an assessment; it
    is not a correction to it, and there is no endpoint that lets one change
    a score.
    """
    _require_run(db, run_id)
    statement = select(ChallengeFinding).where(ChallengeFinding.run_id == run_id)
    if severity is not None:
        statement = statement.where(ChallengeFinding.severity == severity)
    findings = db.scalars(statement.order_by(ChallengeFinding.display_order)).all()
    return [ChallengeFindingOut.model_validate(f) for f in findings]


@campaign_router.get(
    "/candidates/{candidate_id}/evaluations", response_model=list[EvaluationSummary]
)
def candidate_history(campaign_id: str, candidate_id: str, db: Session = Depends(get_db)):
    """
    Every evaluation ever produced for a candidate, newest first.

    This is the audit view: nothing is overwritten, so a superseded result
    from an earlier rubric version is still here with its original score.
    """
    _require_campaign(db, campaign_id)
    candidate = db.get(Candidate, candidate_id)
    if candidate is None or candidate.campaign_id != campaign_id:
        raise HTTPException(status_code=404, detail="Candidate not found in this campaign")

    evaluations = db.scalars(
        select(Evaluation)
        .where(Evaluation.candidate_id == candidate_id)
        .order_by(Evaluation.created_at.desc())
    ).all()
    return [_summary(db, evaluation) for evaluation in evaluations]


# ---------------------------------------------------------------------------
# Re-evaluation — Phase B's reevaluation_required hook
# ---------------------------------------------------------------------------

@campaign_router.get("/evaluations/reevaluation-status", response_model=ReevaluationStatus)
def get_reevaluation_status(campaign_id: str, db: Session = Depends(get_db)):
    """
    What is stale because the rubric changed.

    Phase B sets `reevaluation_required` and deliberately re-scores nothing.
    This reports the consequence — which candidates were scored under which
    version — so a recruiter can decide whether to re-run.
    """
    try:
        return evaluation_service.reevaluation_status(db, campaign_id)
    except EvaluationError as exc:
        raise HTTPException(status_code=404, detail=exc.message) from exc


@campaign_router.post("/evaluations/reevaluate", response_model=RunDetail, status_code=201)
def start_reevaluation(
    campaign_id: str,
    created_by: str = Query("", description="Recruiter starting the re-evaluation."),
    execute: bool = Query(True),
    db: Session = Depends(get_db),
):
    """
    Re-score everything stale against the active rubric version.

    Previous results are superseded, never overwritten: each candidate gains
    a new evaluation and the old one stays readable with `is_current = false`.
    """
    _require_campaign(db, campaign_id)
    try:
        run = evaluation_service.start_reevaluation(db, campaign_id, created_by=created_by)
        if execute and run.total_candidates:
            evaluation_service.execute_run(db, run)
    except EvaluationError as exc:
        raise HTTPException(
            status_code=422, detail={"message": exc.message, "errors": exc.errors}
        ) from exc

    db.commit()
    db.refresh(run)
    return _run_detail(db, run)
