"""
Phase G routes — candidate comparison, what-if analysis, KPI aggregates.

Comparison, the what-if preview, and the KPI routes are all read-only.
What-if preview is a POST because it takes a weight set in the body, not
because it writes anything — its response carries `persisted: false` and a
notice saying so, because a screen that looks like an editor invites the
belief that it is one.

The what-if *proposal* routes at the bottom (B17) are the one deliberate
exception: they persist a proposed weight set and a hiring manager's
decision on it, through `app.services.whatif_service`. They still never
score anything or touch the rubric itself — see that module's docstring.
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import analytics
from app.core.analytics import AnalyticsError, EfficiencyAssumptions
from app.db.models import (
    ActionType, Campaign, CandidateAction, ChallengeFinding, Evaluation,
    EvaluationStatus, ProcessingJob, RubricVersion, User,
)
from app.db.session import get_db
from app.services import campaign_service, whatif_service
from app.services.whatif_service import WhatIfProposalError
from app.services.lifecycle_service import LifecycleError
from app.services.rubric_service import RubricValidationError

router = APIRouter(prefix="/api/campaigns/{campaign_id}", tags=["analytics"])
global_router = APIRouter(prefix="/api/analytics", tags=["analytics"])


class WhatIfRequest(BaseModel):
    weights: dict[str, float] = Field(
        description=(
            "criterion_key -> weight. Must reference criteria in the rubric "
            "version being previewed and total 100, the same invariant Phase B "
            "enforces on a real rubric."
        )
    )


class WhatIfProposeIn(BaseModel):
    weights: dict[str, float]
    proposed_by: str = Field(description="User id of the person proposing the reweighting.")
    approver_id: str = Field(
        description="User id of the hiring manager/admin this is sent to for a decision. "
                    "Must be a different, real, active person from proposed_by."
    )
    note: str = ""


class WhatIfDecisionIn(BaseModel):
    decided_by: str = Field(description="User id of the named approver deciding this proposal.")
    # Approve-only: amend the weights on the way through instead of approving
    # as proposed. Ignored by /reject.
    weights: dict[str, float] | None = None
    # The approval note, or the required reason for a rejection.
    note: str = ""


class WhatIfCreateDraftIn(BaseModel):
    created_by: str = Field(description="User id creating the rubric draft.")


class WhatIfProposalOut(BaseModel):
    id: str
    campaign_id: str
    rubric_version_id: str
    rubric_version_number: int | None = None
    status: str
    proposed_weights: dict[str, float]
    approved_weights: dict[str, float] | None = None
    note: str = ""
    proposed_by: str
    proposed_by_name: str = ""
    approver_id: str
    approver_name: str = ""
    decided_by: str | None = None
    decided_by_name: str = ""
    decision_note: str = ""
    created_at: str = ""
    decided_at: str | None = None
    # B17: set once this approved proposal has been turned into a real
    # rubric draft. Null means the human step to do that hasn't happened.
    draft_version_id: str | None = None
    draft_version_number: int | None = None


class AssumptionsQuery(BaseModel):
    manual_minutes_per_cv: float | None = None
    assisted_minutes_per_cv: float | None = None
    hourly_rate: float | None = None


def _require_campaign(db: Session, campaign_id: str) -> Campaign:
    campaign = campaign_service.get_campaign(db, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign


def _fail(exc: AnalyticsError):
    return HTTPException(
        status_code=422, detail={"message": exc.message, "errors": exc.errors}
    )


def _fail_whatif(exc: Exception) -> HTTPException:
    if isinstance(exc, WhatIfProposalError):
        return HTTPException(
            status_code=422, detail={"message": exc.message, "errors": exc.errors}
        )
    return HTTPException(status_code=422, detail=str(exc))


def _current_evaluations(db: Session, campaign_id: str) -> list[Evaluation]:
    return list(db.scalars(
        select(Evaluation)
        .where(
            Evaluation.campaign_id == campaign_id,
            Evaluation.is_current.is_(True),
            Evaluation.status == EvaluationStatus.COMPLETED,
        )
        .order_by(Evaluation.overall_score.desc())
    ).all())


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------

@router.get("/compare")
def compare_candidates(
    campaign_id: str,
    candidate_ids: list[str] = Query(
        ..., description="Two or more candidate ids to compare side by side."
    ),
    db: Session = Depends(get_db),
):
    """
    Side-by-side comparison on shared criteria.

    422 when the candidates were scored under different rubric versions —
    their scores are genuinely not comparable, and rendering the table anyway
    would imply they were.
    """
    _require_campaign(db, campaign_id)
    requested = list(dict.fromkeys(candidate_ids))

    evaluations = [
        e for e in _current_evaluations(db, campaign_id)
        if e.candidate_id in requested
    ]
    found = {e.candidate_id for e in evaluations}
    missing = [c for c in requested if c not in found]
    if missing:
        raise HTTPException(
            status_code=404,
            detail={
                "message": "Some candidates have no current assessment in this campaign.",
                "errors": missing,
            },
        )

    # Preserve the caller's ordering — the screen puts them in columns.
    evaluations.sort(key=lambda e: requested.index(e.candidate_id))
    try:
        return analytics.compare(evaluations)
    except AnalyticsError as exc:
        raise _fail(exc) from exc


# ---------------------------------------------------------------------------
# What-if
# ---------------------------------------------------------------------------

@router.get("/what-if/baseline")
def what_if_baseline(campaign_id: str, db: Session = Depends(get_db)):
    """
    The current weight set, as a starting point for the what-if sliders.

    Returned from the criteria actually scored rather than from the rubric
    table, so the keys are guaranteed to match what a preview can recompute.
    """
    _require_campaign(db, campaign_id)
    evaluations = _current_evaluations(db, campaign_id)
    if not evaluations:
        raise HTTPException(
            status_code=404, detail="This campaign has no assessed candidates yet"
        )

    version = db.get(RubricVersion, evaluations[0].rubric_version_id)
    criteria = sorted(evaluations[0].criteria, key=lambda c: c.display_order)
    return {
        "rubric_version_id": evaluations[0].rubric_version_id,
        "rubric_version_number": version.version_number if version else None,
        "weight_total": round(sum(c.weight for c in criteria), 2),
        "criteria": [
            {
                "criterion_key": c.criterion_key,
                "label": c.label,
                "category": c.category.value,
                "requirement_type": c.requirement_type.value,
                "weight": c.weight,
            }
            for c in criteria
        ],
        "candidates_assessed": len(evaluations),
    }


@router.post("/what-if")
def what_if(campaign_id: str, payload: WhatIfRequest, db: Session = Depends(get_db)):
    """
    Preview the ranking under a proposed weight set.

    **Writes nothing.** No evaluation is created, no approved result is
    touched, no rubric is modified or locked. The recomputation is arithmetic
    over the stored per-criterion scores, which are immutable, so this is
    non-destructive by construction rather than by care.

    Eligibility is unchanged: a disqualification comes from a rule, not a
    weight, so no reweighting can make an ineligible candidate eligible.
    """
    _require_campaign(db, campaign_id)
    evaluations = _current_evaluations(db, campaign_id)
    if not evaluations:
        raise HTTPException(
            status_code=404, detail="This campaign has no assessed candidates yet"
        )
    try:
        return analytics.what_if(evaluations, payload.weights)
    except AnalyticsError as exc:
        raise _fail(exc) from exc


# ---------------------------------------------------------------------------
# What-if proposals (B17) — the one write path in this file, through
# app.services.whatif_service. See that module's docstring.
# ---------------------------------------------------------------------------

def _proposal_out(db: Session, proposal) -> WhatIfProposalOut:
    version = db.get(RubricVersion, proposal.rubric_version_id)
    proposer = db.get(User, proposal.proposed_by)
    approver = db.get(User, proposal.approver_id)
    decider = db.get(User, proposal.decided_by) if proposal.decided_by else None
    draft = db.get(RubricVersion, proposal.draft_version_id) if proposal.draft_version_id else None
    return WhatIfProposalOut(
        id=proposal.id,
        campaign_id=proposal.campaign_id,
        rubric_version_id=proposal.rubric_version_id,
        rubric_version_number=version.version_number if version else None,
        status=proposal.status.value,
        proposed_weights=proposal.proposed_weights,
        approved_weights=proposal.approved_weights,
        note=proposal.note,
        proposed_by=proposal.proposed_by,
        proposed_by_name=proposer.full_name if proposer else "",
        approver_id=proposal.approver_id,
        approver_name=approver.full_name if approver else "",
        decided_by=proposal.decided_by,
        decided_by_name=decider.full_name if decider else "",
        decision_note=proposal.decision_note,
        created_at=proposal.created_at.isoformat() if proposal.created_at else "",
        decided_at=proposal.decided_at.isoformat() if proposal.decided_at else None,
        draft_version_id=proposal.draft_version_id,
        draft_version_number=draft.version_number if draft else None,
    )


def _require_proposal(db: Session, campaign_id: str, proposal_id: str):
    proposal = whatif_service.get_proposal(db, campaign_id, proposal_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail="What-if proposal not found")
    return proposal


@router.post("/what-if/proposals", response_model=WhatIfProposalOut, status_code=201)
def propose_what_if(campaign_id: str, payload: WhatIfProposeIn, db: Session = Depends(get_db)):
    """
    Send a previewed weight set to a named hiring manager for a decision.

    Still writes nothing to the rubric or any evaluation — only a proposal
    row and an audit event recording who proposed what.
    """
    _require_campaign(db, campaign_id)
    try:
        proposal = whatif_service.propose(
            db, campaign_id, weights=payload.weights,
            proposed_by=payload.proposed_by, approver_id=payload.approver_id,
            note=payload.note,
        )
    except (WhatIfProposalError, LifecycleError) as exc:
        raise _fail_whatif(exc) from exc
    db.commit()
    db.refresh(proposal)
    return _proposal_out(db, proposal)


@router.get("/what-if/proposals", response_model=list[WhatIfProposalOut])
def list_what_if_proposals(campaign_id: str, db: Session = Depends(get_db)):
    _require_campaign(db, campaign_id)
    return [_proposal_out(db, p) for p in whatif_service.list_proposals(db, campaign_id)]


@router.get("/what-if/proposals/{proposal_id}", response_model=WhatIfProposalOut)
def get_what_if_proposal(campaign_id: str, proposal_id: str, db: Session = Depends(get_db)):
    _require_campaign(db, campaign_id)
    return _proposal_out(db, _require_proposal(db, campaign_id, proposal_id))


@router.post("/what-if/proposals/{proposal_id}/approve", response_model=WhatIfProposalOut)
def approve_what_if_proposal(campaign_id: str, proposal_id: str, payload: WhatIfDecisionIn,
                             db: Session = Depends(get_db)):
    """
    Only the named approver can decide their own proposal — never the
    person who proposed it. Approving authorizes proceeding to a real
    rubric revision; it does not create or approve one.
    """
    _require_campaign(db, campaign_id)
    proposal = _require_proposal(db, campaign_id, proposal_id)
    try:
        proposal = whatif_service.approve(
            db, proposal, decided_by=payload.decided_by,
            weights=payload.weights, note=payload.note,
        )
    except (WhatIfProposalError, LifecycleError) as exc:
        raise _fail_whatif(exc) from exc
    db.commit()
    db.refresh(proposal)
    return _proposal_out(db, proposal)


@router.post("/what-if/proposals/{proposal_id}/reject", response_model=WhatIfProposalOut)
def reject_what_if_proposal(campaign_id: str, proposal_id: str, payload: WhatIfDecisionIn,
                            db: Session = Depends(get_db)):
    """`note` is the required reason a returned proposal must carry."""
    _require_campaign(db, campaign_id)
    proposal = _require_proposal(db, campaign_id, proposal_id)
    try:
        proposal = whatif_service.reject(
            db, proposal, decided_by=payload.decided_by, reason=payload.note,
        )
    except (WhatIfProposalError, LifecycleError) as exc:
        raise _fail_whatif(exc) from exc
    db.commit()
    db.refresh(proposal)
    return _proposal_out(db, proposal)


@router.post(
    "/what-if/proposals/{proposal_id}/create-draft", response_model=WhatIfProposalOut,
)
def create_rubric_draft_from_proposal(
    campaign_id: str, proposal_id: str, payload: WhatIfCreateDraftIn,
    db: Session = Depends(get_db),
):
    """
    B17: the step approving a proposal deliberately does not do — turn an
    approved weight set into a real `RubricVersion` draft. 422 (rather than
    a silent queue or overwrite) when another draft is already in flight for
    this rubric; retry once that one is resolved. The draft still has to be
    submitted, approved, and candidates re-scored — all separate, existing
    rubric-review steps.
    """
    _require_campaign(db, campaign_id)
    proposal = _require_proposal(db, campaign_id, proposal_id)
    try:
        whatif_service.create_rubric_draft(db, proposal, created_by=payload.created_by)
    except (WhatIfProposalError, LifecycleError, RubricValidationError) as exc:
        raise _fail_whatif(exc) from exc
    db.commit()
    db.refresh(proposal)
    return _proposal_out(db, proposal)


# ---------------------------------------------------------------------------
# KPIs
# ---------------------------------------------------------------------------

def _assumptions(
    manual_minutes_per_cv: float | None,
    assisted_minutes_per_cv: float | None,
    hourly_rate: float | None,
) -> EfficiencyAssumptions:
    defaults = EfficiencyAssumptions()
    return EfficiencyAssumptions(
        manual_minutes_per_cv=(
            manual_minutes_per_cv if manual_minutes_per_cv is not None
            else defaults.manual_minutes_per_cv
        ),
        assisted_minutes_per_cv=(
            assisted_minutes_per_cv if assisted_minutes_per_cv is not None
            else defaults.assisted_minutes_per_cv
        ),
        hourly_rate=hourly_rate if hourly_rate is not None else defaults.hourly_rate,
    )


def _resolve_period(
    since: datetime | None, until: datetime | None, months: int | None,
) -> tuple[datetime | None, datetime | None, dict]:
    """
    B19: period filters and historical reporting windows for the KPI screen.

    `months` is the convenience the plan asks for by name ("last 3 months /
    6 months") and is ignored once an explicit `since` is given — an exact
    boundary always wins over a rounded one. Every response names the window
    it actually used rather than leaving `web/performance.html`'s placeholder
    period label to imply a real one.
    """
    if since is None and months is not None:
        since = datetime.now(timezone.utc) - timedelta(days=30 * months)
    if since is None and until is None:
        label = "All campaigns to date"
    elif months is not None and until is None:
        label = f"Last {months} month{'s' if months != 1 else ''}"
    else:
        label = "Custom reporting window"
    period = {
        "since": since.isoformat() if since else None,
        "until": until.isoformat() if until else None,
        "months": months,
        "label": label,
    }
    return since, until, period


def _kpi_payload(
    db: Session, campaign_ids: list[str] | None, assumptions,
    *, since: datetime | None = None, until: datetime | None = None,
) -> dict:
    job_statement = select(ProcessingJob)
    evaluation_statement = select(Evaluation).where(
        Evaluation.is_current.is_(True),
        Evaluation.status == EvaluationStatus.COMPLETED,
    )
    finding_statement = select(ChallengeFinding)
    override_statement = select(CandidateAction).where(
        CandidateAction.action_type == ActionType.OVERRIDE,
        CandidateAction.is_current.is_(True),
    )

    if campaign_ids is not None:
        job_statement = job_statement.where(ProcessingJob.campaign_id.in_(campaign_ids or [""]))
        evaluation_statement = evaluation_statement.where(
            Evaluation.campaign_id.in_(campaign_ids or [""])
        )
        override_statement = override_statement.where(
            CandidateAction.campaign_id.in_(campaign_ids or [""])
        )
        run_ids = list(db.scalars(
            select(Evaluation.run_id).where(Evaluation.campaign_id.in_(campaign_ids or [""]))
        ).all())
        finding_statement = finding_statement.where(
            ChallengeFinding.run_id.in_(run_ids or [""])
        )
        campaign_count = len(campaign_ids)
    else:
        campaign_count = len(list(db.scalars(select(Campaign.id)).all()))

    if since is not None:
        job_statement = job_statement.where(ProcessingJob.queued_at >= since)
        evaluation_statement = evaluation_statement.where(Evaluation.created_at >= since)
        override_statement = override_statement.where(CandidateAction.created_at >= since)
        finding_statement = finding_statement.where(ChallengeFinding.created_at >= since)
    if until is not None:
        job_statement = job_statement.where(ProcessingJob.queued_at <= until)
        evaluation_statement = evaluation_statement.where(Evaluation.created_at <= until)
        override_statement = override_statement.where(CandidateAction.created_at <= until)
        finding_statement = finding_statement.where(ChallengeFinding.created_at <= until)

    return analytics.kpis(
        jobs=list(db.scalars(job_statement).all()),
        evaluations=list(db.scalars(evaluation_statement).all()),
        challenge_findings=list(db.scalars(finding_statement).all()),
        override_count=len(list(db.scalars(override_statement).all())),
        campaign_count=campaign_count,
        assumptions=assumptions,
    )


@global_router.get("/kpis")
def global_kpis(
    manual_minutes_per_cv: float | None = Query(
        None, ge=0, description="Planning assumption. Defaults to 8.0 minutes."
    ),
    assisted_minutes_per_cv: float | None = Query(
        None, ge=0, description="Planning assumption. Defaults to 1.1 minutes."
    ),
    hourly_rate: float | None = Query(
        None, ge=0, description="Loaded recruiter rate. Defaults to 42.00."
    ),
    role: str | None = Query(
        None,
        description="Filter to campaigns whose job title contains this text "
                    "(case-insensitive). Unmatched text returns zero campaigns, "
                    "not every campaign.",
    ),
    months: int | None = Query(
        None, ge=1, le=24,
        description="Convenience for the last N months to date, e.g. 3 or 6. "
                    "Ignored if `since` is given.",
    ),
    since: datetime | None = Query(
        None, description="Only include activity on or after this timestamp."
    ),
    until: datetime | None = Query(
        None, description="Only include activity on or before this timestamp."
    ),
    db: Session = Depends(get_db),
):
    """
    HR KPI dashboard across all campaigns, or a `role`-filtered and/or
    period-filtered slice of it (`B19`).

    Efficiency figures are derived from configurable planning assumptions,
    which are returned alongside them. They are not measurements this system
    has taken, and the response says so. The `period` block names the exact
    window applied, so a screen never has to invent its own label for one.
    """
    campaign_ids = None
    if role:
        campaign_ids = list(db.scalars(
            select(Campaign.id).where(Campaign.job_title.ilike(f"%{role}%"))
        ).all())
    resolved_since, resolved_until, period = _resolve_period(since, until, months)
    payload = _kpi_payload(
        db, campaign_ids,
        _assumptions(manual_minutes_per_cv, assisted_minutes_per_cv, hourly_rate),
        since=resolved_since, until=resolved_until,
    )
    payload["period"] = period
    payload["role_filter"] = role
    return payload


@router.get("/kpis")
def campaign_kpis(
    campaign_id: str,
    manual_minutes_per_cv: float | None = Query(None, ge=0),
    assisted_minutes_per_cv: float | None = Query(None, ge=0),
    hourly_rate: float | None = Query(None, ge=0),
    months: int | None = Query(
        None, ge=1, le=24,
        description="Convenience for the last N months to date. Ignored if `since` is given.",
    ),
    since: datetime | None = Query(None),
    until: datetime | None = Query(None),
    db: Session = Depends(get_db),
):
    """The same six KPI groups, scoped to one campaign and, optionally, a period."""
    _require_campaign(db, campaign_id)
    resolved_since, resolved_until, period = _resolve_period(since, until, months)
    payload = _kpi_payload(
        db, [campaign_id],
        _assumptions(manual_minutes_per_cv, assisted_minutes_per_cv, hourly_rate),
        since=resolved_since, until=resolved_until,
    )
    payload["period"] = period
    return payload
