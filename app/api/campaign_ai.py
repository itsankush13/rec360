"""
`POST /api/campaigns/ai-start` — the AI-first campaign entry point.

A recruiter types one free-text hiring request; this drafts a DRAFT
campaign with a generated JD, extracted requirements and a seeded rubric,
using the exact same service calls the guided manual setup
(`new-campaign.html`) already drives — see
`app.services.campaign_from_request_service` for the orchestration. Nothing
here auto-approves anything: the response is a proposal for the recruiter
to review, same contract as B06's `jd/generate` preview.

Naming follows the existing nested-router convention
(`/api/campaigns/{id}/jd/generate`, `/api/campaigns/{id}/requirements/extract`)
as closely as a route with no campaign id yet can — this one *creates* the
campaign, so it hangs directly off `/api/campaigns`, alongside the plain
`POST /api/campaigns`.
"""
from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.campaign import AICampaignStartOut, AICampaignStartRequest
from app.services import campaign_from_request_service as svc

router = APIRouter(prefix="/api/campaigns", tags=["campaign-ai"])


@router.post("/ai-start", response_model=AICampaignStartOut, status_code=201)
def ai_start_campaign(
    payload: AICampaignStartRequest,
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    x_actor: str | None = Header(default=None, alias="X-Actor"),
):
    try:
        result = svc.start_campaign_from_request(
            db, payload.request,
            actor=x_actor or "",
            idempotency_key=idempotency_key,
        )
    except svc.EmptyHiringRequestError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except svc.HiringRequestUnderstandingError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 — never leak an internal trace to the recruiter
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Something went wrong preparing the campaign. Please try again, or use "
            "'Create a campaign' to set it up by hand.",
        ) from exc

    version = result.rubric_version
    return AICampaignStartOut(
        campaign=result.campaign,
        understood=result.understood,
        jd_text=result.jd_text,
        jd_source=result.jd_source,
        requirements=result.requirements,
        rubric_version=version.version_number if version else None,
        rubric_criteria=[
            {
                "criterion_key": w.criterion_key,
                "label": w.label,
                "category": w.category.value,
                "requirement_type": w.requirement_type.value,
                "weight": w.weight,
            }
            for w in (version.weights if version else []) if w.active
        ],
        warnings=result.warnings,
    )
