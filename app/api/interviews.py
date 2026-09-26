"""
Interview scheduling and feedback — journey steps 5 and 6.

A hiring manager who wants to proceed asks for an interview. This is the
calendar invite is simulated by default. The local Outlook demo opts in to
real sending, restricted to four approved recipients; the state change and
audit row are real in either mode.

No new tables. Structured detail lives in `AuditEvent.after`, written
through `disposition_service.record_audit`, exactly as the house rule
requires. The state change itself goes through
`lifecycle_service.transition`, which already writes the transition row and
a generic audit row in the same unit of work; this module adds a second,
detail-carrying audit row for `INTERVIEW_SCHEDULED` and
`INTERVIEW_FEEDBACK_RECORDED` so the screen can read interviews back
without a new table.
"""
from __future__ import annotations

import enum
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import lifecycle
from app.core.calendar_adapter import InviteResult, get_calendar_adapter
from app.core.config import settings
from app.core.mail_guard import DEMO_CO_MANAGERS, DEMO_RECIPIENTS
from app.core.outlook_com import resolve_sender_address
from app.core.lifecycle import TransitionError
from app.db.models import AuditAction, AuditEvent, Candidate, LifecycleStatus, User
from app.db.session import get_db
from app.services import auth_service, campaign_service, disposition_service, lifecycle_service
from app.services.lifecycle_service import LifecycleError

router = APIRouter(
    prefix="/api/campaigns/{campaign_id}/interviews", tags=["interviews"],
)


# ---------------------------------------------------------------------------
# Shapes
# ---------------------------------------------------------------------------

class InterviewMode(str, enum.Enum):
    IN_PERSON = "IN_PERSON"
    VIDEO = "VIDEO"
    PHONE = "PHONE"


class InterviewRecommendation(str, enum.Enum):
    PROCEED = "PROCEED"
    ANOTHER_ROUND = "ANOTHER_ROUND"
    DECLINE = "DECLINE"


class ScheduleIn(BaseModel):
    when: datetime
    duration_minutes: int = Field(gt=0)
    mode: InterviewMode
    location_or_link: str = ""
    panel: list[str] = []
    round: int = Field(ge=1)
    actor_id: str
    co_manager_email: str = ""
    recipient_email: str = ""


class FeedbackIn(BaseModel):
    recommendation: InterviewRecommendation
    scores: dict[str, int] = {}
    strengths: str = ""
    concerns: str = ""
    reason: str = ""
    actor_id: str


class RescheduleIn(BaseModel):
    when: datetime
    reason: str = ""
    actor_id: str


class InterviewOut(BaseModel):
    candidate_id: str
    candidate_name: str
    when: str = ""
    mode: str = ""
    round: int = 0
    duration_minutes: int | None = None
    location_or_link: str = ""
    panel: list[str] = []
    feedback_in: bool = False
    recommendation: str | None = None
    invite_simulated: bool | None = None
    invite_sent: bool | None = None
    invite_detail: str | None = None


def _fail(exc: Exception) -> HTTPException:
    return HTTPException(status_code=422, detail=str(exc))


def _require_campaign(db: Session, campaign_id: str):
    campaign = campaign_service.get_campaign(db, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign


def _resolve_panel(db: Session, panel_ids: list[str]) -> list[str]:
    names = []
    for user_id in panel_ids:
        user = db.get(User, user_id)
        names.append(user.full_name if user else user_id)
    return names


def _candidate_name(db: Session, candidate_id: str) -> str:
    candidate = db.get(Candidate, candidate_id)
    return candidate.full_name if candidate else ""



def _approved_attendees(db: Session, actor_id: str, co_manager_email: str, recipient_email: str) -> list[str]:
    co_manager = co_manager_email.strip().lower()
    recipient = recipient_email.strip().lower()

    # B22 phase 1: whoever is logged in (ankush.saxena or subhadeep.m) can
    # pick the OTHER of the two as co-manager, on top of the fixed demo
    # list. This is a login-session convenience only — it does not touch
    # the real Outlook sender resolution below, which follows whichever
    # account this machine is signed in as (see _require_demo_sender).
    allowed_co_managers = set(DEMO_CO_MANAGERS)
    actor = db.get(User, actor_id) if actor_id else None
    actor_email = (actor.email if actor else "") or ""
    actor_email = actor_email.strip().lower()
    counterpart = auth_service.FLIP_COUNTERPART.get(actor_email)
    if counterpart:
        allowed_co_managers.add(counterpart)
    allowed_co_managers.discard(actor_email)

    if co_manager and co_manager not in allowed_co_managers:
        raise HTTPException(status_code=422, detail="Co-hiring manager email is not approved for this demo.")
    if recipient and recipient not in DEMO_RECIPIENTS:
        raise HTTPException(status_code=422, detail="Interview recipient email is not approved for this demo.")
    if settings.calendar_backend == "outlook" and not (co_manager and recipient):
        raise HTTPException(status_code=422, detail="Choose an approved co-hiring manager and interview recipient before sending.")
    if settings.calendar_backend == "outlook" and resolve_sender_address(settings.calendar_sender_email) is None:
        raise HTTPException(
            status_code=422,
            detail="No Outlook account was found to send from. Sign in to Outlook on "
                   "this machine, or set CALENDAR_SENDER_EMAIL.",
        )
    return [address for address in (co_manager, recipient) if address]


def _require_demo_sender(db: Session, actor_id: str) -> None:
    """The person recorded as arranging the meeting must be the person
    whose mailbox it actually sends from — otherwise the audit trail names
    the wrong actor for a real, delivered email.

    The sender is whichever account this machine is signed in as (or the
    explicit CALENDAR_SENDER_EMAIL override) — see `resolve_sender_address`.
    A seeded demo actor (e.g. a fictional interviewer with no real mailbox)
    is rejected here exactly like anyone else who is not that account: it
    is blocked only when calendar_backend is "outlook", so demo runs stay
    on the "simulated" default and are never affected by this guard.
    """
    if settings.calendar_backend != "outlook":
        return
    sender = resolve_sender_address(settings.calendar_sender_email)
    if sender is None:
        raise HTTPException(
            status_code=422,
            detail="No Outlook account was found to send from. Sign in to Outlook on "
                   "this machine, or set CALENDAR_SENDER_EMAIL.",
        )
    actor = db.get(User, actor_id)
    if not actor or (actor.email or "").strip().lower() != sender.lower():
        raise HTTPException(
            status_code=422,
            detail="The arranged-by person must be the resolved Outlook sender account.",
        )


def _send_calendar_invite(
    *, candidate_name: str, role_title: str, mode: str, attendees: list[str],
    when, duration_minutes: int, location_or_link: str, round_: int,
) -> InviteResult:
    """Only explicitly approved demo addresses receive an invite; never CV emails."""
    body = (
        f"Interview for {role_title or 'the role'}\n"
        f"Candidate: {candidate_name or 'Candidate'}\n"
        f"Round: {round_}\n"
        f"Date and time: {when.strftime('%d %b %Y, %I:%M %p')} to "
        f"{(when + timedelta(minutes=duration_minutes)).strftime('%I:%M %p')} "
        "IST (UTC+05:30)\n"
        f"Duration: {duration_minutes} minutes\n"
        f"Mode: {mode.replace('_', ' ').title()}\n"
        f"Location or link: {location_or_link or 'To be shared'}\n"
    )
    return get_calendar_adapter().send_invite(
        subject=f"Interview round {round_}: {candidate_name or 'Candidate'}",
        start=when, duration_minutes=duration_minutes, location=location_or_link,
        required_attendees=attendees, optional_attendees=[], body=body,
    )
    return invite.simulated, invite.detail


# ---------------------------------------------------------------------------
# Reading interviews back out of the audit rows
# ---------------------------------------------------------------------------

def _events(db: Session, action: AuditAction, campaign_id: str | None = None,
           candidate_id: str | None = None) -> list[AuditEvent]:
    statement = select(AuditEvent).where(AuditEvent.action == action)
    if campaign_id is not None:
        statement = statement.where(AuditEvent.campaign_id == campaign_id)
    if candidate_id is not None:
        statement = statement.where(AuditEvent.candidate_id == candidate_id)
    return list(db.scalars(statement.order_by(AuditEvent.created_at.desc())).all())


def _latest_schedule_detail(db: Session, campaign_id: str, candidate_id: str) -> dict | None:
    events = _events(db, AuditAction.INTERVIEW_SCHEDULED, campaign_id, candidate_id)
    return events[0].after if events else None


def _interview_rows(db: Session, campaign_id: str | None = None,
                    candidate_id: str | None = None) -> list[InterviewOut]:
    """
    One row per interview round, newest first. A reschedule updates the
    row it belongs to rather than adding a new one — it is a new time
    against the same round, not a second interview.
    """
    schedules = _events(db, AuditAction.INTERVIEW_SCHEDULED, campaign_id, candidate_id)
    feedbacks = _events(db, AuditAction.INTERVIEW_FEEDBACK_RECORDED, campaign_id, candidate_id)

    latest_schedule: dict[tuple, AuditEvent] = {}
    order: list[tuple] = []
    for event in schedules:  # newest first
        key = (event.candidate_id, (event.after or {}).get("round"))
        if key not in latest_schedule:
            latest_schedule[key] = event
            order.append(key)

    latest_feedback: dict[tuple, AuditEvent] = {}
    for event in feedbacks:
        key = (event.candidate_id, (event.after or {}).get("round"))
        if key not in latest_feedback:
            latest_feedback[key] = event

    rows = []
    for key in order:
        event = latest_schedule[key]
        detail = event.after or {}
        feedback = latest_feedback.get(key)
        rows.append(InterviewOut(
            candidate_id=event.candidate_id or "",
            candidate_name=_candidate_name(db, event.candidate_id or ""),
            when=detail.get("when", ""),
            mode=detail.get("mode", ""),
            round=detail.get("round") or 0,
            duration_minutes=detail.get("duration_minutes"),
            location_or_link=detail.get("location_or_link", ""),
            panel=detail.get("panel_names", []) or [],
            feedback_in=feedback is not None,
            recommendation=(feedback.after or {}).get("recommendation") if feedback else None,
            invite_simulated=detail.get("invite_simulated"),
            invite_sent=detail.get("invite_sent"),
            invite_detail=detail.get("invite_detail"),
        ))
    return rows


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------

@router.get("", response_model=list[InterviewOut])
def campaign_interviews(campaign_id: str, db: Session = Depends(get_db)):
    """Every interview in the campaign, newest first."""
    _require_campaign(db, campaign_id)
    return _interview_rows(db, campaign_id=campaign_id)


@router.get("/{candidate_id}", response_model=list[InterviewOut])
def candidate_interviews(campaign_id: str, candidate_id: str, db: Session = Depends(get_db)):
    """One candidate's interview history."""
    _require_campaign(db, campaign_id)
    return _interview_rows(db, campaign_id=campaign_id, candidate_id=candidate_id)


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------

@router.post("/{candidate_id}/schedule", response_model=InterviewOut, status_code=201)
def schedule_interview(campaign_id: str, candidate_id: str, payload: ScheduleIn,
                       db: Session = Depends(get_db)):
    campaign = _require_campaign(db, campaign_id)
    attendees = _approved_attendees(db, payload.actor_id, payload.co_manager_email, payload.recipient_email)
    _require_demo_sender(db, payload.actor_id)
    record = lifecycle_service.current(db, campaign_id, candidate_id)
    if record and record.status == LifecycleStatus.INTERVIEW_SCHEDULED.value:
        # A manager's PROCEED verdict already moves the candidate into this
        # state. The first actual appointment is still missing at that point.
        latest = _latest_schedule_detail(db, campaign_id, candidate_id)
        if latest and payload.round <= int(latest.get("round") or 0):
            raise _fail(LifecycleError(
                "That interview round is already scheduled. Use reschedule to move it."
            ))
        try:
            acting = lifecycle_service.require_user(db, payload.actor_id,
                                                    what="arrange this interview")
            if acting.role not in lifecycle.WHO_MAY[LifecycleStatus.INTERVIEW_SCHEDULED]:
                raise LifecycleError("This person's role cannot arrange an interview.")
        except LifecycleError as exc:
            raise _fail(exc) from exc
    else:
        try:
            record = lifecycle_service.transition(
                db, campaign_id=campaign_id, candidate_id=candidate_id,
                to_status=LifecycleStatus.INTERVIEW_SCHEDULED, actor_id=payload.actor_id,
            )
        except (LifecycleError, TransitionError) as exc:
            raise _fail(exc) from exc

    panel_names = _resolve_panel(db, payload.panel)
    candidate_name = _candidate_name(db, candidate_id)
    actor = db.get(User, payload.actor_id)
    invite = _send_calendar_invite(
        candidate_name=candidate_name, role_title=campaign.job_title,
        mode=payload.mode.value, attendees=attendees, when=payload.when,
        duration_minutes=payload.duration_minutes,
        location_or_link=payload.location_or_link, round_=payload.round,
    )
    detail = {
        "when": payload.when.isoformat(),
        "duration_minutes": payload.duration_minutes,
        "mode": payload.mode.value,
        "location_or_link": payload.location_or_link,
        "panel": payload.panel,
        "panel_names": panel_names,
        "round": payload.round,
        "co_manager_email": payload.co_manager_email.strip().lower(),
        "recipient_email": payload.recipient_email.strip().lower(),
        "invite_simulated": invite.simulated,
        "invite_sent": invite.sent,
        "invite_detail": invite.detail,
    }
    summary = (
        f"Interview round {payload.round} arranged for "
        f"{candidate_name or 'this candidate'} on {payload.when.isoformat()} "
        f"({payload.mode.value})."
    )
    summary += (" Calendar invite sent via local Outlook." if invite.sent else
                " Calendar invite recorded, not sent.")
    disposition_service.record_audit(
        db, AuditAction.INTERVIEW_SCHEDULED,
        campaign_id=campaign_id, candidate_id=candidate_id,
        entity_type="candidate_lifecycle", entity_id=record.id,
        summary=summary,
        after=detail,
        actor=actor.full_name if actor else "",
    )
    db.commit()
    return InterviewOut(
        candidate_id=candidate_id, candidate_name=candidate_name,
        when=detail["when"], mode=detail["mode"], round=detail["round"],
        duration_minutes=detail["duration_minutes"],
        location_or_link=detail["location_or_link"], panel=panel_names,
        feedback_in=False, recommendation=None,
        invite_simulated=invite.simulated, invite_sent=invite.sent,
        invite_detail=invite.detail,
    )


@router.post("/{candidate_id}/feedback", response_model=InterviewOut)
def record_feedback(campaign_id: str, candidate_id: str, payload: FeedbackIn,
                    db: Session = Depends(get_db)):
    _require_campaign(db, campaign_id)
    if payload.recommendation == InterviewRecommendation.DECLINE and not payload.reason.strip():
        raise _fail(LifecycleError(
            "Declining a candidate after interview needs a reason. It is the "
            "first thing anyone reviewing this decision will look for."
        ))

    schedule_detail = _latest_schedule_detail(db, campaign_id, candidate_id)
    if not schedule_detail:
        raise _fail(LifecycleError(
            "Record the interview schedule before recording feedback."
        ))
    round_ = schedule_detail.get("round")

    try:
        record = lifecycle_service.transition(
            db, campaign_id=campaign_id, candidate_id=candidate_id,
            to_status=LifecycleStatus.FEEDBACK_COMPLETE, actor_id=payload.actor_id,
            reason=payload.reason,
        )
    except (LifecycleError, TransitionError) as exc:
        raise _fail(exc) from exc

    candidate_name = _candidate_name(db, candidate_id)
    actor = db.get(User, payload.actor_id)
    detail = {
        "recommendation": payload.recommendation.value,
        "scores": payload.scores,
        "strengths": payload.strengths,
        "concerns": payload.concerns,
        "reason": payload.reason,
        "round": round_,
    }
    disposition_service.record_audit(
        db, AuditAction.INTERVIEW_FEEDBACK_RECORDED,
        campaign_id=campaign_id, candidate_id=candidate_id,
        entity_type="candidate_lifecycle", entity_id=record.id,
        summary=(
            f"Interview feedback recorded for {candidate_name or 'this candidate'}: "
            f"{payload.recommendation.value.replace('_', ' ').lower()}."
        ),
        after=detail,
        actor=actor.full_name if actor else "",
    )
    db.commit()
    return InterviewOut(
        candidate_id=candidate_id, candidate_name=candidate_name,
        when=schedule_detail.get("when", ""), mode=schedule_detail.get("mode", ""),
        round=round_ or 0,
        duration_minutes=schedule_detail.get("duration_minutes"),
        location_or_link=schedule_detail.get("location_or_link", ""),
        panel=schedule_detail.get("panel_names", []) or [],
        feedback_in=True, recommendation=payload.recommendation.value,
    )


@router.post("/{candidate_id}/reschedule", response_model=InterviewOut)
def reschedule_interview(campaign_id: str, candidate_id: str, payload: RescheduleIn,
                         db: Session = Depends(get_db)):
    """
    A new time against a candidate already scheduled. Not a state change —
    they stay INTERVIEW_SCHEDULED — so this is an audit row only.
    """
    campaign = _require_campaign(db, campaign_id)
    _require_demo_sender(db, payload.actor_id)
    record = lifecycle_service.current(db, campaign_id, candidate_id)
    if record is None or record.status != LifecycleStatus.INTERVIEW_SCHEDULED.value:
        raise _fail(LifecycleError(
            "This candidate is not currently scheduled for interview, so "
            "there is nothing to reschedule."
        ))

    schedule_detail = _latest_schedule_detail(db, campaign_id, candidate_id)
    if not schedule_detail:
        raise _fail(LifecycleError(
            "There is no recorded schedule to move. Arrange the interview first."
        ))
    old_when = schedule_detail.get("when", "")
    candidate_name = _candidate_name(db, candidate_id)
    actor = db.get(User, payload.actor_id) if payload.actor_id else None

    attendees = _approved_attendees(db, payload.actor_id, schedule_detail.get("co_manager_email", ""),
                                    schedule_detail.get("recipient_email", ""))
    invite = _send_calendar_invite(
        candidate_name=candidate_name, role_title=campaign.job_title,
        mode=schedule_detail.get("mode", ""), attendees=attendees, when=payload.when,
        duration_minutes=schedule_detail.get("duration_minutes") or 30,
        location_or_link=schedule_detail.get("location_or_link", ""),
        round_=schedule_detail.get("round") or 0,
    )

    detail = dict(schedule_detail)
    detail["when"] = payload.when.isoformat()
    detail["rescheduled_from"] = old_when
    detail["invite_simulated"] = invite.simulated
    detail["invite_sent"] = invite.sent
    detail["invite_detail"] = invite.detail
    if payload.reason.strip():
        detail["reschedule_reason"] = payload.reason.strip()

    summary = (
        f"Interview for {candidate_name or 'this candidate'} moved from "
        f"{old_when or 'an earlier time'} to {payload.when.isoformat()}."
    )
    summary += (" Updated invite sent via local Outlook." if invite.sent else
                " Updated invite recorded, not sent.")
    disposition_service.record_audit(
        db, AuditAction.INTERVIEW_SCHEDULED,
        campaign_id=campaign_id, candidate_id=candidate_id,
        entity_type="candidate_lifecycle", entity_id=record.id,
        summary=summary,
        after=detail,
        actor=actor.full_name if actor else "",
    )
    db.commit()
    return InterviewOut(
        candidate_id=candidate_id, candidate_name=candidate_name,
        when=detail["when"], mode=detail.get("mode", ""),
        round=detail.get("round") or 0,
        duration_minutes=detail.get("duration_minutes"),
        location_or_link=detail.get("location_or_link", ""),
        panel=detail.get("panel_names", []) or [],
        feedback_in=False, recommendation=None,
        invite_simulated=invite.simulated, invite_sent=invite.sent,
        invite_detail=invite.detail,
    )
