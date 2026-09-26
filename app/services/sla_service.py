"""
SLA reminders and escalations — B02 phase 5.

`02-LIFECYCLE-MODEL.md`: a target duration per stage, a due date, reminders
before and escalation after, clocks stopping on hold, every reminder itself
an audit event. The due date itself is set in `lifecycle_service._write()`
from `app/core/lifecycle.SLA_HOURS`; this module is what notices a due date
has arrived.

Nothing in this codebase ticks in the background (RQ cannot fork on Windows,
and the deferred queue exists for CV processing, not a clock). `evaluate()`
is written to be called from anywhere — an API route, a script, a future
scheduler — any number of times, and to do the right thing each time: a
lifecycle row gets at most one reminder and one escalation, because the
audit trail itself is the record of what has already been sent.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import lifecycle
from app.db.models import (
    AuditAction, AuditEvent, Candidate, CandidateLifecycle, LifecycleStatus,
)
from app.services import disposition_service

ON_TRACK = "ON_TRACK"
DUE_SOON = "DUE_SOON"
OVERDUE = "OVERDUE"


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _already_sent(db: Session, lifecycle_id: str, action: AuditAction) -> bool:
    return db.scalars(
        select(AuditEvent.id).where(
            AuditEvent.entity_type == "candidate_lifecycle",
            AuditEvent.entity_id == lifecycle_id,
            AuditEvent.action == action,
        )
    ).first() is not None


def sla_status(record: CandidateLifecycle, *, now: datetime | None = None) -> str:
    """
    `'ON_TRACK'`, `'DUE_SOON'` or `'OVERDUE'` — derived from the stored
    `due_at` at read time, not a column of its own. A screen and this
    module compute it the same way, so there is nothing to drift.
    """
    if record.due_at is None:
        return ON_TRACK
    now = now or _now()
    if now >= record.due_at:
        return OVERDUE
    lead = lifecycle.sla_reminder_lead_hours(LifecycleStatus(record.status))
    if lead and now >= record.due_at - timedelta(hours=lead):
        return DUE_SOON
    return ON_TRACK


def evaluate(db: Session, *, campaign_id: str | None = None,
             now: datetime | None = None) -> dict[str, int]:
    """
    Write the reminder/escalation audit events newly due across every
    current lifecycle row with a running clock, optionally scoped to one
    campaign. Commits. Returns counts so a caller can report what happened
    without a second query.
    """
    now = now or _now()
    statement = select(CandidateLifecycle).where(
        CandidateLifecycle.is_current.is_(True),
        CandidateLifecycle.due_at.isnot(None),
    )
    if campaign_id:
        statement = statement.where(CandidateLifecycle.campaign_id == campaign_id)

    reminders = 0
    escalations = 0
    for record in db.scalars(statement).all():
        # Every `CLOCK_STOPPED` status is written with `due_at=None`
        # (`lifecycle_service._write`), so the query above already excludes
        # them — a hold never reaches this loop with a live deadline.
        status = LifecycleStatus(record.status)
        candidate = db.get(Candidate, record.candidate_id)
        name = candidate.full_name if candidate else "A candidate"
        stage = lifecycle.words(status)
        due = record.due_at.isoformat()

        if now >= record.due_at:
            if not _already_sent(db, record.id, AuditAction.SLA_ESCALATED):
                disposition_service.record_audit(
                    db, AuditAction.SLA_ESCALATED,
                    campaign_id=record.campaign_id, candidate_id=record.candidate_id,
                    entity_type="candidate_lifecycle", entity_id=record.id,
                    summary=(
                        f"{name} is past the target time for "
                        f"{stage.lower()}, due {due}."
                    ),
                    after={"stage": stage, "due_at": due},
                    actor="system",
                )
                escalations += 1
            continue

        lead = lifecycle.sla_reminder_lead_hours(status)
        if lead and now >= record.due_at - timedelta(hours=lead):
            if not _already_sent(db, record.id, AuditAction.SLA_REMINDER_SENT):
                disposition_service.record_audit(
                    db, AuditAction.SLA_REMINDER_SENT,
                    campaign_id=record.campaign_id, candidate_id=record.candidate_id,
                    entity_type="candidate_lifecycle", entity_id=record.id,
                    summary=(
                        f"{name} is approaching the target time for "
                        f"{stage.lower()}, due {due}."
                    ),
                    after={"stage": stage, "due_at": due},
                    actor="system",
                )
                reminders += 1

    db.commit()
    return {"reminders_sent": reminders, "escalations_sent": escalations}
