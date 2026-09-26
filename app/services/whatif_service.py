"""
B17 — what-if proposal workflow.

`app.core.analytics.what_if()` stays exactly what it was: a pure, free,
non-persisting preview. Nothing here calls it or needs to — a proposal
simply records a weight set someone wants approved, validated only by
shape (`analytics.validate_weights`, reused unchanged), not re-derived from
the preview a recruiter already saw before clicking "propose".

Two properties the backlog asks for explicitly:

  * **Proposer separate from approver.** Both must be named, real, active
    users (`lifecycle_service.require_user`); they cannot be the same
    person, and the approver must actually be a hiring manager or admin —
    "the correct hiring manager/team", not whoever happens to click first.
  * **Both versions audited.** Proposing writes one audit event carrying
    the proposed weights; deciding writes a second, separate event. An
    approval may amend the weights on the way through, so the approved
    event can carry a different snapshot than the proposed one — both stay
    in the trail rather than the second overwriting the first.

Approving a proposal authorizes proceeding to a real rubric revision; it
does not perform one. `app.services.rubric_service` still has to draft,
submit and approve an actual `RubricVersion` before any CV is re-scored —
exactly what `whatif.html` already tells the recruiter.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from types import SimpleNamespace

from app.core import analytics
from app.core.analytics import AnalyticsError
from app.db.models import (
    AuditAction, RubricVersion, UserRole, WhatIfProposal, WhatIfProposalStatus,
)
from app.services import campaign_service, disposition_service, rubric_service
from app.services.lifecycle_service import require_user
from app.services.rubric_service import RubricStateError, RubricValidationError


class WhatIfProposalError(ValueError):
    """Caller-fixable; the API maps this to 4xx."""

    def __init__(self, message: str, errors: list[str] | None = None):
        super().__init__(message)
        self.message = message
        self.errors = errors or []


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _known_keys(version: RubricVersion) -> set[str]:
    return {w.criterion_key for w in version.weights if w.active}


def _validate_weights(weights: dict[str, float], version: RubricVersion) -> None:
    try:
        analytics.validate_weights(weights, _known_keys(version))
    except AnalyticsError as exc:
        raise WhatIfProposalError(exc.message, exc.errors) from exc


def propose(
    db: Session, campaign_id: str, *, weights: dict[str, float],
    proposed_by: str, approver_id: str, note: str = "",
) -> WhatIfProposal:
    """
    Send a what-if weight set to a named counterpart for a decision.

    Runs either direction of the two-person demo pair: a recruiter (HR)
    proposing to the hiring manager (the original B17 direction), or —
    added when the hiring manager gained his own sliders on `whatif.html`
    — the hiring manager proposing back to HR. Either way the approver must
    be the *other* side of that pair (or an admin standing in for either),
    never another person holding the same role as the proposer.
    """
    version = rubric_service.get_active_version(db, campaign_id)
    if version is None:
        raise WhatIfProposalError(
            "This campaign has no approved rubric to propose a reweighting against."
        )

    proposer = require_user(db, proposed_by, what="propose new weights")
    approver = require_user(db, approver_id, what="receive a what-if proposal")
    if approver.id == proposer.id:
        raise WhatIfProposalError(
            "The proposer and the approver must be different people — nobody "
            "approves their own proposal."
        )
    if proposer.role == UserRole.HIRING_MANAGER:
        allowed = (UserRole.RECRUITER, UserRole.ADMIN)
        if approver.role not in allowed:
            raise WhatIfProposalError(
                f"{approver.full_name} is not HR and cannot receive a what-if "
                "proposal for decision."
            )
    else:
        allowed = (UserRole.HIRING_MANAGER, UserRole.ADMIN)
        if approver.role not in allowed:
            raise WhatIfProposalError(
                f"{approver.full_name} is not a hiring manager and cannot receive a "
                "what-if proposal for decision."
            )
    _validate_weights(weights, version)

    proposal = WhatIfProposal(
        campaign_id=campaign_id,
        rubric_version_id=version.id,
        proposed_weights=dict(weights),
        status=WhatIfProposalStatus.PROPOSED,
        proposed_by=proposer.id,
        approver_id=approver.id,
        note=note.strip(),
    )
    db.add(proposal)
    db.flush()

    disposition_service.record_audit(
        db, AuditAction.APPROVAL_REQUESTED,
        campaign_id=campaign_id, entity_type="whatif_proposal", entity_id=proposal.id,
        summary=(
            f"{proposer.full_name} proposed new rubric weights for version "
            f"{version.version_number}, sent to {approver.full_name} for a decision."
            + (f" {note.strip()}" if note.strip() else "")
        ),
        after={
            "proposed_weights": proposal.proposed_weights,
            "rubric_version": version.version_number,
        },
        actor=proposer.full_name,
    )
    return proposal


def get_proposal(db: Session, campaign_id: str, proposal_id: str) -> WhatIfProposal | None:
    proposal = db.get(WhatIfProposal, proposal_id)
    if proposal is None or proposal.campaign_id != campaign_id:
        return None
    return proposal


def list_proposals(db: Session, campaign_id: str) -> list[WhatIfProposal]:
    return list(db.scalars(
        select(WhatIfProposal)
        .where(WhatIfProposal.campaign_id == campaign_id)
        .order_by(WhatIfProposal.created_at.desc())
    ).all())


def _require_pending(proposal: WhatIfProposal) -> None:
    if proposal.status != WhatIfProposalStatus.PROPOSED:
        raise WhatIfProposalError(
            f"This proposal is already {proposal.status.value.lower()} and "
            "cannot be decided again."
        )


def _require_named_approver(db: Session, proposal: WhatIfProposal, decided_by: str):
    decider = require_user(db, decided_by, what="decide this what-if proposal")
    if decider.id != proposal.approver_id:
        raise WhatIfProposalError(
            "Only the hiring manager this proposal was sent to can decide it."
        )
    return decider


def approve(
    db: Session, proposal: WhatIfProposal, *, decided_by: str,
    weights: dict[str, float] | None = None, note: str = "",
) -> WhatIfProposal:
    """
    Approve as proposed, or amend the weights on the way through. Either way
    this authorizes proceeding to a real rubric revision; it does not
    perform one.
    """
    _require_pending(proposal)
    approver = _require_named_approver(db, proposal, decided_by)

    final_weights = dict(weights) if weights is not None else dict(proposal.proposed_weights)
    if weights is not None:
        version = db.get(RubricVersion, proposal.rubric_version_id)
        _validate_weights(weights, version)

    proposal.status = WhatIfProposalStatus.APPROVED
    proposal.approved_weights = final_weights
    proposal.decided_by = approver.id
    proposal.decision_note = note.strip()
    proposal.decided_at = _now()
    db.flush()

    disposition_service.record_audit(
        db, AuditAction.APPROVAL_GRANTED,
        campaign_id=proposal.campaign_id, entity_type="whatif_proposal", entity_id=proposal.id,
        summary=(
            f"{approver.full_name} approved the proposed weights"
            + (", amended on approval" if weights is not None else "")
            + ". A new rubric draft still needs to be created, submitted, approved "
              "and every CV re-scored before anything actually changes."
        ),
        before={"proposed_weights": proposal.proposed_weights},
        after={"approved_weights": proposal.approved_weights},
        actor=approver.full_name,
    )
    return proposal


def reject(db: Session, proposal: WhatIfProposal, *, decided_by: str, reason: str) -> WhatIfProposal:
    _require_pending(proposal)
    if not reason.strip():
        raise WhatIfProposalError("Returning a what-if proposal needs a reason.")
    approver = _require_named_approver(db, proposal, decided_by)

    proposal.status = WhatIfProposalStatus.REJECTED
    proposal.decided_by = approver.id
    proposal.decision_note = reason.strip()
    proposal.decided_at = _now()
    db.flush()

    disposition_service.record_audit(
        db, AuditAction.APPROVAL_RETURNED,
        campaign_id=proposal.campaign_id, entity_type="whatif_proposal", entity_id=proposal.id,
        summary=f"{approver.full_name} returned the proposed weights: {reason.strip()}",
        after={"proposed_weights": proposal.proposed_weights, "reason": reason.strip()},
        actor=approver.full_name,
    )
    return proposal


def create_rubric_draft(
    db: Session, proposal: WhatIfProposal, *, created_by: str,
) -> RubricVersion:
    """
    The remaining B17 step: turn an *approved* proposal into a real
    `RubricVersion` draft — cloned from the campaign's currently active
    version, with the approved weights applied.

    Deliberately its own call rather than something `approve()` does
    automatically. Approving is a hiring manager's decision about a weight
    set; creating a draft is a separate, later action, and `rubric_service`
    already enforces one draft in flight per rubric — if someone started an
    unrelated draft in the meantime, this has to surface that conflict
    rather than silently overwrite or queue behind it. It also never
    submits or approves the draft it creates: those remain their own,
    separately audited, human steps.
    """
    if proposal.status != WhatIfProposalStatus.APPROVED:
        raise WhatIfProposalError(
            f"This proposal is {proposal.status.value.lower()}, not approved. "
            "Only an approved proposal can become a rubric draft."
        )
    if proposal.draft_version_id is not None:
        raise WhatIfProposalError(
            "A rubric draft has already been created from this proposal "
            f"(version {proposal.draft_version_id})."
        )

    campaign = campaign_service.get_campaign(db, proposal.campaign_id)
    if campaign is None:
        raise WhatIfProposalError("This proposal's campaign no longer exists.")
    active_version = rubric_service.get_active_version(db, proposal.campaign_id)

    approver_name = ""
    if proposal.decided_by:
        approver = require_user(db, proposal.decided_by, what="be named on the draft")
        approver_name = approver.full_name

    try:
        draft = rubric_service.create_version(
            db, campaign,
            notes=f"Drafted from what-if proposal {proposal.id}.",
            change_reason=(
                f"Approved weight change from {approver_name or 'a hiring manager'} "
                "via what-if analysis."
            ),
            created_by=created_by,
            clone_from_version=(active_version.version_number if active_version else None),
        )
    except RubricStateError as exc:
        # Surface the "one draft at a time" conflict as a caller-fixable
        # error rather than a 500 — the proposal stays approved and can be
        # retried once the in-flight draft is resolved.
        raise WhatIfProposalError(str(exc)) from exc

    weights = proposal.approved_weights or proposal.proposed_weights
    known_keys = {w.criterion_key for w in draft.weights if w.active}
    items = [
        SimpleNamespace(criterion_key=key, weight=value)
        for key, value in weights.items()
        if key in known_keys
    ]
    if items:
        try:
            rubric_service.bulk_set_weights(db, draft, items)
        except RubricValidationError as exc:
            raise WhatIfProposalError(str(exc)) from exc

    proposal.draft_version_id = draft.id
    db.flush()

    disposition_service.record_audit(
        db, AuditAction.RUBRIC_VERSION_CREATED,
        campaign_id=proposal.campaign_id, entity_type="whatif_proposal", entity_id=proposal.id,
        summary=(
            f"What-if proposal turned into rubric draft version {draft.version_number}. "
            "The draft still needs to be submitted, approved and every CV re-scored."
        ),
        after={"draft_version": draft.version_number, "approved_weights": proposal.approved_weights},
        actor=created_by,
    )
    return draft
