"""
Starting weightings for a rubric.

A preset is a *starting point*, never a scoring path. It sets the numbers in
a draft rubric version; from there the version is reviewed, adjusted and
approved by a named person exactly like any other. Nothing here can change
how a candidate is scored without somebody approving it, and nothing here
bypasses the rule that weights sum to 100.

Why this exists: until now the only way to get weights was whatever the job
description extraction happened to produce, which varies with how the JD was
written. Recruiters asking for "the standard ATS weighting" were asking for
a template, and there wasn't one.

The market-standard weighting below is the one in common use for CV
screening. Two deliberate departures from how it is usually quoted:

  * **No readability slice.** The usual table reserves ~5 points for how
    machine-readable the CV is. Scoring that means deducting points from a
    strong candidate for their typesetting, and it is the one line in the
    table with no evidence from the person's career to cite — which breaks
    the rule that every scored criterion shows supporting evidence. Document
    quality is measured, but it lowers confidence rather than the score.
    See app/core/document_quality.py. Those 5 points are redistributed
    across the remaining components in proportion.

  * **The mandatory block cuts across categories.** "Mandatory requirements,
    30%" is not a category in the way skills or experience are — a mandatory
    requirement may be a skill, a certification or a location. So the block
    is allocated by requirement type first, and the category budgets are
    then shared among what is left.

A category with no criteria in a given campaign does not silently lose its
budget: it is redistributed in proportion across the buckets that do have
criteria, so the total is always exactly 100.
"""
from __future__ import annotations

from app.db.models import RequirementCategory, RequirementType

MARKET_STANDARD = "market_standard"

# Component budgets before normalisation, in the proportions the standard
# table quotes. Readability's 5 points are absent by design (see above), so
# these sum to 95 and are scaled to 100.
MANDATORY_BUDGET = 30.0

CATEGORY_BUDGETS: dict[RequirementCategory, float] = {
    RequirementCategory.EXPERIENCE: 20.0,
    RequirementCategory.SKILL: 15.0,
    RequirementCategory.QUALIFICATION: 5.0,
    RequirementCategory.CERTIFICATION: 5.0,
    RequirementCategory.RESPONSIBILITY: 10.0,
    RequirementCategory.INDUSTRY: 5.0,
    RequirementCategory.DIFFERENTIATING: 5.0,
}

# Categories the standard table has no line for, folded into the nearest one
# that it does. Eligibility and location are almost always mandatory anyway.
CATEGORY_ALIASES: dict[RequirementCategory, RequirementCategory] = {
    RequirementCategory.FUNCTIONAL: RequirementCategory.RESPONSIBILITY,
    RequirementCategory.SENIORITY: RequirementCategory.EXPERIENCE,
    RequirementCategory.LOCATION: RequirementCategory.SKILL,
    RequirementCategory.ELIGIBILITY: RequirementCategory.SKILL,
}

PRESETS = {
    MARKET_STANDARD: {
        "key": MARKET_STANDARD,
        "label": "Standard screening weighting",
        "description": (
            "The weighting in common use for CV screening: mandatory "
            "requirements carry the most, then experience, then skills, with "
            "smaller shares for education, responsibilities, industry and "
            "preferred criteria. A starting point — adjust it before you "
            "approve it."
        ),
        # Shares as the recruiter sees them: the standard proportions with
        # readability's five points already shared out, rounded so the column
        # adds to 100 on screen. The allocation itself is computed from the
        # budgets above, which is why these are shown as approximate — a
        # campaign missing a whole category redistributes again.
        "components": [
            {"label": "Mandatory requirements", "share": 32},
            {"label": "Relevant experience", "share": 21},
            {"label": "Skills", "share": 16},
            {"label": "Education and certifications", "share": 11},
            {"label": "Responsibilities and role alignment", "share": 10},
            {"label": "Industry experience", "share": 5},
            {"label": "Preferred criteria", "share": 5},
        ],
        "note": (
            "How readable the CV file is does not appear here and is not "
            "scored. It is measured separately and lowers confidence in the "
            "assessment rather than the candidate's score."
        ),
    }
}


class UnknownPreset(ValueError):
    pass


def available() -> list[dict]:
    """The presets a recruiter can choose from, for the rubric screen."""
    return list(PRESETS.values())


def _bucket_of(weight) -> object:
    """Which budget a criterion draws from: the mandatory block, or a category."""
    if weight.requirement_type == RequirementType.MANDATORY:
        return "mandatory"
    category = weight.category
    return CATEGORY_ALIASES.get(category, category)


def apply(version, preset_key: str = MARKET_STANDARD) -> None:
    """
    Re-weight a draft version's active criteria in place.

    Zero-weight criteria stay at zero: those are the informational rows the
    review screen shows without scoring, and a preset must not quietly start
    scoring something a recruiter chose not to score.
    """
    if preset_key not in PRESETS:
        raise UnknownPreset(
            f"There is no weighting called '{preset_key}'. "
            f"Available: {', '.join(sorted(PRESETS))}."
        )

    scored = [w for w in version.weights if w.active and w.weight > 0]
    if not scored:
        return

    buckets: dict[object, list] = {}
    for weight in scored:
        buckets.setdefault(_bucket_of(weight), []).append(weight)

    budgets: dict[object, float] = {"mandatory": MANDATORY_BUDGET}
    budgets.update(CATEGORY_BUDGETS)

    # A bucket with no criteria in this campaign gives its budget back, so
    # the remainder shares out in proportion rather than the total falling
    # short of 100.
    present = {key: budgets.get(key, 0.0) for key in buckets}
    total_budget = sum(present.values())
    if total_budget <= 0:
        # Nothing recognised — an even split is better than a zeroed rubric.
        share = 100.0 / len(scored)
        for weight in scored:
            weight.weight = round(share, 2)
        return

    for key, members in buckets.items():
        allocation = present[key] * 100.0 / total_budget
        share = allocation / len(members)
        for weight in members:
            weight.weight = round(share, 2)
