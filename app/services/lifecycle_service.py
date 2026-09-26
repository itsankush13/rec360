"""
The recruitment lifecycle: what happens to a candidate after screening.

Screening ends at a disposition. From there the process runs through the
hiring manager, an interview, approvals and budget sign-off — today in email
and spreadsheets, and therefore not on any record anyone can produce later.

Everything here writes through `disposition_service.record_audit()`. There is
deliberately one audit path in this codebase; two would eventually disagree,
and a record that disagrees with itself is worse than none.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import lifecycle
from app.core.lifecycle import TransitionError
from app.db.models import (
    AuditAction, Campaign, Candidate, CandidateLifecycle, Disposition,
    Evaluation, LifecycleStatus, LifecycleTransition, ManagerReview,
    ManagerReviewOutcome, User, UserRole,
)
from app.services import disposition_service, evaluation_service


class LifecycleError(ValueError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _aware(value: datetime | None) -> datetime | None:
    """SQLite hands back naive datetimes; Postgres will not. Gotcha 3."""
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# People
# ---------------------------------------------------------------------------

def require_user(db: Session, user_id: str | None, *, what: str = "act") -> User:
    """
    Identity, not yet authentication.

    The caller names the acting person and this checks they exist and are
    active. When login lands, what changes is where `user_id` comes from —
    not what depends on it.
    """
    if not user_id:
        raise LifecycleError(
            f"This needs to be recorded against a named person. "
            f"Nobody was given as the person who would {what}."
        )
    user = db.get(User, user_id)
    if user is None:
        raise LifecycleError("That user is not on file.")
    if not user.active:
        raise LifecycleError(
            f"{user.full_name} is no longer active and cannot {what}."
        )
    return user


def create_user(db: Session, *, full_name: str, email: str, role: UserRole,
                business_unit: str = "") -> User:
    existing = db.scalars(select(User).where(User.email == email)).first()
    if existing is not None:
        raise LifecycleError(f"Someone is already on file with the address {email}.")
    user = User(
        full_name=full_name.strip(), email=email.strip().lower(),
        role=role, business_unit=business_unit.strip(),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def list_users(db: Session, role: UserRole | None = None) -> list[User]:
    statement = select(User).where(User.active.is_(True)).order_by(User.full_name)
    if role is not None:
        statement = statement.where(User.role == role)
    return list(db.scalars(statement).all())


def update_user_role(db: Session, user_id: str, *, role: UserRole) -> User:
    """
    Change who a person is allowed to act as. Every `WHO_MAY` set in
    `app/core/lifecycle.py` that names `RECRUITER` also names `ADMIN` (never
    the reverse), so widening a recruiter to admin never removes a
    capability they already had — only a narrowing (e.g. to `HIRING_MANAGER`)
    can.
    """
    user = db.get(User, user_id)
    if user is None:
        raise LifecycleError("That user is not on file.")
    user.role = role
    db.flush()
    return user


# ---------------------------------------------------------------------------
# Where a candidate is
# ---------------------------------------------------------------------------

def current(db: Session, campaign_id: str, candidate_id: str) -> CandidateLifecycle | None:
    return db.scalars(
        select(CandidateLifecycle).where(
            CandidateLifecycle.campaign_id == campaign_id,
            CandidateLifecycle.candidate_id == candidate_id,
            CandidateLifecycle.is_current.is_(True),
        )
    ).first()


def timeline(db: Session, campaign_id: str, candidate_id: str) -> list[LifecycleTransition]:
    """Oldest first — a timeline is read forwards."""
    return list(db.scalars(
        select(LifecycleTransition).where(
            LifecycleTransition.campaign_id == campaign_id,
            LifecycleTransition.candidate_id == candidate_id,
        ).order_by(LifecycleTransition.created_at)
    ).all())


def statuses_for_campaign(db: Session, campaign_id: str) -> dict[str, CandidateLifecycle]:
    """Every candidate's current position, keyed by candidate — one query."""
    rows = db.scalars(
        select(CandidateLifecycle).where(
            CandidateLifecycle.campaign_id == campaign_id,
            CandidateLifecycle.is_current.is_(True),
        )
    ).all()
    return {row.candidate_id: row for row in rows}


def funnel(db: Session, campaign_id: str) -> list[dict]:
    """
    How many candidates sit at each state, in plain English, in stage order.

    Every stage is returned, including the ones nobody is in. `X11`: this used
    to sort by count and drop the empty stages, which made the pipeline
    reorder itself whenever somebody moved and hid the gaps entirely. An empty
    stage is a finding, not a nothing.
    """
    counts: dict[str, int] = {}
    for row in statuses_for_campaign(db, campaign_id).values():
        key = getattr(row.status, "value", row.status)
        counts[key] = counts.get(key, 0) + 1
    total = sum(counts.values())
    return [
        {
            "status": status.value,
            "label": lifecycle.words(status),
            "count": counts.get(status.value, 0),
            # Never a count without its denominator.
            "of": total,
            # So a chart can draw the spine and the off-ramps differently
            # without having to know the state machine.
            "off_ramp": status in lifecycle.OFF_RAMP,
        }
        for status in lifecycle.STAGE_ORDER
    ]


# ---------------------------------------------------------------------------
# Moving
# ---------------------------------------------------------------------------

def enter(db: Session, *, campaign_id: str, candidate_id: str, actor_id: str | None,
          reason: str = "") -> CandidateLifecycle:
    """
    Put a shortlisted candidate into the lifecycle.

    Only a candidate the recruiter decided to take forward enters. A
    rejection at screening never does — the lifecycle is a record of a hiring
    process, not of everyone who applied.
    """
    existing = current(db, campaign_id, candidate_id)
    if existing is not None:
        return existing

    action = disposition_service.current_action(db, candidate_id)
    if action is None or action.disposition not in (
        Disposition.SHORTLIST, Disposition.INTERVIEW,
    ):
        raise LifecycleError(
            "Only a candidate who has been shortlisted or put forward for "
            "interview enters the hiring process."
        )

    return _write(
        db, campaign_id=campaign_id, candidate_id=candidate_id,
        from_status=None, to_status=LifecycleStatus.SHORTLISTED,
        actor_id=actor_id, reason=reason, owner_id=actor_id,
        campaign_rank=evaluation_service.rank_of(db, campaign_id, candidate_id),
    )


def enter_waitlist(db: Session, *, campaign_id: str, candidate_id: str,
                   actor_id: str | None, reason: str = "") -> CandidateLifecycle:
    """
    Put a waitlisted candidate into the lifecycle as a kept-in-reserve backup.

    B15: preserved alongside the active pipeline rather than rejected
    outright, so a later decline or no-show has someone ranked to fall back
    to. Same entry gate as `enter()` — only a recruiter's explicit decision
    admits a candidate, never a screening score alone.
    """
    existing = current(db, campaign_id, candidate_id)
    if existing is not None:
        return existing

    action = disposition_service.current_action(db, candidate_id)
    if action is None or action.disposition != Disposition.WAITLIST:
        raise LifecycleError(
            "Only a candidate a recruiter has explicitly waitlisted enters "
            "the hiring process as a backup."
        )

    return _write(
        db, campaign_id=campaign_id, candidate_id=candidate_id,
        from_status=None, to_status=LifecycleStatus.WAITLISTED,
        actor_id=actor_id, reason=reason, owner_id=actor_id,
        campaign_rank=evaluation_service.rank_of(db, campaign_id, candidate_id),
    )


def waitlisted_candidates(db: Session, campaign_id: str) -> list[CandidateLifecycle]:
    """
    Current backups for this campaign, best rank first.

    A rank of None (no completed evaluation to rank against) sorts last —
    it is not evidence of a worse candidate, just an absent measurement.
    """
    rows = db.scalars(
        select(CandidateLifecycle).where(
            CandidateLifecycle.campaign_id == campaign_id,
            CandidateLifecycle.is_current.is_(True),
            CandidateLifecycle.status == LifecycleStatus.WAITLISTED.value,
        )
    ).all()
    return sorted(
        rows,
        key=lambda row: (row.campaign_rank is None, row.campaign_rank or 0),
    )


def hired_candidates(db: Session, campaign_id: str) -> list[CandidateLifecycle]:
    """
    Everyone currently HIRED in this campaign, best shortlist rank first —
    B19's basis for a quality-of-hire proxy. `campaign_rank` is the rank
    stored at shortlist/waitlist entry (B15), never recomputed later, so this
    reflects what the AI actually ranked them at when the decision was made,
    not a rank a later re-evaluation might imply.
    """
    rows = db.scalars(
        select(CandidateLifecycle).where(
            CandidateLifecycle.campaign_id == campaign_id,
            CandidateLifecycle.is_current.is_(True),
            CandidateLifecycle.status == LifecycleStatus.HIRED.value,
        )
    ).all()
    return sorted(
        rows,
        key=lambda row: (row.campaign_rank is None, row.campaign_rank or 0),
    )


def next_backup_candidate(
    db: Session, campaign_id: str, *, excluding_candidate_id: str | None = None,
) -> CandidateLifecycle | None:
    """
    B15: who to fall back to when a selected candidate declines or does not
    join — the best-ranked candidate still waitlisted for this campaign.
    """
    for row in waitlisted_candidates(db, campaign_id):
        if row.candidate_id != excluding_candidate_id:
            return row
    return None


def transition(db: Session, *, campaign_id: str, candidate_id: str,
               to_status: LifecycleStatus, actor_id: str,
               reason: str = "", owner_id: str | None = None,
               on_behalf_of_id: str | None = None,
               cost_centre_id: str | None = None) -> CandidateLifecycle:
    """Move a candidate, or refuse and say why in words."""
    actor = require_user(db, actor_id, what="move this candidate")
    record = current(db, campaign_id, candidate_id)
    if record is None:
        raise LifecycleError(
            "This candidate is not in the hiring process yet. Shortlist them "
            "first."
        )

    from_status = LifecycleStatus(record.status)
    held_from = LifecycleStatus(record.held_from_status) if record.held_from_status else None

    lifecycle.check(
        from_status, to_status, role=actor.role, reason=reason, held_from=held_from,
    )

    return _write(
        db, campaign_id=campaign_id, candidate_id=candidate_id,
        from_status=from_status, to_status=to_status, actor_id=actor_id,
        reason=reason, owner_id=owner_id, on_behalf_of_id=on_behalf_of_id,
        held_from=from_status if to_status == LifecycleStatus.ON_HOLD else None,
        cost_centre_id=cost_centre_id,
    )


def _write(db: Session, *, campaign_id: str, candidate_id: str,
           from_status: LifecycleStatus | None, to_status: LifecycleStatus,
           actor_id: str | None, reason: str = "", owner_id: str | None = None,
           on_behalf_of_id: str | None = None,
           held_from: LifecycleStatus | None = None,
           campaign_rank: int | None = None,
           cost_centre_id: str | None = None) -> CandidateLifecycle:
    """
    Supersede rather than edit, exactly as `candidate_actions` does. The
    sequence of positions is itself evidence.
    """
    previous = current(db, campaign_id, candidate_id)
    if previous is not None:
        previous.is_current = False
        # B15: a rank recorded when this candidate entered carries forward
        # to every later position of theirs in this campaign, rather than
        # being lost the moment they move past the row that captured it.
        if campaign_rank is None:
            campaign_rank = previous.campaign_rank
        # B13: same rule for the cost centre a hire is against — set once at
        # PENDING_COST_CENTRE, then carried on every later transition rather
        # than lost the moment the candidate moves past that row.
        if cost_centre_id is None:
            cost_centre_id = previous.cost_centre_id

    entered_at = _now()
    target_hours = lifecycle.sla_target_hours(to_status)
    record = CandidateLifecycle(
        campaign_id=campaign_id, candidate_id=candidate_id,
        status=to_status.value, current_owner_id=owner_id,
        entered_at=entered_at,
        # B02 phase 5: null means no clock is running — every state in
        # `CLOCK_STOPPED` and any state with no SLA policy stays null here.
        due_at=(entered_at + timedelta(hours=target_hours)) if target_hours else None,
        held_from_status=(held_from.value if held_from else None),
        campaign_rank=campaign_rank,
        cost_centre_id=cost_centre_id,
        is_current=True,
    )
    db.add(record)

    db.add(LifecycleTransition(
        campaign_id=campaign_id, candidate_id=candidate_id,
        from_status=(from_status.value if from_status else None),
        to_status=to_status.value, actor_id=actor_id,
        on_behalf_of_id=on_behalf_of_id, reason=reason.strip(),
    ))
    db.flush()

    actor = db.get(User, actor_id) if actor_id else None
    candidate = db.get(Candidate, candidate_id)
    name = candidate.full_name if candidate else "A candidate"
    moved = (
        f"{name} moved from {lifecycle.words(from_status).lower()} to "
        f"{lifecycle.words(to_status).lower()}"
        if from_status else
        f"{name} entered the hiring process as "
        f"{lifecycle.words(to_status).lower()}"
    )

    action = {
        LifecycleStatus.WITH_HIRING_MANAGER: AuditAction.SENT_TO_HIRING_MANAGER,
        LifecycleStatus.ON_HOLD: AuditAction.PUT_ON_HOLD,
        LifecycleStatus.WITHDRAWN: AuditAction.CANDIDATE_WITHDREW,
        LifecycleStatus.HIRED: AuditAction.CANDIDATE_HIRED,
    }.get(to_status, AuditAction.STATUS_CHANGED)

    disposition_service.record_audit(
        db, action,
        campaign_id=campaign_id, candidate_id=candidate_id,
        entity_type="candidate_lifecycle", entity_id=record.id,
        summary=moved + (f". Reason: {reason.strip()}" if reason.strip() else "."),
        before={"stage": lifecycle.words(from_status)} if from_status else None,
        after={"stage": lifecycle.words(to_status)},
        actor=(actor.full_name if actor else ""),
    )

    db.commit()
    db.refresh(record)
    return record


# ---------------------------------------------------------------------------
# Handover and review
# ---------------------------------------------------------------------------

def send_to_hiring_manager(db: Session, *, campaign_id: str, candidate_id: str,
                           actor_id: str, manager_id: str,
                           note: str = "") -> CandidateLifecycle:
    """Hand a shortlisted candidate to a named manager. Not to a role."""
    manager = require_user(db, manager_id, what="review this candidate")
    if manager.role not in (UserRole.HIRING_MANAGER, UserRole.ADMIN):
        raise LifecycleError(
            f"{manager.full_name} is not a hiring manager, so this candidate "
            "cannot be sent to them for review."
        )

    enter(db, campaign_id=campaign_id, candidate_id=candidate_id, actor_id=actor_id)
    return transition(
        db, campaign_id=campaign_id, candidate_id=candidate_id,
        to_status=LifecycleStatus.WITH_HIRING_MANAGER, actor_id=actor_id,
        reason=note, owner_id=manager.id,
    )


def record_manager_review(db: Session, *, campaign_id: str, candidate_id: str,
                          reviewer_id: str, outcome: ManagerReviewOutcome,
                          reason: str = "") -> ManagerReview:
    """
    The hiring manager's verdict, against the assessment they were shown.

    A decline needs a reason. It is the first thing anyone reviewing this
    decision looks for, and optional means empty.
    """
    reviewer = require_user(db, reviewer_id, what="review this candidate")
    if reviewer.role not in (UserRole.HIRING_MANAGER, UserRole.ADMIN):
        raise LifecycleError(
            f"{reviewer.full_name} is not a hiring manager and cannot record "
            "this review."
        )

    record = current(db, campaign_id, candidate_id)
    if record is None or record.status != LifecycleStatus.WITH_HIRING_MANAGER.value:
        raise LifecycleError(
            "This candidate is not currently with a hiring manager."
        )

    if outcome in (ManagerReviewOutcome.DECLINE, ManagerReviewOutcome.QUESTION) \
            and not reason.strip():
        raise LifecycleError(
            "A decision to decline or to ask a question needs a reason."
        )

    evaluation = db.scalars(
        select(Evaluation).where(
            Evaluation.candidate_id == candidate_id,
            Evaluation.campaign_id == campaign_id,
            Evaluation.is_current.is_(True),
        )
    ).first()

    review = ManagerReview(
        campaign_id=campaign_id, candidate_id=candidate_id,
        # Pinned to the assessment on screen at the time, so a later
        # re-assessment cannot retrospectively change what was decided on.
        evaluation_id=(evaluation.id if evaluation else None),
        reviewer_id=reviewer.id, outcome=outcome.value, reason=reason.strip(),
    )
    db.add(review)
    db.flush()

    candidate = db.get(Candidate, candidate_id)
    words = {
        ManagerReviewOutcome.PROCEED: "wants to interview",
        ManagerReviewOutcome.DECLINE: "does not want to proceed with",
        ManagerReviewOutcome.QUESTION: "has a question about",
    }[outcome]
    disposition_service.record_audit(
        db, AuditAction.MANAGER_REVIEWED,
        campaign_id=campaign_id, candidate_id=candidate_id,
        entity_type="manager_review", entity_id=review.id,
        summary=(
            f"{reviewer.full_name} {words} "
            f"{candidate.full_name if candidate else 'this candidate'}"
            + (f". Reason: {reason.strip()}" if reason.strip() else ".")
        ),
        after={"outcome": words},
        actor=reviewer.full_name,
    )
    db.commit()

    next_status = {
        ManagerReviewOutcome.PROCEED: LifecycleStatus.INTERVIEW_SCHEDULED,
        ManagerReviewOutcome.DECLINE: LifecycleStatus.NOT_PROCEEDING,
        ManagerReviewOutcome.QUESTION: LifecycleStatus.RETURNED_TO_RECRUITER,
    }[outcome]
    transition(
        db, campaign_id=campaign_id, candidate_id=candidate_id,
        to_status=next_status, actor_id=reviewer.id, reason=reason,
        owner_id=(None if next_status == LifecycleStatus.NOT_PROCEEDING else None),
    )

    db.refresh(review)
    return review


def reviews_for(db: Session, campaign_id: str, candidate_id: str) -> list[ManagerReview]:
    return list(db.scalars(
        select(ManagerReview).where(
            ManagerReview.campaign_id == campaign_id,
            ManagerReview.candidate_id == candidate_id,
        ).order_by(ManagerReview.created_at)
    ).all())
