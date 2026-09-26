"""
Phase B request/response schemas.

Versions are addressed in the API by `version_number` (1, 2, 3, ...) rather
than UUID, because that is what recruiters see on the Requirement & Rubric
Review screen and what the legacy flat-JSON API already returned.
"""
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.db.models import (
    RequirementCategory,
    RequirementType,
    RubricStatus,
    RuleOperator,
    RuleSeverity,
    RuleType,
    ScoringMethod,
)


# ---------- Weights ----------

class RubricWeightCreate(BaseModel):
    criterion_key: Optional[str] = Field(
        default=None,
        description="Stable machine key. Auto-slugged from the label if omitted.",
    )
    label: str
    requirement_id: Optional[str] = None
    category: RequirementCategory = RequirementCategory.SKILL
    requirement_type: RequirementType = RequirementType.MANDATORY
    weight: float = Field(default=0.0, ge=0.0, le=100.0)
    max_score: float = Field(default=100.0, gt=0.0)
    scoring_method: ScoringMethod = ScoringMethod.WEIGHTED
    evidence_required: bool = True
    active: bool = True
    display_order: int = 0


class RubricWeightUpdate(BaseModel):
    label: Optional[str] = None
    category: Optional[RequirementCategory] = None
    requirement_type: Optional[RequirementType] = None
    weight: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    max_score: Optional[float] = Field(default=None, gt=0.0)
    scoring_method: Optional[ScoringMethod] = None
    evidence_required: Optional[bool] = None
    active: Optional[bool] = None
    display_order: Optional[int] = None


class RubricWeightOut(BaseModel):
    id: str
    rubric_version_id: str
    requirement_id: Optional[str]
    criterion_key: str
    label: str
    category: RequirementCategory
    requirement_type: RequirementType
    weight: float
    max_score: float
    scoring_method: ScoringMethod
    evidence_required: bool
    active: bool
    display_order: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WeightBulkSetItem(BaseModel):
    """One entry in a bulk weight re-set (the 'save the whole weights table' action)."""
    criterion_key: str
    weight: float = Field(ge=0.0, le=100.0)


class WeightBulkSetRequest(BaseModel):
    weights: list[WeightBulkSetItem]


# ---------- Disqualification rules ----------

class DisqualificationRuleCreate(BaseModel):
    code: Optional[str] = Field(
        default=None, description="Stable machine code. Auto-slugged from the label if omitted."
    )
    label: str
    requirement_id: Optional[str] = None
    rule_type: RuleType = RuleType.CUSTOM
    operator: RuleOperator = RuleOperator.MISSING
    threshold: Optional[float] = None
    value: str = ""
    params: Optional[dict[str, Any]] = None
    severity: RuleSeverity = RuleSeverity.HARD_FAIL
    message: str = ""
    active: bool = True
    display_order: int = 0


class DisqualificationRuleUpdate(BaseModel):
    label: Optional[str] = None
    requirement_id: Optional[str] = None
    rule_type: Optional[RuleType] = None
    operator: Optional[RuleOperator] = None
    threshold: Optional[float] = None
    value: Optional[str] = None
    params: Optional[dict[str, Any]] = None
    severity: Optional[RuleSeverity] = None
    message: Optional[str] = None
    active: Optional[bool] = None
    display_order: Optional[int] = None


class DisqualificationRuleOut(BaseModel):
    id: str
    rubric_version_id: str
    requirement_id: Optional[str]
    code: str
    label: str
    rule_type: RuleType
    operator: RuleOperator
    threshold: Optional[float]
    value: str
    params: Optional[dict[str, Any]]
    severity: RuleSeverity
    message: str
    active: bool
    display_order: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------- Versions ----------

class RubricVersionCreate(BaseModel):
    """
    Create a new DRAFT version.

    Exactly one starting point applies, in this precedence order:
      1. `clone_from_version` — copy weights + rules from an existing version
         (this is how an approved rubric is 'edited' without being mutated).
      2. `seed_from_requirements` — build weights and disqualification rules
         from the campaign's Phase A JobRequirement rows.
      3. neither — an empty draft the recruiter fills in by hand.
    """
    notes: str = ""
    change_reason: str = ""
    created_by: str = ""
    clone_from_version: Optional[int] = None
    seed_from_requirements: bool = False
    # Optional starting weighting, applied after seeding. A template for the
    # recruiter to adjust and approve — never a second way of scoring.
    weighting: Optional[str] = None


class RubricVersionUpdate(BaseModel):
    notes: Optional[str] = None
    change_reason: Optional[str] = None


class RubricVersionSummary(BaseModel):
    id: str
    version_number: int
    status: RubricStatus
    notes: str
    change_reason: str
    weight_total: float
    is_balanced: bool
    reevaluation_required: bool
    created_by: str
    approved_by: str
    created_at: datetime
    approved_at: Optional[datetime]
    locked_at: Optional[datetime]
    superseded_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


class RubricVersionOut(BaseModel):
    id: str
    rubric_id: str
    version_number: int
    status: RubricStatus
    notes: str
    change_reason: str
    cloned_from_version_id: Optional[str]
    supersedes_version_id: Optional[str]
    reevaluation_required: bool
    reevaluation_acknowledged_at: Optional[datetime]
    reevaluation_acknowledged_by: str
    created_by: str
    submitted_by: str
    approved_by: str
    rejected_by: str
    rejection_reason: str
    created_at: datetime
    submitted_at: Optional[datetime]
    approved_at: Optional[datetime]
    locked_at: Optional[datetime]
    rejected_at: Optional[datetime]
    superseded_at: Optional[datetime]

    weight_total: float
    is_balanced: bool
    is_editable: bool

    weights: list[RubricWeightOut] = []
    disqualification_rules: list[DisqualificationRuleOut] = []

    model_config = ConfigDict(from_attributes=True)


class RubricOut(BaseModel):
    id: str
    campaign_id: str
    name: str
    created_at: datetime
    versions: list[RubricVersionSummary] = []
    active_version_number: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


# ---------- Workflow actions ----------

class SubmitRequest(BaseModel):
    submitted_by: str = ""


class ApproveRequest(BaseModel):
    approved_by: str = ""
    lock_immediately: bool = False


class RejectRequest(BaseModel):
    rejected_by: str = ""
    rejection_reason: str = ""


class AcknowledgeReevaluationRequest(BaseModel):
    acknowledged_by: str = ""


class ValidationReport(BaseModel):
    """What the Rubric Review screen shows next to the Submit button."""
    valid: bool
    weight_total: float
    is_balanced: bool
    errors: list[str] = []
    warnings: list[str] = []


# ---------- Legacy compatibility (flat-JSON rubric API) ----------

class LegacyRubricRequest(BaseModel):
    rubric: list[dict[str, Any]]


class LegacyApproveRubricRequest(BaseModel):
    version_id: Optional[int] = None


class LegacyRubricResponse(BaseModel):
    version_id: int
    campaign_id: str
    rubric: list[dict[str, Any]]
    approved: bool
    approved_at: Optional[datetime] = None
