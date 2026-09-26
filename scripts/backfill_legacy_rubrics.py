"""
One-off, idempotent backfill: copy pre-Phase-B rubrics out of the flat
`rubric_versions` table in tenants.db into the Phase B tables.

Nothing in tenants.db is modified or deleted — this is a read-only copy, so it
is safe to run more than once and safe to abandon halfway.

Usage (from the repo root, venv active):

    python scripts/backfill_legacy_rubrics.py            # dry run, prints a plan
    python scripts/backfill_legacy_rubrics.py --commit   # actually write

Rows already backfilled are detected by their change_reason marker and skipped.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import select  # noqa: E402

from app.db.models import (  # noqa: E402
    Campaign,
    RequirementType,
    Rubric,
    RubricStatus,
    RubricVersion,
    RubricWeight,
)
from app.db.session import SessionLocal  # noqa: E402
from app.services.rubric_service import (  # noqa: E402
    TOTAL_WEIGHT,
    _absorb_rounding,
    _slug,
    _unique_key,
)

MARKER = "Backfilled from legacy rubric_store"
LEGACY_DB = REPO_ROOT / "tenants.db"

_TYPE_MAP = {
    "mandatory": RequirementType.MANDATORY,
    "preferred": RequirementType.PREFERRED,
    "informational": RequirementType.INFORMATIONAL,
}


def _read_legacy_rows() -> list[dict]:
    if not LEGACY_DB.exists():
        print(f"No legacy database at {LEGACY_DB} — nothing to backfill.")
        return []
    connection = sqlite3.connect(LEGACY_DB)
    connection.row_factory = sqlite3.Row
    try:
        tables = {r[0] for r in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        if "rubric_versions" not in tables:
            print("Legacy tenants.db has no rubric_versions table — nothing to backfill.")
            return []
        return [dict(r) for r in connection.execute(
            "SELECT id, campaign_id, rubric_json, approved, created_at, approved_at "
            "FROM rubric_versions ORDER BY campaign_id, id"
        )]
    finally:
        connection.close()


def _parse_dt(value) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _ensure_campaign(db, campaign_id: str) -> Campaign:
    campaign = db.get(Campaign, campaign_id)
    if campaign is not None:
        return campaign
    campaign = Campaign(
        id=campaign_id,
        name=f"Legacy campaign {campaign_id}",
        job_title="Imported from legacy rubric store",
        job_description="",
        created_by="backfill",
    )
    db.add(campaign)
    db.flush()
    return campaign


def backfill(commit: bool) -> int:
    legacy_rows = _read_legacy_rows()
    if not legacy_rows:
        return 0

    db = SessionLocal()
    written = 0
    try:
        for row in legacy_rows:
            campaign_id = str(row["campaign_id"])
            legacy_id = row["id"]

            try:
                criteria = json.loads(row["rubric_json"]) or []
            except (TypeError, ValueError):
                print(f"  SKIP legacy #{legacy_id}: rubric_json is not valid JSON")
                continue
            if not isinstance(criteria, list) or not criteria:
                print(f"  SKIP legacy #{legacy_id}: no criteria")
                continue

            campaign = _ensure_campaign(db, campaign_id)
            rubric = db.scalar(select(Rubric).where(Rubric.campaign_id == campaign.id))
            if rubric is None:
                rubric = Rubric(campaign_id=campaign.id)
                db.add(rubric)
                db.flush()

            marker = f"{MARKER} (legacy id {legacy_id})"
            already = db.scalar(
                select(RubricVersion).where(
                    RubricVersion.rubric_id == rubric.id,
                    RubricVersion.change_reason == marker,
                )
            )
            if already is not None:
                print(f"  SKIP legacy #{legacy_id}: already backfilled as v{already.version_number}")
                continue

            next_number = (db.scalar(
                select(RubricVersion.version_number)
                .where(RubricVersion.rubric_id == rubric.id)
                .order_by(RubricVersion.version_number.desc())
                .limit(1)
            ) or 0) + 1

            approved = bool(row["approved"])
            version = RubricVersion(
                rubric_id=rubric.id,
                version_number=next_number,
                # Legacy approvals stay approved; unapproved blobs land as
                # SUPERSEDED history rather than a live draft, so they can't
                # occupy the single in-flight draft slot.
                status=RubricStatus.APPROVED if approved else RubricStatus.SUPERSEDED,
                created_by="backfill",
                approved_by="legacy-api" if approved else "",
                change_reason=marker,
                notes="Imported from the pre-Phase-B flat-JSON rubric store.",
                created_at=_parse_dt(row["created_at"]) or datetime.now(timezone.utc),
                approved_at=_parse_dt(row["approved_at"]) if approved else None,
                superseded_at=None if approved else datetime.now(timezone.utc),
            )
            db.add(version)
            db.flush()

            keys: set[str] = set()
            for order, item in enumerate(criteria):
                if not isinstance(item, dict):
                    continue
                label = str(
                    item.get("criterion") or item.get("Criterion")
                    or item.get("label") or item.get("name") or ""
                ).strip()
                if not label:
                    continue
                try:
                    weight_value = float(item.get("weight", item.get("Weight", 0)) or 0)
                except (TypeError, ValueError):
                    weight_value = 0.0
                raw_type = str(item.get("type") or item.get("Type") or "Mandatory")
                key = _unique_key(keys, _slug(label))
                keys.add(key)
                version.weights.append(RubricWeight(
                    criterion_key=key,
                    label=label,
                    requirement_type=_TYPE_MAP.get(raw_type.strip().lower(), RequirementType.MANDATORY),
                    weight=round(max(0.0, weight_value), 2),
                    display_order=order,
                ))

            if not version.weights:
                print(f"  SKIP legacy #{legacy_id}: no usable criteria")
                db.expunge(version)
                continue

            # Legacy blobs rarely sum to 100; rescale so the Phase B invariant
            # holds without changing the recruiter's relative emphasis.
            total = sum(w.weight for w in version.weights)
            if total > 0 and abs(total - TOTAL_WEIGHT) >= 0.01:
                for weight in version.weights:
                    weight.weight = round(weight.weight * TOTAL_WEIGHT / total, 2)
                _absorb_rounding(version)

            print(
                f"  PLAN legacy #{legacy_id} -> campaign {campaign_id} v{next_number} "
                f"[{version.status.value}] {len(version.weights)} criteria, "
                f"total {round(sum(w.weight for w in version.weights), 2)}"
            )
            written += 1

        if commit:
            db.commit()
            print(f"\nCommitted {written} rubric version(s).")
        else:
            db.rollback()
            print(f"\nDRY RUN — {written} rubric version(s) would be written. "
                  f"Re-run with --commit to apply.")
    finally:
        db.close()
    return written


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", action="store_true", help="write changes (default is a dry run)")
    backfill(parser.parse_args().commit)
