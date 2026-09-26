"""
Compatibility routes for the static Recruitment 360 frontend.

The static UI under `web/` was built against a different backend, and it
already works. Rather than rewrite 4,400 lines of working HTML to match the
Phase A-D routes, the routes it expects are provided here and backed by the
real tables. The frontend is copied in byte-identical and stays that way.

Three things the UI needs that Phases A-C did not expose:

    POST /api/documents/extract-text   read a JD file for the compose box
    GET  /api/runs                     recent runs, newest first
    GET  /api/runs/{run_id}            one run, with results

The important difference from the bundle this contract came from: there, runs
were held in a 20-entry in-memory list and vanished on API restart, which is
listed as a known boundary in its README. Here a "run" is an
`EvaluationRun` plus its `ProcessingBatch`, both already durable, so the
same screens gain persistence without changing a line of their JavaScript.

Score shape notes, learned from reading the UI rather than guessed:

  * `hiring_match_pct` is 0-100 and takes precedence in the leaderboard;
    `weighted_total` is the legacy 0-10 figure and is only used as a
    fallback (`weighted_total * 10`). Both are emitted, consistently, so
    whichever the UI reaches for it shows the same number.
  * `recommendation_code` uses the legacy STRONG_HIRE/HIRE/MAYBE/NO_HIRE
    vocabulary. Those four map exactly onto Phase D's four recommendations
    and onto the four `--v-*` verdict colours in the stylesheet, so the
    mapping is lossless and the theme needs no new tokens.
"""
from __future__ import annotations

import os
import tempfile
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import document_intake, document_quality
from app.core.document_intake import DocumentRejected
from app.db.models import (
    Campaign, Candidate, CandidateDocument, Evaluation, EvaluationRun,
    EvaluationStatus, JobErrorCode, JobStatus, ProcessingBatch, ProcessingJob,
    Recommendation,
)
from app.db.session import get_db

router = APIRouter(tags=["frontend-compat"])

CONTRACT_VERSION = "v1"

# Phase D recommendation -> the legacy vocabulary the static UI switches on.
_RECOMMENDATION_CODE = {
    Recommendation.STRONG_FIT: "STRONG_HIRE",
    Recommendation.POTENTIAL_FIT: "HIRE",
    Recommendation.REVIEW_REQUIRED: "MAYBE",
    Recommendation.NOT_RECOMMENDED: "NO_HIRE",
}

# Plain-English held-file reasons. `web/DATA.md` sets the house language
# rules explicitly: write for someone who does not work in software, so
# "Photographs of a CV, with no text to read" rather than "OCR failure" or
# an error code. These are the same four buckets that document lists.
_HELD_REASON = {
    JobErrorCode.NO_TEXT_EXTRACTED: "Photographs of a CV, with no text to read",
    JobErrorCode.PASSWORD_PROTECTED: "The file is password protected",
    JobErrorCode.CORRUPT_FILE: "The file is damaged and cannot be opened",
    JobErrorCode.UNSUPPORTED_FORMAT: "That file type cannot be read",
    JobErrorCode.EMPTY_FILE: "The file is empty",
    JobErrorCode.FILE_TOO_LARGE: "The file is too large to read",
    JobErrorCode.INCOMPLETE_CONTENT: "No name or contact details anywhere in the CV",
    JobErrorCode.EXTRACTION_FAILED: "The text in this file could not be read",
    JobErrorCode.STORAGE_FAILED: "The file could not be saved",
    JobErrorCode.INTERNAL_ERROR: "Something went wrong reading this file",
}

_HELD_ACTION = {
    JobErrorCode.NO_TEXT_EXTRACTED: "Send for scanning",
    JobErrorCode.PASSWORD_PROTECTED: "Ask for it again",
    JobErrorCode.INCOMPLETE_CONTENT: "Read by hand",
}


def held_reason(job: ProcessingJob) -> str:
    if job.status == JobStatus.DUPLICATE:
        return "The same person applied twice"
    if job.error_code is None:
        return "Needs a look"
    return _HELD_REASON.get(job.error_code, "Needs a look")


def held_action(job: ProcessingJob) -> str:
    return _HELD_ACTION.get(job.error_code, "Read by hand")


# ---------------------------------------------------------------------------
# Document extraction
# ---------------------------------------------------------------------------

@router.post("/api/documents/extract-text")
async def extract_text(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """
    Read a JD file into text for the compose box.

    Reuses Phase C's `document_intake` rather than a second extractor, so a
    JD and a CV are validated by exactly the same code. Unlike a CV, a JD
    that comes back as a photograph/scan with too little text to trust is
    still rejected here, not flagged-and-continued — there is no rubric to
    build a screening pass around otherwise, and no downstream step that
    would pick this up and flag it the way a held CV is.
    """
    data = await file.read()
    filename = file.filename or "job-description"

    try:
        document_intake.validate_upload(filename, data)
    except DocumentRejected as exc:
        raise _api_error(422, exc.code.value, held_reason_for_code(exc.code)) from exc

    suffix = document_intake.normalize_extension(filename) or ".pdf"
    handle, path = tempfile.mkstemp(suffix=suffix)
    try:
        with os.fdopen(handle, "wb") as buffer:
            buffer.write(data)
        extracted = document_intake.extract_document(path, filename)
    except DocumentRejected as exc:
        raise _api_error(422, exc.code.value, held_reason_for_code(exc.code)) from exc
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass

    if extracted.low_text:
        raise _api_error(
            422, JobErrorCode.NO_TEXT_EXTRACTED.value,
            held_reason_for_code(JobErrorCode.NO_TEXT_EXTRACTED),
        )

    return {
        "contract_version": CONTRACT_VERSION,
        "filename": filename,
        "text": extracted.text,
        "char_count": len(extracted.text),
        "page_count": extracted.page_count,
    }


def held_reason_for_code(code: JobErrorCode) -> str:
    return _HELD_REASON.get(code, "This file could not be read")


def _api_error(status: int, code: str, message: str) -> HTTPException:
    """
    The error envelope the static UI reads: it looks for
    `body.error.message` and shows `body.error.request_id` as a reference.
    Raw exception text is deliberately never included.
    """
    return HTTPException(
        status_code=status,
        detail={
            "error": {
                "code": code,
                "message": message,
                "request_id": uuid.uuid4().hex[:12],
            }
        },
    )


# ---------------------------------------------------------------------------
# Run serialization
# ---------------------------------------------------------------------------

def _score_block(db: Session, evaluation: Evaluation, candidate: Candidate | None) -> dict:
    """
    Build the `score` object the UI expects, from a Phase D evaluation.

    Criterion-level detail, evidence, confidence bands and eligibility are
    carried alongside the legacy fields rather than flattened away — the
    Phase D screens read those, and nothing here has to change when they do.
    """
    matched: list[str] = []
    missing: list[str] = []
    for criterion in evaluation.criteria:
        matched.extend(criterion.matched_terms or [])
        missing.extend(criterion.missing_terms or [])

    return {
        "candidate_name": (candidate.full_name if candidate else "") or "Unknown",
        "file_name": "",
        # 0-100, what the leaderboard prefers.
        "hiring_match_pct": round(evaluation.overall_score, 1),
        # Legacy 0-10 equivalent, kept consistent with the above.
        "weighted_total": round(evaluation.overall_score / 10.0, 2),
        "confidence": round(evaluation.overall_confidence, 2),
        "recommendation_code": _RECOMMENDATION_CODE.get(evaluation.recommendation, "MAYBE"),
        "hire_recommendation": evaluation.recommendation.value.replace("_", " "),
        "matched_skills": _dedupe(matched),
        "missing_skills": _dedupe(missing),
        "shortlist_reasoning": evaluation.narrative,
        "bias_masked": True,
        # Phase D additions the newer screens use.
        "evaluation_id": evaluation.id,
        "confidence_band": evaluation.confidence_band.value,
        "eligibility_status": evaluation.eligibility_status.value,
        "mandatory_score": round(evaluation.mandatory_score, 1),
        "rubric_version_id": evaluation.rubric_version_id,
        # None unless part of the CV was read from images. The screens show
        # nothing at all in the ordinary case.
        "document_quality": document_quality.describe(
            db.get(CandidateDocument, evaluation.document_id)
            if evaluation.document_id else None
        ),
        "cv_available": bool(
            evaluation.document_id
            and (db.get(CandidateDocument, evaluation.document_id) or None)
            and db.get(CandidateDocument, evaluation.document_id).storage_path
        ),
        "dimensions": [
            {
                "name": criterion.label,
                "criterion_key": criterion.criterion_key,
                # The UI's dimension scale is 0-10.
                "score": round(
                    (criterion.raw_score / criterion.max_score * 10.0)
                    if criterion.max_score else 0.0, 2
                ),
                "weight": criterion.weight,
                "outcome": criterion.outcome.value,
                "confidence": round(criterion.confidence, 2),
                "justification": criterion.rationale,
            }
            for criterion in evaluation.criteria
        ],
    }


def _dedupe(values: list[str], limit: int = 25) -> list[str]:
    seen: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.append(value)
        if len(seen) >= limit:
            break
    return seen


def serialize_run(db: Session, run: EvaluationRun) -> dict:
    """Assemble one run in the shape the static screens consume."""
    campaign = db.get(Campaign, run.campaign_id) if run.campaign_id else None

    results = []
    for evaluation in sorted(
        run.evaluations, key=lambda e: (-e.overall_score, e.created_at)
    ):
        if evaluation.status != EvaluationStatus.COMPLETED:
            continue
        candidate = db.get(Candidate, evaluation.candidate_id)
        document = (
            db.get(CandidateDocument, evaluation.document_id)
            if evaluation.document_id else None
        )
        score = _score_block(db, evaluation, candidate)
        if document is not None:
            score["file_name"] = document.original_filename
        results.append({
            "candidate_id": evaluation.candidate_id,
            "score": score,
            "profile": {
                "name": score["candidate_name"],
                "email": candidate.email if candidate else "",
                "experience_years": evaluation.experience_years_total,
                "skills": score["matched_skills"],
            },
        })

    # Held files come from the batch's exception jobs, which is where Phase C
    # already records them per file with a cause. A held file (FAILED) never
    # got screened and needs someone to act on it. A flagged file (screened
    # normally — completed, or merged as a duplicate — but still carrying a
    # note, e.g. a scanned CV or a repeat applicant) is not held at all; it
    # only gets a note, never a retry/action.
    submitted_files: list[str] = []
    held_files: list[dict] = []
    flagged_files: list[dict] = []
    batch = db.get(ProcessingBatch, run.batch_id) if run.batch_id else None
    if batch is None and campaign:
        batch = db.scalars(
            select(ProcessingBatch)
            .where(ProcessingBatch.campaign_id == run.campaign_id)
            .order_by(ProcessingBatch.created_at.desc())
        ).first()

    if batch is not None:
        for job in batch.jobs:
            submitted_files.append(job.original_filename)
            if job.status == JobStatus.FAILED:
                held_files.append({
                    "id": job.id,
                    "filename": job.original_filename,
                    "reason": held_reason(job),
                    "action": held_action(job),
                    # A job with no attempts allowed was rejected at the door
                    # — the wrong file type, or too big. Trying it again would
                    # fail identically, so the screen must not offer to.
                    "can_retry": job.max_attempts > 0,
                })
            elif job.requires_review:
                flagged_files.append({
                    "id": job.id,
                    "filename": job.original_filename,
                    "note": held_reason(job),
                    "merged": job.status == JobStatus.DUPLICATE,
                })

    return {
        "contract_version": CONTRACT_VERSION,
        "run_id": run.id,
        "short_id": run.short_id,
        "campaign_id": run.campaign_id,
        "rubric_version_id": run.rubric_version_id,
        "status": run.status.value,
        "count": len(results),
        "submitted_count": len(submitted_files) or run.total_candidates,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "campaign": {
            "title": campaign.job_title if campaign else "",
            "name": campaign.name if campaign else "",
            "site": (campaign.location if campaign else "") or "",
            "vacancies": (campaign.vacancies if campaign else 1) or 1,
            "status": campaign.status.value if campaign else "",
        },
        "submitted_files": submitted_files,
        "held_files": held_files,
        "flagged_files": flagged_files,
        "results": results,
    }


@router.get("/api/runs")
def list_runs(
    limit: int = Query(20, ge=1, le=100),
    campaign_id: str | None = None,
    db: Session = Depends(get_db),
):
    """
    Recent runs, newest first. The Campaigns board reads `runs[0]` when no
    run id is supplied, so ordering is part of the contract.
    """
    statement = select(EvaluationRun).order_by(EvaluationRun.created_at.desc())
    if campaign_id:
        statement = statement.where(EvaluationRun.campaign_id == campaign_id)
    runs = db.scalars(statement.limit(limit)).all()
    return {
        "contract_version": CONTRACT_VERSION,
        "runs": [serialize_run(db, run) for run in runs],
    }


@router.get("/api/runs/{run_id}")
def get_run(run_id: str, db: Session = Depends(get_db)):
    run = db.get(EvaluationRun, run_id)
    if run is None:
        # Unlike the in-memory implementation this replaces, a missing run
        # now genuinely means "no such run", not "the API restarted".
        raise _api_error(404, "RUN_NOT_FOUND", "This assessment run is no longer available.")
    return serialize_run(db, run)
