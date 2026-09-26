from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.db.models import CampaignStatus, RequirementCategory, RequirementType


# ---------- Campaign ----------

class CampaignCreate(BaseModel):
    name: str
    job_title: str
    job_description: str = ""
    vacancies: int = Field(default=1, ge=1)
    location: str = ""
    business_unit: str = ""
    recruiter: str = ""
    hiring_manager: str = ""
    start_date: Optional[datetime] = None
    target_completion_date: Optional[datetime] = None
    created_by: str = ""


class CampaignUpdate(BaseModel):
    name: Optional[str] = None
    job_title: Optional[str] = None
    job_description: Optional[str] = None
    vacancies: Optional[int] = Field(default=None, ge=1)
    location: Optional[str] = None
    business_unit: Optional[str] = None
    recruiter: Optional[str] = None
    hiring_manager: Optional[str] = None
    start_date: Optional[datetime] = None
    target_completion_date: Optional[datetime] = None
    # The `version` last seen by the client. Omitted: no conflict check,
    # last write wins. Present and stale: the PATCH is rejected (409) instead
    # of silently overwriting a concurrent edit.
    expected_version: Optional[int] = None


class CampaignStatusUpdate(BaseModel):
    status: CampaignStatus


class CampaignOut(BaseModel):
    id: str
    short_id: Optional[str] = None
    name: str
    job_title: str
    job_description: str
    vacancies: int
    location: str
    business_unit: str
    recruiter: str
    hiring_manager: str
    start_date: Optional[datetime]
    target_completion_date: Optional[datetime]
    status: CampaignStatus
    created_by: str
    created_at: datetime
    updated_at: datetime
    version: int

    model_config = ConfigDict(from_attributes=True)


# ---------- Job Requirement ----------

class RequirementCreate(BaseModel):
    description: str
    category: RequirementCategory
    requirement_type: RequirementType = RequirementType.INFORMATIONAL
    priority: int = Field(default=3, ge=1, le=5)
    weight: float = Field(default=0.0, ge=0.0, le=100.0)
    disqualifying: bool = False
    evidence_required: bool = True


class RequirementUpdate(BaseModel):
    description: Optional[str] = None
    category: Optional[RequirementCategory] = None
    requirement_type: Optional[RequirementType] = None
    priority: Optional[int] = Field(default=None, ge=1, le=5)
    weight: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    disqualifying: Optional[bool] = None
    evidence_required: Optional[bool] = None

    @field_validator("*", mode="before")
    @classmethod
    def _empty_str_to_none(cls, v):
        return v


class RequirementOut(BaseModel):
    id: str
    campaign_id: str
    description: str
    category: RequirementCategory
    requirement_type: RequirementType
    priority: int
    weight: float
    disqualifying: bool
    evidence_required: bool
    source: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ExtractRequirementsRequest(BaseModel):
    """Trigger AI extraction from the campaign's stored job_description,
    or from explicitly supplied text (e.g. before it's saved on the campaign)."""
    jd_text: Optional[str] = None


# ---------- JD generation (B06) ----------

class JDGenerateRequest(BaseModel):
    """
    Everything here is optional — the campaign's own `job_title` is the only
    required input. Anything supplied is passed to the model as an
    override, not a suggestion, per B06's "let the user ... override".
    """
    grade: Optional[str] = None
    min_experience_years: Optional[int] = None
    required_skills: Optional[list[str]] = None
    key_responsibilities: Optional[list[str]] = None
    remuneration: Optional[str] = None


class JDGenerateOut(BaseModel):
    """
    A preview only — nothing here is persisted. The recruiter accepts it by
    saving `jd_text` through the existing `PATCH /api/campaigns/{id}`.
    """
    jd_text: str
    role_title: str
    required_skills: list[str]
    preferred_skills: list[str]
    min_experience_years: Optional[int]
    education_requirement: str
    key_responsibilities: list[str]
    seniority_level: Optional[str]
    source: str
    matched_template: Optional[str]
    based_on_campaign_ids: list[str]
    uncertain: bool
    uncertainty_reason: Optional[str]


# ---------- AI campaign start ----------

class AICampaignStartRequest(BaseModel):
    """One free-text hiring request, e.g. 'Hire a Senior Data Engineer with
    5+ years of experience, strong Python and SQL, AWS, and data pipeline
    experience.'"""
    request: str = Field(..., min_length=1)

    @field_validator("request")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("request must not be blank")
        return v


class AICampaignUnderstanding(BaseModel):
    """What the AI understood from the recruiter's request — shown back to
    the recruiter for review before anything is approved."""
    role_title: str
    seniority_level: Optional[str] = None
    min_experience_years: Optional[int] = None
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    education_requirement: Optional[str] = None
    key_responsibilities: list[str] = Field(default_factory=list)
    location: Optional[str] = None
    work_arrangement: Optional[str] = None
    vacancies: Optional[int] = None
    business_unit: Optional[str] = None
    remuneration: Optional[str] = None


class AICampaignRubricCriterionOut(BaseModel):
    criterion_key: str
    label: str
    category: str
    requirement_type: str
    weight: float


class AICampaignStartOut(BaseModel):
    """
    Everything the AI proposed for the recruiter to review. `campaign` is
    already persisted at DRAFT — same as a manually-created campaign at this
    point — but nothing here has been submitted or approved: the recruiter
    reviews/edits requirements and the rubric through the existing screens,
    then approves through the existing rubric-approval flow. Human approval
    is a separate, later action, not part of this response.
    """
    campaign: CampaignOut
    understood: AICampaignUnderstanding
    jd_text: str
    jd_source: str  # "llm" | "template_only" | "minimal" | "existing"
    requirements: list[RequirementOut]
    rubric_version: Optional[int] = None
    rubric_criteria: list[AICampaignRubricCriterionOut] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
