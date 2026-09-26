from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.campaign import (
    RequirementCreate, RequirementUpdate, RequirementOut, ExtractRequirementsRequest,
)
from app.services import campaign_service, requirement_service
from app.db.models import JobRequirement

router = APIRouter(prefix="/api/campaigns/{campaign_id}/requirements", tags=["requirements"])


def _require_campaign(db: Session, campaign_id: str):
    campaign = campaign_service.get_campaign(db, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign


@router.post("/extract", response_model=list[RequirementOut])
def extract_requirements(
    campaign_id: str,
    payload: ExtractRequirementsRequest,
    db: Session = Depends(get_db),
):
    campaign = _require_campaign(db, campaign_id)
    jd_text = payload.jd_text or campaign.job_description
    if not jd_text or not jd_text.strip():
        raise HTTPException(status_code=422, detail="No job description text available to extract from")
    if payload.jd_text and payload.jd_text != campaign.job_description:
        campaign.job_description = payload.jd_text
        db.commit()
    try:
        return requirement_service.extract_and_store_requirements(db, campaign_id, jd_text)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Requirement extraction failed: {exc}") from exc


@router.get("", response_model=list[RequirementOut])
def list_requirements(campaign_id: str, db: Session = Depends(get_db)):
    _require_campaign(db, campaign_id)
    return requirement_service.list_requirements(db, campaign_id)


@router.post("", response_model=RequirementOut, status_code=201)
def add_requirement(campaign_id: str, payload: RequirementCreate, db: Session = Depends(get_db)):
    _require_campaign(db, campaign_id)
    requirement = JobRequirement(campaign_id=campaign_id, source="MANUAL", **payload.model_dump())
    db.add(requirement)
    db.commit()
    db.refresh(requirement)
    return requirement


@router.patch("/{requirement_id}", response_model=RequirementOut)
def update_requirement(
    campaign_id: str, requirement_id: str, payload: RequirementUpdate, db: Session = Depends(get_db)
):
    _require_campaign(db, campaign_id)
    requirement = db.get(JobRequirement, requirement_id)
    if requirement is None or requirement.campaign_id != campaign_id:
        raise HTTPException(status_code=404, detail="Requirement not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(requirement, field, value)
    requirement.source = "EDITED" if requirement.source == "AI" else requirement.source
    db.commit()
    db.refresh(requirement)
    return requirement


@router.delete("/{requirement_id}", status_code=204)
def delete_requirement(campaign_id: str, requirement_id: str, db: Session = Depends(get_db)):
    _require_campaign(db, campaign_id)
    requirement = db.get(JobRequirement, requirement_id)
    if requirement is None or requirement.campaign_id != campaign_id:
        raise HTTPException(status_code=404, detail="Requirement not found")
    db.delete(requirement)
    db.commit()
