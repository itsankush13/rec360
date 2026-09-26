"""
Turns the existing JD agent's free-form extraction into structured,
persisted, recruiter-editable JobRequirement rows.

This intentionally reuses app.agents.jd_agent.parse_jd (the real LLM call)
rather than re-implementing extraction — Phase A's job is to give that
output a proper home in the database, not to replace the agent.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.jd_agent import parse_jd
from app.core import llm_usage
from app.db.models import JobRequirement, RequirementCategory, RequirementType


def _skill_weight(n_mandatory_skills: int) -> float:
    """Even split of a 40% skills budget across mandatory skills, floor 1."""
    if n_mandatory_skills <= 0:
        return 0.0
    return round(40.0 / n_mandatory_skills, 2)


def extract_and_store_requirements(db: Session, campaign_id: str, jd_text: str) -> list[JobRequirement]:
    # B21: bill this call to the campaign so /api/developer/metrics can show
    # what JD extraction actually costs.
    with llm_usage.track(db, campaign_id=campaign_id, call_type="jd_extraction"):
        parsed = parse_jd(jd_text)

    required_skills = parsed.get("required_skills", []) or []
    preferred_skills = parsed.get("preferred_skills", []) or []
    min_years = parsed.get("min_experience_years")
    education = parsed.get("education_requirement")
    responsibilities = parsed.get("key_responsibilities", []) or []
    seniority = parsed.get("seniority_level")

    # Wipe AI-sourced requirements from any previous extraction on this
    # campaign so re-running extraction doesn't duplicate rows. Manually
    # added/edited requirements (source != "AI") are left alone.
    existing_ai_rows = db.scalars(
        select(JobRequirement).where(
            JobRequirement.campaign_id == campaign_id,
            JobRequirement.source == "AI",
        )
    )
    for row in existing_ai_rows:
        db.delete(row)

    new_rows: list[JobRequirement] = []
    skill_weight = _skill_weight(len(required_skills))

    for skill in required_skills:
        new_rows.append(JobRequirement(
            campaign_id=campaign_id,
            description=skill,
            category=RequirementCategory.SKILL,
            requirement_type=RequirementType.MANDATORY,
            priority=1,
            weight=skill_weight,
            disqualifying=False,
            evidence_required=True,
            source="AI",
        ))

    for skill in preferred_skills:
        new_rows.append(JobRequirement(
            campaign_id=campaign_id,
            description=skill,
            category=RequirementCategory.SKILL,
            requirement_type=RequirementType.PREFERRED,
            priority=3,
            weight=0.0,
            disqualifying=False,
            evidence_required=False,
            source="AI",
        ))

    if min_years is not None:
        new_rows.append(JobRequirement(
            campaign_id=campaign_id,
            description=f"Minimum {min_years} years of relevant experience",
            category=RequirementCategory.EXPERIENCE,
            requirement_type=RequirementType.MANDATORY,
            priority=1,
            weight=25.0,
            disqualifying=True,
            evidence_required=True,
            source="AI",
        ))

    if education:
        new_rows.append(JobRequirement(
            campaign_id=campaign_id,
            description=education,
            category=RequirementCategory.QUALIFICATION,
            requirement_type=RequirementType.MANDATORY,
            priority=2,
            weight=15.0,
            disqualifying=False,
            evidence_required=True,
            source="AI",
        ))

    if seniority:
        new_rows.append(JobRequirement(
            campaign_id=campaign_id,
            description=f"Seniority level: {seniority}",
            category=RequirementCategory.SENIORITY,
            requirement_type=RequirementType.INFORMATIONAL,
            priority=4,
            weight=0.0,
            disqualifying=False,
            evidence_required=False,
            source="AI",
        ))

    for responsibility in responsibilities:
        new_rows.append(JobRequirement(
            campaign_id=campaign_id,
            description=responsibility,
            category=RequirementCategory.RESPONSIBILITY,
            requirement_type=RequirementType.INFORMATIONAL,
            priority=5,
            weight=0.0,
            disqualifying=False,
            evidence_required=False,
            source="AI",
        ))

    db.add_all(new_rows)
    db.commit()
    for row in new_rows:
        db.refresh(row)
    return new_rows


def list_requirements(db: Session, campaign_id: str) -> list[JobRequirement]:
    stmt = select(JobRequirement).where(
        JobRequirement.campaign_id == campaign_id
    ).order_by(JobRequirement.priority, JobRequirement.created_at)
    return list(db.scalars(stmt))
