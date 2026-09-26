"""
ORM models. Grows phase by phase — this file currently covers Phase A
(Campaign + Job Requirement Engine) only. Later phases add Rubric,
RubricVersion, DisqualificationRule, Candidate, CandidateDocument,
EvaluationRun, Evaluation, EvaluationCriterion, EvaluationEvidence,
ChallengeFinding, CandidateAction, AuditLog, ProcessingJob, Integration, etc.
without touching what's defined here.
"""
import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    String, Text, Integer, Float, DateTime, Enum, ForeignKey, Boolean,
    JSON, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class CampaignStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    AWAITING_RUBRIC_APPROVAL = "AWAITING_RUBRIC_APPROVAL"
    APPROVED = "APPROVED"
    PROCESSING = "PROCESSING"
    REVIEW = "REVIEW"
    CLOSED = "CLOSED"


class RequirementCategory(str, enum.Enum):
    SKILL = "SKILL"
    EXPERIENCE = "EXPERIENCE"
    QUALIFICATION = "QUALIFICATION"
    CERTIFICATION = "CERTIFICATION"
    RESPONSIBILITY = "RESPONSIBILITY"
    INDUSTRY = "INDUSTRY"
    FUNCTIONAL = "FUNCTIONAL"
    SENIORITY = "SENIORITY"
    LOCATION = "LOCATION"
    ELIGIBILITY = "ELIGIBILITY"
    DIFFERENTIATING = "DIFFERENTIATING"


class RequirementType(str, enum.Enum):
    MANDATORY = "MANDATORY"
    PREFERRED = "PREFERRED"
    INFORMATIONAL = "INFORMATIONAL"


class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    # A human-readable identifier ("RC36-01", "RC36-02", ...) alongside the
    # UUID primary key — B20 identifier model. The UUID stays the
    # foreign-key target everywhere; this is only for display and search, so
    # a recruiter never has to read or type a UUID.
    short_id: Mapped[str | None] = mapped_column(String(20), unique=True, nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    job_title: Mapped[str] = mapped_column(String(255), nullable=False)
    job_description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    vacancies: Mapped[int] = mapped_column(Integer, default=1)
    location: Mapped[str] = mapped_column(String(255), default="")
    business_unit: Mapped[str] = mapped_column(String(255), default="")
    recruiter: Mapped[str] = mapped_column(String(255), default="")
    hiring_manager: Mapped[str] = mapped_column(String(255), default="")
    start_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    target_completion_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[CampaignStatus] = mapped_column(
        Enum(CampaignStatus, native_enum=False, length=32),
        default=CampaignStatus.DRAFT,
        nullable=False,
    )
    created_by: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc)
    )
    # Optimistic-concurrency counter. A PATCH that names `expected_version`
    # is rejected with a conflict once it no longer matches — see
    # `campaign_service.update_campaign`. Bumped on every field/status change.
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    # Set from the client's `Idempotency-Key` header on create. A retried
    # create with the same key returns the original campaign instead of
    # making a second one — see `campaign_service.create_campaign`.
    idempotency_key: Mapped[str | None] = mapped_column(
        String(255), nullable=True, unique=True
    )

    requirements: Mapped[list["JobRequirement"]] = relationship(
        back_populates="campaign", cascade="all, delete-orphan"
    )
    rubric: Mapped["Rubric | None"] = relationship(
        back_populates="campaign", cascade="all, delete-orphan", uselist=False
    )
    candidates: Mapped[list["Candidate"]] = relationship(
        back_populates="campaign", cascade="all, delete-orphan"
    )
    documents: Mapped[list["CandidateDocument"]] = relationship(
        back_populates="campaign", cascade="all, delete-orphan"
    )
    batches: Mapped[list["ProcessingBatch"]] = relationship(
        back_populates="campaign", cascade="all, delete-orphan"
    )
    # Phase D. Cascaded from the campaign so deleting one does not leave
    # evaluations pointing at deleted candidates.
    evaluation_runs: Mapped[list["EvaluationRun"]] = relationship(
        cascade="all, delete-orphan"
    )

    def can_transition_to(self, new_status: "CampaignStatus") -> bool:
        """Deterministic status graph — no skipping stages via the API."""
        allowed = {
            CampaignStatus.DRAFT: {CampaignStatus.AWAITING_RUBRIC_APPROVAL, CampaignStatus.CLOSED},
            CampaignStatus.AWAITING_RUBRIC_APPROVAL: {CampaignStatus.APPROVED, CampaignStatus.DRAFT, CampaignStatus.CLOSED},
            CampaignStatus.APPROVED: {CampaignStatus.PROCESSING, CampaignStatus.CLOSED},
            CampaignStatus.PROCESSING: {CampaignStatus.REVIEW, CampaignStatus.CLOSED},
            CampaignStatus.REVIEW: {CampaignStatus.PROCESSING, CampaignStatus.CLOSED},
            CampaignStatus.CLOSED: set(),
        }
        return new_status in allowed.get(self.status, set())


class JobRequirement(Base):
    __tablename__ = "job_requirements"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    campaign_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("campaigns.id"), nullable=False, index=True
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[RequirementCategory] = mapped_column(
        Enum(RequirementCategory, native_enum=False, length=32), nullable=False
    )
    requirement_type: Mapped[RequirementType] = mapped_column(
        Enum(RequirementType, native_enum=False, length=32),
        default=RequirementType.INFORMATIONAL,
        nullable=False,
    )
    priority: Mapped[int] = mapped_column(Integer, default=3)  # 1 = highest
    weight: Mapped[float] = mapped_column(Float, default=0.0)
    disqualifying: Mapped[bool] = mapped_column(Boolean, default=False)
    evidence_required: Mapped[bool] = mapped_column(Boolean, default=True)
    source: Mapped[str] = mapped_column(String(16), default="AI")  # AI | MANUAL | EDITED
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc)
    )

    campaign: Mapped["Campaign"] = relationship(back_populates="requirements")


# ---------------------------------------------------------------------------
# Phase B — Rubric + Weights + Disqualification + Versioning
#
# Design rules (carried from the project brief):
#   * Historical rubrics are NEVER overwritten. An APPROVED or LOCKED version
#     is immutable; changing an approved rubric means cloning it into a new
#     DRAFT version and approving that.
#   * A campaign has exactly one Rubric container, which owns an ordered
#     chain of RubricVersion rows (version_number 1, 2, 3, ...).
#   * Weights and disqualification rules hang off a *version*, not the
#     campaign, so an old evaluation can always be replayed against the
#     exact rubric that produced it.
# ---------------------------------------------------------------------------


class RubricStatus(str, enum.Enum):
    DRAFT = "DRAFT"              # editable
    SUBMITTED = "SUBMITTED"      # sent for recruiter approval, editing frozen
    APPROVED = "APPROVED"        # approved, immutable, usable for evaluation
    LOCKED = "LOCKED"            # evaluation has run against it, hard frozen
    REJECTED = "REJECTED"        # approver sent it back; a new draft is cloned
    SUPERSEDED = "SUPERSEDED"    # a later version was approved


class ScoringMethod(str, enum.Enum):
    WEIGHTED = "WEIGHTED"        # 0-100 partial credit x weight
    BINARY = "BINARY"            # met / not met
    GRADED = "GRADED"            # banded (confirmed / partial / not demonstrated)


class RuleType(str, enum.Enum):
    MIN_YEARS_EXPERIENCE = "MIN_YEARS_EXPERIENCE"
    MISSING_MANDATORY_SKILL = "MISSING_MANDATORY_SKILL"
    MISSING_QUALIFICATION = "MISSING_QUALIFICATION"
    MISSING_CERTIFICATION = "MISSING_CERTIFICATION"
    LOCATION_MISMATCH = "LOCATION_MISMATCH"
    ELIGIBILITY_FAILURE = "ELIGIBILITY_FAILURE"
    MIN_CRITERION_SCORE = "MIN_CRITERION_SCORE"
    CUSTOM = "CUSTOM"


class RuleOperator(str, enum.Enum):
    LT = "LT"
    LTE = "LTE"
    GT = "GT"
    GTE = "GTE"
    EQ = "EQ"
    NEQ = "NEQ"
    MISSING = "MISSING"
    PRESENT = "PRESENT"
    IN = "IN"
    NOT_IN = "NOT_IN"


class RuleSeverity(str, enum.Enum):
    HARD_FAIL = "HARD_FAIL"              # candidate is disqualified outright
    REVIEW_REQUIRED = "REVIEW_REQUIRED"  # flagged for a human, not auto-rejected


class Rubric(Base):
    """One rubric container per campaign; owns the version chain."""
    __tablename__ = "rubrics"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    campaign_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("campaigns.id"), nullable=False, unique=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255), default="Evaluation Rubric")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc)
    )

    campaign: Mapped["Campaign"] = relationship(back_populates="rubric")
    versions: Mapped[list["RubricVersion"]] = relationship(
        back_populates="rubric",
        cascade="all, delete-orphan",
        order_by="RubricVersion.version_number",
    )


class RubricVersion(Base):
    __tablename__ = "rubric_versions"
    __table_args__ = (
        UniqueConstraint("rubric_id", "version_number", name="uq_rubric_version_number"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    rubric_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("rubrics.id"), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[RubricStatus] = mapped_column(
        Enum(RubricStatus, native_enum=False, length=32),
        default=RubricStatus.DRAFT,
        nullable=False,
    )
    notes: Mapped[str] = mapped_column(Text, default="")
    change_reason: Mapped[str] = mapped_column(Text, default="")

    # Provenance: which version this one was cloned from, and which approved
    # version it replaced. Both are kept so the audit screen can render the
    # full lineage without guessing.
    cloned_from_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    supersedes_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    # Set when this version is approved while an earlier approved/locked
    # version already existed — i.e. results on file were produced under a
    # different rubric. Cleared only by an explicit recruiter acknowledgement,
    # which is what makes re-evaluation "controlled" rather than automatic.
    reevaluation_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    reevaluation_acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reevaluation_acknowledged_by: Mapped[str] = mapped_column(String(255), default="")

    created_by: Mapped[str] = mapped_column(String(255), default="")
    submitted_by: Mapped[str] = mapped_column(String(255), default="")
    approved_by: Mapped[str] = mapped_column(String(255), default="")
    rejected_by: Mapped[str] = mapped_column(String(255), default="")
    rejection_reason: Mapped[str] = mapped_column(Text, default="")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    rubric: Mapped["Rubric"] = relationship(back_populates="versions")
    weights: Mapped[list["RubricWeight"]] = relationship(
        back_populates="version", cascade="all, delete-orphan", order_by="RubricWeight.display_order"
    )
    disqualification_rules: Mapped[list["DisqualificationRule"]] = relationship(
        back_populates="version", cascade="all, delete-orphan", order_by="DisqualificationRule.display_order"
    )

    # -- state helpers -----------------------------------------------------

    EDITABLE_STATUSES = {RubricStatus.DRAFT}
    IMMUTABLE_STATUSES = {RubricStatus.APPROVED, RubricStatus.LOCKED, RubricStatus.SUPERSEDED}

    @property
    def is_editable(self) -> bool:
        return self.status in self.EDITABLE_STATUSES

    @property
    def is_immutable(self) -> bool:
        return self.status in self.IMMUTABLE_STATUSES

    @property
    def is_usable_for_evaluation(self) -> bool:
        return self.status in {RubricStatus.APPROVED, RubricStatus.LOCKED}

    @property
    def weight_total(self) -> float:
        return round(sum(w.weight for w in self.weights if w.active), 2)

    @property
    def is_balanced(self) -> bool:
        """Weights must sum to exactly 100 (within float tolerance)."""
        return abs(self.weight_total - 100.0) < 0.01

    def can_transition_to(self, new_status: "RubricStatus") -> bool:
        allowed = {
            RubricStatus.DRAFT: {RubricStatus.SUBMITTED},
            RubricStatus.SUBMITTED: {RubricStatus.APPROVED, RubricStatus.REJECTED, RubricStatus.DRAFT},
            RubricStatus.APPROVED: {RubricStatus.LOCKED, RubricStatus.SUPERSEDED},
            RubricStatus.LOCKED: {RubricStatus.SUPERSEDED},
            RubricStatus.REJECTED: set(),
            RubricStatus.SUPERSEDED: set(),
        }
        return new_status in allowed.get(self.status, set())


class RubricWeight(Base):
    """
    One scored criterion inside a rubric version.

    `requirement_id` links back to the Phase A JobRequirement it came from
    where there is one, but is nullable so a recruiter can score a criterion
    that isn't a literal JD line (e.g. "Experience recency").
    """
    __tablename__ = "rubric_weights"
    __table_args__ = (
        UniqueConstraint("rubric_version_id", "criterion_key", name="uq_rubric_weight_criterion"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    rubric_version_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("rubric_versions.id"), nullable=False, index=True
    )
    requirement_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("job_requirements.id", ondelete="SET NULL"), nullable=True
    )

    criterion_key: Mapped[str] = mapped_column(String(128), nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[RequirementCategory] = mapped_column(
        Enum(RequirementCategory, native_enum=False, length=32),
        default=RequirementCategory.SKILL,
        nullable=False,
    )
    requirement_type: Mapped[RequirementType] = mapped_column(
        Enum(RequirementType, native_enum=False, length=32),
        default=RequirementType.MANDATORY,
        nullable=False,
    )
    weight: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    max_score: Mapped[float] = mapped_column(Float, default=100.0, nullable=False)
    scoring_method: Mapped[ScoringMethod] = mapped_column(
        Enum(ScoringMethod, native_enum=False, length=32),
        default=ScoringMethod.WEIGHTED,
        nullable=False,
    )
    evidence_required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    version: Mapped["RubricVersion"] = relationship(back_populates="weights")


class DisqualificationRule(Base):
    __tablename__ = "disqualification_rules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    rubric_version_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("rubric_versions.id"), nullable=False, index=True
    )
    requirement_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("job_requirements.id", ondelete="SET NULL"), nullable=True
    )

    code: Mapped[str] = mapped_column(String(128), nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    rule_type: Mapped[RuleType] = mapped_column(
        Enum(RuleType, native_enum=False, length=48), default=RuleType.CUSTOM, nullable=False
    )
    operator: Mapped[RuleOperator] = mapped_column(
        Enum(RuleOperator, native_enum=False, length=16), default=RuleOperator.MISSING, nullable=False
    )
    threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    value: Mapped[str] = mapped_column(Text, default="")
    params: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    severity: Mapped[RuleSeverity] = mapped_column(
        Enum(RuleSeverity, native_enum=False, length=32), default=RuleSeverity.HARD_FAIL, nullable=False
    )
    message: Mapped[str] = mapped_column(Text, default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    version: Mapped["RubricVersion"] = relationship(back_populates="disqualification_rules")


class WhatIfProposalStatus(str, enum.Enum):
    PROPOSED = "PROPOSED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class WhatIfProposal(Base):
    """
    B17: a recruiter's proposed rubric reweighting, sent to a named hiring
    manager for a decision.

    Separate from the free preview in `app.core.analytics.what_if()`, which
    this table never touches and which stays unauthenticated and
    non-persisting exactly as before. Approving a proposal authorizes
    proceeding to a real rubric revision; it does not create one —
    `app.services.rubric_service` still owns drafting, submitting and
    approving an actual `RubricVersion`, and no CV is re-scored here.
    """
    __tablename__ = "whatif_proposals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    campaign_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("campaigns.id"), nullable=False, index=True
    )
    rubric_version_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("rubric_versions.id"), nullable=False, index=True
    )
    proposed_weights: Mapped[dict] = mapped_column(JSON, nullable=False)
    # Set only on approval. Usually identical to proposed_weights, but the
    # approver may amend the set on the way through — the checklist asks to
    # audit both the proposed and the approved versions, and they can differ.
    approved_weights: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[WhatIfProposalStatus] = mapped_column(
        Enum(WhatIfProposalStatus, native_enum=False, length=16),
        default=WhatIfProposalStatus.PROPOSED, nullable=False, index=True,
    )
    note: Mapped[str] = mapped_column(Text, default="")

    # Real, named, active people (User.id) — never a role alone. The
    # proposer and the approver are required to be different people; see
    # whatif_service.propose.
    proposed_by: Mapped[str] = mapped_column(String(36), nullable=False)
    approver_id: Mapped[str] = mapped_column(String(36), nullable=False)
    decided_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    decision_note: Mapped[str] = mapped_column(Text, default="")

    # Set once an approved proposal has actually been turned into a draft
    # rubric version (see `whatif_service.create_rubric_draft`). Null means
    # the proposal is approved but nobody has taken that next, separate,
    # human step yet — approving never does this automatically.
    draft_version_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("rubric_versions.id"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


# ---------------------------------------------------------------------------
# Phase C — Bulk CV Processing + Queue + Duplicates
#
# Design rules:
#   * Every uploaded file is retained on disk. Phase D's evidence citations
#     need the original document to still exist, so nothing is deleted after
#     processing — unlike the old /api/campaigns/screen flow, which wrote to
#     temp files and discarded them.
#   * One ProcessingJob per file, always. A file that is unsupported, corrupt,
#     password-protected or a duplicate still gets a job row with a status and
#     an error code, because the Control Tower has to show exceptions, not
#     silently drop them.
#   * A batch is pinned to the rubric version in force when it was created.
#     That is the rubric->evaluation linkage: results can always be traced to
#     the exact approved rubric that produced them.
#   * Duplicate detection is scoped to a campaign. The same person applying to
#     two different roles is not a duplicate.
# ---------------------------------------------------------------------------


class BatchStatus(str, enum.Enum):
    PENDING = "PENDING"                              # created, nothing picked up yet
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"                          # every job succeeded
    COMPLETED_WITH_ERRORS = "COMPLETED_WITH_ERRORS"  # finished, some jobs failed
    CANCELLED = "CANCELLED"


class JobStatus(str, enum.Enum):
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    DUPLICATE = "DUPLICATE"
    CANCELLED = "CANCELLED"

    @classmethod
    def terminal(cls) -> set["JobStatus"]:
        return {cls.COMPLETED, cls.FAILED, cls.DUPLICATE, cls.CANCELLED}


class JobErrorCode(str, enum.Enum):
    """
    Why a file failed, or why it needs a human look. Used for both hard
    failures and non-fatal warnings (paired with ProcessingJob.requires_review)
    so the exceptions panel can group by cause.
    """
    UNSUPPORTED_FORMAT = "UNSUPPORTED_FORMAT"
    EMPTY_FILE = "EMPTY_FILE"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    CORRUPT_FILE = "CORRUPT_FILE"
    PASSWORD_PROTECTED = "PASSWORD_PROTECTED"
    NO_TEXT_EXTRACTED = "NO_TEXT_EXTRACTED"      # likely a scanned image, needs OCR
    INCOMPLETE_CONTENT = "INCOMPLETE_CONTENT"    # no usable contact identity
    EXTRACTION_FAILED = "EXTRACTION_FAILED"
    STORAGE_FAILED = "STORAGE_FAILED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class DuplicateType(str, enum.Enum):
    EXACT_FILE = "EXACT_FILE"                    # byte-identical content hash
    SAME_CANDIDATE_EMAIL = "SAME_CANDIDATE_EMAIL"
    SAME_CANDIDATE_PHONE = "SAME_CANDIDATE_PHONE"
    SAME_CANDIDATE_NAME = "SAME_CANDIDATE_NAME"  # weakest signal — review, don't trust


class Candidate(Base):
    """
    A person in a campaign's applicant pool. Identity is resolved from the CV
    during processing; a candidate may own several documents (an updated CV, a
    cover letter) without being a duplicate.
    """
    __tablename__ = "candidates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    campaign_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("campaigns.id"), nullable=False, index=True
    )
    full_name: Mapped[str] = mapped_column(String(255), default="")
    email: Mapped[str] = mapped_column(String(320), default="")
    phone: Mapped[str] = mapped_column(String(64), default="")
    location: Mapped[str] = mapped_column(String(255), default="")

    # Normalized forms used for duplicate matching — never displayed.
    email_normalized: Mapped[str] = mapped_column(String(320), default="", index=True)
    phone_normalized: Mapped[str] = mapped_column(String(32), default="", index=True)
    name_normalized: Mapped[str] = mapped_column(String(255), default="", index=True)

    requires_review: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    source: Mapped[str] = mapped_column(String(32), default="BULK_UPLOAD")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc)
    )

    campaign: Mapped["Campaign"] = relationship(back_populates="candidates")
    documents: Mapped[list["CandidateDocument"]] = relationship(
        back_populates="candidate", order_by="CandidateDocument.created_at"
    )


class CandidateDocument(Base):
    """
    A retained uploaded file plus its extracted text. `candidate_id` is
    nullable because a document is stored before identity resolution — and
    stays unlinked if the file turned out to be unreadable.
    """
    __tablename__ = "candidate_documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    campaign_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("campaigns.id"), nullable=False, index=True
    )
    candidate_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("candidates.id", ondelete="SET NULL"), nullable=True, index=True
    )

    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    extension: Mapped[str] = mapped_column(String(16), default="")
    content_type: Mapped[str] = mapped_column(String(128), default="")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    content_hash: Mapped[str] = mapped_column(String(64), default="", index=True)
    storage_path: Mapped[str] = mapped_column(String(1024), default="")

    page_count: Mapped[int] = mapped_column(Integer, default=0)
    extracted_text: Mapped[str] = mapped_column(Text, default="")
    text_char_count: Mapped[int] = mapped_column(Integer, default=0)
    section_map: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # How the text was obtained: "extracted" from a real text layer, "ocr"
    # from images, or "mixed". Stored as a plain string rather than an Enum
    # because it is descriptive metadata, not a state machine. Text read
    # from an image is an approximation, and an assessment built on one is
    # held to a lower confidence ceiling — see app/core/document_quality.py.
    text_source: Mapped[str] = mapped_column(String(16), default="extracted")
    pages_with_text: Mapped[int] = mapped_column(Integer, default=0)
    ocr_pages: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    campaign: Mapped["Campaign"] = relationship(back_populates="documents")
    candidate: Mapped["Candidate | None"] = relationship(back_populates="documents")


class ProcessingBatch(Base):
    __tablename__ = "processing_batches"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    campaign_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("campaigns.id"), nullable=False, index=True
    )
    # The rubric in force when this batch was accepted. Nullable only so the
    # column can be added to existing rows; new batches always set it.
    rubric_version_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("rubric_versions.id"), nullable=True
    )

    name: Mapped[str] = mapped_column(String(255), default="")
    status: Mapped[BatchStatus] = mapped_column(
        Enum(BatchStatus, native_enum=False, length=32), default=BatchStatus.PENDING, nullable=False
    )
    total_files: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_by: Mapped[str] = mapped_column(String(255), default="")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    campaign: Mapped["Campaign"] = relationship(back_populates="batches")
    jobs: Mapped[list["ProcessingJob"]] = relationship(
        back_populates="batch", cascade="all, delete-orphan", order_by="ProcessingJob.sequence"
    )


class ProcessingJob(Base):
    """One file, one job. Carries the per-file status the upload screen shows."""
    __tablename__ = "processing_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    batch_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("processing_batches.id"), nullable=False, index=True
    )
    campaign_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("campaigns.id"), nullable=False, index=True
    )
    sequence: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)

    document_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("candidate_documents.id", ondelete="SET NULL"), nullable=True
    )
    candidate_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("candidates.id", ondelete="SET NULL"), nullable=True
    )

    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, native_enum=False, length=32), default=JobStatus.QUEUED, nullable=False, index=True
    )
    error_code: Mapped[JobErrorCode | None] = mapped_column(
        Enum(JobErrorCode, native_enum=False, length=40), nullable=True
    )
    error_message: Mapped[str] = mapped_column(Text, default="")
    # True when the file processed but a human should look at it — partial
    # identity, suspiciously short text, weak duplicate signal.
    requires_review: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    duplicate_type: Mapped[DuplicateType | None] = mapped_column(
        Enum(DuplicateType, native_enum=False, length=32), nullable=True
    )
    duplicate_of_document_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    duplicate_of_candidate_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, nullable=False)

    queued_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    batch: Mapped["ProcessingBatch"] = relationship(back_populates="jobs")

    @property
    def is_retryable(self) -> bool:
        return self.status == JobStatus.FAILED and self.attempts < self.max_attempts


# ---------------------------------------------------------------------------
# Phase D — Rubric-driven evaluation, evidence, eligibility, confidence
#
# Design rules:
#   * An Evaluation is IMMUTABLE once written. Re-scoring a candidate creates
#     a new EvaluationRun and a new Evaluation row; the old one keeps its
#     criteria, evidence and eligibility findings verbatim. The only field
#     that is ever mutated after commit is the `is_current` /
#     `superseded_by_evaluation_id` pointer pair, which is navigation, not a
#     result. There is deliberately no `updated_at` on these tables.
#   * Every Evaluation pins `rubric_version_id`. A score is meaningless
#     without the rubric that produced it, so the two are never separated.
#     The version comes from the batch (ProcessingBatch.rubric_version_id),
#     not from "whatever is approved now".
#   * Eligibility is decided by EligibilityFinding rows produced by the
#     deterministic rule engine. The LLM never writes them and cannot
#     overturn them — a HARD_FAIL stands regardless of how well the
#     candidate scores.
#   * `engine_version` is stamped on every run so a score can be attributed
#     to the exact scoring logic that produced it.
# ---------------------------------------------------------------------------


class RunStatus(str, enum.Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_ERRORS = "COMPLETED_WITH_ERRORS"
    CANCELLED = "CANCELLED"


class RunTrigger(str, enum.Enum):
    MANUAL = "MANUAL"                    # recruiter pressed evaluate
    BATCH_COMPLETION = "BATCH_COMPLETION"
    REEVALUATION = "REEVALUATION"        # rubric changed; reevaluation_required


class ScoringMode(str, enum.Enum):
    """
    DETERMINISTIC is the floor and is always computed. LLM_ASSISTED runs the
    deterministic pass first and then lets the model adjust criterion scores
    within a bounded band and supply narrative. If the model is unreachable
    or returns junk, the run silently stays deterministic — it never fails.
    """
    DETERMINISTIC = "DETERMINISTIC"
    LLM_ASSISTED = "LLM_ASSISTED"


class EvaluationStatus(str, enum.Enum):
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"       # no usable document, or already current


class CriterionOutcome(str, enum.Enum):
    """The five classifications the client asked for, verbatim."""
    CONFIRMED_MATCH = "CONFIRMED_MATCH"
    PARTIAL_MATCH = "PARTIAL_MATCH"                    # partial or adjacent
    NOT_DEMONSTRATED = "NOT_DEMONSTRATED"
    CONTRADICTORY_EVIDENCE = "CONTRADICTORY_EVIDENCE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"    # CV too thin to judge


class ConfidenceBand(str, enum.Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class EligibilityStatus(str, enum.Enum):
    ELIGIBLE = "ELIGIBLE"
    DISQUALIFIED = "DISQUALIFIED"            # at least one HARD_FAIL rule fired
    REVIEW_REQUIRED = "REVIEW_REQUIRED"      # only REVIEW_REQUIRED rules fired


class Recommendation(str, enum.Enum):
    STRONG_FIT = "STRONG_FIT"
    POTENTIAL_FIT = "POTENTIAL_FIT"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    NOT_RECOMMENDED = "NOT_RECOMMENDED"


class EvidenceMatchType(str, enum.Enum):
    EXACT = "EXACT"                  # the literal term appears
    EQUIVALENT = "EQUIVALENT"        # matched via the skill taxonomy
    CONTRADICTION = "CONTRADICTION"  # text that argues against the criterion
    CONTEXT = "CONTEXT"              # supporting but not a term hit


class EvaluationRun(Base):
    __tablename__ = "evaluation_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    # B20, extended to runs: the UUID stays the primary key and foreign-key
    # target (03-IDENTIFIER-MODEL.md's additive migration note); this is a
    # second, unique, display-only id in the same RC+date+random shape as
    # Campaign.short_id, so "assessment run cdc651b4" becomes something a
    # recruiter can actually read out loud. See campaign_service._next_short_id
    # for the identical generation/collision-check pattern.
    short_id: Mapped[str | None] = mapped_column(String(20), unique=True, nullable=True)
    campaign_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("campaigns.id"), nullable=False, index=True
    )
    rubric_version_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("rubric_versions.id"), nullable=False, index=True
    )
    batch_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("processing_batches.id", ondelete="SET NULL"), nullable=True
    )
    # Set when this run exists because a rubric version superseded another.
    reevaluation_of_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    status: Mapped[RunStatus] = mapped_column(
        Enum(RunStatus, native_enum=False, length=32), default=RunStatus.PENDING, nullable=False
    )
    trigger: Mapped[RunTrigger] = mapped_column(
        Enum(RunTrigger, native_enum=False, length=32), default=RunTrigger.MANUAL, nullable=False
    )
    scoring_mode: Mapped[ScoringMode] = mapped_column(
        Enum(ScoringMode, native_enum=False, length=32),
        default=ScoringMode.DETERMINISTIC,
        nullable=False,
    )
    engine_version: Mapped[str] = mapped_column(String(32), default="", nullable=False)

    total_candidates: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    evaluated_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    skipped_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    notes: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    evaluations: Mapped[list["Evaluation"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class Evaluation(Base):
    """One candidate scored against one rubric version. Write-once."""
    __tablename__ = "evaluations"
    __table_args__ = (
        UniqueConstraint("run_id", "candidate_id", name="uq_evaluation_run_candidate"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("evaluation_runs.id"), nullable=False, index=True
    )
    campaign_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("campaigns.id"), nullable=False, index=True
    )
    candidate_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("candidates.id"), nullable=False, index=True
    )
    document_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("candidate_documents.id", ondelete="SET NULL"), nullable=True
    )
    rubric_version_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("rubric_versions.id"), nullable=False, index=True
    )

    # Navigation pointers, not results. `is_current` marks the newest
    # evaluation for a candidate; superseded rows stay on disk untouched.
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    superseded_by_evaluation_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    status: Mapped[EvaluationStatus] = mapped_column(
        Enum(EvaluationStatus, native_enum=False, length=32),
        default=EvaluationStatus.COMPLETED,
        nullable=False,
    )
    error_message: Mapped[str] = mapped_column(Text, default="")

    overall_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    overall_confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    confidence_band: Mapped[ConfidenceBand] = mapped_column(
        Enum(ConfidenceBand, native_enum=False, length=16),
        default=ConfidenceBand.LOW,
        nullable=False,
    )
    mandatory_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    preferred_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # Phase F. The requirement asks for "skills, experience, education and
    # certification scores" as distinct figures; Phase D produced only
    # per-criterion scores. Each is a weight-weighted rollup of the criteria
    # in that category, expressed 0-100, and is None when the rubric has no
    # criteria in the category — 0.0 would read as "scored badly" rather
    # than "not assessed", which is a materially different claim.
    skills_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    experience_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    education_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    certification_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    category_scores: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Derived from eligibility, confidence and challenge findings — never
    # model-generated. See services/disposition_service._next_action.
    # Annotated as str rather than Mapped[NextAction] because NextAction is
    # declared further down this file (Phase F) and a forward reference in a
    # Mapped[] annotation cannot resolve. The Enum type still constrains the
    # stored values, and the API schema coerces back to the enum on read.
    next_action: Mapped[str | None] = mapped_column(
        Enum("INTERVIEW", "MANUAL_REVIEW", "REQUEST_EVIDENCE",
             "CONFIRM_ELIGIBILITY", "REJECT",
             native_enum=False, length=32, name="nextaction"),
        nullable=True,
    )
    next_action_reason: Mapped[str] = mapped_column(Text, default="")
    validation_questions: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    interview_focus: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    eligibility_status: Mapped[EligibilityStatus] = mapped_column(
        Enum(EligibilityStatus, native_enum=False, length=32),
        default=EligibilityStatus.ELIGIBLE,
        nullable=False,
        index=True,
    )
    recommendation: Mapped[Recommendation] = mapped_column(
        Enum(Recommendation, native_enum=False, length=32),
        default=Recommendation.REVIEW_REQUIRED,
        nullable=False,
        index=True,
    )

    # Experience engine output. The scalar is kept alongside the breakdown so
    # the leaderboard can sort without unpacking JSON.
    experience_years_total: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    experience_years_relevant: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    experience_profile: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    strengths: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    gaps: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    missing_information: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    contradictions: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    narrative: Mapped[str] = mapped_column(Text, default="")

    # B05/B08: the LLM-brief rendering of _suggested_rationale, generated the
    # first time it's asked for and reused after — an evaluation is write-once
    # (see the class docstring), so once a summary is written for one it never
    # goes stale. Cheap insurance against re-billing the LLM on every
    # Candidate 360 page view. None until the first request generates it.
    ai_rationale_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    scoring_mode: Mapped[ScoringMode] = mapped_column(
        Enum(ScoringMode, native_enum=False, length=32),
        default=ScoringMode.DETERMINISTIC,
        nullable=False,
    )
    engine_version: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    run: Mapped["EvaluationRun"] = relationship(back_populates="evaluations")
    criteria: Mapped[list["EvaluationCriterion"]] = relationship(
        back_populates="evaluation",
        cascade="all, delete-orphan",
        order_by="EvaluationCriterion.display_order",
    )
    evidence: Mapped[list["EvaluationEvidence"]] = relationship(
        back_populates="evaluation", cascade="all, delete-orphan"
    )
    eligibility_findings: Mapped[list["EligibilityFinding"]] = relationship(
        back_populates="evaluation",
        cascade="all, delete-orphan",
        order_by="EligibilityFinding.display_order",
    )


class EvaluationCriterion(Base):
    """
    One rubric criterion scored for one candidate.

    The rubric fields (label, weight, max_score, scoring_method) are copied in
    rather than only referenced, so a historical evaluation still renders
    correctly even though the rubric weight row it came from lives on a
    version that has since been superseded.
    """
    __tablename__ = "evaluation_criteria"
    __table_args__ = (
        UniqueConstraint("evaluation_id", "criterion_key", name="uq_evaluation_criterion_key"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    evaluation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("evaluations.id"), nullable=False, index=True
    )
    rubric_weight_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("rubric_weights.id", ondelete="SET NULL"), nullable=True
    )

    criterion_key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    label: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[RequirementCategory] = mapped_column(
        Enum(RequirementCategory, native_enum=False, length=32),
        default=RequirementCategory.SKILL,
        nullable=False,
    )
    requirement_type: Mapped[RequirementType] = mapped_column(
        Enum(RequirementType, native_enum=False, length=32),
        default=RequirementType.MANDATORY,
        nullable=False,
    )
    weight: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    max_score: Mapped[float] = mapped_column(Float, default=100.0, nullable=False)
    scoring_method: Mapped[ScoringMethod] = mapped_column(
        Enum(ScoringMethod, native_enum=False, length=32),
        default=ScoringMethod.WEIGHTED,
        nullable=False,
    )

    # `deterministic_score` is what the rule-based pass produced; `raw_score`
    # is what was finally used. They differ only when the LLM adjusted within
    # its allowed band, which `llm_adjusted` records. Keeping both is what
    # lets the Challenge Agent (Phase E) spot unsupported model adjustments.
    deterministic_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    raw_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    weighted_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    llm_adjusted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    outcome: Mapped[CriterionOutcome] = mapped_column(
        Enum(CriterionOutcome, native_enum=False, length=32),
        default=CriterionOutcome.INSUFFICIENT_EVIDENCE,
        nullable=False,
    )
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    confidence_band: Mapped[ConfidenceBand] = mapped_column(
        Enum(ConfidenceBand, native_enum=False, length=16),
        default=ConfidenceBand.LOW,
        nullable=False,
    )

    matched_terms: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    equivalent_terms: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    missing_terms: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    rationale: Mapped[str] = mapped_column(Text, default="")
    evidence_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    evaluation: Mapped["Evaluation"] = relationship(back_populates="criteria")
    evidence: Mapped[list["EvaluationEvidence"]] = relationship(
        back_populates="criterion", order_by="EvaluationEvidence.relevance.desc()"
    )


class EvaluationEvidence(Base):
    """
    A quoted excerpt from the retained CV, with a page and/or section
    reference. Character offsets are into `CandidateDocument.extracted_text`
    so the UI can highlight in place rather than re-searching.
    """
    __tablename__ = "evaluation_evidence"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    evaluation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("evaluations.id"), nullable=False, index=True
    )
    criterion_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("evaluation_criteria.id", ondelete="CASCADE"), nullable=True, index=True
    )
    document_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("candidate_documents.id", ondelete="SET NULL"), nullable=True
    )

    excerpt: Mapped[str] = mapped_column(Text, default="")
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    section: Mapped[str] = mapped_column(String(64), default="")
    char_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    char_end: Mapped[int | None] = mapped_column(Integer, nullable=True)

    match_type: Mapped[EvidenceMatchType] = mapped_column(
        Enum(EvidenceMatchType, native_enum=False, length=32),
        default=EvidenceMatchType.EXACT,
        nullable=False,
    )
    matched_term: Mapped[str] = mapped_column(String(255), default="")
    relevance: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    evaluation: Mapped["Evaluation"] = relationship(back_populates="evidence")
    criterion: Mapped["EvaluationCriterion | None"] = relationship(back_populates="evidence")


class EligibilityFinding(Base):
    """
    Result of one DisqualificationRule against one candidate. Written only by
    the deterministic engine in `app/core/eligibility_engine.py`. The rule
    definition is copied in for the same reason the criterion copies its
    rubric fields: the version may later be superseded.
    """
    __tablename__ = "eligibility_findings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    evaluation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("evaluations.id"), nullable=False, index=True
    )
    rule_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("disqualification_rules.id", ondelete="SET NULL"), nullable=True
    )

    code: Mapped[str] = mapped_column(String(128), nullable=False)
    label: Mapped[str] = mapped_column(Text, default="")
    rule_type: Mapped[RuleType] = mapped_column(
        Enum(RuleType, native_enum=False, length=48), default=RuleType.CUSTOM, nullable=False
    )
    operator: Mapped[RuleOperator] = mapped_column(
        Enum(RuleOperator, native_enum=False, length=16), default=RuleOperator.MISSING, nullable=False
    )
    threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    severity: Mapped[RuleSeverity] = mapped_column(
        Enum(RuleSeverity, native_enum=False, length=32), default=RuleSeverity.HARD_FAIL, nullable=False
    )

    # `triggered` means the rule fired, i.e. the candidate FAILED it.
    triggered: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    observed_value: Mapped[str] = mapped_column(Text, default="")
    message: Mapped[str] = mapped_column(Text, default="")
    # True when the engine could not establish the fact either way. Recorded
    # rather than silently passing the rule — an unverifiable mandatory
    # requirement is a review item, not a pass.
    indeterminate: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    evaluation: Mapped["Evaluation"] = relationship(back_populates="eligibility_findings")


# ---------------------------------------------------------------------------
# Phase E — Challenge Agent
#
# Phase D deliberately persists both `deterministic_score` and `raw_score` on
# every criterion, plus `llm_adjusted`. That was groundwork for this: the
# single most useful "unsupported conclusion" signal is a model adjustment
# that the cited evidence does not justify, and it is only detectable because
# the pre-adjustment number was kept.
#
# Design rules:
#   * A finding NEVER alters a score, an outcome, or an eligibility verdict.
#     The Challenge Agent is a reviewer, not a second scorer. It writes rows
#     and nothing else.
#   * Findings are immutable and tied to the evaluation they reviewed, so a
#     historical result carries the concerns raised about it at the time.
#   * Every check is deterministic. The client's six checks are all
#     structural — they compare numbers, evidence counts and distributions —
#     so none of them needs a model, and an LLM opinion about whether an
#     LLM's own conclusion was supported would be worth little.
# ---------------------------------------------------------------------------


class ChallengeCheck(str, enum.Enum):
    """The client's six checks, plus the two sub-cases worth separating."""
    UNSUPPORTED_CONCLUSION = "UNSUPPORTED_CONCLUSION"
    INCONSISTENT_SCORING = "INCONSISTENT_SCORING"
    MISSING_EVIDENCE = "MISSING_EVIDENCE"
    WEAK_EVIDENCE = "WEAK_EVIDENCE"
    CONTRADICTION = "CONTRADICTION"
    WEIGHTING_ANOMALY = "WEIGHTING_ANOMALY"
    OUTLIER_RECOMMENDATION = "OUTLIER_RECOMMENDATION"


class ChallengeSeverity(str, enum.Enum):
    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class ChallengeScope(str, enum.Enum):
    """
    Whether a finding is about one criterion, the whole candidate, or the
    rubric/run itself. Weighting anomalies are a property of the rubric and
    would be misleading attached to a single candidate.
    """
    CRITERION = "CRITERION"
    EVALUATION = "EVALUATION"
    RUN = "RUN"


class ChallengeFinding(Base):
    __tablename__ = "challenge_findings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("evaluation_runs.id"), nullable=False, index=True
    )
    # Nullable for RUN-scoped findings, which belong to the run as a whole.
    evaluation_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("evaluations.id", ondelete="CASCADE"),
        nullable=True, index=True,
    )
    criterion_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("evaluation_criteria.id", ondelete="CASCADE"),
        nullable=True, index=True,
    )
    # Denormalised so a finding still reads correctly if the rubric version
    # it referenced is later superseded.
    criterion_key: Mapped[str] = mapped_column(String(128), default="")

    check: Mapped[ChallengeCheck] = mapped_column(
        Enum(ChallengeCheck, native_enum=False, length=40), nullable=False, index=True
    )
    severity: Mapped[ChallengeSeverity] = mapped_column(
        Enum(ChallengeSeverity, native_enum=False, length=16),
        default=ChallengeSeverity.LOW, nullable=False, index=True,
    )
    scope: Mapped[ChallengeScope] = mapped_column(
        Enum(ChallengeScope, native_enum=False, length=16),
        default=ChallengeScope.CRITERION, nullable=False,
    )

    title: Mapped[str] = mapped_column(String(255), default="")
    detail: Mapped[str] = mapped_column(Text, default="")
    recommendation: Mapped[str] = mapped_column(Text, default="")
    # The numbers behind the finding, so a recruiter can see why it fired
    # without re-deriving it.
    observed: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    engine_version: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# Phase F — Candidate 360 completion, recruiter disposition, audit trail
#
# The client's Candidate 360 lists sixteen sections. Phases D and E covered
# eleven. This closes the rest, plus the two governance items.
#
# The load-bearing design rule here: **a recruiter override never mutates an
# Evaluation.** It is a separate CandidateAction row that supersedes the AI
# recommendation for display purposes only. The client's first requirement is
# that AI recommendations are never presented as autonomous decisions — and
# that cuts both ways. The AI's original output has to survive the human's
# disagreement, or there is no record that a person overruled the machine,
# which is precisely the thing an auditor will ask to see.
# ---------------------------------------------------------------------------


class Disposition(str, enum.Enum):
    """What a recruiter decided to do with a candidate."""
    SHORTLIST = "SHORTLIST"
    REJECT = "REJECT"
    HOLD = "HOLD"
    REQUEST_REVIEW = "REQUEST_REVIEW"
    INTERVIEW = "INTERVIEW"
    # B15: a candidate worth keeping in reserve for this campaign, without
    # being sent forward yet. Distinct from HOLD, which pauses someone
    # already in the hiring process — this is a screening-time decision,
    # before the lifecycle is ever entered.
    WAITLIST = "WAITLIST"


class ActionType(str, enum.Enum):
    COMMENT = "COMMENT"            # a note, no decision attached
    DISPOSITION = "DISPOSITION"    # shortlist / reject / hold / etc.
    OVERRIDE = "OVERRIDE"          # disagreeing with the AI recommendation


class NextAction(str, enum.Enum):
    """
    Derived, never generated. Eligibility, confidence and the presence of
    HIGH-severity challenge findings determine this arithmetically, so it
    cannot drift from the evidence the way a model-written suggestion would.
    """
    INTERVIEW = "INTERVIEW"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    REQUEST_EVIDENCE = "REQUEST_EVIDENCE"
    CONFIRM_ELIGIBILITY = "CONFIRM_ELIGIBILITY"
    REJECT = "REJECT"


class CandidateAction(Base):
    """
    A human decision about a candidate. Append-only: changing your mind adds
    a row, it does not edit one, so the sequence of decisions is preserved.
    `is_current` marks the operative one.
    """
    __tablename__ = "candidate_actions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    campaign_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("campaigns.id"), nullable=False, index=True
    )
    candidate_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("candidates.id"), nullable=False, index=True
    )
    # The evaluation this decision was taken against. Kept so a disposition
    # made on a superseded result stays attributable to what was on screen
    # at the time.
    evaluation_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("evaluations.id", ondelete="SET NULL"), nullable=True
    )

    action_type: Mapped[ActionType] = mapped_column(
        Enum(ActionType, native_enum=False, length=24), nullable=False, index=True
    )
    disposition: Mapped[Disposition | None] = mapped_column(
        Enum(Disposition, native_enum=False, length=24), nullable=True, index=True
    )
    # For OVERRIDE rows: what the AI said, and what the human decided
    # instead. Both are stored so the disagreement is legible without
    # re-reading the evaluation.
    ai_recommendation: Mapped[Recommendation | None] = mapped_column(
        Enum(Recommendation, native_enum=False, length=32), nullable=True
    )
    overridden_to: Mapped[Recommendation | None] = mapped_column(
        Enum(Recommendation, native_enum=False, length=32), nullable=True
    )

    comment: Mapped[str] = mapped_column(Text, default="")
    # A reason is required for an override; the service enforces it.
    reason: Mapped[str] = mapped_column(Text, default="")
    actor: Mapped[str] = mapped_column(String(255), default="")
    actor_role: Mapped[str] = mapped_column(String(64), default="")

    is_current: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    superseded_by_action_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class AuditAction(str, enum.Enum):
    CAMPAIGN_CREATED = "CAMPAIGN_CREATED"
    CAMPAIGN_UPDATED = "CAMPAIGN_UPDATED"
    CAMPAIGN_STATUS_CHANGED = "CAMPAIGN_STATUS_CHANGED"
    REQUIREMENTS_EXTRACTED = "REQUIREMENTS_EXTRACTED"
    # AI-first campaign entry point: one recruiter sentence, drafted end to
    # end (JD + requirements + rubric) through the same services the manual
    # guided setup uses. The campaign stays DRAFT — this is not an approval.
    AI_CAMPAIGN_DRAFTED = "AI_CAMPAIGN_DRAFTED"
    RUBRIC_VERSION_CREATED = "RUBRIC_VERSION_CREATED"
    RUBRIC_SUBMITTED = "RUBRIC_SUBMITTED"
    RUBRIC_APPROVED = "RUBRIC_APPROVED"
    RUBRIC_REJECTED = "RUBRIC_REJECTED"
    RUBRIC_LOCKED = "RUBRIC_LOCKED"
    BATCH_UPLOADED = "BATCH_UPLOADED"
    FILE_HELD = "FILE_HELD"
    JOB_RETRIED = "JOB_RETRIED"
    # Lifecycle — workstream 7. The screening half of the platform ends at a
    # disposition; everything below is what happens to a person afterwards.
    SENT_TO_HIRING_MANAGER = "SENT_TO_HIRING_MANAGER"
    MANAGER_REVIEWED = "MANAGER_REVIEWED"
    STATUS_CHANGED = "STATUS_CHANGED"
    PUT_ON_HOLD = "PUT_ON_HOLD"
    CANDIDATE_WITHDREW = "CANDIDATE_WITHDREW"
    EVALUATION_RUN_STARTED = "EVALUATION_RUN_STARTED"
    EVALUATION_RUN_COMPLETED = "EVALUATION_RUN_COMPLETED"
    REEVALUATION_STARTED = "REEVALUATION_STARTED"
    DISPOSITION_SET = "DISPOSITION_SET"
    RECOMMENDATION_OVERRIDDEN = "RECOMMENDATION_OVERRIDDEN"
    COMMENT_ADDED = "COMMENT_ADDED"
    EXPORTED = "EXPORTED"
    # Wide pass — journey steps 4-10. Each of these is a real state change
    # whose outward action (an email, an invite, a signed document) is
    # simulated for now. The structured detail lives in `AuditEvent.after`
    # rather than in four new tables: the row is the record, and a table per
    # proxy would have to be migrated again when the real integration lands.
    INTERVIEW_SCHEDULED = "INTERVIEW_SCHEDULED"
    INTERVIEW_FEEDBACK_RECORDED = "INTERVIEW_FEEDBACK_RECORDED"
    APPROVAL_REQUESTED = "APPROVAL_REQUESTED"
    APPROVAL_GRANTED = "APPROVAL_GRANTED"
    APPROVAL_RETURNED = "APPROVAL_RETURNED"
    OFFER_DRAFTED = "OFFER_DRAFTED"
    OFFER_SENT = "OFFER_SENT"
    OFFER_RESPONSE_RECORDED = "OFFER_RESPONSE_RECORDED"
    CANDIDATE_HIRED = "CANDIDATE_HIRED"
    MESSAGE_SENT = "MESSAGE_SENT"
    # B02 phase 5: SLA reminders and escalations. Written by
    # `app/services/sla_service.py`, never by a person — `actor` reads
    # "system" on these two.
    SLA_REMINDER_SENT = "SLA_REMINDER_SENT"
    SLA_ESCALATED = "SLA_ESCALATED"
    # B10/B11: one row per email reply the local Outlook inbox reader
    # classified, whether the decision it read off the reply was only
    # proposed or (opt-in, see `settings.auto_apply_reply_decisions`) applied
    # through an existing service call. `actor` reads "system (Outlook
    # inbox)" for the automatic read, and the person's name for a manual
    # apply — see `app/services/reply_service.py`.
    EMAIL_REPLY_RECEIVED = "EMAIL_REPLY_RECEIVED"


class AuditEvent(Base):
    """
    Append-only audit trail for screen 9.

    Deliberately NOT an extension of the `audit_log` table in
    `app/core/auth.py`: that one is raw SQLite against a different database
    (`tenants.db`) with a different schema, and covers login and OTP events
    only. Mixing hiring-decision audit into it would put the record in a
    database Alembic does not manage.
    """
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    campaign_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    # Indexed alongside campaign_id so "everything that ever happened to this
    # person" is one query. It duplicates entity_id for candidate-scoped
    # events by design: entity_id names whatever the event is *about* (a
    # batch, a rubric version, a job), and an auditor asking about a named
    # applicant cannot be made to know which of those to search.
    candidate_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    action: Mapped[AuditAction] = mapped_column(
        Enum(AuditAction, native_enum=False, length=40), nullable=False, index=True
    )
    # Free-form subject reference rather than a foreign key: the subject may
    # be a rubric version, a batch, a candidate or a run, and an audit row
    # must survive the deletion of whatever it describes.
    entity_type: Mapped[str] = mapped_column(String(48), default="")
    entity_id: Mapped[str] = mapped_column(String(36), default="")

    summary: Mapped[str] = mapped_column(Text, default="")
    before: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    actor: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), index=True
    )


# ---------------------------------------------------------------------------
# Identity — phase 0 of the recruitment lifecycle
#
# An approval by an unauthenticated user is not an approval, so everything in
# the lifecycle needs a real person behind it. This table is that person.
#
# It deliberately does NOT extend `tenants.db`, the separate SQLite database
# behind `app/core/auth.py`. That file belongs to the legacy Streamlit app and
# is imported nowhere in `app/`; Alembic does not manage it, and building the
# lifecycle on top of it would put identity in two places that could disagree.
#
# This is identity, not yet authentication. Callers name the acting user and
# the system checks that they exist and hold the right role. Session handling
# and login come with the RBAC work; the shape here is chosen so that adding
# them later changes who fills `actor_user_id`, not what depends on it.
# ---------------------------------------------------------------------------

class UserRole(str, enum.Enum):
    RECRUITER = "RECRUITER"
    HIRING_MANAGER = "HIRING_MANAGER"
    REVIEWER = "REVIEWER"
    ADMIN = "ADMIN"


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True, index=True)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, native_enum=False, length=20), nullable=False
    )
    business_unit: Mapped[str] = mapped_column(String(120), default="")
    # Deactivated rather than deleted: a person who has approved something
    # must remain nameable for as long as that approval is on the record.
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    # B22 phase 1 (login gate): null until a password is set via
    # scripts/set_password.py. app/core/session_auth.py hashes/verifies it.
    password_hash: Mapped[str | None] = mapped_column(String(200), nullable=True)


# ---------------------------------------------------------------------------
# The lifecycle state machine
# ---------------------------------------------------------------------------

class LifecycleStatus(str, enum.Enum):
    """
    Where a candidate is in the hiring process, as distinct from what the
    recruiter concluded from their CV.

    `Disposition` is a screening outcome and must keep meaning exactly that.
    Overloading it with lifecycle states would leave "shortlisted" competing
    with "awaiting cost-centre approval", and the question "what did the
    recruiter decide from the CV" would no longer have an answer.
    """
    SHORTLISTED = "SHORTLISTED"
    WITH_HIRING_MANAGER = "WITH_HIRING_MANAGER"
    RETURNED_TO_RECRUITER = "RETURNED_TO_RECRUITER"
    INTERVIEW_SCHEDULED = "INTERVIEW_SCHEDULED"
    FEEDBACK_COMPLETE = "FEEDBACK_COMPLETE"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    PENDING_COST_CENTRE = "PENDING_COST_CENTRE"
    APPROVED = "APPROVED"
    # There is deliberately no "offer pending" state. APPROVED already means
    # exactly that: approved to hire, offer not yet drafted.
    OFFER_DRAFTED = "OFFER_DRAFTED"
    OFFER_SENT = "OFFER_SENT"
    OFFER_ACCEPTED = "OFFER_ACCEPTED"
    OFFER_DECLINED = "OFFER_DECLINED"
    HIRED = "HIRED"
    CLOSED = "CLOSED"
    ON_HOLD = "ON_HOLD"
    NOT_PROCEEDING = "NOT_PROCEEDING"
    WITHDRAWN = "WITHDRAWN"
    # B15: kept in reserve for this campaign. Entered directly (like
    # SHORTLISTED), never arrived at from another lifecycle state.
    WAITLISTED = "WAITLISTED"


class CandidateLifecycle(Base):
    """
    One row per candidate per campaign, superseded rather than edited — the
    same append-only shape as `candidate_actions`, for the same reason.
    """
    __tablename__ = "candidate_lifecycle"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    campaign_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("campaigns.id"), nullable=False, index=True
    )
    candidate_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("candidates.id"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(
        Enum(LifecycleStatus, native_enum=False, length=30), nullable=False, index=True
    )
    # Whose turn it is. Null where nobody owes anything — a closed record.
    current_owner_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    entered_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    # Set from SLA policy when that lands. Null means no clock is running.
    due_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # The state this record will return to when a hold is lifted.
    held_from_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    # B15: the leaderboard position this candidate held at the moment they
    # entered the lifecycle (shortlisted or waitlisted). Stored, not
    # recomputed later — a re-evaluation can move scores around, but the
    # ranking a decision was actually made against must stay what it was.
    campaign_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # B13: set once, at the PENDING_COST_CENTRE step, from the validated
    # `CostCentre` registry — never from the caller's claimed code directly.
    # Carried forward on every later transition the same way campaign_rank
    # is, so "which budget this hire is against" survives the supersede.
    cost_centre_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("cost_centres.id"), nullable=True
    )
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class LifecycleTransition(Base):
    """
    Every move, with who made it and why. Nothing about a candidate's
    position is derived on read: a status nobody can point at a transition
    for is a status nobody can audit.
    """
    __tablename__ = "lifecycle_transitions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    campaign_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    candidate_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    from_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    to_status: Mapped[str] = mapped_column(String(30), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    # Delegation is a first-class column from the start rather than a note in
    # the reason field, so the approval work can fill it without a migration.
    on_behalf_of_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)


class ManagerReviewOutcome(str, enum.Enum):
    PROCEED = "PROCEED"
    DECLINE = "DECLINE"
    QUESTION = "QUESTION"


class ManagerReview(Base):
    """
    The hiring manager's verdict, recorded against the assessment they were
    actually shown. If the rubric is re-approved and candidates re-assessed,
    the verdict stays attributable to what was on screen at the time — the
    same rule `candidate_actions` already follows.
    """
    __tablename__ = "manager_reviews"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    campaign_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    candidate_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    evaluation_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    reviewer_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    outcome: Mapped[str] = mapped_column(
        Enum(ManagerReviewOutcome, native_enum=False, length=20), nullable=False
    )
    # Required on a decline. The single most-requested field in any audit of
    # a hiring process, and optional means empty.
    reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# B13 — cost-centre controls and delegation of authority
#
# `app/api/approvals.py` used to log a cost-centre code and a budget holder
# as free-form strings on the audit row and nothing ever checked them — any
# code, any claimed holder, was accepted. These two tables are the registry
# and the grant ledger that make both claims checkable. They are not a
# violation of that file's own "no new tables for approval detail" rule:
# that rule is about not duplicating a fact that already lives on the audit
# trail. A cost centre's budget holder, and whether a delegation is actually
# active, are not facts an audit row can hold — they are facts something has
# to be validated against, which requires a table that exists independently
# of any one approval.
# ---------------------------------------------------------------------------

class CostCentre(Base):
    """A budget the business recognizes, with the person who holds it.

    `business_unit` through `salary_band_max` (added 2026-09-14, demo-readiness
    pass) hold the BU-level pre-approved requisition envelope described by the
    business: prior-year workforce planning approves a headcount/role/grade and
    a salary band per BU per fiscal year, before recruitment starts against it.
    All nullable and additive — existing rows (and `annual_budget_usd`, which
    stays USD-denominated and untouched) are unaffected. A row created for this
    envelope purpose states its own `currency` rather than assuming USD, so a
    screen never has to convert between currencies to show it.
    """
    __tablename__ = "cost_centres"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200), default="")
    # A user id, not wrapped in a foreign key — the same choice this file
    # already makes for every other "who" column (actor_id, owner_id,
    # on_behalf_of_id, created_by).
    budget_holder_id: Mapped[str] = mapped_column(String(36), nullable=False)
    annual_budget_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    business_unit: Mapped[str | None] = mapped_column(String(200), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    fiscal_year: Mapped[str | None] = mapped_column(String(20), nullable=True)
    role_grade: Mapped[str | None] = mapped_column(String(100), nullable=True)
    approved_headcount: Mapped[int | None] = mapped_column(Integer, nullable=True)
    salary_band_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    salary_band_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class JDTemplate(Base):
    """A saved, reusable job description — the smallest honest JD library.

    Deliberately independent of `Campaign`: a template is visible/retrievable
    without ever creating a campaign to hold it. `new-campaign.html` reads one
    to prefill its JD text; nothing here is scored or approved — that still
    happens per-campaign via the existing rubric flow once a recruiter starts
    a campaign from a template.
    """
    __tablename__ = "jd_templates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    role_title: Mapped[str] = mapped_column(String(200), nullable=False)
    summary: Mapped[str] = mapped_column(String(500), default="")
    body: Mapped[str] = mapped_column(Text, nullable=False)
    tags: Mapped[str] = mapped_column(String(300), default="")
    source_file: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_by: Mapped[str] = mapped_column(String(36), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class DelegationGrant(Base):
    """
    One person authorizing another to act in their name, for a bounded scope
    and window. `LifecycleTransition.on_behalf_of_id` has existed since the
    lifecycle model shipped, named for exactly this, and nothing ever
    checked it — this table is what makes it checkable.
    """
    __tablename__ = "delegation_grants"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    grantor_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    delegate_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    # What the delegate may do in the grantor's name. Kept a free string
    # rather than an enum with one member today ("approval"), so a second
    # scope later does not need a migration to add.
    scope: Mapped[str] = mapped_column(String(40), nullable=False, default="approval")
    # Null means the grant applies across every campaign.
    campaign_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    ends_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_by: Mapped[str] = mapped_column(String(36), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# B21 — FinOps: what a screening run actually costs
#
# One row per recorded model call. `run_id` is null for a call made before
# an `EvaluationRun` exists (JD extraction/generation) and set for every
# call made inside `evaluation_service.execute_run`. Prompt, JD, CV and
# candidate content is never written here — only token counts and a derived
# cost estimate, matching the privacy note already on `web/developer.html`.
# ---------------------------------------------------------------------------

class LLMCallLog(Base):
    __tablename__ = "llm_call_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    campaign_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    run_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("evaluation_runs.id"), nullable=True, index=True
    )
    # "jd_extraction", "screening", ... — free text, not an enum: a new call
    # site names its own call_type rather than needing a migration.
    call_type: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    model_name: Mapped[str] = mapped_column(String(120), default="")
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    estimated_cost_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), index=True
    )
