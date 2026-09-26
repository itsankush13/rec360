"""
Phase B routes.

Mounted at /api/campaigns/{campaign_id}/rubric. The two legacy flat-JSON
routes the existing React/Streamlit screens call live at the bottom of this
module on the same prefix, so all rubric path handling stays in one file.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core import rubric_presets
from app.db.models import DisqualificationRule, RubricVersion, RubricWeight
from app.db.session import get_db
from app.schemas.rubric import (
    AcknowledgeReevaluationRequest,
    ApproveRequest,
    DisqualificationRuleCreate,
    DisqualificationRuleOut,
    DisqualificationRuleUpdate,
    LegacyApproveRubricRequest,
    LegacyRubricRequest,
    LegacyRubricResponse,
    RejectRequest,
    RubricOut,
    RubricVersionCreate,
    RubricVersionOut,
    RubricVersionSummary,
    RubricVersionUpdate,
    RubricWeightCreate,
    RubricWeightOut,
    RubricWeightUpdate,
    SubmitRequest,
    ValidationReport,
    WeightBulkSetRequest,
)
from app.services import campaign_service, rubric_service
from app.services.rubric_service import RubricStateError, RubricValidationError

router = APIRouter(prefix="/api/campaigns/{campaign_id}/rubric", tags=["rubric"])


# ---------------------------------------------------------------------------
# Shared lookups / error translation
# ---------------------------------------------------------------------------

def _require_campaign(db: Session, campaign_id: str):
    campaign = campaign_service.get_campaign(db, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign


def _require_version(db: Session, campaign_id: str, version_number: int) -> RubricVersion:
    _require_campaign(db, campaign_id)
    version = rubric_service.get_version(db, campaign_id, version_number)
    if version is None:
        raise HTTPException(status_code=404, detail=f"Rubric version {version_number} not found")
    return version


def _require_weight(db: Session, version: RubricVersion, weight_id: str) -> RubricWeight:
    weight = db.get(RubricWeight, weight_id)
    if weight is None or weight.rubric_version_id != version.id:
        raise HTTPException(status_code=404, detail="Rubric criterion not found")
    return weight


def _require_rule(db: Session, version: RubricVersion, rule_id: str) -> DisqualificationRule:
    rule = db.get(DisqualificationRule, rule_id)
    if rule is None or rule.rubric_version_id != version.id:
        raise HTTPException(status_code=404, detail="Disqualification rule not found")
    return rule


def _state_error(exc: RubricStateError) -> HTTPException:
    return HTTPException(status_code=409, detail=str(exc))


def _validation_error(exc: RubricValidationError) -> HTTPException:
    return HTTPException(status_code=422, detail={"message": str(exc), "errors": exc.errors})


# ---------------------------------------------------------------------------
# Rubric container + version history
# ---------------------------------------------------------------------------

@router.get("", response_model=RubricOut)
def get_rubric(campaign_id: str, db: Session = Depends(get_db)):
    """Rubric container with the full version history — backs the Audit and
    Requirement & Rubric Review screens."""
    _require_campaign(db, campaign_id)
    rubric = rubric_service.get_rubric(db, campaign_id)
    if rubric is None:
        raise HTTPException(
            status_code=404,
            detail="No rubric exists for this campaign yet. POST to .../rubric/versions to create one.",
        )
    payload = RubricOut.model_validate(rubric)
    payload.active_version_number = rubric_service.active_version_number(db, campaign_id)
    return payload


@router.get("/versions", response_model=list[RubricVersionSummary])
def list_versions(campaign_id: str, db: Session = Depends(get_db)):
    _require_campaign(db, campaign_id)
    return rubric_service.list_versions(db, campaign_id)


@router.get("/weightings")
def list_weightings():
    """
    The starting weightings a recruiter can choose from when drafting.

    Offered as a template only: whichever is chosen, the draft still goes
    through submission and approval before anything is scored against it.
    """
    return rubric_presets.available()


@router.post("/versions", response_model=RubricVersionOut, status_code=201)
def create_version(campaign_id: str, payload: RubricVersionCreate, db: Session = Depends(get_db)):
    campaign = _require_campaign(db, campaign_id)
    try:
        return rubric_service.create_version(
            db,
            campaign,
            notes=payload.notes,
            change_reason=payload.change_reason,
            created_by=payload.created_by,
            clone_from_version=payload.clone_from_version,
            seed_from_requirements_flag=payload.seed_from_requirements,
            weighting=payload.weighting,
        )
    except rubric_presets.UnknownPreset as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RubricStateError as exc:
        raise _state_error(exc) from exc
    except RubricValidationError as exc:
        raise _validation_error(exc) from exc


@router.get("/active", response_model=RubricVersionOut)
def get_active_version(campaign_id: str, db: Session = Depends(get_db)):
    """The version evaluations must run against. Phase C/D read this."""
    _require_campaign(db, campaign_id)
    version = rubric_service.get_active_version(db, campaign_id)
    if version is None:
        raise HTTPException(status_code=404, detail="No approved rubric version for this campaign")
    return version


@router.get("/versions/{version_number}", response_model=RubricVersionOut)
def get_version(campaign_id: str, version_number: int, db: Session = Depends(get_db)):
    return _require_version(db, campaign_id, version_number)


@router.patch("/versions/{version_number}", response_model=RubricVersionOut)
def update_version(
    campaign_id: str, version_number: int, payload: RubricVersionUpdate, db: Session = Depends(get_db)
):
    version = _require_version(db, campaign_id, version_number)
    try:
        return rubric_service.update_version(
            db, version, notes=payload.notes, change_reason=payload.change_reason
        )
    except RubricStateError as exc:
        raise _state_error(exc) from exc


@router.delete("/versions/{version_number}", status_code=204)
def delete_version(campaign_id: str, version_number: int, db: Session = Depends(get_db)):
    version = _require_version(db, campaign_id, version_number)
    try:
        rubric_service.delete_version(db, version)
    except RubricStateError as exc:
        raise _state_error(exc) from exc


@router.get("/versions/{version_number}/validate", response_model=ValidationReport)
def validate_version(campaign_id: str, version_number: int, db: Session = Depends(get_db)):
    """Non-mutating pre-flight check — drives the review screen's Submit button."""
    version = _require_version(db, campaign_id, version_number)
    return rubric_service.validate_version(version)


# ---------------------------------------------------------------------------
# Weights
# ---------------------------------------------------------------------------

@router.get("/versions/{version_number}/weights", response_model=list[RubricWeightOut])
def list_weights(campaign_id: str, version_number: int, db: Session = Depends(get_db)):
    return _require_version(db, campaign_id, version_number).weights


@router.post("/versions/{version_number}/weights", response_model=RubricWeightOut, status_code=201)
def add_weight(
    campaign_id: str, version_number: int, payload: RubricWeightCreate, db: Session = Depends(get_db)
):
    version = _require_version(db, campaign_id, version_number)
    try:
        return rubric_service.add_weight(db, version, payload)
    except RubricStateError as exc:
        raise _state_error(exc) from exc
    except RubricValidationError as exc:
        raise _validation_error(exc) from exc


@router.patch("/versions/{version_number}/weights/{weight_id}", response_model=RubricWeightOut)
def update_weight(
    campaign_id: str,
    version_number: int,
    weight_id: str,
    payload: RubricWeightUpdate,
    db: Session = Depends(get_db),
):
    version = _require_version(db, campaign_id, version_number)
    weight = _require_weight(db, version, weight_id)
    try:
        return rubric_service.update_weight(db, version, weight, payload)
    except RubricStateError as exc:
        raise _state_error(exc) from exc


@router.delete("/versions/{version_number}/weights/{weight_id}", status_code=204)
def delete_weight(campaign_id: str, version_number: int, weight_id: str, db: Session = Depends(get_db)):
    version = _require_version(db, campaign_id, version_number)
    weight = _require_weight(db, version, weight_id)
    try:
        rubric_service.delete_weight(db, version, weight)
    except RubricStateError as exc:
        raise _state_error(exc) from exc


@router.put("/versions/{version_number}/weights", response_model=RubricVersionOut)
def bulk_set_weights(
    campaign_id: str, version_number: int, payload: WeightBulkSetRequest, db: Session = Depends(get_db)
):
    """Save the whole weights table in one request."""
    version = _require_version(db, campaign_id, version_number)
    try:
        return rubric_service.bulk_set_weights(db, version, payload.weights)
    except RubricStateError as exc:
        raise _state_error(exc) from exc
    except RubricValidationError as exc:
        raise _validation_error(exc) from exc


@router.post("/versions/{version_number}/weights/normalize", response_model=RubricVersionOut)
def normalize_weights(campaign_id: str, version_number: int, db: Session = Depends(get_db)):
    """Rescale active weights proportionally to sum to exactly 100."""
    version = _require_version(db, campaign_id, version_number)
    try:
        return rubric_service.normalize_weights(db, version)
    except RubricStateError as exc:
        raise _state_error(exc) from exc
    except RubricValidationError as exc:
        raise _validation_error(exc) from exc


@router.post("/versions/{version_number}/weights/suggest", response_model=RubricVersionOut)
def suggest_weights(campaign_id: str, version_number: int, db: Session = Depends(get_db)):
    """B07 — ask the LLM for a per-JD weight suggestion for every active criterion."""
    version = _require_version(db, campaign_id, version_number)
    try:
        return rubric_service.suggest_weights(db, version)
    except RubricStateError as exc:
        raise _state_error(exc) from exc
    except RubricValidationError as exc:
        raise _validation_error(exc) from exc


# ---------------------------------------------------------------------------
# Disqualification rules
# ---------------------------------------------------------------------------

@router.get("/versions/{version_number}/rules", response_model=list[DisqualificationRuleOut])
def list_rules(campaign_id: str, version_number: int, db: Session = Depends(get_db)):
    return _require_version(db, campaign_id, version_number).disqualification_rules


@router.post("/versions/{version_number}/rules", response_model=DisqualificationRuleOut, status_code=201)
def add_rule(
    campaign_id: str, version_number: int, payload: DisqualificationRuleCreate, db: Session = Depends(get_db)
):
    version = _require_version(db, campaign_id, version_number)
    try:
        return rubric_service.add_rule(db, version, payload)
    except RubricStateError as exc:
        raise _state_error(exc) from exc
    except RubricValidationError as exc:
        raise _validation_error(exc) from exc


@router.patch("/versions/{version_number}/rules/{rule_id}", response_model=DisqualificationRuleOut)
def update_rule(
    campaign_id: str,
    version_number: int,
    rule_id: str,
    payload: DisqualificationRuleUpdate,
    db: Session = Depends(get_db),
):
    version = _require_version(db, campaign_id, version_number)
    rule = _require_rule(db, version, rule_id)
    try:
        return rubric_service.update_rule(db, version, rule, payload)
    except RubricStateError as exc:
        raise _state_error(exc) from exc
    except RubricValidationError as exc:
        raise _validation_error(exc) from exc


@router.delete("/versions/{version_number}/rules/{rule_id}", status_code=204)
def delete_rule(campaign_id: str, version_number: int, rule_id: str, db: Session = Depends(get_db)):
    version = _require_version(db, campaign_id, version_number)
    rule = _require_rule(db, version, rule_id)
    try:
        rubric_service.delete_rule(db, version, rule)
    except RubricStateError as exc:
        raise _state_error(exc) from exc


# ---------------------------------------------------------------------------
# Workflow: Draft -> Submitted -> Approved -> Locked
# ---------------------------------------------------------------------------

@router.post("/versions/{version_number}/submit", response_model=RubricVersionOut)
def submit_version(
    campaign_id: str, version_number: int, payload: SubmitRequest, db: Session = Depends(get_db)
):
    version = _require_version(db, campaign_id, version_number)
    try:
        return rubric_service.submit_version(db, version, payload.submitted_by)
    except RubricStateError as exc:
        raise _state_error(exc) from exc
    except RubricValidationError as exc:
        raise _validation_error(exc) from exc


@router.post("/versions/{version_number}/approve", response_model=RubricVersionOut)
def approve_version(
    campaign_id: str, version_number: int, payload: ApproveRequest, db: Session = Depends(get_db)
):
    version = _require_version(db, campaign_id, version_number)
    try:
        return rubric_service.approve_version(
            db, version, payload.approved_by, payload.lock_immediately
        )
    except RubricStateError as exc:
        raise _state_error(exc) from exc
    except RubricValidationError as exc:
        raise _validation_error(exc) from exc


@router.post("/versions/{version_number}/reject", response_model=RubricVersionOut)
def reject_version(
    campaign_id: str, version_number: int, payload: RejectRequest, db: Session = Depends(get_db)
):
    version = _require_version(db, campaign_id, version_number)
    try:
        return rubric_service.reject_version(
            db, version, payload.rejected_by, payload.rejection_reason
        )
    except RubricStateError as exc:
        raise _state_error(exc) from exc


@router.post("/versions/{version_number}/lock", response_model=RubricVersionOut)
def lock_version(campaign_id: str, version_number: int, db: Session = Depends(get_db)):
    version = _require_version(db, campaign_id, version_number)
    try:
        return rubric_service.lock_version(db, version)
    except RubricStateError as exc:
        raise _state_error(exc) from exc


@router.post("/versions/{version_number}/acknowledge-reevaluation", response_model=RubricVersionOut)
def acknowledge_reevaluation(
    campaign_id: str,
    version_number: int,
    payload: AcknowledgeReevaluationRequest,
    db: Session = Depends(get_db),
):
    """
    Recruiter confirms that results produced under the previous rubric are
    known to be stale. Clears the flag; re-scoring itself is Phase D/E work
    and never touches historical results.
    """
    version = _require_version(db, campaign_id, version_number)
    try:
        return rubric_service.acknowledge_reevaluation(db, version, payload.acknowledged_by)
    except RubricStateError as exc:
        raise _state_error(exc) from exc


# ---------------------------------------------------------------------------
# Legacy flat-JSON endpoints — unchanged request/response contract.
# Previously served by app.core.rubric_store writing JSON blobs into
# tenants.db; now backed by the Phase B tables.
# ---------------------------------------------------------------------------

@router.post("", response_model=LegacyRubricResponse, deprecated=True)
def create_rubric_legacy(campaign_id: str, request: LegacyRubricRequest, db: Session = Depends(get_db)):
    """Deprecated. Use POST /versions. Kept for the existing React + Streamlit screens."""
    try:
        return rubric_service.save_legacy_rubric(db, campaign_id, request.rubric)
    except RubricValidationError as exc:
        raise _validation_error(exc) from exc
    except RubricStateError as exc:
        raise _state_error(exc) from exc


@router.post("/approve", response_model=LegacyRubricResponse, deprecated=True)
def approve_rubric_legacy(
    campaign_id: str, request: LegacyApproveRubricRequest, db: Session = Depends(get_db)
):
    """Deprecated. Use POST /versions/{n}/submit then /approve."""
    try:
        return rubric_service.approve_legacy_rubric(db, campaign_id, request.version_id)
    except RubricValidationError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RubricStateError as exc:
        raise _state_error(exc) from exc
