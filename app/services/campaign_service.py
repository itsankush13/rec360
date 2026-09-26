"""
Campaign CRUD and status transitions.

Every state change here writes an `AuditEvent` through
`disposition_service.record_audit` — the same path Phase F already uses for
dispositions, overrides and comments. There is deliberately only one audit
path in the codebase: two would eventually disagree, and an audit trail that
disagrees with itself is worse than none.
"""
import secrets
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AuditAction, Campaign, CampaignStatus
from app.schemas.campaign import CampaignCreate, CampaignUpdate
from app.services import disposition_service


class CampaignTransitionError(ValueError):
    pass


class CampaignConflictError(ValueError):
    """Raised when `expected_version` no longer matches the stored row."""
    pass


# B20 identifier model, revised 2026-09-13 (see docs/DECISIONS.md — supersedes
# both the earlier "RC36 fixed cohort prefix" shape and the later
# "RC + date + running number" shape). Format is RC + the creation date
# (YYYYMMDD) + a random number, e.g. "RC20260913-58204", per direct client
# instruction: meaningful (RC, then the date) without exposing a running
# count of how many campaigns exist. Collision is checked against the
# database rather than assumed away — astronomically unlikely at this
# volume, but "unique" means checked, not merely improbable.
_SHORT_ID_PREFIX = "RC"
_SHORT_ID_RANDOM_DIGITS = 5
_SHORT_ID_MAX_ATTEMPTS = 50


def _next_short_id(db: Session) -> str:
    date_part = datetime.now(timezone.utc).strftime("%Y%m%d")
    ceiling = 10 ** _SHORT_ID_RANDOM_DIGITS
    for _ in range(_SHORT_ID_MAX_ATTEMPTS):
        candidate = (
            f"{_SHORT_ID_PREFIX}{date_part}-"
            f"{secrets.randbelow(ceiling):0{_SHORT_ID_RANDOM_DIGITS}d}"
        )
        taken = db.scalar(select(Campaign.short_id).where(Campaign.short_id == candidate))
        if taken is None:
            return candidate
    raise RuntimeError("Could not generate a unique campaign short id.")


# Plain English for the audit screen. DATA.md: an enum value never reaches a
# reader. These are the words a recruiter would use for the same states.
STAGE_WORDS = {
    CampaignStatus.DRAFT: "being prepared",
    CampaignStatus.AWAITING_RUBRIC_APPROVAL: "waiting for the rubric to be approved",
    CampaignStatus.APPROVED: "approved and ready for CVs",
    CampaignStatus.PROCESSING: "reading CVs",
    CampaignStatus.REVIEW: "ready for review",
    CampaignStatus.CLOSED: "closed",
}

# Field names as a person would say them, for the "changed" event.
FIELD_WORDS = {
    "name": "campaign name",
    "job_title": "job title",
    "job_description": "job description",
    "vacancies": "number of vacancies",
    "location": "location",
    "business_unit": "business unit",
    "recruiter": "recruiter",
    "hiring_manager": "hiring manager",
    "start_date": "start date",
    "target_completion_date": "target completion date",
}


def _plain(value):
    """JSON-safe for the before/after columns."""
    return value.isoformat() if hasattr(value, "isoformat") else value


def _actor_for(campaign: Campaign, actor: str) -> str:
    return actor or campaign.created_by or campaign.recruiter or ""


def find_by_idempotency_key(db: Session, idempotency_key: str) -> Campaign | None:
    return db.scalar(select(Campaign).where(Campaign.idempotency_key == idempotency_key))


def create_campaign(
    db: Session, payload: CampaignCreate, *, actor: str = "", idempotency_key: str | None = None
) -> tuple[Campaign, bool]:
    """Returns (campaign, was_created). `was_created` is False when a retried
    create (client timeout, double-click, network retry) with the same
    `idempotency_key` returned the campaign already made for it rather than
    making a second draft. No key means no protection, same as before."""
    if idempotency_key:
        existing = find_by_idempotency_key(db, idempotency_key)
        if existing is not None:
            return existing, False

    campaign = Campaign(
        **payload.model_dump(),
        idempotency_key=idempotency_key,
        short_id=_next_short_id(db),
    )
    db.add(campaign)
    # SessionLocal is autoflush=False, so the id the audit row references
    # does not exist until this flush.
    db.flush()
    disposition_service.record_audit(
        db, AuditAction.CAMPAIGN_CREATED,
        campaign_id=campaign.id,
        entity_type="campaign",
        entity_id=campaign.id,
        summary=(
            f"Campaign opened for {campaign.job_title or campaign.name}"
            + (f" at {campaign.location}" if campaign.location else "")
            + f", {campaign.vacancies} "
            + ("vacancy" if campaign.vacancies == 1 else "vacancies")
        ),
        after={
            "name": campaign.name,
            "job_title": campaign.job_title,
            "vacancies": campaign.vacancies,
            "location": campaign.location,
        },
        actor=_actor_for(campaign, actor),
    )
    db.commit()
    db.refresh(campaign)
    return campaign, True


def list_campaigns(db: Session, status: CampaignStatus | None = None) -> list[Campaign]:
    stmt = select(Campaign).order_by(Campaign.created_at.desc())
    if status is not None:
        stmt = stmt.where(Campaign.status == status)
    return list(db.scalars(stmt))


def get_campaign(db: Session, campaign_id: str) -> Campaign | None:
    return db.get(Campaign, campaign_id)


def update_campaign(
    db: Session, campaign: Campaign, payload: CampaignUpdate, *, actor: str = ""
) -> Campaign:
    fields = payload.model_dump(exclude_unset=True, exclude={"expected_version"})

    if payload.expected_version is not None and payload.expected_version != campaign.version:
        raise CampaignConflictError(
            f"Campaign was changed by someone else (have version {campaign.version}, "
            f"expected {payload.expected_version})"
        )

    before: dict = {}
    after: dict = {}
    for field, value in fields.items():
        if getattr(campaign, field) == value:
            continue
        before[field] = _plain(getattr(campaign, field))
        after[field] = _plain(value)
        setattr(campaign, field, value)

    # A no-op PATCH is not an event. An audit trail padded with entries that
    # changed nothing is harder to read, not more complete. It also does not
    # advance `version` — nothing happened for a concurrent editor to race.
    if after:
        campaign.version += 1
        changed = [FIELD_WORDS.get(f, f.replace("_", " ")) for f in after]
        disposition_service.record_audit(
            db, AuditAction.CAMPAIGN_UPDATED,
            campaign_id=campaign.id,
            entity_type="campaign",
            entity_id=campaign.id,
            summary="Campaign details changed: " + ", ".join(changed),
            before=before,
            after=after,
            actor=_actor_for(campaign, actor),
        )

    db.commit()
    db.refresh(campaign)
    return campaign


def transition_status(
    db: Session, campaign: Campaign, new_status: CampaignStatus, *, actor: str = ""
) -> Campaign:
    if new_status == campaign.status:
        return campaign
    if not campaign.can_transition_to(new_status):
        raise CampaignTransitionError(
            f"Cannot move campaign from {campaign.status.value} to {new_status.value}"
        )
    previous = campaign.status
    campaign.status = new_status
    campaign.version += 1
    disposition_service.record_audit(
        db, AuditAction.CAMPAIGN_STATUS_CHANGED,
        campaign_id=campaign.id,
        entity_type="campaign",
        entity_id=campaign.id,
        summary=(
            f"Campaign moved from {STAGE_WORDS.get(previous, 'an earlier stage')} "
            f"to {STAGE_WORDS.get(new_status, 'a new stage')}"
        ),
        before={"stage": STAGE_WORDS.get(previous, "")},
        after={"stage": STAGE_WORDS.get(new_status, "")},
        actor=_actor_for(campaign, actor),
    )
    db.commit()
    db.refresh(campaign)
    return campaign


def delete_campaign(db: Session, campaign: Campaign) -> None:
    db.delete(campaign)
    db.commit()
