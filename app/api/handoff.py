"""
The hiring-manager handoff work queue (wide pass, journey steps 4 and 10).

The lifecycle already records where a candidate is (`lifecycle_service`) and
the state machine already says what moves are legal (`app.core.lifecycle`).
What is missing is the one call a screen needs: who owes what right now,
grouped the way a recruiter reads it, so the screen does not make six calls
and then group them in JavaScript.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core import lifecycle
from app.db.models import (
    Candidate, CandidateLifecycle, LifecycleStatus, ManagerReviewOutcome, User,
)
from app.db.session import get_db
from app.services import campaign_service, lifecycle_service

router = APIRouter(prefix="/api/campaigns/{campaign_id}/handoff", tags=["handoff"])


class QueueOut(BaseModel):
    campaign_id: str
    # No count in the groups below appears without this denominator.
    total: int
    ready_to_send: list[dict]
    with_manager: list[dict]
    returned: list[dict]
    ready_to_close: list[dict]


def _require_campaign(db: Session, campaign_id: str):
    campaign = campaign_service.get_campaign(db, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    """SQLite hands back naive datetimes; Postgres will not. Gotcha 3."""
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _name(db: Session, user_id: str | None) -> str:
    if not user_id:
        return ""
    user = db.get(User, user_id)
    return user.full_name if user else ""


def _last_question(db: Session, campaign_id: str, candidate_id: str) -> str:
    """The most recent question a manager asked, or "" if none is on file."""
    reviews = lifecycle_service.reviews_for(db, campaign_id, candidate_id)
    for review in reversed(reviews):
        if review.outcome == ManagerReviewOutcome.QUESTION.value:
            return review.reason
    return ""


def _entry(db: Session, record: CandidateLifecycle, *, question: str = "") -> dict:
    candidate = db.get(Candidate, record.candidate_id)
    status = LifecycleStatus(record.status)
    entered = _aware(record.entered_at)
    days_in_state = (_now() - entered).days if entered else 0
    entry = {
        "candidate_id": record.candidate_id,
        "name": candidate.full_name if candidate else "",
        "status": status.value,
        "status_label": lifecycle.words(status),
        "entered_at": record.entered_at.isoformat() if record.entered_at else "",
        "days_in_state": days_in_state,
        "owner_name": _name(db, record.current_owner_id),
    }
    if question:
        entry["question"] = question
    return entry


@router.get("/queue", response_model=QueueOut)
def handoff_queue(campaign_id: str, db: Session = Depends(get_db)):
    """Who owes what right now, grouped by what happens next."""
    _require_campaign(db, campaign_id)
    rows = list(lifecycle_service.statuses_for_campaign(db, campaign_id).values())

    ready_to_send = [
        _entry(db, r) for r in rows if r.status == LifecycleStatus.SHORTLISTED.value
    ]
    with_manager = [
        _entry(db, r) for r in rows
        if r.status == LifecycleStatus.WITH_HIRING_MANAGER.value
    ]
    returned = [
        _entry(db, r, question=_last_question(db, campaign_id, r.candidate_id))
        for r in rows if r.status == LifecycleStatus.RETURNED_TO_RECRUITER.value
    ]
    ready_to_close = [
        _entry(db, r) for r in rows
        if r.status in (
            LifecycleStatus.OFFER_ACCEPTED.value, LifecycleStatus.OFFER_DECLINED.value,
        )
    ]

    by_days = lambda groups: sorted(groups, key=lambda e: e["days_in_state"], reverse=True)
    return QueueOut(
        campaign_id=campaign_id,
        total=len(rows),
        ready_to_send=by_days(ready_to_send),
        with_manager=by_days(with_manager),
        returned=by_days(returned),
        ready_to_close=by_days(ready_to_close),
    )
