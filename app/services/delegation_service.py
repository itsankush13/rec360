"""
B13 — delegation of authority.

`LifecycleTransition.on_behalf_of_id` has existed since the lifecycle model
shipped, named for exactly this: recording that a move was made in someone
else's name. Nothing ever checked it. This is that check — a grant has to
exist, be unrevoked, and cover the scope and window of the action before an
approval can claim it.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import DelegationGrant
from app.services.lifecycle_service import require_user


class DelegationError(ValueError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def grant(
    db: Session, *, grantor_id: str, delegate_id: str, created_by: str,
    scope: str = "approval", campaign_id: str | None = None,
    ends_at: datetime | None = None,
) -> DelegationGrant:
    grantor = require_user(db, grantor_id, what="delegate their authority")
    delegate = require_user(db, delegate_id, what="receive a delegation")
    if grantor.id == delegate.id:
        raise DelegationError("A person cannot delegate authority to themselves.")

    record = DelegationGrant(
        grantor_id=grantor.id, delegate_id=delegate.id, scope=scope,
        campaign_id=campaign_id, ends_at=_aware(ends_at), created_by=created_by,
    )
    db.add(record)
    db.flush()
    return record


def revoke(db: Session, grant_row: DelegationGrant) -> DelegationGrant:
    grant_row.revoked_at = _now()
    db.flush()
    return grant_row


def grants_for(db: Session, *, grantor_id: str) -> list[DelegationGrant]:
    return list(db.scalars(
        select(DelegationGrant)
        .where(DelegationGrant.grantor_id == grantor_id)
        .order_by(DelegationGrant.created_at.desc())
    ).all())


def active_grant(
    db: Session, *, grantor_id: str, delegate_id: str, scope: str,
    campaign_id: str | None = None,
) -> DelegationGrant | None:
    now = _now()
    rows = db.scalars(
        select(DelegationGrant).where(
            DelegationGrant.grantor_id == grantor_id,
            DelegationGrant.delegate_id == delegate_id,
            DelegationGrant.scope == scope,
            DelegationGrant.revoked_at.is_(None),
        )
    ).all()
    for row in rows:
        if row.campaign_id is not None and row.campaign_id != campaign_id:
            continue
        starts = _aware(row.starts_at)
        if starts and starts > now:
            continue
        ends = _aware(row.ends_at)
        if ends and ends < now:
            continue
        return row
    return None


def require_delegation(
    db: Session, *, delegate_id: str, on_behalf_of_id: str,
    scope: str = "approval", campaign_id: str | None = None,
) -> DelegationGrant:
    found = active_grant(
        db, grantor_id=on_behalf_of_id, delegate_id=delegate_id, scope=scope,
        campaign_id=campaign_id,
    )
    if found is None:
        raise DelegationError(
            "No active delegation lets this person act on that person's "
            "behalf for this scope."
        )
    return found
