"""
HR discussion and approval routing (journey step 7, plan W-C).

Screening and the hiring manager's verdict are recorded elsewhere. From
FEEDBACK_COMPLETE, a candidate must clear two waiting states before an offer
can be drafted: named approvers, then a cost centre. Real position lives in
`CandidateLifecycle` via `lifecycle_service.transition` — this router adds no
table of its own. The approver chain, the grade, the salary band, the
justification, the cost centre and the return reason are structured detail
on the audit row, through `disposition_service.record_audit`, per the
no-new-tables rule: two places to look for the same fact would eventually
disagree.

A returned approval is a state the machine already allows (PENDING_APPROVAL
back to FEEDBACK_COMPLETE, PENDING_COST_CENTRE back to PENDING_APPROVAL) but
does not force a reason for. This router forces one anyway: a returned
approval with no stated reason is the exact thing an audit asks about.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.lifecycle import ROLE_WORDS, _name, _require_campaign
from app.core.lifecycle import TransitionError
from app.db.models import AuditAction, Candidate, LifecycleStatus
from app.db.session import get_db
from app.services import cost_centre_service, delegation_service, disposition_service, lifecycle_service
from app.services.cost_centre_service import CostCentreError
from app.services.delegation_service import DelegationError
from app.services.lifecycle_service import LifecycleError

router = APIRouter(
    prefix="/api/campaigns/{campaign_id}/approvals", tags=["approvals"],
)

# The step just completed, named for who was waiting on it. Kept the same on
# the way forward (cost-centre, grant) and the way back (return), so a
# reader never has to translate one vocabulary into another.
STEP_LABELS = {
    LifecycleStatus.PENDING_APPROVAL: "hr",
    LifecycleStatus.PENDING_COST_CENTRE: "cost_centre",
}


class ApprovalError(ValueError):
    """Caller-fixable; mapped to 422 the same way as LifecycleError."""


def _fail(exc: Exception) -> HTTPException:
    return HTTPException(status_code=422, detail=str(exc))


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _days_waiting(entered_at: datetime | None) -> int:
    if entered_at is None:
        return 0
    delta = datetime.now(timezone.utc) - _aware(entered_at)
    return max(delta.days, 0)


def _candidate_name(db: Session, candidate_id: str) -> str:
    candidate = db.get(Candidate, candidate_id)
    return candidate.full_name if candidate else ""


def _resolve_delegation(db: Session, campaign_id: str, *, actor_id: str,
                        on_behalf_of_id: str) -> str | None:
    """
    Empty string means nobody claimed a delegation — the common case, and
    not an error. A non-empty claim has to resolve to a real, active,
    unrevoked `DelegationGrant` covering this campaign (or a global one) and
    the "approval" scope, or the request is refused before it moves anyone.
    """
    if not on_behalf_of_id:
        return None
    delegation_service.require_delegation(
        db, delegate_id=actor_id, on_behalf_of_id=on_behalf_of_id,
        scope="approval", campaign_id=campaign_id,
    )
    return on_behalf_of_id


def _out(db: Session, record) -> "ApprovalActionOut":
    return ApprovalActionOut(
        candidate_id=record.candidate_id,
        status=record.status,
        owner_id=record.current_owner_id,
        owner_name=_name(db, record.current_owner_id),
    )


# ---------------------------------------------------------------------------
# Shapes
# ---------------------------------------------------------------------------

class RequestIn(BaseModel):
    chain: list[str] = Field(default_factory=list)
    grade: str = ""
    salary_band: str = ""
    justification: str = ""
    actor_id: str
    # B13: set when `actor_id` is acting in another named person's stead.
    # Checked against an active `DelegationGrant` before the move is made.
    on_behalf_of_id: str = ""


class CostCentreIn(BaseModel):
    cost_centre_code: str
    # Who the caller believes holds this cost centre's budget. Checked
    # against the `CostCentre` registry rather than trusted outright — a
    # mismatch is rejected, and the registry's own holder becomes the
    # record's owner either way.
    budget_holder_id: str
    actor_id: str
    on_behalf_of_id: str = ""


class GrantIn(BaseModel):
    actor_id: str
    note: str = ""
    on_behalf_of_id: str = ""


class ReturnIn(BaseModel):
    actor_id: str
    reason: str = ""


class ApprovalActionOut(BaseModel):
    candidate_id: str
    status: str
    owner_id: str | None = None
    owner_name: str = ""


class ApprovalQueueOut(BaseModel):
    candidate_id: str
    candidate_name: str
    status: str
    step_label: str
    owner_id: str | None = None
    owner_name: str = ""
    days_waiting: int
    justification: str = ""


class ApprovalHistoryOut(BaseModel):
    action: str
    summary: str
    after: dict | None = None
    actor: str = ""
    created_at: str = ""


# ---------------------------------------------------------------------------
# Requesting approval
# ---------------------------------------------------------------------------

@router.post("/{candidate_id}/request", response_model=ApprovalActionOut)
def request_approval(campaign_id: str, candidate_id: str, payload: RequestIn,
                     db: Session = Depends(get_db)):
    """FEEDBACK_COMPLETE -> PENDING_APPROVAL, with a named chain of approvers."""
    _require_campaign(db, campaign_id)
    if not payload.chain:
        raise _fail(ApprovalError(
            "An approval with no named approver is not an approval. Name "
            "at least one person in the chain."
        ))

    try:
        resolved_chain = [
            {
                "user_id": user.id,
                "name": user.full_name,
                "role_label": ROLE_WORDS.get(user.role, "Team member"),
            }
            for user in (
                lifecycle_service.require_user(db, uid, what="approve this candidate")
                for uid in payload.chain
            )
        ]
        on_behalf_of_id = _resolve_delegation(
            db, campaign_id, actor_id=payload.actor_id,
            on_behalf_of_id=payload.on_behalf_of_id,
        )
        record = lifecycle_service.transition(
            db, campaign_id=campaign_id, candidate_id=candidate_id,
            to_status=LifecycleStatus.PENDING_APPROVAL, actor_id=payload.actor_id,
            reason=payload.justification, owner_id=payload.chain[0],
            on_behalf_of_id=on_behalf_of_id,
        )
    except (LifecycleError, TransitionError, DelegationError) as exc:
        raise _fail(exc) from exc

    disposition_service.record_audit(
        db, AuditAction.APPROVAL_REQUESTED,
        campaign_id=campaign_id, candidate_id=candidate_id,
        entity_type="candidate_lifecycle", entity_id=record.id,
        summary=(
            f"Approval requested for {_candidate_name(db, candidate_id)}, "
            f"grade {payload.grade or 'not given'}."
        ),
        after={
            "chain": resolved_chain,
            "grade": payload.grade,
            "salary_band": payload.salary_band,
            "justification": payload.justification,
        },
        actor=_name(db, payload.actor_id),
    )
    db.commit()
    db.refresh(record)
    return _out(db, record)


# ---------------------------------------------------------------------------
# Cost centre and grant
# ---------------------------------------------------------------------------

@router.post("/{candidate_id}/cost-centre", response_model=ApprovalActionOut)
def cost_centre(campaign_id: str, candidate_id: str, payload: CostCentreIn,
                db: Session = Depends(get_db)):
    """
    PENDING_APPROVAL -> PENDING_COST_CENTRE, owned by the budget holder.

    B13: `cost_centre_code` and `budget_holder_id` are validated against the
    `CostCentre` registry rather than logged as whatever the caller sent.
    The registry's own `budget_holder_id` becomes the record's owner — a
    caller cannot route this to someone who does not actually hold the
    budget by simply naming them.
    """
    _require_campaign(db, campaign_id)
    try:
        centre = cost_centre_service.validate(
            db, code=payload.cost_centre_code,
            claimed_budget_holder_id=payload.budget_holder_id,
        )
        on_behalf_of_id = _resolve_delegation(
            db, campaign_id, actor_id=payload.actor_id,
            on_behalf_of_id=payload.on_behalf_of_id,
        )
        record = lifecycle_service.transition(
            db, campaign_id=campaign_id, candidate_id=candidate_id,
            to_status=LifecycleStatus.PENDING_COST_CENTRE, actor_id=payload.actor_id,
            owner_id=centre.budget_holder_id, on_behalf_of_id=on_behalf_of_id,
            cost_centre_id=centre.id,
        )
    except (LifecycleError, TransitionError, CostCentreError, DelegationError) as exc:
        raise _fail(exc) from exc

    disposition_service.record_audit(
        db, AuditAction.APPROVAL_GRANTED,
        campaign_id=campaign_id, candidate_id=candidate_id,
        entity_type="candidate_lifecycle", entity_id=record.id,
        summary=(
            f"HR approval granted for {_candidate_name(db, candidate_id)}, "
            f"sent to the cost centre {centre.code}."
        ),
        after={
            "step": "hr",
            "cost_centre_code": centre.code,
            "budget_holder_id": centre.budget_holder_id,
            "budget_holder_name": _name(db, centre.budget_holder_id),
        },
        actor=_name(db, payload.actor_id),
    )
    db.commit()
    db.refresh(record)
    return _out(db, record)


@router.post("/{candidate_id}/grant", response_model=ApprovalActionOut)
def grant(campaign_id: str, candidate_id: str, payload: GrantIn,
         db: Session = Depends(get_db)):
    """PENDING_COST_CENTRE -> APPROVED."""
    _require_campaign(db, campaign_id)
    try:
        on_behalf_of_id = _resolve_delegation(
            db, campaign_id, actor_id=payload.actor_id,
            on_behalf_of_id=payload.on_behalf_of_id,
        )
        record = lifecycle_service.transition(
            db, campaign_id=campaign_id, candidate_id=candidate_id,
            to_status=LifecycleStatus.APPROVED, actor_id=payload.actor_id,
            on_behalf_of_id=on_behalf_of_id,
        )
    except (LifecycleError, TransitionError, DelegationError) as exc:
        raise _fail(exc) from exc

    disposition_service.record_audit(
        db, AuditAction.APPROVAL_GRANTED,
        campaign_id=campaign_id, candidate_id=candidate_id,
        entity_type="candidate_lifecycle", entity_id=record.id,
        summary=f"Cost centre approval granted for {_candidate_name(db, candidate_id)}.",
        after={"step": "cost_centre", "note": payload.note},
        actor=_name(db, payload.actor_id),
    )
    db.commit()
    db.refresh(record)
    return _out(db, record)


# ---------------------------------------------------------------------------
# Return
# ---------------------------------------------------------------------------

@router.post("/{candidate_id}/return", response_model=ApprovalActionOut)
def return_one_step(campaign_id: str, candidate_id: str, payload: ReturnIn,
                    db: Session = Depends(get_db)):
    """
    Back one waiting step, with a reason.

    The state machine already allows PENDING_APPROVAL -> FEEDBACK_COMPLETE
    and PENDING_COST_CENTRE -> PENDING_APPROVAL. It does not force a reason;
    this does.
    """
    _require_campaign(db, campaign_id)
    if not payload.reason.strip():
        raise _fail(ApprovalError(
            "Returning an approval needs a reason. It is the first thing "
            "anyone reviewing this decision will look for."
        ))

    current = lifecycle_service.current(db, campaign_id, candidate_id)
    if current is None:
        raise _fail(ApprovalError(
            "This candidate is not in the hiring process yet."
        ))
    current_status = LifecycleStatus(current.status)
    target = {
        LifecycleStatus.PENDING_APPROVAL: LifecycleStatus.FEEDBACK_COMPLETE,
        LifecycleStatus.PENDING_COST_CENTRE: LifecycleStatus.PENDING_APPROVAL,
    }.get(current_status)
    if target is None:
        raise _fail(ApprovalError(
            "This candidate is not currently awaiting approval or a cost "
            "centre decision, so there is nothing to return."
        ))
    step = STEP_LABELS[current_status]

    try:
        record = lifecycle_service.transition(
            db, campaign_id=campaign_id, candidate_id=candidate_id,
            to_status=target, actor_id=payload.actor_id, reason=payload.reason,
        )
    except (LifecycleError, TransitionError) as exc:
        raise _fail(exc) from exc

    disposition_service.record_audit(
        db, AuditAction.APPROVAL_RETURNED,
        campaign_id=campaign_id, candidate_id=candidate_id,
        entity_type="candidate_lifecycle", entity_id=record.id,
        summary=(
            f"Approval returned for {_candidate_name(db, candidate_id)}. "
            f"Reason: {payload.reason.strip()}"
        ),
        after={"step": step, "reason": payload.reason.strip()},
        actor=_name(db, payload.actor_id),
    )
    db.commit()
    db.refresh(record)
    return _out(db, record)


# ---------------------------------------------------------------------------
# Queue and history
# ---------------------------------------------------------------------------

@router.get("/queue", response_model=list[ApprovalQueueOut])
def queue(campaign_id: str, db: Session = Depends(get_db)):
    """
    Everyone currently waiting on HR or the cost centre, oldest wait first.

    A queue sorted any other way buries the thing that is actually stuck.
    """
    _require_campaign(db, campaign_id)
    rows = lifecycle_service.statuses_for_campaign(db, campaign_id)
    waiting = [
        record for record in rows.values()
        if record.status in (
            LifecycleStatus.PENDING_APPROVAL.value,
            LifecycleStatus.PENDING_COST_CENTRE.value,
        )
    ]
    waiting.sort(key=lambda r: r.entered_at or _now())

    out = []
    for record in waiting:
        justification = ""
        requested = disposition_service.audit_trail(
            db, campaign_id, action=AuditAction.APPROVAL_REQUESTED,
            candidate_id=record.candidate_id, limit=1,
        )
        if requested and requested[0].after:
            justification = requested[0].after.get("justification", "")
        out.append(ApprovalQueueOut(
            candidate_id=record.candidate_id,
            candidate_name=_candidate_name(db, record.candidate_id),
            status=record.status,
            step_label=STEP_LABELS.get(LifecycleStatus(record.status), ""),
            owner_id=record.current_owner_id,
            owner_name=_name(db, record.current_owner_id),
            days_waiting=_days_waiting(record.entered_at),
            justification=justification,
        ))
    return out


@router.get("/{candidate_id}", response_model=list[ApprovalHistoryOut])
def history(campaign_id: str, candidate_id: str, db: Session = Depends(get_db)):
    """That candidate's approval history, oldest first, including returns."""
    _require_campaign(db, campaign_id)
    events = disposition_service.audit_trail(
        db, campaign_id, candidate_id=candidate_id, limit=500,
    )
    approval_events = [
        e for e in events
        if e.action in (
            AuditAction.APPROVAL_REQUESTED, AuditAction.APPROVAL_GRANTED,
            AuditAction.APPROVAL_RETURNED,
        )
    ]
    approval_events.reverse()  # audit_trail is newest-first; a history reads forwards.
    return [
        ApprovalHistoryOut(
            action=e.action.value if hasattr(e.action, "value") else e.action,
            summary=e.summary,
            after=e.after,
            actor=e.actor,
            created_at=e.created_at.isoformat() if e.created_at else "",
        )
        for e in approval_events
    ]
