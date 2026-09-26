"""
Task functions executed by a worker.

Each task opens and closes its own DB session. A worker process has no request
scope, so it cannot use the FastAPI `get_db` dependency, and the session must
not be passed in from the enqueuing process — it will have been closed by the
time the task runs.

Task arguments are IDs only, never ORM objects. RQ pickles its arguments, and a
detached SQLAlchemy instance does not survive that round trip.
"""
from __future__ import annotations

import logging

from app.db.models import ProcessingJob
from app.db.session import SessionLocal
from app.services import processing_service

logger = logging.getLogger(__name__)


def process_document_job(job_id: str) -> str:
    """Process one uploaded CV. Returns the terminal job status."""
    db = SessionLocal()
    try:
        job = db.get(ProcessingJob, job_id)
        if job is None:
            logger.warning("Job %s no longer exists; nothing to do.", job_id)
            return "MISSING"
        try:
            processing_service.process_job(db, job)
        except processing_service.BatchStateError as exc:
            # Already processed or in flight — a duplicate enqueue, not an error.
            logger.info("Skipping job %s: %s", job_id, exc)
        return job.status.value
    finally:
        db.close()


def drain_pending(batch_id: str | None = None, limit: int | None = None) -> dict:
    """Process every QUEUED job. Used by the deferred backend's worker script."""
    db = SessionLocal()
    try:
        return processing_service.run_pending(db, batch_id=batch_id, limit=limit)
    finally:
        db.close()
