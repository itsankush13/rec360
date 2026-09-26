from fastapi import APIRouter, Depends, Header, HTTPException, Response
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.campaign import (
    CampaignCreate, CampaignUpdate, CampaignOut, CampaignStatusUpdate,
)
from app.services import campaign_service
from app.services.campaign_service import CampaignConflictError, CampaignTransitionError

router = APIRouter(prefix="/api/campaigns", tags=["campaigns"])


def _get_or_404(db: Session, campaign_id: str):
    campaign = campaign_service.get_campaign(db, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign


@router.post("", response_model=CampaignOut, status_code=201)
def create_campaign(
    payload: CampaignCreate,
    response: Response,
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    campaign, created = campaign_service.create_campaign(db, payload, idempotency_key=idempotency_key)
    if not created:
        # A replayed create is not a new resource — 200, not 201, on the
        # campaign that already exists for this key.
        response.status_code = 200
    return campaign


@router.get("", response_model=list[CampaignOut])
def list_campaigns(status: str | None = None, db: Session = Depends(get_db)):
    from app.db.models import CampaignStatus
    status_enum = CampaignStatus(status) if status else None
    return campaign_service.list_campaigns(db, status_enum)


@router.get("/{campaign_id}", response_model=CampaignOut)
def get_campaign(campaign_id: str, db: Session = Depends(get_db)):
    return _get_or_404(db, campaign_id)


@router.patch("/{campaign_id}", response_model=CampaignOut)
def update_campaign(campaign_id: str, payload: CampaignUpdate, db: Session = Depends(get_db)):
    campaign = _get_or_404(db, campaign_id)
    try:
        return campaign_service.update_campaign(db, campaign, payload)
    except CampaignConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/{campaign_id}/status", response_model=CampaignOut)
def transition_status(campaign_id: str, payload: CampaignStatusUpdate, db: Session = Depends(get_db)):
    campaign = _get_or_404(db, campaign_id)
    try:
        return campaign_service.transition_status(db, campaign, payload.status)
    except CampaignTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.delete("/{campaign_id}", status_code=204)
def delete_campaign(campaign_id: str, db: Session = Depends(get_db)):
    campaign = _get_or_404(db, campaign_id)
    campaign_service.delete_campaign(db, campaign)
