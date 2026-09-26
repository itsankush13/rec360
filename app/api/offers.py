"""
The offer: drafted, sent, and the candidate's answer.

Journey steps 8 and 9 of the recruitment lifecycle. This is the step with
money at the end of it, so it is the one an auditor reads first.

There is no new table for an offer. Every draft, send and response is a
structured `AuditEvent` written through `disposition_service.record_audit` —
one audit path, per the rule in `disposition_service`. The state itself
(`APPROVED` -> `OFFER_DRAFTED` -> `OFFER_SENT` -> `OFFER_ACCEPTED` /
`OFFER_DECLINED`) is real, moved through `lifecycle_service.transition`, so
the state machine's role checks and reason rules apply exactly as they do
everywhere else.

B12: a draft/revise now renders an approved offer letter (`offer_letter.py`)
from the same payload — that rendered text is the "draft for HR review",
carried in the audit `after.letter` alongside the package numbers. Sending
reuses the same `outlook_adapter.get_mail_adapter()` B10 built for messages:
simulated by default, a real local-Outlook send only when
`settings.email_backend == "outlook"`.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core import lifecycle
from app.core.lifecycle import TransitionError
from app.core.config import settings
from app.core.mail_guard import ensure_approved_mail_recipients
from app.core.offer_letter import render_offer_letter
from app.core.outlook_adapter import get_mail_adapter
from app.db.models import AuditAction, Campaign, Candidate, LifecycleStatus, User
from app.db.session import get_db
from app.services import disposition_service, lifecycle_service
from app.services.lifecycle_service import LifecycleError

router = APIRouter(
    prefix="/api/campaigns/{campaign_id}/offers", tags=["offers"],
)

# A decline is counted later, so the reason is a code from a fixed list, not
# free text somebody has to read one at a time.
DECLINE_REASON_CODES = {
    "COMPENSATION", "COUNTER_OFFER", "LOCATION", "TIMING", "ROLE_SCOPE", "OTHER",
}


class OfferError(ValueError):
    """Caller-fixable; refused in words a person can act on."""


def _fail(exc: Exception) -> HTTPException:
    return HTTPException(status_code=422, detail=str(exc))


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _require_candidate(db: Session, campaign_id: str, candidate_id: str) -> Candidate:
    candidate = db.get(Candidate, candidate_id)
    if candidate is None or candidate.campaign_id != campaign_id:
        raise OfferError(f"Candidate '{candidate_id}' is not in campaign '{campaign_id}'.")
    return candidate


def _require_campaign(db: Session, campaign_id: str) -> Campaign:
    campaign = db.get(Campaign, campaign_id)
    if campaign is None:
        raise OfferError(f"Campaign '{campaign_id}' not found.")
    return campaign


# ---------------------------------------------------------------------------
# Shapes
# ---------------------------------------------------------------------------

class OfferDraftIn(BaseModel):
    actor_id: str
    base_salary: float
    currency: str = "QAR"
    grade: str = ""
    start_date: date
    expiry_date: date
    allowances: dict[str, float] = Field(default_factory=dict)
    notes: str = ""


class OfferOut(BaseModel):
    candidate_id: str
    status: str
    status_label: str
    base_salary: float
    currency: str
    grade: str
    start_date: str
    expiry_date: str
    allowances: dict
    notes: str
    total_package: float
    letter: str
    revision_of: str | None = None
    changed: dict | None = None


class OfferSendIn(BaseModel):
    actor_id: str
    # A demo candidate's CV-extracted address is never an approved real
    # recipient, so with EMAIL_BACKEND=outlook the offer could not be sent
    # at all. comms.html already solves this with a proxy picker; this is
    # the same idea. Blank keeps the old behaviour (the candidate's own
    # address), and the allowlist below still judges whatever is chosen.
    recipient: str = ""


class OfferSentOut(BaseModel):
    candidate_id: str
    status: str
    status_label: str
    recipient_email: str
    sent_at: str
    draft: dict
    simulated: bool = True
    send_detail: str | None = None


class OfferResponseIn(BaseModel):
    actor_id: str
    response: str  # "ACCEPTED" | "DECLINED"
    reason: str = ""
    reason_code: str | None = None


class OfferResponseOut(BaseModel):
    candidate_id: str
    status: str
    status_label: str
    response: str
    reason: str
    reason_code: str | None
    recorded_at: str
    # B15: populated only on a decline — the best-ranked candidate still
    # waitlisted for this campaign, so the recruiter is told who to fall
    # back to in the same response as the decline itself. None means
    # nobody is in reserve.
    next_backup_candidate_id: str | None = None
    next_backup_candidate_name: str = ""
    next_backup_rank: int | None = None


class OfferSummaryOut(BaseModel):
    candidate_id: str
    candidate_name: str
    status: str
    status_label: str
    currency: str
    base_salary: float
    total_package: float
    expiry_date: str | None
    days_until_expiry: int | None
    sent_at: str | None
    days_since_sent: int | None
    response: str | None
    response_reason: str | None
    response_reason_code: str | None


class OfferEventOut(BaseModel):
    action: str
    created_at: str
    after: dict


class OfferHistoryOut(BaseModel):
    candidate_id: str
    candidate_name: str
    status: str
    status_label: str
    events: list[OfferEventOut]


# ---------------------------------------------------------------------------
# Draft validation
# ---------------------------------------------------------------------------

def _validate_draft(payload: OfferDraftIn) -> None:
    if payload.base_salary <= 0:
        raise OfferError("The base salary must be a positive amount.")
    if payload.start_date <= date.today():
        raise OfferError("The offer's start date must be in the future.")
    if payload.expiry_date >= payload.start_date:
        raise OfferError(
            "The offer must expire before the candidate's start date."
        )


def _draft_after(payload: OfferDraftIn, *, candidate_name: str, role: str,
                  actor_name: str) -> dict:
    total_package = payload.base_salary + sum(payload.allowances.values())
    letter = render_offer_letter(
        candidate_name=candidate_name, role=role, company=settings.company_name,
        base_salary=payload.base_salary, currency=payload.currency,
        allowances=payload.allowances, total_package=total_package,
        grade=payload.grade, start_date=payload.start_date.isoformat(),
        expiry_date=payload.expiry_date.isoformat(), notes=payload.notes,
        hr_name=actor_name or "Human Resources",
    )
    return {
        "base_salary": payload.base_salary,
        "currency": payload.currency,
        "grade": payload.grade,
        "start_date": payload.start_date.isoformat(),
        "expiry_date": payload.expiry_date.isoformat(),
        "allowances": payload.allowances,
        "notes": payload.notes,
        "total_package": total_package,
        "letter": letter,
    }


def _offer_out(candidate_id: str, status: LifecycleStatus, after: dict) -> OfferOut:
    return OfferOut(
        candidate_id=candidate_id,
        status=status.value,
        status_label=lifecycle.words(status),
        base_salary=after["base_salary"],
        currency=after["currency"],
        grade=after["grade"],
        start_date=after["start_date"],
        expiry_date=after["expiry_date"],
        allowances=after["allowances"],
        notes=after["notes"],
        total_package=after["total_package"],
        letter=after.get("letter", ""),
        revision_of=after.get("revision_of"),
        changed=after.get("changed"),
    )


def _latest(db: Session, campaign_id: str, candidate_id: str, action: AuditAction):
    events = disposition_service.audit_trail(
        db, campaign_id, action=action, candidate_id=candidate_id, limit=1,
    )
    return events[0] if events else None


# ---------------------------------------------------------------------------
# Draft and revise
# ---------------------------------------------------------------------------

@router.post("/{candidate_id}/draft", response_model=OfferOut, status_code=201)
def draft_offer(campaign_id: str, candidate_id: str, payload: OfferDraftIn,
                db: Session = Depends(get_db)):
    candidate = _require_candidate(db, campaign_id, candidate_id)
    campaign = _require_campaign(db, campaign_id)
    try:
        _validate_draft(payload)
        record = lifecycle_service.transition(
            db, campaign_id=campaign_id, candidate_id=candidate_id,
            to_status=LifecycleStatus.OFFER_DRAFTED, actor_id=payload.actor_id,
        )
    except (OfferError, LifecycleError, TransitionError) as exc:
        raise _fail(exc) from exc

    actor = db.get(User, payload.actor_id)
    after = _draft_after(
        payload, candidate_name=candidate.full_name, role=campaign.job_title,
        actor_name=actor.full_name if actor else "",
    )
    disposition_service.record_audit(
        db, AuditAction.OFFER_DRAFTED,
        campaign_id=campaign_id, candidate_id=candidate_id,
        entity_type="offer", entity_id=candidate_id,
        summary=f"Offer drafted: {after['currency']} {after['total_package']:,.2f} total package.",
        after=after,
        actor=(actor.full_name if actor else ""),
    )
    db.commit()

    status = LifecycleStatus(record.status)
    return _offer_out(candidate_id, status, after)


@router.post("/{candidate_id}/revise", response_model=OfferOut)
def revise_offer(campaign_id: str, candidate_id: str, payload: OfferDraftIn,
                 db: Session = Depends(get_db)):
    candidate = _require_candidate(db, campaign_id, candidate_id)
    campaign = _require_campaign(db, campaign_id)
    try:
        actor = lifecycle_service.require_user(db, payload.actor_id, what="revise this offer")
        record = lifecycle_service.current(db, campaign_id, candidate_id)
        if record is None or record.status != LifecycleStatus.OFFER_DRAFTED.value:
            raise OfferError(
                "This candidate does not have a drafted offer to revise."
            )
        permitted = lifecycle.WHO_MAY.get(LifecycleStatus.OFFER_DRAFTED)
        if permitted is not None and actor.role not in permitted:
            raise OfferError(
                "Your role does not allow you to revise an offer."
            )
        _validate_draft(payload)
    except (OfferError, LifecycleError) as exc:
        raise _fail(exc) from exc

    previous = _latest(db, campaign_id, candidate_id, AuditAction.OFFER_DRAFTED)
    after = _draft_after(
        payload, candidate_name=candidate.full_name, role=campaign.job_title,
        actor_name=actor.full_name,
    )

    changed: dict = {}
    if previous is not None and previous.after:
        for field in ("base_salary", "currency", "grade", "start_date",
                      "expiry_date", "allowances", "notes", "total_package"):
            old = previous.after.get(field)
            new = after.get(field)
            if old != new:
                changed[field] = {"old": old, "new": new}
        after["revision_of"] = previous.id

    after["changed"] = changed

    disposition_service.record_audit(
        db, AuditAction.OFFER_DRAFTED,
        campaign_id=campaign_id, candidate_id=candidate_id,
        entity_type="offer", entity_id=candidate_id,
        summary=(
            f"Offer revised: {after['currency']} {after['total_package']:,.2f} "
            "total package."
        ),
        after=after,
        actor=actor.full_name,
    )
    db.commit()

    return _offer_out(candidate_id, LifecycleStatus.OFFER_DRAFTED, after)


# ---------------------------------------------------------------------------
# Send
# ---------------------------------------------------------------------------

@router.post("/{candidate_id}/send", response_model=OfferSentOut)
def send_offer(campaign_id: str, candidate_id: str, payload: OfferSendIn,
               db: Session = Depends(get_db)):
    candidate = _require_candidate(db, campaign_id, candidate_id)
    campaign = _require_campaign(db, campaign_id)
    try:
        recipient = (payload.recipient or candidate.email or "").strip()
        if not recipient:
            raise OfferError(
                "This candidate has no email on file, so the offer letter "
                "cannot be recorded as sent."
            )
        # The allowlist is checked BEFORE the transition on purpose. It used
        # to run after, so a rejected recipient still left the candidate
        # recorded as OFFER_SENT with no letter ever sent — the record
        # claimed a send that did not happen.
        ensure_approved_mail_recipients(to_address=recipient)
        record = lifecycle_service.transition(
            db, campaign_id=campaign_id, candidate_id=candidate_id,
            to_status=LifecycleStatus.OFFER_SENT, actor_id=payload.actor_id,
        )
    except (OfferError, LifecycleError, TransitionError) as exc:
        raise _fail(exc) from exc

    draft = _latest(db, campaign_id, candidate_id, AuditAction.OFFER_DRAFTED)
    draft_after = draft.after if draft else {}
    letter = draft_after.get("letter", "")
    sent_at = _now()
    actor = db.get(User, payload.actor_id)

    transmission = get_mail_adapter().send(
        to_address=recipient, subject=f"Offer for {campaign.job_title}", body=letter,
    )
    simulated = transmission.simulated
    send_detail = transmission.detail

    summary = f"Offer letter recorded as sent to {recipient}."
    if not transmission.simulated:
        summary += " (sent via local Outlook)"
    disposition_service.record_audit(
        db, AuditAction.OFFER_SENT,
        campaign_id=campaign_id, candidate_id=candidate_id,
        entity_type="offer", entity_id=candidate_id,
        summary=summary,
        after={"recipient_email": recipient, "draft": draft_after,
               "sent_at": sent_at.isoformat(),
               "simulated": simulated, "send_detail": send_detail},
        actor=(actor.full_name if actor else ""),
    )
    db.commit()

    status = LifecycleStatus(record.status)
    return OfferSentOut(
        candidate_id=candidate_id, status=status.value,
        status_label=lifecycle.words(status), recipient_email=recipient,
        sent_at=sent_at.isoformat(), draft=draft_after,
        simulated=simulated, send_detail=send_detail,
    )


# ---------------------------------------------------------------------------
# Response
# ---------------------------------------------------------------------------

_RESPONSE_TARGETS = {
    "ACCEPTED": LifecycleStatus.OFFER_ACCEPTED,
    "DECLINED": LifecycleStatus.OFFER_DECLINED,
}


@router.post("/{candidate_id}/response", response_model=OfferResponseOut)
def record_offer_response(campaign_id: str, candidate_id: str,
                          payload: OfferResponseIn, db: Session = Depends(get_db)):
    _require_candidate(db, campaign_id, candidate_id)
    target = _RESPONSE_TARGETS.get(payload.response)
    if target is None:
        raise _fail(OfferError(
            "A candidate's response must be recorded as accepted or declined."
        ))
    if target == LifecycleStatus.OFFER_DECLINED and (
        not payload.reason_code or payload.reason_code not in DECLINE_REASON_CODES
    ):
        raise _fail(OfferError(
            "A decline needs a reason code, so declines can be counted later."
        ))

    try:
        record = lifecycle_service.transition(
            db, campaign_id=campaign_id, candidate_id=candidate_id,
            to_status=target, actor_id=payload.actor_id, reason=payload.reason,
        )
    except (LifecycleError, TransitionError) as exc:
        raise _fail(exc) from exc

    recorded_at = _now()
    actor = db.get(User, payload.actor_id)
    reason_code = payload.reason_code if target == LifecycleStatus.OFFER_DECLINED else None
    disposition_service.record_audit(
        db, AuditAction.OFFER_RESPONSE_RECORDED,
        campaign_id=campaign_id, candidate_id=candidate_id,
        entity_type="offer", entity_id=candidate_id,
        summary=f"Candidate response recorded: {payload.response.lower()}.",
        after={"response": payload.response, "reason": payload.reason,
               "reason_code": reason_code},
        actor=(actor.full_name if actor else ""),
    )
    db.commit()

    status = LifecycleStatus(record.status)
    backup = None
    if target == LifecycleStatus.OFFER_DECLINED:
        backup = lifecycle_service.next_backup_candidate(
            db, campaign_id, excluding_candidate_id=candidate_id,
        )
    backup_candidate = db.get(Candidate, backup.candidate_id) if backup else None

    return OfferResponseOut(
        candidate_id=candidate_id, status=status.value,
        status_label=lifecycle.words(status), response=payload.response,
        reason=payload.reason, reason_code=reason_code,
        recorded_at=recorded_at.isoformat(),
        next_backup_candidate_id=backup.candidate_id if backup else None,
        next_backup_candidate_name=backup_candidate.full_name if backup_candidate else "",
        next_backup_rank=backup.campaign_rank if backup else None,
    )


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------

@router.get("", response_model=list[OfferSummaryOut])
def campaign_offers(campaign_id: str, db: Session = Depends(get_db)):
    draft_events = disposition_service.audit_trail(
        db, campaign_id, action=AuditAction.OFFER_DRAFTED, limit=1000,
    )
    seen: set[str] = set()
    candidate_ids: list[str] = []
    for event in draft_events:
        if event.candidate_id and event.candidate_id not in seen:
            seen.add(event.candidate_id)
            candidate_ids.append(event.candidate_id)

    now = _now()
    out: list[OfferSummaryOut] = []
    for candidate_id in candidate_ids:
        candidate = db.get(Candidate, candidate_id)
        record = lifecycle_service.current(db, campaign_id, candidate_id)
        if record is None:
            continue
        status = LifecycleStatus(record.status)

        draft = _latest(db, campaign_id, candidate_id, AuditAction.OFFER_DRAFTED)
        after = draft.after if draft and draft.after else {}
        sent = _latest(db, campaign_id, candidate_id, AuditAction.OFFER_SENT)
        response = _latest(db, campaign_id, candidate_id, AuditAction.OFFER_RESPONSE_RECORDED)

        sent_at = sent.created_at if sent else None
        days_since_sent = (now - sent_at).days if sent_at else None
        expiry_date = after.get("expiry_date")
        days_until_expiry = (
            (date.fromisoformat(expiry_date) - now.date()).days
            if expiry_date else None
        )

        out.append(OfferSummaryOut(
            candidate_id=candidate_id,
            candidate_name=candidate.full_name if candidate else "",
            status=status.value, status_label=lifecycle.words(status),
            currency=after.get("currency", "QAR"),
            base_salary=after.get("base_salary", 0.0),
            total_package=after.get("total_package", 0.0),
            expiry_date=expiry_date, days_until_expiry=days_until_expiry,
            sent_at=sent_at.isoformat() if sent_at else None,
            days_since_sent=days_since_sent,
            response=(response.after or {}).get("response") if response else None,
            response_reason=(response.after or {}).get("reason") if response else None,
            response_reason_code=(response.after or {}).get("reason_code") if response else None,
        ))
    return out


@router.get("/{candidate_id}", response_model=OfferHistoryOut)
def candidate_offer_history(campaign_id: str, candidate_id: str,
                            db: Session = Depends(get_db)):
    candidate = _require_candidate(db, campaign_id, candidate_id)
    record = lifecycle_service.current(db, campaign_id, candidate_id)
    if record is None:
        raise HTTPException(
            status_code=404,
            detail="This candidate is not in the hiring process yet.",
        )
    status = LifecycleStatus(record.status)

    events = []
    for action in (AuditAction.OFFER_DRAFTED, AuditAction.OFFER_SENT,
                   AuditAction.OFFER_RESPONSE_RECORDED):
        events.extend(disposition_service.audit_trail(
            db, campaign_id, action=action, candidate_id=candidate_id, limit=1000,
        ))
    events.sort(key=lambda e: e.created_at)

    return OfferHistoryOut(
        candidate_id=candidate_id, candidate_name=candidate.full_name,
        status=status.value, status_label=lifecycle.words(status),
        events=[
            OfferEventOut(
                action=e.action.value if hasattr(e.action, "value") else e.action,
                created_at=e.created_at.isoformat() if e.created_at else "",
                after=e.after or {},
            )
            for e in events
        ],
    )
