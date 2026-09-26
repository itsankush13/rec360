"""
`B06` — generate a JD after role entry.

Mirrors `evaluation_service._apply_llm_refinement`'s safe-fallback shape:
an industry-standard template (`app/core/jd_templates.py`) is the
deterministic floor, always available; the model is a layer on top that can
fail without failing the request, provided a floor exists to fall back to.
"Learn from prior campaigns" is a real few-shot signal, not a claim: recent
campaigns with the same job title and a saved description are read and
passed to the model as examples of how this company has hired for the role
before.

This never writes to the campaign. It returns a preview; the recruiter
accepts it by saving it through the existing `PATCH /api/campaigns/{id}`,
same as any other edit — generation is a suggestion, not a decision.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import jd_templates
from app.db.models import Campaign

logger = logging.getLogger(__name__)

SIMILAR_CAMPAIGN_LIMIT = 3


class JDGenerationUnavailableError(Exception):
    """
    Raised only when there is truly nothing to offer: no matching template
    and the model could not be reached either. An honest failure, not a
    guess — the caller should ask the recruiter to write the JD directly.
    """


@dataclass
class JDGenerationResult:
    jd_text: str
    role_title: str
    required_skills: list[str] = field(default_factory=list)
    preferred_skills: list[str] = field(default_factory=list)
    min_experience_years: int | None = None
    education_requirement: str = ""
    key_responsibilities: list[str] = field(default_factory=list)
    seniority_level: str | None = None
    source: str = "llm"  # "llm" | "template_only"
    matched_template: str | None = None
    based_on_campaign_ids: list[str] = field(default_factory=list)
    uncertain: bool = False
    uncertainty_reason: str | None = None


def _similar_campaigns(db: Session, job_title: str, exclude_id: str) -> list[Campaign]:
    normalized = job_title.strip().lower()
    if not normalized:
        return []
    candidates = db.scalars(
        select(Campaign)
        .where(Campaign.id != exclude_id, Campaign.job_description != "")
        .order_by(Campaign.created_at.desc())
    )
    matches = [c for c in candidates if c.job_title.strip().lower() == normalized]
    return matches[:SIMILAR_CAMPAIGN_LIMIT]


def _template_result(
    template_name: str,
    template: jd_templates.JDTemplate,
    role_title: str,
    uncertain: bool,
    uncertainty_reason: str | None,
) -> JDGenerationResult:
    lines = [
        f"{role_title}",
        "",
        f"We are looking for a {template.canonical_title} with at least "
        f"{template.min_experience_years} years of relevant experience.",
        "",
        "Required skills:",
        *(f"- {s}" for s in template.required_skills),
    ]
    if template.preferred_skills:
        lines += ["", "Preferred skills:", *(f"- {s}" for s in template.preferred_skills)]
    if template.key_responsibilities:
        lines += ["", "Key responsibilities:", *(f"- {r}" for r in template.key_responsibilities)]
    lines += ["", f"Education: {template.education_requirement}"]

    return JDGenerationResult(
        jd_text="\n".join(lines),
        role_title=role_title,
        required_skills=list(template.required_skills),
        preferred_skills=list(template.preferred_skills),
        min_experience_years=template.min_experience_years,
        education_requirement=template.education_requirement,
        key_responsibilities=list(template.key_responsibilities),
        seniority_level=template.seniority_level,
        source="template_only",
        matched_template=template_name,
        uncertain=uncertain,
        uncertainty_reason=uncertainty_reason,
    )


def generate_for_campaign(
    db: Session,
    campaign: Campaign,
    grade: str | None = None,
    min_experience_years: int | None = None,
    required_skills: list[str] | None = None,
    key_responsibilities: list[str] | None = None,
    remuneration: str | None = None,
) -> JDGenerationResult:
    matched = jd_templates.match_template(campaign.job_title)
    template_name, template = matched if matched else (None, None)
    similar = _similar_campaigns(db, campaign.job_title, campaign.id)

    # A niche role: nothing built-in and nothing this company has hired for
    # before under this exact title. Still attempted below, but flagged so
    # the recruiter knows to check it more carefully than a known role.
    uncertain = template is None and not similar
    uncertainty_reason = (
        "No built-in template or prior campaign matched this job title — review this JD "
        "carefully before using it."
        if uncertain else None
    )

    try:
        from app.agents.jd_agent import generate_jd
    except Exception as exc:
        logger.warning("JD generation agent unavailable (%s)", exc)
        if template is None:
            raise JDGenerationUnavailableError(
                "AI generation is unavailable and no built-in template matches this role. "
                "Write the job description directly."
            ) from exc
        return _template_result(
            template_name, template, campaign.job_title, uncertain=True,
            uncertainty_reason="AI generation is unavailable; showing the industry-standard "
            "template only. Review carefully before using it.",
        )

    try:
        raw = generate_jd(
            role_title=campaign.job_title,
            grade=grade,
            min_experience_years=min_experience_years,
            required_skills=required_skills,
            key_responsibilities=key_responsibilities,
            remuneration=remuneration,
            reference_template=(
                {
                    "required_skills": template.required_skills,
                    "preferred_skills": template.preferred_skills,
                    "min_experience_years": template.min_experience_years,
                    "key_responsibilities": template.key_responsibilities,
                }
                if template else None
            ),
            similar_examples=[c.job_description for c in similar],
        )
    except Exception as exc:
        logger.warning("JD generation failed (%s)", exc)
        if template is None:
            raise JDGenerationUnavailableError(
                "AI generation failed and no built-in template matches this role. "
                "Write the job description directly."
            ) from exc
        return _template_result(
            template_name, template, campaign.job_title, uncertain=True,
            uncertainty_reason="AI generation failed; showing the industry-standard template "
            "only. Review carefully before using it.",
        )

    return JDGenerationResult(
        jd_text=raw.get("jd_text", ""),
        role_title=raw.get("role_title") or campaign.job_title,
        required_skills=raw.get("required_skills") or [],
        preferred_skills=raw.get("preferred_skills") or [],
        min_experience_years=raw.get("min_experience_years"),
        education_requirement=raw.get("education_requirement") or "",
        key_responsibilities=raw.get("key_responsibilities") or [],
        seniority_level=raw.get("seniority_level"),
        source="llm",
        matched_template=template_name,
        based_on_campaign_ids=[c.id for c in similar],
        uncertain=uncertain,
        uncertainty_reason=uncertainty_reason,
    )
