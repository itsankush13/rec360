"""
Phase B — Rubric + Weights + Disqualification + Versioning.

Replaces the flat-JSON `app.core.rubric_store` with real tables while keeping
the two legacy endpoints working (see `save_legacy_rubric` /
`approve_legacy_rubric` at the bottom of this module).

Invariants enforced here, not in the router:
  * Active weights in a version must sum to exactly 100 before it can be
    submitted or approved.
  * DRAFT is the only editable status. Anything APPROVED / LOCKED /
    SUPERSEDED is immutable — "editing" it means cloning to a new draft.
  * Approving a version never mutates the version it replaces; the old one
    is marked SUPERSEDED and kept intact so historical evaluations remain
    explainable.
  * Approving over an existing approved/locked rubric raises
    `reevaluation_required` on the new version. Nothing is re-scored
    automatically — a recruiter must acknowledge it. That is what makes
    re-evaluation "controlled".
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    AuditAction,
    Campaign,
    CampaignStatus,
    DisqualificationRule,
    JobRequirement,
    RequirementCategory,
    RequirementType,
    Rubric,
    RubricStatus,
    RubricVersion,
    RubricWeight,
    RuleOperator,
    RuleSeverity,
    RuleType,
    ScoringMethod,
)

from app.core import llm_usage, rubric_presets
from app.services import disposition_service

WEIGHT_TOLERANCE = 0.01
TOTAL_WEIGHT = 100.0


def _audit(db: Session, version: RubricVersion, action, summary: str,
           actor: str = "", after: dict | None = None) -> None:
    """
    One audit row per rubric state change, through the single audit path
    in disposition_service. Rubric approval is the control the client
    cares about most: it is what says a person signed off the rules
    before any CV was scored against them.
    """
    disposition_service.record_audit(
        db, action,
        campaign_id=version.rubric.campaign_id,
        entity_type="rubric_version",
        entity_id=version.id,
        summary=summary,
        after=after,
        actor=actor,
    )


class RubricStateError(RuntimeError):
    """Illegal workflow transition or an edit against a frozen version -> 409."""


class RubricValidationError(ValueError):
    """Content is invalid (weights, rules) -> 422."""

    def __init__(self, message: str, errors: list[str] | None = None):
        super().__init__(message)
        self.errors = errors or [message]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _slug(text: str, fallback: str = "criterion") -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", (text or "").lower()).strip("_")
    return (slug or fallback)[:120]


def _unique_key(existing: set[str], base: str) -> str:
    if base not in existing:
        return base
    n = 2
    while f"{base}_{n}" in existing:
        n += 1
    return f"{base}_{n}"


# ---------------------------------------------------------------------------
# Rubric container + version lookup
# ---------------------------------------------------------------------------

def get_rubric(db: Session, campaign_id: str) -> Rubric | None:
    return db.scalar(select(Rubric).where(Rubric.campaign_id == campaign_id))


def get_or_create_rubric(db: Session, campaign_id: str, name: str = "Evaluation Rubric") -> Rubric:
    rubric = get_rubric(db, campaign_id)
    if rubric is None:
        rubric = Rubric(campaign_id=campaign_id, name=name)
        db.add(rubric)
        db.flush()
    return rubric


def list_versions(db: Session, campaign_id: str) -> list[RubricVersion]:
    rubric = get_rubric(db, campaign_id)
    if rubric is None:
        return []
    return list(db.scalars(
        select(RubricVersion)
        .where(RubricVersion.rubric_id == rubric.id)
        .order_by(RubricVersion.version_number)
    ))


def get_version(db: Session, campaign_id: str, version_number: int) -> RubricVersion | None:
    rubric = get_rubric(db, campaign_id)
    if rubric is None:
        return None
    return db.scalar(
        select(RubricVersion).where(
            RubricVersion.rubric_id == rubric.id,
            RubricVersion.version_number == version_number,
        )
    )


def get_active_version(db: Session, campaign_id: str) -> RubricVersion | None:
    """The rubric evaluations should currently run against: newest APPROVED or LOCKED."""
    rubric = get_rubric(db, campaign_id)
    if rubric is None:
        return None
    return db.scalar(
        select(RubricVersion)
        .where(
            RubricVersion.rubric_id == rubric.id,
            RubricVersion.status.in_([RubricStatus.APPROVED, RubricStatus.LOCKED]),
        )
        .order_by(RubricVersion.version_number.desc())
        .limit(1)
    )


def get_latest_version(db: Session, campaign_id: str) -> RubricVersion | None:
    rubric = get_rubric(db, campaign_id)
    if rubric is None:
        return None
    return db.scalar(
        select(RubricVersion)
        .where(RubricVersion.rubric_id == rubric.id)
        .order_by(RubricVersion.version_number.desc())
        .limit(1)
    )


def active_version_number(db: Session, campaign_id: str) -> int | None:
    version = get_active_version(db, campaign_id)
    return version.version_number if version else None


def _next_version_number(db: Session, rubric: Rubric) -> int:
    latest = db.scalar(
        select(RubricVersion.version_number)
        .where(RubricVersion.rubric_id == rubric.id)
        .order_by(RubricVersion.version_number.desc())
        .limit(1)
    )
    return (latest or 0) + 1


def _require_editable(version: RubricVersion) -> None:
    if not version.is_editable:
        raise RubricStateError(
            f"Rubric version {version.version_number} is {version.status.value} and cannot be "
            f"edited. Create a new draft (clone_from_version={version.version_number}) instead — "
            f"approved rubrics are never modified in place."
        )


# ---------------------------------------------------------------------------
# Seeding from Phase A requirements
# ---------------------------------------------------------------------------

_RULE_TYPE_BY_CATEGORY = {
    RequirementCategory.EXPERIENCE: RuleType.MIN_YEARS_EXPERIENCE,
    RequirementCategory.SKILL: RuleType.MISSING_MANDATORY_SKILL,
    RequirementCategory.QUALIFICATION: RuleType.MISSING_QUALIFICATION,
    RequirementCategory.CERTIFICATION: RuleType.MISSING_CERTIFICATION,
    RequirementCategory.LOCATION: RuleType.LOCATION_MISMATCH,
    RequirementCategory.ELIGIBILITY: RuleType.ELIGIBILITY_FAILURE,
}


def _years_from_text(text: str) -> float | None:
    match = re.search(r"(\d+(?:\.\d+)?)\s*(?:\+)?\s*year", text or "", re.IGNORECASE)
    return float(match.group(1)) if match else None


def seed_from_requirements(db: Session, version: RubricVersion, campaign_id: str) -> RubricVersion:
    """
    Build weights + disqualification rules from the campaign's JobRequirement
    rows (Phase A). Scored criteria are the MANDATORY and PREFERRED
    requirements; INFORMATIONAL rows are carried as zero-weight criteria so
    they still show on the review screen without affecting the score.

    Existing requirement weights are rescaled proportionally to sum to 100 —
    Phase A's extraction produces a partial budget (40 skills + 25 experience
    + 15 education = 80), which would otherwise fail submit validation.
    """
    requirements = list(db.scalars(
        select(JobRequirement)
        .where(JobRequirement.campaign_id == campaign_id)
        .order_by(JobRequirement.priority, JobRequirement.created_at)
    ))
    if not requirements:
        raise RubricValidationError(
            "Cannot seed a rubric: this campaign has no requirements yet. "
            "Run requirement extraction first."
        )

    scored = [r for r in requirements if r.requirement_type in (
        RequirementType.MANDATORY, RequirementType.PREFERRED
    )]
    informational = [r for r in requirements if r.requirement_type == RequirementType.INFORMATIONAL]

    if not scored:
        raise RubricValidationError(
            "Cannot seed a rubric: the campaign has no mandatory or preferred "
            "requirements to score against."
        )

    raw_total = sum(r.weight for r in scored)
    if raw_total > 0:
        weights = {r.id: r.weight * TOTAL_WEIGHT / raw_total for r in scored}
    else:
        # Nothing carried a weight — split evenly across mandatory rows if
        # there are any, otherwise evenly across everything scored.
        mandatory = [r for r in scored if r.requirement_type == RequirementType.MANDATORY]
        target = mandatory or scored
        share = TOTAL_WEIGHT / len(target)
        weights = {r.id: (share if r in target else 0.0) for r in scored}

    keys: set[str] = set()
    order = 0

    def _add_weight(requirement: JobRequirement, weight_value: float) -> None:
        nonlocal order
        key = _unique_key(keys, _slug(requirement.description))
        keys.add(key)
        version.weights.append(RubricWeight(
            requirement_id=requirement.id,
            criterion_key=key,
            label=requirement.description,
            category=requirement.category,
            requirement_type=requirement.requirement_type,
            weight=round(weight_value, 2),
            max_score=100.0,
            scoring_method=(
                ScoringMethod.BINARY
                if requirement.category in (RequirementCategory.ELIGIBILITY, RequirementCategory.LOCATION)
                else ScoringMethod.WEIGHTED
            ),
            evidence_required=requirement.evidence_required,
            active=True,
            display_order=order,
        ))
        order += 1

    for requirement in scored:
        _add_weight(requirement, weights.get(requirement.id, 0.0))
    for requirement in informational:
        _add_weight(requirement, 0.0)

    # Rounding to 2dp can leave the total a hair off 100; push the remainder
    # onto the heaviest active criterion so the invariant holds exactly.
    _absorb_rounding(version)

    # Disqualification rules from requirements flagged disqualifying.
    codes: set[str] = set()
    rule_order = 0
    for requirement in requirements:
        if not requirement.disqualifying:
            continue
        rule_type = _RULE_TYPE_BY_CATEGORY.get(requirement.category, RuleType.CUSTOM)
        code = _unique_key(codes, _slug(requirement.description, "rule"))
        codes.add(code)

        if rule_type == RuleType.MIN_YEARS_EXPERIENCE:
            years = _years_from_text(requirement.description)
            operator, threshold = RuleOperator.LT, years
        else:
            operator, threshold = RuleOperator.MISSING, None

        version.disqualification_rules.append(DisqualificationRule(
            requirement_id=requirement.id,
            code=code,
            label=requirement.description,
            rule_type=rule_type,
            operator=operator,
            threshold=threshold,
            severity=(
                RuleSeverity.REVIEW_REQUIRED
                if threshold is None and rule_type == RuleType.MIN_YEARS_EXPERIENCE
                else RuleSeverity.HARD_FAIL
            ),
            message=f"Does not meet mandatory requirement: {requirement.description}",
            active=True,
            display_order=rule_order,
        ))
        rule_order += 1

    db.flush()
    return version


def _absorb_rounding(version: RubricVersion) -> None:
    active = [w for w in version.weights if w.active and w.weight > 0]
    if not active:
        return
    drift = round(TOTAL_WEIGHT - sum(w.weight for w in active), 2)
    if abs(drift) < WEIGHT_TOLERANCE:
        return
    heaviest = max(active, key=lambda w: w.weight)
    heaviest.weight = round(max(0.0, heaviest.weight + drift), 2)


# ---------------------------------------------------------------------------
# Version create / clone
# ---------------------------------------------------------------------------

def create_version(
    db: Session,
    campaign: Campaign,
    *,
    notes: str = "",
    change_reason: str = "",
    created_by: str = "",
    clone_from_version: int | None = None,
    seed_from_requirements_flag: bool = False,
    weighting: str | None = None,
) -> RubricVersion:
    rubric = get_or_create_rubric(db, campaign.id, name=f"{campaign.job_title} rubric")

    # Only one draft in flight at a time — otherwise "which draft am I
    # approving?" becomes ambiguous on the review screen.
    existing_draft = db.scalar(
        select(RubricVersion).where(
            RubricVersion.rubric_id == rubric.id,
            RubricVersion.status.in_([RubricStatus.DRAFT, RubricStatus.SUBMITTED]),
        )
    )
    if existing_draft is not None:
        raise RubricStateError(
            f"Version {existing_draft.version_number} is already {existing_draft.status.value}. "
            "Approve or reject it before starting another draft."
        )

    source: RubricVersion | None = None
    if clone_from_version is not None:
        source = get_version(db, campaign.id, clone_from_version)
        if source is None:
            raise RubricValidationError(f"Rubric version {clone_from_version} does not exist")

    version = RubricVersion(
        rubric_id=rubric.id,
        version_number=_next_version_number(db, rubric),
        status=RubricStatus.DRAFT,
        notes=notes,
        change_reason=change_reason,
        created_by=created_by,
        cloned_from_version_id=source.id if source else None,
    )
    db.add(version)
    db.flush()

    if source is not None:
        _copy_contents(source, version)
        db.flush()
    elif seed_from_requirements_flag:
        seed_from_requirements(db, version, campaign.id)

    # A starting weighting is applied over whatever was seeded or cloned, and
    # only ever to a DRAFT. The version still has to be submitted and
    # approved by a person before a single CV is scored against it.
    if weighting:
        rubric_presets.apply(version, weighting)
        _absorb_rounding(version)
        db.flush()

    _audit(
        db, version, AuditAction.RUBRIC_VERSION_CREATED,
        f"Rubric version {version.version_number} drafted"
        + (f" using the {rubric_presets.PRESETS[weighting]['label'].lower()}"
           if weighting in rubric_presets.PRESETS else "")
        + (f": {change_reason}" if change_reason else ""),
        actor=created_by,
        after={"version": version.version_number,
               "copied_from_version": source.version_number if source else None},
    )

    db.commit()
    db.refresh(version)
    return version


def _copy_contents(source: RubricVersion, target: RubricVersion) -> None:
    """Deep-copy weights and rules. The source rows are never touched."""
    for weight in source.weights:
        target.weights.append(RubricWeight(
            requirement_id=weight.requirement_id,
            criterion_key=weight.criterion_key,
            label=weight.label,
            category=weight.category,
            requirement_type=weight.requirement_type,
            weight=weight.weight,
            max_score=weight.max_score,
            scoring_method=weight.scoring_method,
            evidence_required=weight.evidence_required,
            active=weight.active,
            display_order=weight.display_order,
        ))
    for rule in source.disqualification_rules:
        target.disqualification_rules.append(DisqualificationRule(
            requirement_id=rule.requirement_id,
            code=rule.code,
            label=rule.label,
            rule_type=rule.rule_type,
            operator=rule.operator,
            threshold=rule.threshold,
            value=rule.value,
            params=dict(rule.params) if rule.params else None,
            severity=rule.severity,
            message=rule.message,
            active=rule.active,
            display_order=rule.display_order,
        ))


def update_version(db: Session, version: RubricVersion, *, notes=None, change_reason=None) -> RubricVersion:
    _require_editable(version)
    if notes is not None:
        version.notes = notes
    if change_reason is not None:
        version.change_reason = change_reason
    db.commit()
    db.refresh(version)
    return version


def delete_version(db: Session, version: RubricVersion) -> None:
    if version.status != RubricStatus.DRAFT:
        raise RubricStateError(
            f"Only DRAFT versions can be deleted; version {version.version_number} "
            f"is {version.status.value}. Rubric history is never destroyed."
        )
    db.delete(version)
    db.commit()


# ---------------------------------------------------------------------------
# Weights
# ---------------------------------------------------------------------------

def add_weight(db: Session, version: RubricVersion, payload) -> RubricWeight:
    _require_editable(version)
    data = payload.model_dump()
    requested_key = data.pop("criterion_key", None)
    existing_keys = {w.criterion_key for w in version.weights}
    key = _unique_key(existing_keys, requested_key or _slug(data["label"]))

    if requested_key and requested_key in existing_keys:
        raise RubricValidationError(
            f"criterion_key '{requested_key}' is already used in version {version.version_number}"
        )

    requirement_id = data.get("requirement_id")
    if requirement_id:
        _validate_requirement_belongs(db, version, requirement_id)

    weight = RubricWeight(rubric_version_id=version.id, criterion_key=key, **data)
    db.add(weight)
    db.commit()
    db.refresh(weight)
    return weight


def update_weight(db: Session, version: RubricVersion, weight: RubricWeight, payload) -> RubricWeight:
    _require_editable(version)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(weight, field, value)
    db.commit()
    db.refresh(weight)
    return weight


def delete_weight(db: Session, version: RubricVersion, weight: RubricWeight) -> None:
    _require_editable(version)
    db.delete(weight)
    db.commit()


def bulk_set_weights(db: Session, version: RubricVersion, items) -> RubricVersion:
    """Save the whole weights table in one call (the UI's primary save action)."""
    _require_editable(version)
    by_key = {w.criterion_key: w for w in version.weights}
    unknown = [i.criterion_key for i in items if i.criterion_key not in by_key]
    if unknown:
        raise RubricValidationError(
            f"Unknown criterion_key(s) for version {version.version_number}: {', '.join(unknown)}"
        )
    for item in items:
        by_key[item.criterion_key].weight = round(item.weight, 2)
    db.commit()
    db.refresh(version)
    return version


def normalize_weights(db: Session, version: RubricVersion) -> RubricVersion:
    """
    Rescale active weights proportionally so they sum to exactly 100.
    Convenience for the review screen's "balance weights" button — it does not
    change the *relative* emphasis a recruiter has already set.
    """
    _require_editable(version)
    active = [w for w in version.weights if w.active]
    total = sum(w.weight for w in active)
    if not active:
        raise RubricValidationError("Version has no active criteria to normalize")
    if total <= 0:
        share = round(TOTAL_WEIGHT / len(active), 2)
        for weight in active:
            weight.weight = share
    else:
        for weight in active:
            weight.weight = round(weight.weight * TOTAL_WEIGHT / total, 2)
    _absorb_rounding(version)
    db.commit()
    db.refresh(version)
    return version


def suggest_weights(db: Session, version: RubricVersion) -> RubricVersion:
    """
    B07 — ask the LLM for a per-JD weight suggestion for every active
    criterion, then rescale to sum to exactly 100 (same math as
    `normalize_weights`). Unlike `rubric_presets` (a static
    MARKET_STANDARD table), this is tailored to the campaign's own job
    title and job description.
    """
    _require_editable(version)
    active = [w for w in version.weights if w.active]
    if not active:
        raise RubricValidationError("Version has no active criteria to suggest weights for")

    campaign = version.rubric.campaign
    criteria = [
        {
            "criterion_key": w.criterion_key,
            "label": w.label,
            "category": w.category.value,
            "requirement_type": w.requirement_type.value,
        }
        for w in active
    ]

    try:
        from app.agents.weight_suggestion_agent import suggest_weights as _suggest_weights
        with llm_usage.track(db, campaign_id=version.rubric.campaign_id, call_type="weight_suggestion"):
            suggested = _suggest_weights(campaign.job_title, campaign.job_description, criteria)
    except Exception as exc:
        raise RubricValidationError(
            "AI weight suggestion is unavailable right now — enter weights manually."
        ) from exc

    for weight in active:
        if weight.criterion_key in suggested:
            weight.weight = round(suggested[weight.criterion_key], 2)

    total = sum(w.weight for w in active)
    if total <= 0:
        share = round(TOTAL_WEIGHT / len(active), 2)
        for weight in active:
            weight.weight = share
    else:
        for weight in active:
            weight.weight = round(weight.weight * TOTAL_WEIGHT / total, 2)
    _absorb_rounding(version)

    db.commit()
    db.refresh(version)
    return version


def _validate_requirement_belongs(db: Session, version: RubricVersion, requirement_id: str) -> None:
    requirement = db.get(JobRequirement, requirement_id)
    campaign_id = version.rubric.campaign_id
    if requirement is None or requirement.campaign_id != campaign_id:
        raise RubricValidationError(
            f"Requirement {requirement_id} does not belong to this campaign"
        )


# ---------------------------------------------------------------------------
# Disqualification rules
# ---------------------------------------------------------------------------

def add_rule(db: Session, version: RubricVersion, payload) -> DisqualificationRule:
    _require_editable(version)
    data = payload.model_dump()
    requested_code = data.pop("code", None)
    existing = {r.code for r in version.disqualification_rules}
    if requested_code and requested_code in existing:
        raise RubricValidationError(
            f"Rule code '{requested_code}' is already used in version {version.version_number}"
        )
    code = _unique_key(existing, requested_code or _slug(data["label"], "rule"))

    if data.get("requirement_id"):
        _validate_requirement_belongs(db, version, data["requirement_id"])

    _validate_rule_payload(data)

    rule = DisqualificationRule(rubric_version_id=version.id, code=code, **data)
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


def update_rule(db: Session, version: RubricVersion, rule: DisqualificationRule, payload) -> DisqualificationRule:
    _require_editable(version)
    updates = payload.model_dump(exclude_unset=True)
    if updates.get("requirement_id"):
        _validate_requirement_belongs(db, version, updates["requirement_id"])
    merged = {
        "rule_type": rule.rule_type,
        "operator": rule.operator,
        "threshold": rule.threshold,
        "value": rule.value,
        **updates,
    }
    _validate_rule_payload(merged)
    for field, value in updates.items():
        setattr(rule, field, value)
    db.commit()
    db.refresh(rule)
    return rule


def delete_rule(db: Session, version: RubricVersion, rule: DisqualificationRule) -> None:
    _require_editable(version)
    db.delete(rule)
    db.commit()


_NUMERIC_OPERATORS = {RuleOperator.LT, RuleOperator.LTE, RuleOperator.GT, RuleOperator.GTE}
_VALUE_OPERATORS = {RuleOperator.EQ, RuleOperator.NEQ, RuleOperator.IN, RuleOperator.NOT_IN}


def _validate_rule_payload(data: dict) -> None:
    operator = data.get("operator")
    if operator in _NUMERIC_OPERATORS and data.get("threshold") is None:
        raise RubricValidationError(
            f"Operator {operator.value} requires a numeric 'threshold'"
        )
    if operator in _VALUE_OPERATORS and not (data.get("value") or "").strip():
        raise RubricValidationError(
            f"Operator {operator.value} requires a non-empty 'value'"
        )


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_version(version: RubricVersion) -> dict:
    errors: list[str] = []
    warnings: list[str] = []

    active = [w for w in version.weights if w.active]
    if not active:
        errors.append("Rubric has no active scoring criteria.")

    total = version.weight_total
    if active and not version.is_balanced:
        errors.append(
            f"Active criterion weights sum to {total} — they must sum to exactly 100."
        )

    seen: set[str] = set()
    for weight in version.weights:
        if weight.criterion_key in seen:
            errors.append(f"Duplicate criterion_key '{weight.criterion_key}'.")
        seen.add(weight.criterion_key)
        if weight.weight < 0:
            errors.append(f"Criterion '{weight.label}' has a negative weight.")

    zero_mandatory = [
        w.label for w in active
        if w.requirement_type == RequirementType.MANDATORY and w.weight <= 0
    ]
    if zero_mandatory:
        warnings.append(
            "Mandatory criteria carry zero weight and will not affect the score: "
            + ", ".join(zero_mandatory[:5])
        )

    no_evidence = [
        w.label for w in active
        if w.requirement_type == RequirementType.MANDATORY and not w.evidence_required
    ]
    if no_evidence:
        warnings.append(
            "Mandatory criteria without required evidence: " + ", ".join(no_evidence[:5])
        )

    for rule in version.disqualification_rules:
        if not rule.active:
            continue
        try:
            _validate_rule_payload({
                "operator": rule.operator,
                "threshold": rule.threshold,
                "value": rule.value,
            })
        except RubricValidationError as exc:
            errors.append(f"Rule '{rule.label}': {exc}")

    if not [r for r in version.disqualification_rules if r.active]:
        warnings.append(
            "No active disqualification rules — every candidate will pass eligibility screening."
        )

    return {
        "valid": not errors,
        "weight_total": total,
        "is_balanced": version.is_balanced,
        "errors": errors,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# Workflow: Draft -> Submitted -> Approved -> Locked
# ---------------------------------------------------------------------------

def _sync_campaign_status(db: Session, campaign: Campaign, target: CampaignStatus) -> None:
    """Best-effort campaign status nudge; never blocks the rubric action."""
    if campaign.status == target:
        return
    if campaign.can_transition_to(target):
        campaign.status = target


def submit_version(db: Session, version: RubricVersion, submitted_by: str = "") -> RubricVersion:
    if version.status != RubricStatus.DRAFT:
        raise RubricStateError(
            f"Only a DRAFT version can be submitted; version {version.version_number} "
            f"is {version.status.value}."
        )
    report = validate_version(version)
    if not report["valid"]:
        raise RubricValidationError(
            "Rubric version failed validation and cannot be submitted", report["errors"]
        )

    version.status = RubricStatus.SUBMITTED
    version.submitted_at = _now()
    version.submitted_by = submitted_by
    _audit(
        db, version, AuditAction.RUBRIC_SUBMITTED,
        f"Rubric version {version.version_number} sent for approval",
        actor=submitted_by,
    )
    _sync_campaign_status(db, version.rubric.campaign, CampaignStatus.AWAITING_RUBRIC_APPROVAL)
    db.commit()
    db.refresh(version)
    return version


def approve_version(
    db: Session, version: RubricVersion, approved_by: str = "", lock_immediately: bool = False
) -> RubricVersion:
    if version.status != RubricStatus.SUBMITTED:
        raise RubricStateError(
            f"Only a SUBMITTED version can be approved; version {version.version_number} "
            f"is {version.status.value}."
        )
    report = validate_version(version)
    if not report["valid"]:
        raise RubricValidationError(
            "Rubric version failed validation and cannot be approved", report["errors"]
        )

    # Supersede whatever was live. The old rows are left byte-for-byte intact.
    previous = list(db.scalars(
        select(RubricVersion)
        .where(
            RubricVersion.rubric_id == version.rubric_id,
            RubricVersion.id != version.id,
            RubricVersion.status.in_([RubricStatus.APPROVED, RubricStatus.LOCKED]),
        )
        .order_by(RubricVersion.version_number.desc())
    ))
    if previous:
        version.supersedes_version_id = previous[0].id
        version.reevaluation_required = True
        for old in previous:
            old.status = RubricStatus.SUPERSEDED
            old.superseded_at = _now()

    version.status = RubricStatus.APPROVED
    version.approved_at = _now()
    version.approved_by = approved_by
    if lock_immediately:
        version.status = RubricStatus.LOCKED
        version.locked_at = _now()

    _audit(
        db, version, AuditAction.RUBRIC_APPROVED,
        f"Rubric version {version.version_number} approved"
        + (f", replacing version {previous[0].version_number}" if previous else "")
        + ". Every CV assessed from now on is scored against it.",
        actor=approved_by,
        after={"version": version.version_number,
               "replaced_version": previous[0].version_number if previous else None,
               "earlier_results_need_assessing_again": bool(previous)},
    )
    if lock_immediately:
        _audit(
            db, version, AuditAction.RUBRIC_LOCKED,
            f"Rubric version {version.version_number} locked. "
            "It can no longer be edited; a change needs a new version "
            "and a new approval.",
            actor=approved_by,
        )
    _sync_campaign_status(db, version.rubric.campaign, CampaignStatus.APPROVED)
    db.commit()
    db.refresh(version)
    return version


def reject_version(
    db: Session, version: RubricVersion, rejected_by: str = "", rejection_reason: str = ""
) -> RubricVersion:
    if version.status != RubricStatus.SUBMITTED:
        raise RubricStateError(
            f"Only a SUBMITTED version can be rejected; version {version.version_number} "
            f"is {version.status.value}."
        )
    version.status = RubricStatus.REJECTED
    version.rejected_at = _now()
    version.rejected_by = rejected_by
    version.rejection_reason = rejection_reason
    _audit(
        db, version, AuditAction.RUBRIC_REJECTED,
        f"Rubric version {version.version_number} sent back"
        + (f": {rejection_reason}" if rejection_reason else ""),
        actor=rejected_by,
    )
    # Send the campaign back so the recruiter can revise and resubmit.
    _sync_campaign_status(db, version.rubric.campaign, CampaignStatus.DRAFT)
    db.commit()
    db.refresh(version)
    return version


def lock_version(db: Session, version: RubricVersion) -> RubricVersion:
    if version.status != RubricStatus.APPROVED:
        raise RubricStateError(
            f"Only an APPROVED version can be locked; version {version.version_number} "
            f"is {version.status.value}."
        )
    version.status = RubricStatus.LOCKED
    version.locked_at = _now()
    _audit(
        db, version, AuditAction.RUBRIC_LOCKED,
        f"Rubric version {version.version_number} locked. "
        "It can no longer be edited; a change needs a new version "
        "and a new approval.",
    )
    db.commit()
    db.refresh(version)
    return version


def acknowledge_reevaluation(db: Session, version: RubricVersion, acknowledged_by: str = "") -> RubricVersion:
    """
    Recruiter confirms they've seen that results on file predate this rubric.
    Phase D/E will read this flag to decide which candidates need re-scoring;
    nothing is re-scored here, and no historical result is touched.
    """
    if not version.reevaluation_required:
        raise RubricStateError(
            f"Version {version.version_number} does not require re-evaluation acknowledgement."
        )
    version.reevaluation_required = False
    version.reevaluation_acknowledged_at = _now()
    version.reevaluation_acknowledged_by = acknowledged_by
    db.commit()
    db.refresh(version)
    return version


# ---------------------------------------------------------------------------
# Legacy flat-JSON compatibility
#
# The existing React client (frontend/src/lib/api.js) and Streamlit rubric tab
# post a flat list like:
#     [{"criterion": "Skills", "weight": 25, "type": "Mandatory"}, ...]
# and expect back {"version_id": <int>, "campaign_id", "rubric", "approved"}.
# These two functions keep that contract while writing to the real Phase B
# tables, so the old screens keep working through the transition.
# `app.core.rubric_store` is left on disk untouched for historical reads.
# ---------------------------------------------------------------------------

_LEGACY_TYPE_MAP = {
    "mandatory": RequirementType.MANDATORY,
    "preferred": RequirementType.PREFERRED,
    "informational": RequirementType.INFORMATIONAL,
}


def _legacy_get(item: dict, *names, default=None):
    for name in names:
        for candidate in (name, name.capitalize(), name.upper(), name.title()):
            if candidate in item:
                return item[candidate]
    return default


def legacy_serialize(version: RubricVersion) -> dict:
    return {
        "version_id": version.version_number,
        "campaign_id": version.rubric.campaign_id,
        "rubric": [
            {
                "criterion": w.label,
                "weight": w.weight,
                "type": w.requirement_type.value.capitalize(),
                "criterion_key": w.criterion_key,
            }
            for w in version.weights
            if w.active
        ],
        "approved": version.is_usable_for_evaluation,
        "approved_at": version.approved_at,
    }


def _ensure_campaign(db: Session, campaign_id: str) -> Campaign:
    """
    The legacy client uses opaque ids (e.g. "1") that may not exist as real
    campaigns. Rather than 404 and break the old screen, provision a
    placeholder campaign so the rubric has a valid parent row.
    """
    campaign = db.get(Campaign, campaign_id)
    if campaign is not None:
        return campaign
    campaign = Campaign(
        id=str(campaign_id),
        name=f"Legacy campaign {campaign_id}",
        job_title="Imported from legacy rubric API",
        job_description="",
        created_by="legacy-api",
    )
    db.add(campaign)
    db.flush()
    return campaign


def save_legacy_rubric(db: Session, campaign_id: str, rubric: list[dict]) -> dict:
    if not rubric:
        raise RubricValidationError("Rubric payload is empty")

    campaign = _ensure_campaign(db, str(campaign_id))
    rubric_row = get_or_create_rubric(db, campaign.id)

    # Supersede any in-flight draft: the legacy client has no concept of
    # draft slots, so a fresh POST replaces the pending one.
    stale = list(db.scalars(
        select(RubricVersion).where(
            RubricVersion.rubric_id == rubric_row.id,
            RubricVersion.status.in_([RubricStatus.DRAFT, RubricStatus.SUBMITTED]),
        )
    ))
    for old in stale:
        db.delete(old)
    db.flush()

    version = RubricVersion(
        rubric_id=rubric_row.id,
        version_number=_next_version_number(db, rubric_row),
        status=RubricStatus.DRAFT,
        created_by="legacy-api",
        change_reason="Saved via legacy flat-JSON rubric endpoint",
    )
    db.add(version)
    db.flush()

    keys: set[str] = set()
    for order, item in enumerate(rubric):
        label = str(_legacy_get(item, "criterion", "label", "name", default="") or "").strip()
        if not label:
            continue
        raw_weight = _legacy_get(item, "weight", default=0) or 0
        try:
            weight_value = float(raw_weight)
        except (TypeError, ValueError):
            weight_value = 0.0
        raw_type = str(_legacy_get(item, "type", "requirement_type", default="Mandatory") or "")
        key = _unique_key(keys, _slug(label))
        keys.add(key)
        version.weights.append(RubricWeight(
            criterion_key=key,
            label=label,
            requirement_type=_LEGACY_TYPE_MAP.get(raw_type.strip().lower(), RequirementType.MANDATORY),
            weight=round(max(0.0, weight_value), 2),
            display_order=order,
        ))

    if not version.weights:
        raise RubricValidationError("Rubric payload contained no usable criteria")

    db.flush()
    db.commit()
    db.refresh(version)
    return legacy_serialize(version)


def approve_legacy_rubric(db: Session, campaign_id: str, version_id: int | None = None) -> dict:
    campaign_id = str(campaign_id)
    if version_id is None:
        version = get_latest_version(db, campaign_id)
    else:
        version = get_version(db, campaign_id, int(version_id))
    if version is None:
        raise RubricValidationError("No rubric draft exists for this campaign")

    if version.is_usable_for_evaluation:
        return legacy_serialize(version)

    # Legacy payloads routinely don't sum to 100 (the shipped default sums to
    # 80). Normalize rather than reject, so the old screen keeps working while
    # the weights-sum-to-100 invariant still holds in the database.
    if version.status == RubricStatus.DRAFT:
        if not version.is_balanced:
            normalize_weights(db, version)
        submit_version(db, version, submitted_by="legacy-api")

    if version.status == RubricStatus.SUBMITTED:
        approve_version(db, version, approved_by="legacy-api")

    db.refresh(version)
    return legacy_serialize(version)
