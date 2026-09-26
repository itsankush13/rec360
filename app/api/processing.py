"""
Phase C routes — bulk upload, per-file status, retry, and the candidate pool.

Split across two prefixes on purpose: batches and candidates are created
inside a campaign, but once a batch exists the Control Tower polls it by id
without knowing or caring which campaign it belongs to.
"""
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app.db.models import (
    Candidate,
    CandidateDocument,
    JobStatus,
    ProcessingBatch,
    ProcessingJob,
)
from app.db.session import get_db
from app.schemas.processing import (
    BatchCreatedOut,
    BatchDetailOut,
    CandidateDetailOut,
    CandidateOut,
    DocumentTextOut,
    ProcessingBatchOut,
    ProcessingJobOut,
    RunBatchOut,
)
from app.services import campaign_service, processing_service
from app.services.processing_service import (
    BatchStateError,
    BatchValidationError,
    RubricNotApprovedError,
)
from app.workers import queue

campaign_router = APIRouter(prefix="/api/campaigns/{campaign_id}", tags=["processing"])
processing_router = APIRouter(prefix="/api/processing", tags=["processing"])


def _require_campaign(db: Session, campaign_id: str):
    campaign = campaign_service.get_campaign(db, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign


def _require_batch(db: Session, batch_id: str) -> ProcessingBatch:
    batch = db.get(ProcessingBatch, batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="Batch not found")
    return batch


def _require_job(db: Session, job_id: str) -> ProcessingJob:
    job = db.get(ProcessingJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Processing job not found")
    return job


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------

@campaign_router.post("/batches", response_model=BatchCreatedOut, status_code=201)
async def create_batch(
    campaign_id: str,
    files: list[UploadFile] = File(..., description="PDF or DOCX CVs"),
    name: str = Query("", description="Optional batch label"),
    created_by: str = Query(""),
    db: Session = Depends(get_db),
):
    """
    Accept a folder of CVs. Returns immediately with one job per file; the
    files themselves are processed by the queue backend.

    Every supplied file gets a job row, including ones rejected on intake for
    being unsupported, empty, oversized or byte-identical to an earlier
    upload — the upload screen has to account for all of them.
    """
    campaign = _require_campaign(db, campaign_id)

    payloads: list[tuple[str, str, bytes]] = []
    for upload in files:
        payloads.append((upload.filename or "unnamed", upload.content_type or "", await upload.read()))

    try:
        batch = processing_service.create_batch(
            db, campaign, payloads, name=name, created_by=created_by
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


@campaign_router.get("/batches", response_model=list[ProcessingBatchOut])
def list_batches(campaign_id: str, db: Session = Depends(get_db)):
    _require_campaign(db, campaign_id)
    return processing_service.list_batches(db, campaign_id)


# ---------------------------------------------------------------------------
# Batch status / control
# ---------------------------------------------------------------------------

@processing_router.get("/batches/{batch_id}", response_model=BatchDetailOut)
def get_batch(batch_id: str, db: Session = Depends(get_db)):
    """Poll this for live progress, throughput and ETA."""
    batch = _require_batch(db, batch_id)
    return {"batch": batch, "progress": processing_service.batch_progress(db, batch)}


@processing_router.get("/batches/{batch_id}/jobs", response_model=list[ProcessingJobOut])
def list_jobs(
    batch_id: str,
    status: JobStatus | None = Query(None, description="Filter by job status"),
    requires_review: bool | None = Query(None),
    db: Session = Depends(get_db),
):
    """Per-file rows for the upload screen. Filter by FAILED or DUPLICATE for
    the exceptions panel."""
    _require_batch(db, batch_id)
    return processing_service.list_jobs(db, batch_id, status=status, requires_review=requires_review)


@processing_router.post("/batches/{batch_id}/run", response_model=RunBatchOut)
def run_batch(
    batch_id: str,
    limit: int | None = Query(None, description="Cap files processed this call"),
    db: Session = Depends(get_db),
):
    """
    Drain this batch's queued files in the request thread.

    For local development with the deferred backend, and for small demo
    batches. It is not a substitute for a worker: a large batch will exceed
    any sensible HTTP timeout. Use `python scripts/run_worker.py --watch`
    instead, or the rq backend in production.
    """
    batch = _require_batch(db, batch_id)
    result = processing_service.run_pending(db, batch_id=batch.id, limit=limit)
    db.refresh(batch)
    return {**result, "progress": processing_service.batch_progress(db, batch)}


@processing_router.post("/batches/{batch_id}/cancel", response_model=BatchDetailOut)
def cancel_batch(batch_id: str, db: Session = Depends(get_db)):
    """Cancels queued work. Files already processed keep their results."""
    batch = _require_batch(db, batch_id)
    try:
        processing_service.cancel_batch(db, batch)
    except BatchStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"batch": batch, "progress": processing_service.batch_progress(db, batch)}


# ---------------------------------------------------------------------------
# Per-file retry
# ---------------------------------------------------------------------------

@processing_router.post("/jobs/{job_id}/retry", response_model=ProcessingJobOut)
def retry_job(job_id: str, db: Session = Depends(get_db)):
    """
    Re-queue one failed file. Works because the original document was
    retained — files rejected before storage (unsupported format, oversized)
    cannot be retried and must be re-uploaded.
    """
    job = _require_job(db, job_id)
    try:
        processing_service.retry_job(db, job)
    except BatchStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    # With the inline backend this returns after the file has been reprocessed;
    # with deferred/rq the job comes back as QUEUED and the client polls.
    queue.enqueue(job.id, db=db)
    db.refresh(job)
    return job


@processing_router.get("/jobs/{job_id}", response_model=ProcessingJobOut)
def get_job(job_id: str, db: Session = Depends(get_db)):
    return _require_job(db, job_id)


# ---------------------------------------------------------------------------
# Candidate pool
# ---------------------------------------------------------------------------

@campaign_router.get("/candidates", response_model=list[CandidateOut])
def list_candidates(
    campaign_id: str,
    requires_review: bool | None = Query(None),
    db: Session = Depends(get_db),
):
    _require_campaign(db, campaign_id)
    return processing_service.list_candidates(db, campaign_id, requires_review=requires_review)


@processing_router.get("/candidates/{candidate_id}", response_model=CandidateDetailOut)
def get_candidate(candidate_id: str, db: Session = Depends(get_db)):
    candidate = db.get(Candidate, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return candidate


@processing_router.get("/documents/{document_id}/text", response_model=DocumentTextOut)
def get_document_text(document_id: str, db: Session = Depends(get_db)):
    """Retained text for one CV — what Phase D will cite evidence from."""
    document = db.get(CandidateDocument, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return {
        "document_id": document.id,
        "original_filename": document.original_filename,
        "page_count": document.page_count,
        "text_char_count": document.text_char_count,
        "extracted_text": document.extracted_text,
        "section_map": document.section_map,
    }
