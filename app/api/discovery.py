"""
CV discovery — paste a SharePoint link or a folder path, see the CVs there,
pick which ones to import.

Tier 1 only: the library is resolved against a folder already synced to
local disk (`app/core/cv_source.py`). No Microsoft Graph, no OAuth.

`/discovery/import` deliberately does not repeat any of the intake logic —
it builds the same `(filename, content_type, bytes)` payloads that
`create_batch` in `app/api/processing.py` accepts, and calls the same
`processing_service.create_batch`. A CV that arrives by link gets the exact
same exception codes, duplicate detection and audit trail as one that
arrives by upload.
"""
from __future__ import annotations

import mimetypes
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core import cv_relevance
from app.core.cv_source import CVSourceResolutionError, SyncedFolderSource
from app.db.models import JobStatus
from app.db.session import get_db
from app.schemas.processing import BatchCreatedOut
from app.services import campaign_service, processing_service, rubric_service
from app.services.processing_service import BatchValidationError, RubricNotApprovedError
from app.workers import queue

router = APIRouter(prefix="/discovery", tags=["discovery"])

_source = SyncedFolderSource()


def _require_campaign(db: Session, campaign_id: str):
    campaign = campaign_service.get_campaign(db, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class DiscoveryResolveIn(BaseModel):
    location: str = Field(..., description="A SharePoint/OneDrive URL, a UNC path, or a local folder path")
    campaign_id: str | None = Field(
        None,
        description="When given, files are ranked by coverage of the campaign's active rubric terms",
    )


class DiscoveredFileOut(BaseModel):
    filename: str
    path: str
    size_bytes: int
    modified_at: str
    extension: str
    relevance_score: float | None = Field(
        None, description="0-1 rubric-term coverage; null when ranking is unavailable or the file couldn't be read"
    )
    matched_terms: list[str] = Field(default_factory=list, description="Rubric terms found in this file")
    recommended: bool = False


class DiscoveryResolveOut(BaseModel):
    resolved_folder: str
    source_kind: str
    files: list[DiscoveredFileOut]
    skipped_placeholders: int
    ranking_available: bool = Field(
        False, description="True when campaign_id was given and an approved rubric supplied ranking terms"
    )


class DiscoveryImportIn(BaseModel):
    campaign_id: str
    resolved_root: str = Field(..., description="The `resolved_folder` returned by a prior /discovery/resolve call")
    paths: list[str]
    name: str = ""
    created_by: str = ""


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/resolve", response_model=DiscoveryResolveOut)
def resolve_location(payload: DiscoveryResolveIn, db: Session = Depends(get_db)):
    try:
        resolved = _source.resolve(payload.location)
        listing = _source.list_cvs(resolved)
    except CVSourceResolutionError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "message": exc.message,
                "searched_roots": exc.searched_roots,
            },
        ) from exc

    terms: list[str] = []
    if payload.campaign_id:
        _require_campaign(db, payload.campaign_id)
        version = rubric_service.get_active_version(db, payload.campaign_id)
        if version is not None:
            terms = cv_relevance.terms_for_weights([w for w in version.weights if w.active])

    # Score before sorting so the response order matches the shown scores;
    # a file that can't be read (None) sorts last, never mixed in as if it
    # scored zero relevance.
    scored = [
        (cv, cv_relevance.score_file(Path(cv.path), cv.filename, terms))
        for cv in listing.cvs
    ]
    if terms:
        scored.sort(key=lambda pair: pair[1].coverage if pair[1] else -1.0, reverse=True)

    return {
        "resolved_folder": resolved.root_path,
        "source_kind": resolved.source_kind,
        "ranking_available": bool(terms),
        "files": [
            {
                "filename": cv.filename,
                "path": cv.path,
                "size_bytes": cv.size_bytes,
                "modified_at": cv.modified_at.isoformat(),
                "extension": cv.extension,
                "relevance_score": round(score.coverage, 3) if score else None,
                "matched_terms": score.matched_terms if score else [],
                "recommended": bool(score and score.coverage >= cv_relevance.RECOMMENDED_THRESHOLD),
            }
            for cv, score in scored
        ],
        "skipped_placeholders": listing.skipped_placeholders,
    }


@router.post("/import", response_model=BatchCreatedOut, status_code=201)
def import_discovered(payload: DiscoveryImportIn, db: Session = Depends(get_db)):
    campaign = _require_campaign(db, payload.campaign_id)

    root = Path(payload.resolved_root).resolve()
    payloads: list[tuple[str, str, bytes]] = []
    for path_str in payload.paths:
        candidate = Path(path_str).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"'{path_str}' is outside the resolved folder and cannot be imported.",
            )
        if not candidate.is_file():
            raise HTTPException(status_code=404, detail=f"File not found: {path_str}")
        content_type, _ = mimetypes.guess_type(candidate.name)
        payloads.append((candidate.name, content_type or "", candidate.read_bytes()))

    try:
        batch = processing_service.create_batch(
            db, campaign, payloads, name=payload.name, created_by=payload.created_by
        )
    except RubricNotApprovedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except BatchValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    queued_ids = [job.id for job in batch.jobs if job.status == JobStatus.QUEUED]
    backend_used = queue.enqueue_many(queued_ids, db=db) if queued_ids else queue.backend()

    db.refresh(batch)
    jobs = processing_service.list_jobs(db, batch.id)
    return {
        "batch": batch,
        "progress": processing_service.batch_progress(db, batch),
        "jobs": jobs,
        "queue_backend": backend_used,
        "accepted_files": len(queued_ids),
        "rejected_on_intake": len(payloads) - len(queued_ids),
    }
