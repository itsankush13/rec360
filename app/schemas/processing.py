"""Phase C request/response schemas — bulk upload, per-file status, candidates."""
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict

from app.db.models import (
    BatchStatus,
    DuplicateType,
    JobErrorCode,
    JobStatus,
)


# ---------- Jobs (one per uploaded file) ----------

class ProcessingJobOut(BaseModel):
    id: str
    batch_id: str
    campaign_id: str
    sequence: int
    original_filename: str
    size_bytes: int
    document_id: Optional[str]
    candidate_id: Optional[str]
    status: JobStatus
    error_code: Optional[JobErrorCode]
    error_message: str
    requires_review: bool
    duplicate_type: Optional[DuplicateType]
    duplicate_of_document_id: Optional[str]
    duplicate_of_candidate_id: Optional[str]
    attempts: int
    max_attempts: int
    is_retryable: bool
    queued_at: datetime
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    duration_ms: Optional[int]

    model_config = ConfigDict(from_attributes=True)


# ---------- Batches ----------

class ProcessingBatchOut(BaseModel):
    id: str
    campaign_id: str
    rubric_version_id: Optional[str]
    name: str
    status: BatchStatus
    total_files: int
    created_by: str
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


class BatchProgressOut(BaseModel):
    """Backs the Campaign Control Tower progress panel."""
    batch_id: str
    status: BatchStatus
    total_files: int
    queued: int
    processing: int
    completed: int
    failed: int
    duplicates: int
    cancelled: int
    requires_review: int
    percent_complete: float
    average_seconds_per_file: Optional[float]
    elapsed_seconds: Optional[float]
    estimated_seconds_remaining: Optional[float]


class BatchCreatedOut(BaseModel):
    """
    Returned straight after upload. `queue_backend` tells the client whether
    the work has already run (inline), is waiting for a drainer (deferred), or
    went to Redis (rq) — the UI needs to know whether to start polling.
    """
    batch: ProcessingBatchOut
    progress: BatchProgressOut
    jobs: list[ProcessingJobOut]
    queue_backend: str
    accepted_files: int
    rejected_on_intake: int


class BatchDetailOut(BaseModel):
    batch: ProcessingBatchOut
    progress: BatchProgressOut


class RunBatchOut(BaseModel):
    processed: int
    remaining: int
    progress: Optional[BatchProgressOut] = None


# ---------- Candidates ----------

class CandidateDocumentOut(BaseModel):
    id: str
    campaign_id: str
    candidate_id: Optional[str]
    original_filename: str
    extension: str
    content_type: str
    size_bytes: int
    content_hash: str
    page_count: int
    text_char_count: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CandidateOut(BaseModel):
    id: str
    campaign_id: str
    full_name: str
    email: str
    phone: str
    location: str
    requires_review: bool
    source: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CandidateDetailOut(CandidateOut):
    documents: list[CandidateDocumentOut] = []

    model_config = ConfigDict(from_attributes=True)


class DocumentTextOut(BaseModel):
    """
    Extracted text for one document. Phase D will cite from this; exposed now
    so the retained text can be verified without digging into the DB.
    """
    document_id: str
    original_filename: str
    page_count: int
    text_char_count: int
    extracted_text: str
    section_map: Optional[dict[str, Any]]
