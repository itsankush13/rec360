"""
Identity and the recruitment lifecycle over HTTP.

Two routers. `/api/users` is identity — phase 0, without which an approval is
just a row someone typed. `/api/campaigns/{id}/lifecycle/...` is what happens
to a candidate after screening.

Errors return FastAPI's `{"detail": ...}` shape and read as sentences: these
refusals are shown to a recruiter mid-task, and "illegal transition" tells
them nothing they can act on.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.core import lifecycle
from app.core.lifecycle import TransitionError
from app.core.mail_guard import ensure_approved_mail_recipients
from app.core.outlook_adapter import get_mail_adapter
from app.db.models import (
    Candidate, LifecycleStatus, ManagerReviewOutcome, User, UserRole,
)
from app.db.session import get_db
from app.services import campaign_service, lifecycle_service, sla_service
from app.services.lifecycle_service import LifecycleError

users_router = APIRouter(prefix="/api/users", tags=["users"])
router = APIRouter(prefix="/api/campaigns/{campaign_id}/lifecycle", tags=["lifecycle"])
# B02 phase 5: not nested under a candidate, since one call evaluates every
# candidate (optionally scoped to a campaign) in one pass.
sla_router = APIRouter(prefix="/api/lifecycle/sla", tags=["lifecycle"])


# ---------------------------------------------------------------------------
# Shapes
# ---------------------------------------------------------------------------

class UserIn(BaseModel):
    full_name: str = Field(min_length=1, max_length=200)
    email: str = Field(min_length=3, max_length=320)
    role: UserRole
    business_unit: str = ""


class UserRoleUpdate(BaseModel):
    role: UserRole


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    full_name: str
    email: str
    role: UserRole
    business_unit: str
    active: bool
    # What the role is called on screen, so no enum value reaches a reader.
    role_label: str = ""


class TransitionIn(BaseModel):
    to_status: LifecycleStatus
    actor_id: str
    reason: str = ""
    owner_id: str | None = None
    # Delegation is carried from the start so the approval work can use it
    # without a migration or a contract change.
    on_behalf_of_id: str | None = None


class HandoverIn(BaseModel):
    actor_id: str
    manager_id: str
    note: str = ""


class ReviewIn(BaseModel):
    reviewer_id: str
    outcome: ManagerReviewOutcome
    reason: str = ""


class LifecycleOut(BaseModel):
    candidate_id: str
    status: str
    status_label: str
    owner_id: str | None = None
    owner_name: str = ""
    entered_at: str = ""
    due_at: str | None = None
    # 'ON_TRACK' | 'DUE_SOON' | 'OVERDUE' — derived from `due_at` at read
    # time by the same rule `sla_service.evaluate()` uses to decide when to
    # write a reminder or escalation, so a screen's badge and the audit
    # trail can never disagree about whether a stage is late.
    sla_status: str = "ON_TRACK"
    # Where this candidate can go next, already filtered — so a screen does
    # not have to encode the state machine a second time and drift from it.
    next_steps: list[dict] = []
    # The stage a hold paused, straight from the stored `held_from_status`
    # column (X15). A screen showing where an on-hold candidate came from
    # should read this rather than re-deriving it by walking transition
    # history backwards — that duplicates a value already recorded here,
    # and can disagree with it across more than one hold/resume cycle.
    held_from_status: str | None = None
    held_from_label: str = ""
    # B15: the leaderboard position this candidate held when they entered
    # the lifecycle. Stored at the time, not recomputed now.
    campaign_rank: int | None = None
    # B15: who to fall back to, populated only once this candidate has
    # declined or withdrawn — the best-ranked candidate still waitlisted
    # for this campaign. None means there is nobody in reserve.
    next_backup_candidate_id: str | None = None
    next_backup_candidate_name: str = ""
    next_backup_rank: int | None = None
    # Only ever set by `/send-to-manager`: whether the manager's note (the
    # recruiter's answer, on a re-send after a QUESTION) actually went out
    # as a real Outlook message versus was only simulated/skipped. `None`
    # means no send was attempted for this response at all.
    mail_sent: bool | None = None
    mail_detail: str | None = None


class BackupCandidateOut(BaseModel):
    candidate_id: str
    candidate_name: str
    campaign_rank: int | None = None
    entered_at: str = ""


class TransitionOut(BaseModel):
    from_status: str | None
    from_label: str
    to_status: str
    to_label: str
    actor_id: str | None
    actor_name: str = ""
    on_behalf_of_name: str = ""
    reason: str
    created_at: str


class ReviewOut(BaseModel):
    id: str
    reviewer_id: str
    reviewer_name: str = ""
    outcome: str
    outcome_label: str
    reason: str
    evaluation_id: str | None
    created_at: str


ROLE_WORDS = {
    UserRole.RECRUITER: "Recruiter",
    UserRole.HIRING_MANAGER: "Hiring manager",
    # B25: this role was unused (no screen or WHO_MAY entry referenced it) —
    # repurposed as the budget approver, the person who holds a cost
    # centre's budget and grants the final PENDING_COST_CENTRE -> APPROVED
    # move. No enum/migration change needed since the value itself is
    # unchanged, only what it's called on screen.
    UserRole.REVIEWER: "Budget approver",
    UserRole.ADMIN: "Administrator",
}

OUTCOME_WORDS = {
    ManagerReviewOutcome.PROCEED: "Wants to interview",
    ManagerReviewOutcome.DECLINE: "Does not want to proceed",
    ManagerReviewOutcome.QUESTION: "Has a question for the recruiter",
}


def _fail(exc: Exception) -> HTTPException:
    return HTTPException(status_code=422, detail=str(exc))


def _require_campaign(db: Session, campaign_id: str):
    campaign = campaign_service.get_campaign(db, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign


def _name(db: Session, user_id: str | None) -> str:
    from app.db.models import User

    if not user_id:
        return ""
    user = db.get(User, user_id)
    return user.full_name if user else ""


# ---------------------------------------------------------------------------
# People
# ---------------------------------------------------------------------------

@users_router.get("", response_model=list[UserOut])
def list_users(role: UserRole | None = Query(None), db: Session = Depends(get_db)):
    return [
        UserOut(
            id=u.id, full_name=u.full_name, email=u.email, role=u.role,
            business_unit=u.business_unit, active=u.active,
            role_label=ROLE_WORDS.get(u.role, "Team member"),
        )
        for u in lifecycle_service.list_users(db, role)
    ]


@users_router.post("", response_model=UserOut, status_code=201)
def create_user(payload: UserIn, db: Session = Depends(get_db)):
    try:
        user = lifecycle_service.create_user(
            db, full_name=payload.full_name, email=payload.email,
            role=payload.role, business_unit=payload.business_unit,
        )
    except LifecycleError as exc:
        raise _fail(exc) from exc
    return UserOut(
        id=user.id, full_name=user.full_name, email=user.email, role=user.role,
        business_unit=user.business_unit, active=user.active,
        role_label=ROLE_WORDS.get(user.role, "Team member"),
    )


@users_router.patch("/{user_id}/role", response_model=UserOut)
def change_user_role(user_id: str, payload: UserRoleUpdate, db: Session = Depends(get_db)):
    """
    Change which role a person acts under — e.g. so one account can stand
    in for a hiring manager in a demo/self-test send. No endpoint edits a
    user's name or email; those identify the account and stay fixed.
    """
    try:
        user = lifecycle_service.update_user_role(db, user_id, role=payload.role)
    except LifecycleError as exc:
        raise _fail(exc) from exc
    db.commit()
    db.refresh(user)
    return UserOut(
        id=user.id, full_name=user.full_name, email=user.email, role=user.role,
        business_unit=user.business_unit, active=user.active,
        role_label=ROLE_WORDS.get(user.role, "Team member"),
    )


# ---------------------------------------------------------------------------
# Where everyone is
# ---------------------------------------------------------------------------

@router.get("", response_model=list[LifecycleOut])
def campaign_lifecycle(campaign_id: str, db: Session = Depends(get_db)):
    _require_campaign(db, campaign_id)
    rows = lifecycle_service.statuses_for_campaign(db, campaign_id)
    return [_out(db, record) for record in rows.values()]


@router.get("/funnel")
def campaign_funnel(campaign_id: str, db: Session = Depends(get_db)):
    """How many candidates sit at each stage. Counts carry their denominator."""
    _require_campaign(db, campaign_id)
    return lifecycle_service.funnel(db, campaign_id)


@router.get("/backups", response_model=list[BackupCandidateOut])
def campaign_backups(campaign_id: str, db: Session = Depends(get_db)):
    """
    B15: current backups for this campaign, best rank first.

    Declared ahead of `/{candidate_id}` below — a path parameter route
    registered first would otherwise swallow this literal path as
    candidate_id="backups".
    """
    _require_campaign(db, campaign_id)
    out = []
    for row in lifecycle_service.waitlisted_candidates(db, campaign_id):
        candidate = db.get(Candidate, row.candidate_id)
        out.append(BackupCandidateOut(
            candidate_id=row.candidate_id,
            candidate_name=candidate.full_name if candidate else "",
            campaign_rank=row.campaign_rank,
            entered_at=row.entered_at.isoformat() if row.entered_at else "",
        ))
    return out


@router.get("/{candidate_id}", response_model=LifecycleOut)
def candidate_status(campaign_id: str, candidate_id: str, db: Session = Depends(get_db)):
    _require_campaign(db, campaign_id)
    record = lifecycle_service.current(db, campaign_id, candidate_id)
    if record is None:
        raise HTTPException(
            status_code=404,
            detail="This candidate is not in the hiring process yet.",
        )
    return _out(db, record)


@router.get("/{candidate_id}/timeline", response_model=list[TransitionOut])
def candidate_timeline(campaign_id: str, candidate_id: str, db: Session = Depends(get_db)):
    """
    Every move, oldest first — the same information the auditor gets, shown
    to the person doing the work.
    """
    _require_campaign(db, campaign_id)
    return [
        TransitionOut(
            from_status=t.from_status,
            from_label=lifecycle.words(t.from_status) if t.from_status else "",
            to_status=t.to_status, to_label=lifecycle.words(t.to_status),
            actor_id=t.actor_id, actor_name=_name(db, t.actor_id),
            on_behalf_of_name=_name(db, t.on_behalf_of_id),
            reason=t.reason,
            created_at=t.created_at.isoformat() if t.created_at else "",
        )
        for t in lifecycle_service.timeline(db, campaign_id, candidate_id)
    ]


# ---------------------------------------------------------------------------
# Moving
# ---------------------------------------------------------------------------

def _last_question(db: Session, campaign_id: str, candidate_id: str) -> str:
    """The most recent question a manager asked, or "" if none is on file.

    Mirrors `app/api/handoff.py::_last_question` — kept separate rather than
    imported, since `handoff.py`'s router is the read-side queue and this is
    the write-side action; nothing here justifies a shared module yet.
    """
    for review in reversed(lifecycle_service.reviews_for(db, campaign_id, candidate_id)):
        if review.outcome == ManagerReviewOutcome.QUESTION.value:
            return review.reason
    return ""


@router.post("/{candidate_id}/send-to-manager", response_model=LifecycleOut)
def send_to_manager(campaign_id: str, candidate_id: str, payload: HandoverIn,
                    db: Session = Depends(get_db)):
    campaign = _require_campaign(db, campaign_id)
    question = _last_question(db, campaign_id, candidate_id)
    try:
        record = lifecycle_service.send_to_hiring_manager(
            db, campaign_id=campaign_id, candidate_id=candidate_id,
            actor_id=payload.actor_id, manager_id=payload.manager_id,
            note=payload.note,
        )
    except (LifecycleError, TransitionError) as exc:
        raise _fail(exc) from exc

    out = _out(db, record)
    # Only when there was actually a question to answer — the same button
    # also does the very first handoff (no QUESTION on file yet), which the
    # hiring manager already knows is coming and does not need an email for.
    if question:
        manager = db.get(User, payload.manager_id)
        candidate = db.get(Candidate, candidate_id)
        if manager and manager.email:
            title = campaign.job_title or campaign.name or "this role"
            subject = f"Re: your question on {candidate.full_name if candidate else 'a candidate'} ({title})"
            body = (
                f"Hi {manager.full_name},\n\n"
                f'You asked: "{question}"\n\n'
                f"{payload.note.strip() or 'The recruiter has sent this candidate back to you.'}\n\n"
                "— sent from Recruitment 360"
            )
            try:
                ensure_approved_mail_recipients(to_address=manager.email)
                transmission = get_mail_adapter().send(
                    to_address=manager.email, subject=subject, body=body,
                )
                out.mail_sent = not transmission.simulated
                out.mail_detail = transmission.detail
            except HTTPException as exc:
                out.mail_sent = False
                out.mail_detail = str(exc.detail)
    return out


@router.post("/{candidate_id}/review", response_model=ReviewOut, status_code=201)
def manager_review(campaign_id: str, candidate_id: str, payload: ReviewIn,
                   db: Session = Depends(get_db)):
    _require_campaign(db, campaign_id)
    try:
        review = lifecycle_service.record_manager_review(
            db, campaign_id=campaign_id, candidate_id=candidate_id,
            reviewer_id=payload.reviewer_id, outcome=payload.outcome,
            reason=payload.reason,
        )
    except (LifecycleError, TransitionError) as exc:
        raise _fail(exc) from exc
    return ReviewOut(
        id=review.id, reviewer_id=review.reviewer_id,
        reviewer_name=_name(db, review.reviewer_id),
        outcome=review.outcome,
        outcome_label=OUTCOME_WORDS.get(
            ManagerReviewOutcome(review.outcome), "Reviewed"
        ),
        reason=review.reason, evaluation_id=review.evaluation_id,
        created_at=review.created_at.isoformat() if review.created_at else "",
    )


@router.get("/{candidate_id}/reviews", response_model=list[ReviewOut])
def candidate_reviews(campaign_id: str, candidate_id: str, db: Session = Depends(get_db)):
    _require_campaign(db, campaign_id)
    return [
        ReviewOut(
            id=r.id, reviewer_id=r.reviewer_id,
            reviewer_name=_name(db, r.reviewer_id), outcome=r.outcome,
            outcome_label=OUTCOME_WORDS.get(
                ManagerReviewOutcome(r.outcome), "Reviewed"
            ),
            reason=r.reason, evaluation_id=r.evaluation_id,
            created_at=r.created_at.isoformat() if r.created_at else "",
        )
        for r in lifecycle_service.reviews_for(db, campaign_id, candidate_id)
    ]


@router.post("/{candidate_id}/transition", response_model=LifecycleOut)
def move_candidate(campaign_id: str, candidate_id: str, payload: TransitionIn,
                   db: Session = Depends(get_db)):
    _require_campaign(db, campaign_id)
    try:
        record = lifecycle_service.transition(
            db, campaign_id=campaign_id, candidate_id=candidate_id,
            to_status=payload.to_status, actor_id=payload.actor_id,
            reason=payload.reason, owner_id=payload.owner_id,
            on_behalf_of_id=payload.on_behalf_of_id,
        )
    except (LifecycleError, TransitionError) as exc:
        raise _fail(exc) from exc
    return _out(db, record)


@router.post("/{candidate_id}/enter", response_model=LifecycleOut, status_code=201)
def enter_lifecycle(campaign_id: str, candidate_id: str, actor_id: str = Query(...),
                    db: Session = Depends(get_db)):
    _require_campaign(db, campaign_id)
    try:
        record = lifecycle_service.enter(
            db, campaign_id=campaign_id, candidate_id=candidate_id,
            actor_id=actor_id,
        )
    except LifecycleError as exc:
        raise _fail(exc) from exc
    return _out(db, record)


@router.post("/{candidate_id}/waitlist", response_model=LifecycleOut, status_code=201)
def waitlist_candidate(campaign_id: str, candidate_id: str, actor_id: str = Query(...),
                       db: Session = Depends(get_db)):
    """B15: enter a waitlisted candidate as a kept-in-reserve backup."""
    _require_campaign(db, campaign_id)
    try:
        record = lifecycle_service.enter_waitlist(
            db, campaign_id=campaign_id, candidate_id=candidate_id,
            actor_id=actor_id,
        )
    except LifecycleError as exc:
        raise _fail(exc) from exc
    return _out(db, record)


# B15: statuses where the candidate the offer/lifecycle was tracking is no
# longer in the running, and a recruiter would want to know who is next.
_SURFACES_BACKUP = {LifecycleStatus.OFFER_DECLINED, LifecycleStatus.WITHDRAWN}


def _out(db: Session, record) -> LifecycleOut:
    status = LifecycleStatus(record.status)
    held_from = LifecycleStatus(record.held_from_status) if record.held_from_status else None

    backup = None
    if status in _SURFACES_BACKUP:
        backup = lifecycle_service.next_backup_candidate(
            db, record.campaign_id, excluding_candidate_id=record.candidate_id,
        )
    backup_candidate = db.get(Candidate, backup.candidate_id) if backup else None

    return LifecycleOut(
        candidate_id=record.candidate_id,
        status=record.status,
        status_label=lifecycle.words(status),
        owner_id=record.current_owner_id,
        owner_name=_name(db, record.current_owner_id),
        entered_at=record.entered_at.isoformat() if record.entered_at else "",
        due_at=record.due_at.isoformat() if record.due_at else None,
        sla_status=sla_service.sla_status(record),
        next_steps=[
            {"status": s.value, "label": lifecycle.words(s)}
            for s in sorted(lifecycle.targets(status, held_from), key=lambda x: x.value)
        ],
        held_from_status=held_from.value if held_from else None,
        held_from_label=lifecycle.words(held_from) if held_from else "",
        campaign_rank=record.campaign_rank,
        next_backup_candidate_id=backup.candidate_id if backup else None,
        next_backup_candidate_name=backup_candidate.full_name if backup_candidate else "",
        next_backup_rank=backup.campaign_rank if backup else None,
    )


# ---------------------------------------------------------------------------
# SLA — phase 5
# ---------------------------------------------------------------------------

@sla_router.post("/evaluate")
def evaluate_sla(campaign_id: str | None = Query(None), db: Session = Depends(get_db)):
    """
    Send the reminder/escalation audit events newly due, across one campaign
    or all of them. Safe to call repeatedly — nothing here fires twice for
    the same lifecycle row. No scheduler calls this yet; it exists to be
    called by one (or by hand) once B02 phase 5 has an owner for that.
    """
    if campaign_id:
        _require_campaign(db, campaign_id)
    return sla_service.evaluate(db, campaign_id=campaign_id)
