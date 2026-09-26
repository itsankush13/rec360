"""
Queue abstraction.

The target architecture is React -> FastAPI -> Postgres -> Redis -> workers.
Getting there from a Windows dev box with no Docker needs three backends, all
behind one `enqueue` call, selected by the QUEUE_BACKEND environment variable:

  deferred (default)
      Jobs are written as QUEUED and left alone. A separate process drains
      them: `python scripts/run_worker.py --once`. Uploads return immediately,
      and the shape mirrors production — a worker pulls from a queue — without
      needing Redis. This is the right default for local dev.

  inline
      Jobs run synchronously inside the request. Deterministic, so this is
      what the test suite uses, and it's a reasonable fallback for a small
      demo batch. Do not use it for real volume: a 500-file upload becomes a
      500-file HTTP request.

  rq
      Real Redis-backed background workers. Requires the docker-compose
      services. Note that RQ forks, so its workers do not run on Windows —
      this backend is for Linux/production only. That constraint is why
      `deferred` exists rather than making RQ the dev default.

Deliberately not offered: a thread-pool backend. It would look like the
obvious way to get concurrency on Windows, but concurrent writers against
SQLite hit database-level write locking and produce intermittent "database is
locked" failures under exactly the load it's meant to help with. Concurrency
here needs Postgres, not threads.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

BACKEND_DEFERRED = "deferred"
BACKEND_INLINE = "inline"
BACKEND_RQ = "rq"

VALID_BACKENDS = {BACKEND_DEFERRED, BACKEND_INLINE, BACKEND_RQ}

DEFAULT_QUEUE_NAME = "cv-processing"


def backend() -> str:
    """Read at call time so tests and scripts can switch backends per-run."""
    value = os.getenv("QUEUE_BACKEND", BACKEND_DEFERRED).strip().lower()
    if value not in VALID_BACKENDS:
        logger.warning(
            "Unknown QUEUE_BACKEND %r; falling back to %r. Valid: %s",
            value, BACKEND_DEFERRED, ", ".join(sorted(VALID_BACKENDS)),
        )
        return BACKEND_DEFERRED
    return value


def redis_url() -> str:
    return os.getenv("REDIS_URL", "redis://localhost:6379/0")


def _rq_queue():
    from redis import Redis
    from rq import Queue

    return Queue(
        os.getenv("QUEUE_NAME", DEFAULT_QUEUE_NAME),
        connection=Redis.from_url(redis_url()),
        default_timeout=int(os.getenv("QUEUE_JOB_TIMEOUT", "600")),
    )


def enqueue(job_id: str, db=None) -> str:
    """
    Hand one ProcessingJob off for execution and report which backend took it.

    `db` is the caller's session, used only by the inline backend. Inline means
    "run it now, in this transaction", so it must share the caller's session —
    opening a second one would read a different connection and, under a test
    or a transaction that hasn't committed, would not see the job at all.
    The deferred and rq backends ignore `db`: their workers run in another
    process and must open their own session.

    Never raises on queue failure: the job row is already persisted as QUEUED,
    so a Redis outage degrades to "drain it later" rather than losing the
    upload. The caller has already stored the file.
    """
    selected = backend()

    if selected == BACKEND_INLINE:
        # Imported here, not at module scope — both of these import the service
        # layer, which imports models, which would be a circular import.
        if db is not None:
            from app.db.models import ProcessingJob
            from app.services import processing_service

            job = db.get(ProcessingJob, job_id)
            if job is not None:
                try:
                    processing_service.process_job(db, job)
                except processing_service.BatchStateError as exc:
                    logger.info("Skipping job %s: %s", job_id, exc)
            return BACKEND_INLINE

        from app.workers import tasks

        tasks.process_document_job(job_id)
        return BACKEND_INLINE

    if selected == BACKEND_RQ:
        try:
            _rq_queue().enqueue("app.workers.tasks.process_document_job", job_id)
            return BACKEND_RQ
        except Exception as exc:
            logger.error(
                "Could not enqueue job %s to Redis (%s). The job stays QUEUED and "
                "can be drained with scripts/run_worker.py.", job_id, exc,
            )
            return BACKEND_DEFERRED

    return BACKEND_DEFERRED


def enqueue_many(job_ids: list[str], db=None) -> str:
    last = backend()
    for job_id in job_ids:
        last = enqueue(job_id, db=db)
    return last
