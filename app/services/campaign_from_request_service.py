"""
"AI should start the campaign" — a recruiter types one free-text hiring
request and this orchestrates the existing campaign/JD/requirement/rubric
services to produce a DRAFT campaign ready for review, instead of the
recruiter filling in new-campaign.html's three steps by hand.

Deliberately an orchestrator, not a reimplementation: every step below is an
existing service call (campaign_service, jd_generation_service,
requirement_service, rubric_service) in the same order the guided-setup UI
already drives them. Nothing here is a new source of truth — a campaign
built this way looks, on every existing screen, exactly like one built by
hand: CampaignStatus.DRAFT, with an unsubmitted rubric version, awaiting the
same recruiter review/edit/approve steps as any other campaign. The AI never
submits or approves the rubric, and never moves the campaign out of DRAFT —
that stays a human action, same as B06's JD generation and B07's weight
suggestion before it.

Each AI step degrades independently rather than aborting the whole request:
a JD-generation, requirement-extraction or rubric-drafting failure still
leaves a usable DRAFT campaign behind, flagged with a warning, rather than
nothing at all. Only a request the model cannot even understand (no
identifiable role) is rejected outright, since there is nothing yet to build
a campaign from.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.agents.campaign_request_agent import HiringRequestParseError, extract_hiring_intent
from app.db.models import AuditAction, Campaign, JobRequirement, RubricVersion
from app.schemas.campaign import CampaignCreate, CampaignUpdate
from app.services import campaign_service, disposition_service, requirement_service, rubric_service
from app.services.jd_generation_service import JDGenerationUnavailableError, generate_for_campaign
from app.services.rubric_service import RubricStateError, RubricValidationError

logger = logging.getLogger(__name__)


class EmptyHiringRequestError(ValueError):
    """The recruiter submitted nothing to work with."""


class HiringRequestUnderstandingError(ValueError):
    """AI could not turn the request into a usable role at all — nothing was created."""


@dataclass
class CampaignFromRequestResult:
    campaign: Campaign
    understood: dict
    jd_text: str
    jd_source: str  # "llm" | "template_only" | "minimal" | "existing"
    requirements: list[JobRequirement] = field(default_factory=list)
    rubric_version: RubricVersion | None = None
    warnings: list[str] = field(default_factory=list)


def _minimal_jd_text(understood: dict) -> str:
    """
    The floor beneath jd_generation_service's own floor: used only when even
    its built-in templates don't match and its own LLM call failed too. Built
    entirely from what the request-understanding step already extracted, so
    a JD-generation outage never blocks campaign creation outright.
    """
    role = understood.get("role_title") or "This role"
    lines = [role, ""]
    if understood.get("min_experience_years") is not None:
        lines.append(f"Minimum {understood['min_experience_years']} years of relevant experience.")
    if understood.get("required_skills"):
        lines += ["", "Required skills:", *(f"- {s}" for s in understood["required_skills"])]
    if understood.get("preferred_skills"):
        lines += ["", "Preferred skills:", *(f"- {s}" for s in understood["preferred_skills"])]
    if understood.get("key_responsibilities"):
        lines += ["", "Key responsibilities:", *(f"- {r}" for r in understood["key_responsibilities"])]
    if understood.get("education_requirement"):
        lines += ["", f"Education: {understood['education_requirement']}"]
    return "\n".join(lines)


def start_campaign_from_request(
    db: Session,
    request_text: str,
    *,
    actor: str = "",
    idempotency_key: str | None = None,
) -> CampaignFromRequestResult:
    request_text = (request_text or "").strip()
    if not request_text:
        raise EmptyHiringRequestError("Tell the AI what you need to hire — the request was empty.")

    try:
        understood = extract_hiring_intent(request_text)
    except HiringRequestParseError as exc:
        raise HiringRequestUnderstandingError(str(exc)) from exc
    except Exception as exc:
        logger.warning("Hiring request understanding failed (%s)", exc)
        raise HiringRequestUnderstandingError(
            "The AI assistant is unavailable right now — try again in a moment, or use "
            "'Create a campaign' to set it up by hand."
        ) from exc

    warnings: list[str] = []

    payload = CampaignCreate(
        name=f"{understood['role_title']} hiring",
        job_title=understood["role_title"],
        vacancies=understood.get("vacancies") or 1,
        location=understood.get("location") or "",
        business_unit=understood.get("business_unit") or "",
        recruiter=actor,
        created_by=actor,
    )
    campaign, created = campaign_service.create_campaign(
        db, payload, actor=actor, idempotency_key=idempotency_key,
    )
    if not created:
        # Idempotency replay: the campaign (and whatever it already has)
        # already exists — hand it straight back rather than redoing AI
        # work against it a second time and risking a second draft.
        return CampaignFromRequestResult(
            campaign=campaign,
            understood=understood,
            jd_text=campaign.job_description,
            jd_source="existing",
            requirements=requirement_service.list_requirements(db, campaign.id),
            rubric_version=rubric_service.get_latest_version(db, campaign.id),
            warnings=["A campaign already existed for this request; returning it unchanged."],
        )

    try:
        jd_result = generate_for_campaign(
            db, campaign,
            grade=understood.get("seniority_level"),
            min_experience_years=understood.get("min_experience_years"),
            required_skills=understood.get("required_skills") or None,
            key_responsibilities=understood.get("key_responsibilities") or None,
            remuneration=understood.get("remuneration"),
        )
        jd_text = jd_result.jd_text
        jd_source = jd_result.source
        if jd_result.uncertain:
            warnings.append(jd_result.uncertainty_reason or "Review the generated JD carefully.")
    except JDGenerationUnavailableError as exc:
        logger.warning("JD generation unavailable for AI campaign start (%s)", exc)
        jd_text = _minimal_jd_text(understood)
        jd_source = "minimal"
        warnings.append(
            "AI could not generate a full job description — a short summary was used instead. "
            "Write or generate a fuller JD before approving."
        )

    campaign = campaign_service.update_campaign(
        db, campaign, CampaignUpdate(job_description=jd_text), actor=actor,
    )

    requirements: list[JobRequirement] = []
    try:
        requirements = requirement_service.extract_and_store_requirements(db, campaign.id, jd_text)
    except Exception as exc:
        logger.warning("Requirement extraction failed for AI campaign start (%s)", exc)
        warnings.append(
            "AI could not extract structured requirements from the generated JD — add them "
            "manually before building the rubric."
        )

    rubric_version: RubricVersion | None = None
    if requirements:
        try:
            rubric_version = rubric_service.create_version(
                db, campaign,
                created_by=actor,
                change_reason="Drafted by AI from a recruiter request",
                seed_from_requirements_flag=True,
                weighting="market_standard",
            )
            try:
                rubric_service.suggest_weights(db, rubric_version)
            except Exception as exc:
                # A static market-standard weighting was already applied by
                # create_version above — losing the LLM tailoring layer is a
                # quality gap, not a missing rubric.
                logger.info("LLM weight suggestion skipped, keeping market-standard preset (%s)", exc)
        except (RubricStateError, RubricValidationError) as exc:
            logger.warning("Rubric draft creation failed for AI campaign start (%s)", exc)
            warnings.append(f"AI could not draft a scoring rubric: {exc}")
    else:
        warnings.append("No requirements were extracted, so no scoring rubric was drafted yet.")

    disposition_service.record_audit(
        db, AuditAction.AI_CAMPAIGN_DRAFTED,
        campaign_id=campaign.id,
        entity_type="campaign",
        entity_id=campaign.id,
        summary=f"AI drafted a campaign for {understood['role_title']} from a recruiter's request",
        after={
            "request": request_text[:2000],
            "role_title": understood["role_title"],
            "jd_source": jd_source,
            "requirements_extracted": len(requirements),
            "rubric_drafted": rubric_version is not None,
        },
        actor=actor,
    )
    db.commit()
    db.refresh(campaign)

    return CampaignFromRequestResult(
        campaign=campaign,
        understood=understood,
        jd_text=jd_text,
        jd_source=jd_source,
        requirements=requirements,
        rubric_version=rubric_version,
        warnings=warnings,
    )
