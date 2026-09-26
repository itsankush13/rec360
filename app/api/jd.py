"""
`POST /api/campaigns/{campaign_id}/jd/generate` — B06.

Returns a preview only; nothing is written to the campaign here. The
recruiter accepts, edits or discards it, then saves through the existing
`PATCH /api/campaigns/{id}` like any other edit — same separation the rest
of the product keeps between an AI suggestion and a human decision.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.campaign import JDGenerateRequest, JDGenerateOut
from app.services import campaign_service, jd_generation_service
from app.services.jd_generation_service import JDGenerationUnavailableError

router = APIRouter(prefix="/api/campaigns/{campaign_id}/jd", tags=["jd"])


def _require_campaign(db: Session, campaign_id: str):
    campaign = campaign_service.get_campaign(db, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign


@router.post("/generate", response_model=JDGenerateOut)
def generate_jd(campaign_id: str, payload: JDGenerateRequest, db: Session = Depends(get_db)):
    campaign = _require_campaign(db, campaign_id)
    try:
        return jd_generation_service.generate_for_campaign(
            db,
            campaign,
            grade=payload.grade,
            min_experience_years=payload.min_experience_years,
            required_skills=payload.required_skills,
            key_responsibilities=payload.key_responsibilities,
            remuneration=payload.remuneration,
        )
    except JDGenerationUnavailableError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
