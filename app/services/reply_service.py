"""
B10 inbound / B11 feedback-from-reply — dispatch classified email replies
into the domain.

`ingest_replies` reads the Outlook Inbox (`app.core.reply_ingestion`),
classifies each `[REF-...]`-tagged reply it finds (`app.core.reply_classifier`),
and writes exactly one `AuditAction.EMAIL_REPLY_RECEIVED` audit event per
reply — the raw signal, always, whether or not anything else happened.

Two rows can exist for the same reply: the first, written at ingestion, with
`after["status"]` one of "proposed" or "auto_applied"; and, only if a person
later applies a decision this module only proposed, a second with the same
`entity_id` and `after["status"] == "manually_applied"`. `pending_decisions`
derives "still open" from that stream the same way
`app.api.interviews._latest_schedule_detail` already derives "the current
schedule" from `AuditAction.INTERVIEW_SCHEDULED` events — newest event per
`entity_id` wins, no second table. That module's docstring gives the reason
this repeats: a demo-scope, audit-derived read of a journey step, not a
second source of truth for state that already lives in `CandidateLifecycle`.

The one rule `settings.auto_apply_reply_decisions` does not relax: this
module never invents a new irreversible action from an LLM's read of an
email. `_try_auto_apply` only ever calls a service function a person could
already call by hand from the UI — `lifecycle_service.record_manager_review`
— and only when every precondition for that call already holds (a named,
active hiring manager on file whose email matches the sender; the candidate
currently `WITH_HIRING_MANAGER`). A schedule confirmation, a reschedule
request, a budget mention, or a reply from an address that doesn't resolve
to a hiring manager, is recorded as a proposed decision only, regardless of
the setting — there is no service call this module can point at for those
without guessing at fields (an interview's exact new time, a cost centre, an
offer) an email reply does not reliably contain.

Convention: this module `db.add()`/`db.flush()`; the API layer in
`app.api.replies` commits. (Note `lifecycle_service.record_manager_review`
itself calls `db.commit()` internally — a pre-existing exception to that
house rule this module inherits rather than reproduces; see the B10 handoff
notes.)
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.reply_classifier import ReplySignal, classify_reply
from app.core.reply_ingestion import ParsedReply, get_inbox_reader
from app.db.models import (
    AuditAction, AuditEvent, Campaign, LifecycleStatus, ManagerReviewOutcome,
    User, UserRole,
)
from app.services import disposition_service, lifecycle_service
from app.services.lifecycle_service import LifecycleError

# A reply's classified intent maps onto a hiring-manager verdict 1:1 for the
# three outcomes that verdict recognizes. Anything else (a schedule
# confirmation, a reschedule request, an unclear read) has no existing
# service call to reach for, so it is left out of this map on purpose.
_INTENT_TO_MANAGER_OUTCOME = {
    "approve": ManagerReviewOutcome.PROCEED,
    "decline": ManagerReviewOutcome.DECLINE,
    "need_more_info": ManagerReviewOutcome.QUESTION,
}


class ReplyServiceError(Exception):
    """Caller-fixable; the API maps this to 4xx."""


def _safe_iso(value) -> str:
    try:
        return value.isoformat()
    except Exception:
        return str(value) if value is not None else ""


def _already_recorded(db: Session, entity_id: str) -> bool:
    return db.scalars(
        select(AuditEvent.id).where(
            AuditEvent.action == AuditAction.EMAIL_REPLY_RECEIVED,
            AuditEvent.entity_id == entity_id,
        ).limit(1)
    ).first() is not None


def _try_auto_apply(db: Session, parsed: ParsedReply, signal: ReplySignal) -> dict | None:
    """
    Returns what was applied, or `None` if nothing here maps cleanly onto an
    existing action — in which case the caller records a proposed decision
    instead. Never raises past this function: a precondition miss is simply
    "nothing to auto-apply", not a failure of ingestion.
    """
    if not parsed.candidate_id:
        return None  # a campaign-level reply (the hiring-manager report) names no one candidate

    outcome = _INTENT_TO_MANAGER_OUTCOME.get(signal.intent)
    if outcome is None:
        return None  # schedule_confirm / reschedule_request / unclear: proposed only, always

    record = lifecycle_service.current(db, parsed.campaign_id, parsed.candidate_id)
    if record is None or record.status != LifecycleStatus.WITH_HIRING_MANAGER.value:
        return None  # not currently awaiting a manager verdict — nothing this call fits

    sender = (parsed.sender_address or "").strip().lower()
    if not sender:
        return None
    manager = db.scalars(select(User).where(User.email == sender)).first()
    if manager is None or manager.role not in (UserRole.HIRING_MANAGER, UserRole.ADMIN):
        return None  # the sender isn't a hiring manager on file — don't guess who they are

    reason = (signal.rationale or "").strip()
    if outcome in (ManagerReviewOutcome.DECLINE, ManagerReviewOutcome.QUESTION) and not reason:
        reason = "Reason not stated explicitly; recorded from an automated read of the email reply."

    try:
        lifecycle_service.record_manager_review(
            db, campaign_id=parsed.campaign_id, candidate_id=parsed.candidate_id,
            reviewer_id=manager.id, outcome=outcome, reason=reason,
        )
    except LifecycleError:
        return None  # e.g. the candidate moved on between ingestion passes

    return {
        "action": "record_manager_review", "outcome": outcome.value,
        "reviewer_id": manager.id, "reviewer_name": manager.full_name,
    }


def _record(db: Session, parsed: ParsedReply, signal: ReplySignal, *,
           status: str, applied: dict | None) -> dict:
    after = {
        "campaign_id": parsed.campaign_id,
        "candidate_id": parsed.candidate_id,
        "sender": parsed.sender_address,
        "received_at": _safe_iso(parsed.received_at),
        "subject": parsed.subject,
        "body_excerpt": (parsed.body or "")[:1000],
        "intent": signal.intent,
        "sentiment": signal.sentiment,
        "extracted_datetime": signal.extracted_datetime,
        "extracted_amount": signal.extracted_amount,
        "confidence": signal.confidence,
        "rationale": signal.rationale,
        "status": status,
        "applied": applied,
    }
    summary = (
        f"Reply received from {parsed.sender_address or 'an unknown sender'}, "
        f"read as {signal.intent.replace('_', ' ')}"
        + (f" ({signal.extracted_datetime})" if signal.extracted_datetime else "")
        + "."
    )
    summary += (
        " Applied automatically." if status == "auto_applied" else
        " Recorded as a proposed decision, not yet applied."
    )
    disposition_service.record_audit(
        db, AuditAction.EMAIL_REPLY_RECEIVED,
        campaign_id=parsed.campaign_id, candidate_id=parsed.candidate_id,
        entity_type="email_reply", entity_id=parsed.message_id,
        summary=summary, after=after, actor="system (Outlook inbox)",
    )
    return {"entity_id": parsed.message_id, **after}


def ingest_replies(db: Session, *, limit: int = 200) -> list[dict]:
    """
    One on-demand pass over the Inbox. Never raises: the adapter itself never
    raises (see `InboxReader.read_replies`), a reply that fails to classify
    comes back "unclear" rather than being dropped, and a reply naming a
    campaign this database doesn't have is skipped rather than recorded
    against nothing.

    Idempotent across passes: a reply already recorded (by `message_id`,
    i.e. the Outlook `EntryID`) is not recorded again, so calling this
    endpoint repeatedly is safe.
    """
    reader = get_inbox_reader()
    if reader is None:
        return []

    processed: list[dict] = []
    for parsed in reader.read_replies(limit=limit):
        if db.get(Campaign, parsed.campaign_id) is None:
            continue  # a REF tag naming a campaign we don't have on file
        if _already_recorded(db, parsed.message_id):
            continue  # seen on an earlier ingestion pass

        signal = classify_reply(parsed.body)
        applied = None
        status = "proposed"
        if settings.auto_apply_reply_decisions:
            applied = _try_auto_apply(db, parsed, signal)
            if applied is not None:
                status = "auto_applied"

        processed.append(_record(db, parsed, signal, status=status, applied=applied))
    return processed


def pending_decisions(db: Session, *, campaign_id: str,
                      candidate_id: str | None = None) -> list[dict]:
    """
    Every reply whose latest recorded state is still "proposed", newest
    first. A reply that was auto-applied at ingestion, or has since been
    applied by hand, is not "pending" — it is resolved, and stays out of
    this list even though its audit row is never deleted.
    """
    statement = select(AuditEvent).where(
        AuditEvent.action == AuditAction.EMAIL_REPLY_RECEIVED,
        AuditEvent.campaign_id == campaign_id,
    )
    if candidate_id is not None:
        statement = statement.where(AuditEvent.candidate_id == candidate_id)
    events = list(db.scalars(statement.order_by(AuditEvent.created_at.desc())).all())

    latest: dict[str, AuditEvent] = {}
    order: list[str] = []
    for event in events:
        if event.entity_id not in latest:
            latest[event.entity_id] = event
            order.append(event.entity_id)

    pending = []
    for entity_id in order:
        event = latest[entity_id]
        detail = event.after or {}
        if detail.get("status") == "proposed":
            pending.append({"entity_id": entity_id, "audit_event_id": event.id, **detail})
    return pending


def apply_decision(db: Session, *, entity_id: str, actor_id: str,
                   outcome: str | None = None, reason: str = "") -> dict:
    """
    A person applying a decision this module only proposed. `outcome`, when
    given, overrides the classifier's own read — a recruiter correcting a
    misread reply, the same "a person decides" rule the rest of the
    disposition layer already follows.

    Only ever reaches `lifecycle_service.record_manager_review`, for the
    same reason `_try_auto_apply` is restricted to it: it is the one
    existing call this module has evidence maps cleanly onto a reply's
    intent. A reply naming no candidate (a campaign-level thread) or an
    intent/outcome this endpoint does not recognize is refused with a
    message telling the caller to act on it directly instead of guessing.
    """
    event = db.scalars(
        select(AuditEvent).where(
            AuditEvent.action == AuditAction.EMAIL_REPLY_RECEIVED,
            AuditEvent.entity_id == entity_id,
        ).order_by(AuditEvent.created_at.desc())
    ).first()
    if event is None:
        raise ReplyServiceError("No recorded reply with that id.")

    detail = event.after or {}
    if detail.get("status") != "proposed":
        raise ReplyServiceError("This reply's decision has already been resolved.")

    candidate_id = detail.get("candidate_id")
    campaign_id = detail.get("campaign_id")
    if not candidate_id:
        raise ReplyServiceError(
            "This reply named no candidate (a campaign-level thread), so there "
            "is no single hiring-manager verdict to apply here — act on it directly."
        )

    chosen = outcome or detail.get("intent")
    mapped = _INTENT_TO_MANAGER_OUTCOME.get(chosen) or {
        "PROCEED": ManagerReviewOutcome.PROCEED,
        "DECLINE": ManagerReviewOutcome.DECLINE,
        "QUESTION": ManagerReviewOutcome.QUESTION,
    }.get(chosen)
    if mapped is None:
        raise ReplyServiceError(
            f"'{chosen}' is not a hiring-manager verdict this endpoint can apply "
            "(expected approve/decline/need_more_info, or PROCEED/DECLINE/QUESTION). "
            "Act on it directly instead."
        )

    reviewer = lifecycle_service.require_user(db, actor_id, what="apply this decision")
    resolved_reason = (reason or detail.get("rationale") or "").strip() or (
        "Applied by hand from a recorded email reply."
    )
    try:
        lifecycle_service.record_manager_review(
            db, campaign_id=campaign_id, candidate_id=candidate_id,
            reviewer_id=reviewer.id, outcome=mapped, reason=resolved_reason,
        )
    except LifecycleError as exc:
        raise ReplyServiceError(str(exc)) from exc

    applied = {
        "action": "record_manager_review", "outcome": mapped.value,
        "reviewer_id": reviewer.id, "reviewer_name": reviewer.full_name,
    }
    resolved_after = dict(detail)
    resolved_after["status"] = "manually_applied"
    resolved_after["applied"] = applied
    disposition_service.record_audit(
        db, AuditAction.EMAIL_REPLY_RECEIVED,
        campaign_id=campaign_id, candidate_id=candidate_id,
        entity_type="email_reply", entity_id=entity_id,
        summary=f"{reviewer.full_name} applied the proposed decision from this reply.",
        after=resolved_after, actor=reviewer.full_name,
    )
    return {"entity_id": entity_id, **resolved_after}
