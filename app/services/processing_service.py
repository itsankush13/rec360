"""
Phase C — bulk CV intake, per-file processing, duplicate detection.

Flow for one upload:

    validate  ->  exact-duplicate check  ->  store file  ->  job QUEUED
                                                              |
                                          (queue backend picks it up)
                                                              v
    extract text  ->  extract identity  ->  resolve candidate  ->  COMPLETED
                                                    |
                                              (match found)  ->  DUPLICATE

Every file ends in a terminal job status with a reason, including the ones
that were rejected before a byte was stored. The upload screen needs to
account for all N files, not just the ones that worked.

Deliberate choices worth knowing:

  * A batch cannot be created unless the campaign has an APPROVED or LOCKED
    rubric version, and the batch records which version that was. Screening
    against an unapproved rubric would produce results nobody signed off on,
    and would break the client's requirement that re-evaluation is controlled.
  * Accepting the first batch locks the rubric (APPROVED -> LOCKED). Once
    candidates have been scored against it, changing it in place is exactly
    what the versioning rules forbid; the recruiter clones a new version
    instead.
  * Duplicate detection is scoped to the campaign, in descending order of
    signal strength: identical file bytes, then email, then phone, then name.
    A name match alone sets requires_review rather than being trusted.
  * A DUPLICATE job still keeps its document and links it to the existing
    candidate. A second, newer CV for a known applicant is useful; it just
    isn't a new applicant.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import document_intake, storage
from app.core.document_intake import DocumentRejected
from app.db.models import (
    AuditAction,
    BatchStatus,
    Campaign,
    CampaignStatus,
    Candidate,
    CandidateDocument,
    DuplicateType,
    JobErrorCode,
    JobStatus,
    ProcessingBatch,
    ProcessingJob,
    RubricStatus,
)
from app.services import disposition_service, rubric_service

logger = logging.getLogger(__name__)


class BatchStateError(RuntimeError):
    """Illegal batch/job action -> 409."""


class BatchValidationError(ValueError):
    """Bad batch input -> 422."""


class RubricNotApprovedError(RuntimeError):
    """No approved rubric to screen against -> 409."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    """
    Attach UTC to a naive timestamp read back from the database.

    The DateTime columns are not timezone-aware (SQLite has no tz type), so a
    value written as aware comes back naive. Subtracting one from _now()
    raises TypeError, which is how this surfaced. Every duration calculation
    goes through here.
    """
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=timezone.utc)


def _audit_file_held(db: Session, job: ProcessingJob) -> None:
    """
    One row per file that will not be assessed.

    Written per file rather than per batch on purpose: "this CV was
    never scored, and here is why" is a question asked about one named
    person, and a batch-level count cannot answer it. The reason is the
    message already written on the job, which is plain English by
    Phase C's own rule; the error code is kept in `after` for support,
    not for the screen.
    """
    reason = job.error_message or "The file could not be read."
    disposition_service.record_audit(
        db, AuditAction.FILE_HELD,
        campaign_id=job.campaign_id,
        candidate_id=job.candidate_id,
        entity_type="processing_job",
        entity_id=job.id,
        summary=f"{job.original_filename or 'A file'} was held and not "
                f"assessed. {reason}",
        after={"file": job.original_filename,
               "reason_code": job.error_code.value if job.error_code else None,
               "can_be_tried_again": job.max_attempts > 0},
    )


def max_upload_bytes() -> int:
    return int(os.getenv("MAX_UPLOAD_BYTES", str(document_intake.DEFAULT_MAX_BYTES)))


def max_files_per_batch() -> int:
    return int(os.getenv("MAX_FILES_PER_BATCH", "1000"))


# ---------------------------------------------------------------------------
# Batch creation
# ---------------------------------------------------------------------------

def create_batch(
    db: Session,
    campaign: Campaign,
    files: list[tuple[str, str, bytes]],
    *,
    name: str = "",
    created_by: str = "",
) -> ProcessingBatch:
    """
    `files` is a list of (filename, content_type, data) already read into
    memory by the router. Returns the persisted batch with one job per file.
    """
    if not files:
        raise BatchValidationError("No files were supplied.")
    limit = max_files_per_batch()
    if len(files) > limit:
        raise BatchValidationError(
            f"{len(files)} files exceeds the per-batch limit of {limit}. "
            "Split the upload into smaller batches."
        )

    active_rubric = rubric_service.get_active_version(db, campaign.id)
    if active_rubric is None:
        raise RubricNotApprovedError(
            "This campaign has no approved rubric version. Approve a rubric "
            "before uploading CVs — screening against an unapproved rubric "
            "would produce results that nobody has signed off on."
        )

    batch = ProcessingBatch(
        campaign_id=campaign.id,
        rubric_version_id=active_rubric.id,
        name=name or f"Batch {_now():%Y-%m-%d %H:%M}",
        status=BatchStatus.PENDING,
        total_files=len(files),
        created_by=created_by,
    )
    db.add(batch)
    db.flush()

    for sequence, (filename, content_type, data) in enumerate(files):
        _intake_one_file(db, batch, campaign, sequence, filename, content_type, data)

    # Lock the rubric now that candidates are being screened against it, and
    # move the campaign into PROCESSING. Both are guarded, so a re-upload
    # against an already-locked rubric is fine.
    if active_rubric.status == RubricStatus.APPROVED:
        active_rubric.status = RubricStatus.LOCKED
        active_rubric.locked_at = _now()
    if campaign.can_transition_to(CampaignStatus.PROCESSING):
        campaign.status = CampaignStatus.PROCESSING

    held = [job for job in batch.jobs if job.status == JobStatus.FAILED]
    disposition_service.record_audit(
        db, AuditAction.BATCH_UPLOADED,
        campaign_id=campaign.id,
        entity_type="batch",
        entity_id=batch.id,
        summary=f"{len(files)} file(s) uploaded as '{batch.name}'"
                + (f", of which {len(held)} of {len(files)} could not be "
                   f"read and were held" if held else "")
                + f". Scored against rubric version "
                  f"{active_rubric.version_number}.",
        after={"files": len(files), "held": len(held),
               "rubric_version": active_rubric.version_number},
        actor=created_by,
    )
    for job in held:
        _audit_file_held(db, job)

    db.commit()
    db.refresh(batch)
    return batch


def _intake_one_file(
    db: Session,
    batch: ProcessingBatch,
    campaign: Campaign,
    sequence: int,
    filename: str,
    content_type: str,
    data: bytes,
) -> ProcessingJob:
    filename = (filename or "unnamed").strip()
    job = ProcessingJob(
        batch_id=batch.id,
        campaign_id=campaign.id,
        sequence=sequence,
        original_filename=filename,
        size_bytes=len(data or b""),
        status=JobStatus.QUEUED,
        max_attempts=int(os.getenv("JOB_MAX_ATTEMPTS", "3")),
    )
    db.add(job)

    # 1. Cheap validation. A rejection here is permanent — retrying an
    #    unsupported extension or a 0-byte file cannot succeed — so no
    #    document is stored and max_attempts drops to 0.
    try:
        document_intake.validate_upload(filename, data, max_upload_bytes())
    except DocumentRejected as rejection:
        _fail_permanently(job, rejection.code, rejection.message)
        db.flush()
        return job

    # 2. Exact-duplicate check before storing, so identical bytes are never
    #    written twice.
    digest = document_intake.content_hash(data)
    existing_document = db.scalar(
        select(CandidateDocument).where(
            CandidateDocument.campaign_id == campaign.id,
            CandidateDocument.content_hash == digest,
        ).limit(1)
    )
    if existing_document is not None:
        job.status = JobStatus.DUPLICATE
        job.duplicate_type = DuplicateType.EXACT_FILE
        job.duplicate_of_document_id = existing_document.id
        job.duplicate_of_candidate_id = existing_document.candidate_id
        job.document_id = existing_document.id
        job.candidate_id = existing_document.candidate_id
        job.error_message = (
            f"Byte-identical to an already-uploaded file "
            f"('{existing_document.original_filename}')."
        )
        job.finished_at = _now()
        job.duration_ms = 0
        db.flush()
        return job

    # 3. Store the file. Retention is what makes retry and Phase D evidence
    #    citation possible.
    document = CandidateDocument(
        campaign_id=campaign.id,
        original_filename=filename,
        extension=document_intake.normalize_extension(filename),
        content_type=content_type or "",
        size_bytes=len(data),
        content_hash=digest,
    )
    db.add(document)
    db.flush()

    key = storage.build_key(campaign.id, document.id, document.extension)
    try:
        storage.save(key, data)
    except storage.StorageError as exc:
        db.delete(document)
        db.flush()
        _fail_permanently(job, JobErrorCode.STORAGE_FAILED, str(exc))
        db.flush()
        return job

    document.storage_path = key
    job.document_id = document.id
    db.flush()
    return job


def _fail_permanently(job: ProcessingJob, code: JobErrorCode, message: str) -> None:
    job.status = JobStatus.FAILED
    job.error_code = code
    job.error_message = message
    job.finished_at = _now()
    job.duration_ms = 0
    job.max_attempts = 0  # nothing to retry


# ---------------------------------------------------------------------------
# Processing one job
# ---------------------------------------------------------------------------

def process_job(db: Session, job: ProcessingJob) -> ProcessingJob:
    """
    Extract, identify, deduplicate, link. Safe to call on a QUEUED job or on a
    FAILED job being retried. Never raises for a bad document — the failure is
    recorded on the job so the exceptions panel can show it.
    """
    if job.status == JobStatus.PROCESSING:
        raise BatchStateError(f"Job {job.id} is already being processed.")
    if job.status in (JobStatus.COMPLETED, JobStatus.DUPLICATE, JobStatus.CANCELLED):
        raise BatchStateError(
            f"Job {job.id} is already {job.status.value} and will not be reprocessed."
        )

    document = db.get(CandidateDocument, job.document_id) if job.document_id else None
    if document is None or not document.storage_path:
        _fail_permanently(
            job, JobErrorCode.STORAGE_FAILED,
            "No stored document is associated with this job.",
        )
        db.commit()
        return job

    started = _now()
    job.status = JobStatus.PROCESSING
    job.started_at = started
    job.attempts += 1
    job.error_code = None
    job.error_message = ""
    job.requires_review = False
    _mark_batch_running(db, job)
    db.commit()

    def _finish() -> None:
        job.finished_at = _now()
        # Floored at 1ms, not 0. A small CV on fast hardware can finish in
        # under a millisecond, and 0 is reserved: intake rejections record a
        # literal 0 and are excluded from throughput because they are not
        # work. Without the floor, real jobs land in the same bucket and the
        # Control Tower reports no throughput and no ETA on exactly the
        # machines that are quickest.
        job.duration_ms = max(
            1, int((_aware(job.finished_at) - _aware(started)).total_seconds() * 1000)
        )

    try:
        extracted = document_intake.extract_document(
            storage.local_path(document.storage_path), document.original_filename
        )
    except DocumentRejected as rejection:
        job.status = JobStatus.FAILED
        job.error_code = rejection.code
        job.error_message = rejection.message
        _finish()
        _audit_file_held(db, job)
        _recompute_batch_status(db, job.batch_id)
        db.commit()
        return job
    except Exception as exc:
        logger.exception("Unexpected failure extracting job %s", job.id)
        job.status = JobStatus.FAILED
        job.error_code = JobErrorCode.INTERNAL_ERROR
        job.error_message = f"Unexpected error: {exc}"
        _finish()
        _audit_file_held(db, job)
        _recompute_batch_status(db, job.batch_id)
        db.commit()
        return job

    document.extracted_text = extracted.text
    document.text_char_count = len(extracted.text)
    document.page_count = extracted.page_count
    document.section_map = document_intake.segment(extracted.text)
    # Where the text came from. A CV read from images is still assessed, but
    # the assessment has to know it is working from approximate text.
    document.text_source = extracted.text_source
    document.pages_with_text = extracted.pages_with_text
    document.ocr_pages = extracted.ocr_pages
    if extracted.ocr_pages:
        job.requires_review = True
        note = (
            f"{extracted.ocr_pages} page(s) had no readable text and were read "
            "by character recognition."
        )
        job.error_message = f"{job.error_message} {note}".strip() if job.error_message else note

    # A photographed/scanned CV that stayed thin even after OCR. This no
    # longer holds the file out of the batch — it is screened on whatever
    # text is available, same as every other CV — but it is flagged so a
    # person knows to also look at the original file.
    if extracted.low_text:
        job.requires_review = True
        job.error_code = JobErrorCode.NO_TEXT_EXTRACTED
        note = (
            "Very little text could be read from this file — it looks like a "
            "photograph or scanned image of a CV. It was still screened using "
            "whatever text recognition could recover; a person should also "
            "read the original file."
        )
        job.error_message = f"{job.error_message} {note}".strip() if job.error_message else note

    identity = document_intake.extract_identity(extracted.text)

    match, duplicate_type = _find_matching_candidate(db, job.campaign_id, identity)

    if match is not None:
        candidate = match
        job.status = JobStatus.DUPLICATE
        job.duplicate_type = duplicate_type
        job.duplicate_of_candidate_id = candidate.id
        # Append rather than replace: this file may also have carried an
        # OCR/low-text flag above, and that must survive being merged into
        # the existing candidate, not be silently dropped.
        dup_note = _duplicate_message(duplicate_type, candidate)
        job.error_message = f"{dup_note} {job.error_message}".strip() if job.error_message else dup_note
        # A name-only match is a guess, not a fact — always worth a look,
        # regardless of whatever this file's own requires_review already was.
        job.requires_review = job.requires_review or duplicate_type == DuplicateType.SAME_CANDIDATE_NAME
        _enrich_candidate(candidate, identity)
    else:
        candidate = Candidate(
            campaign_id=job.campaign_id,
            full_name=identity.full_name,
            email=identity.email,
            phone=identity.phone,
            email_normalized=document_intake.normalize_email(identity.email),
            phone_normalized=document_intake.normalize_phone(identity.phone),
            name_normalized=document_intake.normalize_name(identity.full_name),
            requires_review=not identity.has_strong_identity,
        )
        db.add(candidate)
        db.flush()
        job.status = JobStatus.COMPLETED

    # No usable identity at all is not a failure either, any more — the CV
    # is screened on its text alone and a person is told to confirm who it
    # belongs to. Partial identity (a name but no email/phone) is the same
    # idea, one notch less severe. Append rather than replace: a name-only
    # duplicate above already carries a message asking the recruiter to
    # confirm the match, and that instruction must not be overwritten.
    if identity.is_empty:
        job.requires_review = True
        job.error_code = job.error_code or JobErrorCode.INCOMPLETE_CONTENT
        note = (
            "No name, email or phone number could be found in this CV. It was "
            "screened on its text content alone; a person should confirm who "
            "this application belongs to."
        )
        job.error_message = f"{job.error_message} {note}".strip() if job.error_message else note
    elif not identity.has_strong_identity:
        job.requires_review = True
        job.error_code = job.error_code or JobErrorCode.INCOMPLETE_CONTENT
        note = (
            "Processed with incomplete contact details. " + " ".join(identity.warnings)
        ).strip()
        job.error_message = f"{job.error_message} {note}".strip() if job.error_message else note

    document.candidate_id = candidate.id
    job.candidate_id = candidate.id
    _finish()
    _recompute_batch_status(db, job.batch_id)
    db.commit()
    db.refresh(job)
    return job


def _duplicate_message(duplicate_type: DuplicateType | None, candidate: Candidate) -> str:
    label = candidate.full_name or candidate.email or candidate.phone or "an existing candidate"
    if duplicate_type == DuplicateType.SAME_CANDIDATE_EMAIL:
        return f"Same email address as {label}; treated as an additional document."
    if duplicate_type == DuplicateType.SAME_CANDIDATE_PHONE:
        return f"Same phone number as {label}; treated as an additional document."
    if duplicate_type == DuplicateType.SAME_CANDIDATE_NAME:
        return (
            f"Name matches {label} but no email or phone confirms it — "
            "please confirm whether this is the same person."
        )
    return f"Duplicate of {label}."


def _find_matching_candidate(
    db: Session, campaign_id: str, identity: document_intake.Identity
) -> tuple[Candidate | None, DuplicateType | None]:
    """Strongest signal first; a name match is only consulted as a last resort."""
    email = document_intake.normalize_email(identity.email)
    if email:
        match = db.scalar(select(Candidate).where(
            Candidate.campaign_id == campaign_id,
            Candidate.email_normalized == email,
        ).limit(1))
        if match:
            return match, DuplicateType.SAME_CANDIDATE_EMAIL

    phone = document_intake.normalize_phone(identity.phone)
    if phone:
        match = db.scalar(select(Candidate).where(
            Candidate.campaign_id == campaign_id,
            Candidate.phone_normalized == phone,
        ).limit(1))
        if match:
            return match, DuplicateType.SAME_CANDIDATE_PHONE

    name = document_intake.normalize_name(identity.full_name)
    if name:
        match = db.scalar(select(Candidate).where(
            Candidate.campaign_id == campaign_id,
            Candidate.name_normalized == name,
        ).limit(1))
        if match:
            return match, DuplicateType.SAME_CANDIDATE_NAME

    return None, None


def _enrich_candidate(candidate: Candidate, identity: document_intake.Identity) -> None:
    """
    Fill blanks on a known candidate from a newer CV. Existing values are
    never overwritten — a recruiter may have corrected them by hand.
    """
    if not candidate.email and identity.email:
        candidate.email = identity.email
        candidate.email_normalized = document_intake.normalize_email(identity.email)
    if not candidate.phone and identity.phone:
        candidate.phone = identity.phone
        candidate.phone_normalized = document_intake.normalize_phone(identity.phone)
    if not candidate.full_name and identity.full_name:
        candidate.full_name = identity.full_name
        candidate.name_normalized = document_intake.normalize_name(identity.full_name)


# ---------------------------------------------------------------------------
# Batch status bookkeeping
# ---------------------------------------------------------------------------

def _mark_batch_running(db: Session, job: ProcessingJob) -> None:
    batch = db.get(ProcessingBatch, job.batch_id)
    if batch is None or batch.status == BatchStatus.CANCELLED:
        return
    if batch.status in (BatchStatus.PENDING, BatchStatus.COMPLETED, BatchStatus.COMPLETED_WITH_ERRORS):
        batch.status = BatchStatus.RUNNING
    if batch.started_at is None:
        batch.started_at = _now()
    batch.completed_at = None


def _recompute_batch_status(db: Session, batch_id: str) -> None:
    batch = db.get(ProcessingBatch, batch_id)
    if batch is None or batch.status == BatchStatus.CANCELLED:
        return

    # SessionLocal is built with autoflush=False, so the caller's pending
    # status change is not yet visible to an aggregate query. Without this
    # flush the counts below reflect the job's *previous* status and every
    # batch stays RUNNING forever.
    db.flush()
    counts = _status_counts(db, batch_id)
    outstanding = counts.get(JobStatus.QUEUED, 0) + counts.get(JobStatus.PROCESSING, 0)
    if outstanding:
        batch.status = BatchStatus.RUNNING
        batch.completed_at = None
        return

    failed = counts.get(JobStatus.FAILED, 0)
    batch.status = BatchStatus.COMPLETED_WITH_ERRORS if failed else BatchStatus.COMPLETED
    batch.completed_at = _now()


def _status_counts(db: Session, batch_id: str) -> dict[JobStatus, int]:
    rows = db.execute(
        select(ProcessingJob.status, func.count(ProcessingJob.id))
        .where(ProcessingJob.batch_id == batch_id)
        .group_by(ProcessingJob.status)
    ).all()
    return {status: count for status, count in rows}


def batch_progress(db: Session, batch: ProcessingBatch) -> dict:
    """Counts, percent complete, throughput and ETA for the Control Tower."""
    counts = _status_counts(db, batch.id)
    total = batch.total_files or sum(counts.values())
    done = sum(counts.get(status, 0) for status in JobStatus.terminal())
    remaining = max(0, total - done)

    avg_ms = db.scalar(
        select(func.avg(ProcessingJob.duration_ms)).where(
            ProcessingJob.batch_id == batch.id,
            ProcessingJob.duration_ms.isnot(None),
            ProcessingJob.duration_ms > 0,
        )
    )
    avg_ms = float(avg_ms) if avg_ms else None

    # Single-worker estimate. With the rq backend and N workers this is
    # pessimistic by roughly a factor of N; it is not a commitment, and real
    # figures need the benchmarking run on the client's hardware.
    eta_seconds = round(avg_ms / 1000 * remaining, 1) if (avg_ms and remaining) else (0.0 if not remaining else None)

    elapsed = None
    if batch.started_at:
        end = _aware(batch.completed_at) or _now()
        elapsed = round((end - _aware(batch.started_at)).total_seconds(), 1)

    return {
        "batch_id": batch.id,
        "status": batch.status,
        "total_files": total,
        "queued": counts.get(JobStatus.QUEUED, 0),
        "processing": counts.get(JobStatus.PROCESSING, 0),
        "completed": counts.get(JobStatus.COMPLETED, 0),
        "failed": counts.get(JobStatus.FAILED, 0),
        "duplicates": counts.get(JobStatus.DUPLICATE, 0),
        "cancelled": counts.get(JobStatus.CANCELLED, 0),
        "requires_review": db.scalar(
            select(func.count(ProcessingJob.id)).where(
                ProcessingJob.batch_id == batch.id,
                ProcessingJob.requires_review.is_(True),
            )
        ) or 0,
        "percent_complete": round(done / total * 100, 1) if total else 0.0,
        "average_seconds_per_file": round(avg_ms / 1000, 2) if avg_ms else None,
        "elapsed_seconds": elapsed,
        "estimated_seconds_remaining": eta_seconds,
    }


# ---------------------------------------------------------------------------
# Draining, retry, cancel
# ---------------------------------------------------------------------------

def pending_job_ids(db: Session, batch_id: str | None = None, limit: int | None = None) -> list[str]:
    stmt = (
        select(ProcessingJob.id)
        .where(ProcessingJob.status == JobStatus.QUEUED)
        .order_by(ProcessingJob.queued_at, ProcessingJob.sequence)
    )
    if batch_id:
        stmt = stmt.where(ProcessingJob.batch_id == batch_id)
    if limit:
        stmt = stmt.limit(limit)
    return list(db.scalars(stmt))


def run_pending(db: Session, batch_id: str | None = None, limit: int | None = None) -> dict:
    """
    Drain QUEUED jobs in this process. Used by the deferred backend's worker
    script and by the dev-only run endpoint.
    """
    processed = 0
    for job_id in pending_job_ids(db, batch_id, limit):
        job = db.get(ProcessingJob, job_id)
        if job is None or job.status != JobStatus.QUEUED:
            continue
        try:
            process_job(db, job)
        except BatchStateError:
            continue
        except Exception:
            logger.exception("Job %s crashed while draining", job_id)
            db.rollback()
            continue
        processed += 1
    return {"processed": processed, "remaining": len(pending_job_ids(db, batch_id))}


def retry_job(db: Session, job: ProcessingJob) -> ProcessingJob:
    if job.status != JobStatus.FAILED:
        raise BatchStateError(
            f"Only FAILED jobs can be retried; this job is {job.status.value}."
        )
    if job.document_id is None:
        raise BatchStateError(
            "This file was rejected before it could be stored, so there is "
            "nothing to retry. Fix the file and upload it again."
        )
    if job.attempts >= job.max_attempts:
        raise BatchStateError(
            f"Job has already used all {job.max_attempts} attempts. "
            "Re-upload the file if the underlying problem has been fixed."
        )
    job.status = JobStatus.QUEUED
    job.error_code = None
    job.error_message = ""
    job.finished_at = None
    job.duration_ms = None

    disposition_service.record_audit(
        db, AuditAction.JOB_RETRIED,
        campaign_id=job.campaign_id,
        candidate_id=job.candidate_id,
        entity_type="processing_job",
        entity_id=job.id,
        summary=f"{job.original_filename or 'A held file'} was put back in "
                f"the queue to be read again "
                f"(attempt {job.attempts + 1} of {job.max_attempts}).",
        after={"file": job.original_filename,
               "attempts_used": job.attempts,
               "attempts_allowed": job.max_attempts},
    )
    db.commit()
    return job


def cancel_batch(db: Session, batch: ProcessingBatch) -> ProcessingBatch:
    """Cancels outstanding work only. Files already processed are left alone."""
    if batch.status in (BatchStatus.COMPLETED, BatchStatus.COMPLETED_WITH_ERRORS):
        raise BatchStateError(f"Batch is already {batch.status.value}.")
    if batch.status == BatchStatus.CANCELLED:
        raise BatchStateError("Batch is already cancelled.")

    for job in batch.jobs:
        if job.status in (JobStatus.QUEUED, JobStatus.PROCESSING):
            job.status = JobStatus.CANCELLED
            job.finished_at = _now()
    batch.status = BatchStatus.CANCELLED
    batch.completed_at = _now()
    db.commit()
    db.refresh(batch)
    return batch


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------

def list_batches(db: Session, campaign_id: str) -> list[ProcessingBatch]:
    return list(db.scalars(
        select(ProcessingBatch)
        .where(ProcessingBatch.campaign_id == campaign_id)
        .order_by(ProcessingBatch.created_at.desc())
    ))


def list_jobs(
    db: Session, batch_id: str, status: JobStatus | None = None, requires_review: bool | None = None
) -> list[ProcessingJob]:
    stmt = select(ProcessingJob).where(ProcessingJob.batch_id == batch_id)
    if status is not None:
        stmt = stmt.where(ProcessingJob.status == status)
    if requires_review is not None:
        stmt = stmt.where(ProcessingJob.requires_review.is_(requires_review))
    return list(db.scalars(stmt.order_by(ProcessingJob.sequence)))


def list_candidates(db: Session, campaign_id: str, requires_review: bool | None = None) -> list[Candidate]:
    stmt = select(Candidate).where(Candidate.campaign_id == campaign_id)
    if requires_review is not None:
        stmt = stmt.where(Candidate.requires_review.is_(requires_review))
    return list(db.scalars(stmt.order_by(Candidate.created_at)))
