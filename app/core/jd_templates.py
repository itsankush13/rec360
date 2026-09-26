"""
Industry-standard JD templates for common roles — the deterministic floor
for `B06`.

A template is a *starting point*, never a delivered JD: exactly the same
relationship `app/core/rubric_presets.py` has to a rubric. It exists so
generation for a role everyone has hired for before doesn't depend on the
model being reachable, and so a niche role — one that matches neither a
template nor a prior campaign — can be told apart from a common one instead
of both silently getting the same confident-looking output.

Deliberately no remuneration figures: a fabricated salary band is actively
misleading, unlike a generic skills/responsibilities list. Remuneration is
either a caller-supplied override or left for the recruiter to fill in.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class JDTemplate:
    canonical_title: str
    required_skills: list[str]
    preferred_skills: list[str] = field(default_factory=list)
    min_experience_years: int = 2
    education_requirement: str = "Bachelor's degree or equivalent practical experience"
    key_responsibilities: list[str] = field(default_factory=list)
    seniority_level: str = "Mid"


# Keyed by a normalised alias; several aliases can point at the same
# template. Small and hand-picked on purpose — this is a floor for the
# roles this product's own campaigns are actually likely to hire for, not
# an attempt to cover every job title that exists.
_TEMPLATES: dict[str, JDTemplate] = {
    "software engineer": JDTemplate(
        canonical_title="Software Engineer",
        required_skills=["Python", "SQL", "Git", "REST APIs"],
        preferred_skills=["Docker", "CI/CD", "Cloud platforms"],
        min_experience_years=3,
        key_responsibilities=[
            "Design, build and maintain backend services",
            "Write automated tests and participate in code review",
            "Collaborate with product and QA on feature delivery",
        ],
        seniority_level="Mid",
    ),
    "data analyst": JDTemplate(
        canonical_title="Data Analyst",
        required_skills=["SQL", "Excel", "Data visualisation"],
        preferred_skills=["Python", "Power BI", "Statistics"],
        min_experience_years=2,
        key_responsibilities=[
            "Build and maintain recurring reports and dashboards",
            "Analyse data to answer business questions",
            "Present findings to non-technical stakeholders",
        ],
        seniority_level="Mid",
    ),
    "recruiter": JDTemplate(
        canonical_title="Recruiter",
        required_skills=["Sourcing", "Applicant tracking systems", "Interviewing"],
        preferred_skills=["Employer branding", "Boolean search"],
        min_experience_years=2,
        key_responsibilities=[
            "Manage the full recruitment cycle for assigned roles",
            "Source and screen candidates",
            "Coordinate with hiring managers on requirements and feedback",
        ],
        seniority_level="Mid",
    ),
    "hr business partner": JDTemplate(
        canonical_title="HR Business Partner",
        required_skills=["Employee relations", "HR policy", "Stakeholder management"],
        preferred_skills=["Change management", "Workforce planning"],
        min_experience_years=5,
        key_responsibilities=[
            "Partner with business leaders on people strategy",
            "Advise on employee relations and performance management",
            "Support workforce planning and organisational change",
        ],
        seniority_level="Senior",
    ),
    "project manager": JDTemplate(
        canonical_title="Project Manager",
        required_skills=["Project planning", "Stakeholder management", "Risk management"],
        preferred_skills=["Agile/Scrum", "PMP certification"],
        min_experience_years=4,
        key_responsibilities=[
            "Plan and track project timelines, budget and scope",
            "Coordinate cross-functional teams and vendors",
            "Report status and risks to stakeholders",
        ],
        seniority_level="Senior",
    ),
    "sales executive": JDTemplate(
        canonical_title="Sales Executive",
        required_skills=["Lead generation", "Negotiation", "CRM tools"],
        preferred_skills=["Account management", "Solution selling"],
        min_experience_years=2,
        key_responsibilities=[
            "Generate and qualify new business leads",
            "Manage the sales pipeline through to close",
            "Maintain accurate records in the CRM",
        ],
        seniority_level="Mid",
    ),
}


def match_template(job_title: str) -> tuple[str, JDTemplate] | None:
    """
    Match a job title to a known template, or `None` for a role this
    product has no built-in baseline for. Matching is intentionally loose
    (substring, either direction) so "Senior Software Engineer" or "Software
    Engineer II" still finds "Software Engineer" — but it is not fuzzy
    beyond that: an unrelated title must not silently borrow the wrong
    template.
    """
    normalized = " ".join(job_title.strip().lower().split())
    if not normalized:
        return None
    for alias, template in _TEMPLATES.items():
        if alias in normalized or normalized in alias:
            return alias, template
    return None
