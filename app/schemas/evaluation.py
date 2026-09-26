"""
Request/response schemas for the Phase D evaluation API.

Response shapes follow the client's Candidate 360 requirement closely:
criterion-level scores, confidence, eligibility, evidence excerpts with page
or section references, and missing information are all first-class fields
rather than something a caller has to reconstruct. Phase E's Challenge
Agent findings and the recruiter disposition are the two remaining
Candidate 360 sections, and they hang off this shape without changing it.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.db.models import (
    ChallengeCheck, ChallengeScope, ChallengeSeverity,
    ConfidenceBand, CriterionOutcome, EligibilityStatus, EvaluationStatus,
    EvidenceMatchType, Recommendation, RequirementCategory, RequirementType,
    RuleOperator, RuleSeverity, RuleType, RunStatus, RunTrigger, ScoringMethod,
    ScoringMode,
)


class RunCreate(BaseModel):
    """Start an evaluation run."""
    batch_id: str | None = Field(
        default=None,
        description=(
            "Score the candidates from this batch, against the rubric version "
            "the batch was pinned to."
        ),
    )
    rubric_version_id: str | None = Field(
        default=None,
        description=(
            "Override the rubric version. Must be APPROVED or LOCKED and belong "
            "to this campaign. Defaults to the batch's pinned version, or the "
            "campaign's active version."
        ),
    )
    candidate_ids: list[str] | None = Field(
        default=None, description="Score only these candidates."
    )
    scoring_mode: ScoringMode = Field(
        default=ScoringMode.DETERMINISTIC,
        description=(
            "DETERMINISTIC is fully reproducible and needs no model. "
            "LLM_ASSISTED runs the same deterministic pass and then allows "
            "bounded per-criterion adjustments; eligibility is unaffected either way."
        ),
    )
    only_unevaluated: bool = Field(
        default=False,
        description="Skip candidates already scored against this rubric version.",
    )
    execute: bool = Field(
        default=True,
        description="Score immediately. False creates the run for a worker to drain.",
    )
    demo_delay_seconds: float = Field(
        default=0.0,
        ge=0.0,
        le=5.0,
        description="Optional pacing delay after each candidate, for a live walkthrough.",
    )
    created_by: str = ""
    notes: str = ""


class EvidenceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    excerpt: str
    page_number: int | None
    section: str
    char_start: int | None
    char_end: int | None
    match_type: EvidenceMatchType
    matched_term: str
    relevance: float


class CriterionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    criterion_key: str
    label: str
    category: RequirementCategory
    requirement_type: RequirementType
    weight: float
    max_score: float
    scoring_method: ScoringMethod
    deterministic_score: float
    raw_score: float
    weighted_score: float
    llm_adjusted: bool
    outcome: CriterionOutcome
    confidence: float
    confidence_band: ConfidenceBand
    matched_terms: list[str] = []
    equivalent_terms: list[str] = []
    missing_terms: list[str] = []
    rationale: str
    evidence_count: int
    display_order: int
    evidence: list[EvidenceOut] = []


class EligibilityFindingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    code: str
    label: str
    rule_type: RuleType
    operator: RuleOperator
    threshold: float | None
    severity: RuleSeverity
    triggered: bool
    indeterminate: bool
    observed_value: str
    message: str
    display_order: int


class ChallengeFindingOut(BaseModel):
    """A Challenge Agent concern. Never alters a score — commentary only."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    run_id: str
    evaluation_id: str | None
    criterion_id: str | None
    criterion_key: str
    check: ChallengeCheck
    severity: ChallengeSeverity
    scope: ChallengeScope
    title: str
    detail: str
    recommendation: str
    observed: dict | None = None
    display_order: int
    engine_version: str


class EvaluationSummary(BaseModel):
    """Leaderboard row — no criteria or evidence, so it stays cheap in bulk."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    run_id: str
    # Exposed because a deep link to one assessment needs to know which
    # campaign it belongs to before it can load anything else. Its absence
    # meant /api/evaluations/{id} could not be resolved from a URL alone.
    campaign_id: str
    candidate_id: str
    document_id: str | None
    rubric_version_id: str
    is_current: bool
    status: EvaluationStatus
    overall_score: float
    overall_confidence: float
    confidence_band: ConfidenceBand
    mandatory_score: float
    preferred_score: float
    skills_score: float | None = None
    experience_score: float | None = None
    education_score: float | None = None
    certification_score: float | None = None
    next_action: str | None = None
    eligibility_status: EligibilityStatus
    recommendation: Recommendation
    experience_years_total: float
    experience_years_relevant: float
    created_at: datetime
    candidate_name: str = ""
    error_message: str = ""


class EvaluationDetail(EvaluationSummary):
    """Candidate 360 payload."""

    engine_version: str
    scoring_mode: ScoringMode
    duration_ms: int | None
    superseded_by_evaluation_id: str | None
    narrative: str
    experience_profile: dict | None = None
    strengths: list[dict] = []
    gaps: list[dict] = []
    missing_information: list[str] = []
    contradictions: list[dict] = []
    criteria: list[CriterionOut] = []
    eligibility_findings: list[EligibilityFindingOut] = []
    challenge_findings: list[ChallengeFindingOut] = []
    category_scores: dict | None = None
    next_action_reason: str = ""
    validation_questions: list[dict] = []
    interview_focus: list[dict] = []
    rubric_version_number: int | None = None
    # None when the CV was read normally — there is nothing to warn about.
    document_quality: dict | None = None
    # Whether the original CV can still be opened. False once retention has
    # removed the file, so the screen hides the link rather than offering a
    # button that 404s.
    cv_available: bool = False


class RunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    short_id: str | None = None
    campaign_id: str
    rubric_version_id: str
    batch_id: str | None
    reevaluation_of_run_id: str | None
    status: RunStatus
    trigger: RunTrigger
    scoring_mode: ScoringMode
    engine_version: str
    total_candidates: int
    evaluated_count: int
    failed_count: int
    skipped_count: int
    notes: str
    created_by: str
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    rubric_version_number: int | None = None


class RunDetail(RunOut):
    evaluations: list[EvaluationSummary] = []


class LeaderboardEntry(EvaluationSummary):
    # Defaulted because the row is validated from the ORM object first and
    # ranked afterwards, once the ordered result set is known.
    rank: int = 0
    criterion_scores: dict[str, float] = Field(
        default_factory=dict,
        description="criterion_key -> score, for the leaderboard's column view.",
    )


class ReevaluationStatus(BaseModel):
    campaign_id: str
    active_version_number: int | None
    active_version_id: str | None
    reevaluation_required: bool
    reevaluation_acknowledged_at: str | None
    supersedes_version_id: str | None
    counts: dict
    stale_candidates: list[dict]
    unevaluated_candidates: list[dict]
    action_required: str
