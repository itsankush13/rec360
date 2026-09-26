"""
Phase F routes — recruiter disposition, override, comments, audit trail,
and campaign benchmarks.

Note what is absent: there is no endpoint that edits or deletes a
`CandidateAction`, and none that edits an `Evaluation`. Decisions are
append-only and assessments are immutable. Changing a decision posts a new
one, which supersedes the last; the previous decision stays readable.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import candidate_360
from app.db.models import (
    ActionType, AuditAction, Campaign, Candidate, Disposition, Evaluation,
    EvaluationStatus, Recommendation,
)
from app.db.session import get_db
from app.services import campaign_service, disposition_service
from app.services.disposition_service import DispositionError

router = APIRouter(prefix="/api/campaigns/{campaign_id}", tags=["decisions"])

# The audit record is not campaign-shaped. An auditor asks "what did this
# person do last week" and "everything that happened to this applicant",
# neither of which starts from a campaign, so these routes sit outside the
# campaign prefix.
audit_router = APIRouter(prefix="/api/audit", tags=["audit"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class CommentCreate(BaseModel):
    comment: str = Field(min_length=1)
    actor: str = ""
    actor_role: str = ""


class DispositionCreate(BaseModel):
    disposition: Disposition
    comment: str = ""
    actor: str = ""
    actor_role: str = ""


class OverrideCreate(BaseModel):
    overridden_to: Recommendation
    reason: str = Field(
        min_length=1,
        description=(
            "Mandatory. Recorded in the audit trail as the justification for "
            "departing from the assessment."
        ),
    )
    disposition: Disposition | None = None
    actor: str = ""
    actor_role: str = ""


class ActionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    campaign_id: str
    candidate_id: str
    evaluation_id: str | None
    action_type: ActionType
    disposition: Disposition | None
    ai_recommendation: Recommendation | None
    overridden_to: Recommendation | None
    comment: str
    reason: str
    actor: str
    actor_role: str
    is_current: bool
    superseded_by_action_id: str | None
    created_at: str

    @classmethod
    def of(cls, action) -> "ActionOut":
        return cls(
            id=action.id, campaign_id=action.campaign_id,
            candidate_id=action.candidate_id, evaluation_id=action.evaluation_id,
            action_type=action.action_type, disposition=action.disposition,
            ai_recommendation=action.ai_recommendation,
            overridden_to=action.overridden_to, comment=action.comment,
            reason=action.reason, actor=action.actor, actor_role=action.actor_role,
            is_current=action.is_current,
            superseded_by_action_id=action.superseded_by_action_id,
            created_at=action.created_at.isoformat() if action.created_at else "",
        )


class AuditEventOut(BaseModel):
    id: str
    campaign_id: str | None
    candidate_id: str | None = None
    action: AuditAction
    entity_type: str
    entity_id: str
    summary: str
    before: dict | None
    after: dict | None
    actor: str
    created_at: str
    # Ids identify; names are what a person reads. Both, because an auditor
    # quoting a row in a report needs the name, and anyone tracing it back
    # through the database needs the id.
    campaign_name: str = ""
    candidate_name: str = ""
    action_label: str = ""


# DATA.md: no enum value reaches a reader. An action without words here would
# render as a blank line on the screen an auditor reads most literally, so a
# missing entry is a visible defect rather than a silent one.
ACTION_WORDS = {
    AuditAction.CAMPAIGN_CREATED: "Campaign opened",
    AuditAction.CAMPAIGN_UPDATED: "Campaign details changed",
    AuditAction.CAMPAIGN_STATUS_CHANGED: "Campaign moved to a new stage",
    AuditAction.REQUIREMENTS_EXTRACTED: "Requirements read from the job description",
    AuditAction.AI_CAMPAIGN_DRAFTED: "Campaign drafted by AI from a recruiter request",
    AuditAction.RUBRIC_VERSION_CREATED: "New rubric version drafted",
    AuditAction.RUBRIC_SUBMITTED: "Rubric version sent for approval",
    AuditAction.RUBRIC_APPROVED: "Rubric version approved",
    AuditAction.RUBRIC_REJECTED: "Rubric version sent back",
    AuditAction.RUBRIC_LOCKED: "Rubric version locked",
    AuditAction.BATCH_UPLOADED: "CVs uploaded",
    AuditAction.FILE_HELD: "A file was held and not assessed",
    AuditAction.JOB_RETRIED: "A held file was tried again",
    AuditAction.EVALUATION_RUN_STARTED: "Assessment started",
    AuditAction.EVALUATION_RUN_COMPLETED: "Assessment finished",
    AuditAction.REEVALUATION_STARTED: "Assessment started again after a rubric change",
    AuditAction.DISPOSITION_SET: "A decision was recorded",
    AuditAction.RECOMMENDATION_OVERRIDDEN: "A person overruled the recommendation",
    AuditAction.COMMENT_ADDED: "A comment was added",
    AuditAction.EXPORTED: "Records exported",
    AuditAction.SENT_TO_HIRING_MANAGER: "Sent to the hiring manager",
    AuditAction.MANAGER_REVIEWED: "The hiring manager gave a verdict",
    AuditAction.STATUS_CHANGED: "Moved to a new stage of the hiring process",
    AuditAction.PUT_ON_HOLD: "Put on hold",
    AuditAction.CANDIDATE_WITHDREW: "The candidate withdrew",
    AuditAction.CANDIDATE_HIRED: "Candidate recorded as hired",
    # B10/B11: kept here for consistency with web/audit.html's own copy of
    # this map, even though this dict was already missing several actions
    # added since (INTERVIEW_SCHEDULED, OFFER_SENT, SLA_ESCALATED, ...) —
    # those fall back to "Action recorded" below rather than failing; see
    # the B10 handoff notes for this pre-existing gap.
    AuditAction.EMAIL_REPLY_RECEIVED: "An email reply was read and classified",
}


def _serialize_audit(db: Session, events) -> list[AuditEventOut]:
    """
    Resolve ids to names once per batch rather than once per row.

    A 200-row trail spanning a handful of campaigns and candidates would
    otherwise be 400 lookups, and screen 9 is the one screen somebody scrolls.
    """
    campaign_ids = {e.campaign_id for e in events if e.campaign_id}
    candidate_ids = {e.candidate_id for e in events if e.candidate_id}

    campaigns = {
        c.id: (c.job_title or c.name or "")
        for c in db.scalars(select(Campaign).where(Campaign.id.in_(campaign_ids))).all()
    } if campaign_ids else {}
    candidates = {
        c.id: (c.full_name or "")
        for c in db.scalars(select(Candidate).where(Candidate.id.in_(candidate_ids))).all()
    } if candidate_ids else {}

    return [
        AuditEventOut(
            id=e.id, campaign_id=e.campaign_id, candidate_id=e.candidate_id,
            action=e.action, entity_type=e.entity_type, entity_id=e.entity_id,
            summary=e.summary, before=e.before, after=e.after, actor=e.actor,
            created_at=e.created_at.isoformat() if e.created_at else "",
            campaign_name=campaigns.get(e.campaign_id, ""),
            # A candidate whose row has since been deleted keeps the id and
            # loses the name. The event still stands: the record is
            # append-only and does not depend on what it describes surviving.
            candidate_name=candidates.get(e.candidate_id, ""),
            action_label=ACTION_WORDS.get(e.action, "Action recorded"),
        )
        for e in events
    ]


def _require_campaign(db: Session, campaign_id: str):
    campaign = campaign_service.get_campaign(db, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign


def _fail(exc: DispositionError):
    return HTTPException(
        status_code=422, detail={"message": exc.message, "errors": exc.errors}
    )


# ---------------------------------------------------------------------------
# Decisions
# ---------------------------------------------------------------------------

@router.post("/candidates/{candidate_id}/comments", response_model=ActionOut, status_code=201)
def add_comment(
    campaign_id: str, candidate_id: str, payload: CommentCreate,
    db: Session = Depends(get_db),
):
    _require_campaign(db, campaign_id)
    try:
        action = disposition_service.add_comment(
            db, campaign_id, candidate_id, comment=payload.comment,
            actor=payload.actor, actor_role=payload.actor_role,
        )
    except DispositionError as exc:
        raise _fail(exc) from exc
    db.commit()
    db.refresh(action)
    return ActionOut.of(action)


@router.post("/candidates/{candidate_id}/disposition", response_model=ActionOut, status_code=201)
def set_disposition(
    campaign_id: str, candidate_id: str, payload: DispositionCreate,
    db: Session = Depends(get_db),
):
    """
    Record shortlist / reject / hold / request review / interview.

    The assessment is not modified. A disposition that diverges from the AI
    recommendation is allowed and simply recorded alongside it — the
    recruiter is the decision-maker.
    """
    _require_campaign(db, campaign_id)
    try:
        action = disposition_service.set_disposition(
            db, campaign_id, candidate_id, disposition=payload.disposition,
            comment=payload.comment, actor=payload.actor, actor_role=payload.actor_role,
        )
    except DispositionError as exc:
        raise _fail(exc) from exc
    db.commit()
    db.refresh(action)
    return ActionOut.of(action)


@router.post("/candidates/{candidate_id}/override", response_model=ActionOut, status_code=201)
def override_recommendation(
    campaign_id: str, candidate_id: str, payload: OverrideCreate,
    db: Session = Depends(get_db),
):
    """
    Record a recruiter overruling the AI recommendation.

    A reason is required. The evaluation keeps its original recommendation —
    the override supersedes it for display only, so the disagreement stays
    on the record.
    """
    _require_campaign(db, campaign_id)
    try:
        action = disposition_service.override_recommendation(
            db, campaign_id, candidate_id, overridden_to=payload.overridden_to,
            reason=payload.reason, disposition=payload.disposition,
            actor=payload.actor, actor_role=payload.actor_role,
        )
    except DispositionError as exc:
        raise _fail(exc) from exc
    db.commit()
    db.refresh(action)
    return ActionOut.of(action)


@router.get("/candidates/{candidate_id}/actions", response_model=list[ActionOut])
def action_history(campaign_id: str, candidate_id: str, db: Session = Depends(get_db)):
    """Every decision ever taken for this candidate, newest first."""
    _require_campaign(db, campaign_id)
    return [
        ActionOut.of(a) for a in disposition_service.action_history(db, candidate_id)
    ]


@router.get("/candidates/{candidate_id}/recommendation")
def effective_recommendation(campaign_id: str, candidate_id: str, db: Session = Depends(get_db)):
    """
    What to display: the AI recommendation, the recruiter's decision, and
    whether the two diverge. Both are always returned.

    A GET that also commits: the first read of a given evaluation generates
    and caches its AI-rationale summary (disposition_service.
    _suggested_rationale), which needs to persist for every later read to
    reuse it instead of re-calling the LLM. Routes commit, services flush —
    the cache-fill is real work this endpoint does, not a side effect.
    """
    _require_campaign(db, campaign_id)
    result = disposition_service.effective_recommendation(db, candidate_id)
    db.commit()
    return result


# ---------------------------------------------------------------------------
# Benchmarks
# ---------------------------------------------------------------------------

def _campaign_scores(db: Session, campaign_id: str) -> list[float]:
    return list(db.scalars(
        select(Evaluation.overall_score).where(
            Evaluation.campaign_id == campaign_id,
            Evaluation.is_current.is_(True),
            Evaluation.status == EvaluationStatus.COMPLETED,
        )
    ).all())


@router.get("/benchmarks")
def campaign_benchmarks(campaign_id: str, db: Session = Depends(get_db)):
    """
    Score distribution for the campaign.

    Returns `benchmarks: null` below four assessed candidates. A median
    across two people is arithmetically valid and practically meaningless,
    and presenting it as a benchmark would be false precision.
    """
    _require_campaign(db, campaign_id)
    scores = _campaign_scores(db, campaign_id)
    return {
        "campaign_id": campaign_id,
        "benchmarks": candidate_360.benchmarks(scores),
        "override_rate": disposition_service.override_rate(db, campaign_id),
    }


@router.get("/candidates/{candidate_id}/benchmark")
def candidate_benchmark(campaign_id: str, candidate_id: str, db: Session = Depends(get_db)):
    """
    Where one candidate sits in the campaign — the Candidate 360's
    "comparison with campaign benchmarks" section. Always reported with its
    denominator.
    """
    _require_campaign(db, campaign_id)
    evaluation = db.scalars(
        select(Evaluation)
        .where(Evaluation.candidate_id == candidate_id, Evaluation.is_current.is_(True))
        .order_by(Evaluation.created_at.desc())
    ).first()
    if evaluation is None:
        raise HTTPException(status_code=404, detail="This candidate has no assessment yet")

    scores = _campaign_scores(db, campaign_id)
    return {
        "candidate_id": candidate_id,
        "overall_score": evaluation.overall_score,
        "position": candidate_360.percentile_of(evaluation.overall_score, scores),
        "benchmarks": candidate_360.benchmarks(scores),
    }


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------

@router.get("/audit", response_model=list[AuditEventOut])
def audit_trail(
    campaign_id: str,
    action: AuditAction | None = Query(None, description="Filter to one action type."),
    candidate_id: str | None = Query(None, description="Everything that happened to one applicant."),
    actor: str | None = Query(None, description="Part of a person's name."),
    since: datetime | None = Query(None, description="Events at or after this time."),
    until: datetime | None = Query(None, description="Events at or before this time."),
    limit: int = Query(200, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    """
    Campaign audit trail, newest first — screen 9's backend.

    Separate from the `audit_log` in `app/core/auth.py`, which covers login
    and OTP events in a different database.
    """
    _require_campaign(db, campaign_id)
    return _serialize_audit(db, disposition_service.audit_trail(
        db, campaign_id, action=action, candidate_id=candidate_id,
        actor=actor, since=since, until=until, limit=limit,
    ))


# ---------------------------------------------------------------------------
# The record across campaigns
# ---------------------------------------------------------------------------

@audit_router.get("", response_model=list[AuditEventOut])
def audit_across_campaigns(
    campaign_id: str | None = Query(None, description="Narrow to one campaign."),
    candidate_id: str | None = Query(None, description="Everything that happened to one applicant."),
    action: AuditAction | None = Query(None, description="Filter to one action type."),
    actor: str | None = Query(None, description="Part of a person's name."),
    since: datetime | None = Query(None),
    until: datetime | None = Query(None),
    limit: int = Query(200, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    """Every recorded action, newest first, filtered however the reader asks."""
    return _serialize_audit(db, disposition_service.audit_trail(
        db, campaign_id, action=action, candidate_id=candidate_id,
        actor=actor, since=since, until=until, limit=limit,
    ))


@audit_router.get("/actions")
def audit_actions():
    """
    Every action the record can contain, with the words it is shown in.

    The screen builds its filter from this rather than hardcoding a list, so
    an action added to the backend cannot go missing from the filter.
    """
    return [
        {"action": action.value, "label": ACTION_WORDS.get(action, "Action recorded")}
        for action in AuditAction
    ]


@audit_router.get("/export.csv")
def audit_csv(
    campaign_id: str | None = Query(None),
    candidate_id: str | None = Query(None),
    action: AuditAction | None = Query(None),
    actor: str | None = Query(None),
    since: datetime | None = Query(None),
    until: datetime | None = Query(None),
    limit: int = Query(5000, ge=1, le=20000),
    db: Session = Depends(get_db),
):
    """
    The filtered record as a CSV.

    An auditor works in their own tools and will want the evidence out of the
    screen and into a file they can keep. Ids travel alongside names so a row
    quoted in a report can be traced back.
    """
    import csv
    import io

    events = _serialize_audit(db, disposition_service.audit_trail(
        db, campaign_id, action=action, candidate_id=candidate_id,
        actor=actor, since=since, until=until, limit=limit,
    ))

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([
        "When", "What happened", "Who", "Campaign", "Campaign id",
        "Candidate", "Candidate id", "Detail", "Changed from", "Changed to",
        "Event id",
    ])
    for event in events:
        writer.writerow([
            event.created_at,
            event.action_label,
            event.actor or "Recorded by the system",
            event.campaign_name,
            event.campaign_id or "",
            event.candidate_name,
            event.candidate_id or "",
            event.summary,
            _flatten(event.before),
            _flatten(event.after),
            event.id,
        ])

    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="audit-trail.csv"'},
    )


def _flatten(payload: dict | None) -> str:
    """before/after as something readable in a spreadsheet cell."""
    if not payload:
        return ""
    return "; ".join(
        f"{key.replace('_', ' ')}: {value}" for key, value in payload.items()
    )
