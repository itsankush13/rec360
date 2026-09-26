"""
B13 — delegation-of-authority grants. See `app/services/delegation_service.py`
and the `on_behalf_of_id` field `app/api/approvals.py`'s write routes accept.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services import delegation_service
from app.services.delegation_service import DelegationError
from app.services.lifecycle_service import LifecycleError

router = APIRouter(prefix="/api/delegations", tags=["delegations"])


def _fail(exc: Exception) -> HTTPException:
    return HTTPException(status_code=422, detail=str(exc))


class DelegationGrantIn(BaseModel):
    grantor_id: str
    delegate_id: str
    created_by: str
    scope: str = "approval"
    campaign_id: str | None = None
    ends_at: datetime | None = None


class DelegationGrantOut(BaseModel):
    id: str
    grantor_id: str
    delegate_id: str
    scope: str
    campaign_id: str | None = None
    starts_at: str = ""
    ends_at: str | None = None
    revoked_at: str | None = None


def _out(grant) -> DelegationGrantOut:
    return DelegationGrantOut(
        id=grant.id, grantor_id=grant.grantor_id, delegate_id=grant.delegate_id,
        scope=grant.scope, campaign_id=grant.campaign_id,
        starts_at=grant.starts_at.isoformat() if grant.starts_at else "",
        ends_at=grant.ends_at.isoformat() if grant.ends_at else None,
        revoked_at=grant.revoked_at.isoformat() if grant.revoked_at else None,
    )


@router.get("", response_model=list[DelegationGrantOut])
def list_delegations(grantor_id: str, db: Session = Depends(get_db)):
    return [_out(g) for g in delegation_service.grants_for(db, grantor_id=grantor_id)]


@router.post("", response_model=DelegationGrantOut, status_code=201)
def create_delegation(payload: DelegationGrantIn, db: Session = Depends(get_db)):
    try:
        grant = delegation_service.grant(
            db, grantor_id=payload.grantor_id, delegate_id=payload.delegate_id,
            created_by=payload.created_by, scope=payload.scope,
            campaign_id=payload.campaign_id, ends_at=payload.ends_at,
        )
    except (DelegationError, LifecycleError) as exc:
        raise _fail(exc) from exc
    db.commit()
    db.refresh(grant)
    return _out(grant)


@router.post("/{grant_id}/revoke", response_model=DelegationGrantOut)
def revoke_delegation(grant_id: str, db: Session = Depends(get_db)):
    from app.db.models import DelegationGrant
    grant = db.get(DelegationGrant, grant_id)
    if grant is None:
        raise HTTPException(status_code=404, detail="Delegation grant not found")
    delegation_service.revoke(db, grant)
    db.commit()
    db.refresh(grant)
    return _out(grant)
