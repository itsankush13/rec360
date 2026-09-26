"""
B10/B11 — on-demand Outlook reply ingestion and the proposed decisions it
produces.

No background scheduler exists anywhere in this repo (checked: nothing in
`app/main.py`, `app/core`, or `app/services` wires an interval job — SLA
reminders in `app/services/sla_service.py` are themselves computed on read,
not pushed by a timer). This is deliberately on-demand only: a button the
demo can call, not new standing infrastructure.

Two routers, same split `app.api.processing` already uses for the same
reason: `router` for the campaign-agnostic action (reading the inbox names
no campaign until a reply's subject is parsed), `campaign_router` for
reading/acting on what came out of it, which is always about one campaign.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services import reply_service
from app.services.reply_service import ReplyServiceError

router = APIRouter(prefix="/api/replies", tags=["replies"])
campaign_router = APIRouter(
    prefix="/api/campaigns/{campaign_id}/replies", tags=["replies"],
)


class ApplyDecisionIn(BaseModel):
    actor_id: str
    # Overrides the classifier's own read when given — a recruiter correcting
    # a misread reply. Accepts either the classifier's own intent words
    # (approve/decline/need_more_info) or the ManagerReviewOutcome names
    # (PROCEED/DECLINE/QUESTION).
    outcome: str | None = None
    reason: str = ""


def _fail(exc: Exception) -> HTTPException:
    return HTTPException(status_code=422, detail=str(exc))


@router.post("/ingest")
def ingest_replies(db: Session = Depends(get_db)):
    """
    One pass over the local Outlook Inbox. Returns an empty list — not an
    error — when `settings.email_backend != "outlook"` or the adapter
    couldn't be built, the same quiet fallback the send-side adapters use;
    there is nothing wrong with calling this when reply ingestion isn't
    configured, it just does nothing.
    """
    processed = reply_service.ingest_replies(db)
    db.commit()
    return {"processed": len(processed), "replies": processed}


@campaign_router.get("/pending")
def pending_decisions(
    campaign_id: str, candidate_id: str | None = None, db: Session = Depends(get_db),
):
    """Every reply for this campaign whose proposed decision has not been resolved."""
    return reply_service.pending_decisions(db, campaign_id=campaign_id, candidate_id=candidate_id)


@campaign_router.post("/{entity_id}/apply")
def apply_decision(
    campaign_id: str, entity_id: str, payload: ApplyDecisionIn, db: Session = Depends(get_db),
):
    """
    Apply a decision this module only proposed. Only ever reaches an
    existing hiring-manager-verdict call — see `reply_service.apply_decision`
    for exactly what is and isn't in scope here.
    """
    try:
        result = reply_service.apply_decision(
            db, entity_id=entity_id, actor_id=payload.actor_id,
            outcome=payload.outcome, reason=payload.reason,
        )
    except ReplyServiceError as exc:
        raise _fail(exc) from exc
    db.commit()
    return result
