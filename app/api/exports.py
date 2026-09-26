"""
Phase H routes — Candidate 360 PDF, and shortlist export for the ATS.

Every export is an audited event. `AuditAction.EXPORTED` has existed since
Phase F for this: who took candidate data out of the system, when, and for
which campaign is exactly the kind of question an audit asks, and it cannot
be reconstructed after the fact.

There is no "send to SuccessFactors" endpoint here. Whether the handover is
a live API call or a file their team imports is undecided and needs the
client's HRIS owner. Shipping a button that posts to a tenant nobody has
agreed on would be worse than shipping the file — and both routes consume
the same field-mapped record, so nothing here is wasted when that decision
lands.
"""
from __future__ import annotations

import io
import zipfile

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import (
    ats_export, candidate_360, document_quality, report_builder, report_docx,
    storage,
)
from app.db.models import (
    ActionType, AuditAction, Campaign, Candidate, CandidateAction,
    CandidateDocument, ChallengeFinding, Disposition, EligibilityFinding,
    Evaluation, EvaluationCriterion, EvaluationEvidence, EvaluationStatus,
    RubricVersion,
)
from app.db.session import get_db
from app.services import campaign_service, disposition_service

router = APIRouter(tags=["exports"])


def _safe_filename(text: str, fallback: str) -> str:
    cleaned = "".join(c if c.isalnum() or c in "-_ " else "" for c in (text or "")).strip()
    return (cleaned.replace(" ", "-").lower() or fallback)[:60]


def _require_campaign(db: Session, campaign_id: str) -> Campaign:
    campaign = campaign_service.get_campaign(db, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign


def _current_action(db: Session, candidate_id: str) -> CandidateAction | None:
    return disposition_service.current_action(db, candidate_id)


# ---------------------------------------------------------------------------
# Candidate 360 — PDF
# ---------------------------------------------------------------------------

def _report_inputs(db: Session, evaluation_id: str) -> dict:
    """
    Everything one Candidate 360 report needs, loaded once.

    Both report formats render the same assessment, so they must not load it
    two different ways — a PDF and a Word file that disagree would be worse
    than having only one of them.
    """
    evaluation = db.get(Evaluation, evaluation_id)
    if evaluation is None:
        raise HTTPException(status_code=404, detail="Assessment not found")

    candidate = db.get(Candidate, evaluation.candidate_id)
    campaign = db.get(Campaign, evaluation.campaign_id)
    version = db.get(RubricVersion, evaluation.rubric_version_id)
    document = (db.get(CandidateDocument, evaluation.document_id)
                if evaluation.document_id else None)

    criteria = list(db.scalars(
        select(EvaluationCriterion)
        .where(EvaluationCriterion.evaluation_id == evaluation.id)
        .order_by(EvaluationCriterion.display_order)
    ).all())

    evidence_by_criterion: dict[str, list] = {}
    for item in db.scalars(
        select(EvaluationEvidence)
        .where(EvaluationEvidence.evaluation_id == evaluation.id)
        .order_by(EvaluationEvidence.relevance.desc())
    ).all():
        evidence_by_criterion.setdefault(item.criterion_id, []).append(item)

    findings = list(db.scalars(
        select(EligibilityFinding)
        .where(EligibilityFinding.evaluation_id == evaluation.id)
        .order_by(EligibilityFinding.display_order)
    ).all())

    challenge = list(db.scalars(
        select(ChallengeFinding)
        .where(
            ChallengeFinding.run_id == evaluation.run_id,
            (ChallengeFinding.evaluation_id == evaluation.id)
            | (ChallengeFinding.evaluation_id.is_(None)),
        )
        .order_by(ChallengeFinding.display_order)
    ).all())

    scores = list(db.scalars(
        select(Evaluation.overall_score).where(
            Evaluation.campaign_id == evaluation.campaign_id,
            Evaluation.is_current.is_(True),
            Evaluation.status == EvaluationStatus.COMPLETED,
        )
    ).all())

    return {
        "evaluation": evaluation,
        "candidate": candidate,
        "campaign": campaign,
        "criteria": criteria,
        "evidence_by_criterion": evidence_by_criterion,
        "eligibility_findings": findings,
        "challenge_findings": challenge,
        "rubric_version": version,
        "benchmark": {
            "position": candidate_360.percentile_of(evaluation.overall_score, scores),
            "benchmarks": candidate_360.benchmarks(scores),
        },
        "action": _current_action(db, evaluation.candidate_id),
        "document": document,
    }


def _record_export(db: Session, inputs: dict, file_format: str) -> None:
    candidate = inputs["candidate"]
    evaluation = inputs["evaluation"]
    disposition_service.record_audit(
        db, AuditAction.EXPORTED,
        campaign_id=evaluation.campaign_id,
        candidate_id=evaluation.candidate_id,
        entity_type="evaluation", entity_id=evaluation.id,
        summary=f"Candidate assessment sent as "
                f"{'a Word document' if file_format == 'docx' else 'a PDF'} for "
                f"{getattr(candidate, 'full_name', 'a candidate')}",
        after={"format": file_format},
    )
    db.commit()


@router.get("/api/evaluations/{evaluation_id}/cv")
def candidate_cv(evaluation_id: str, db: Session = Depends(get_db)):
    """
    The candidate's original CV, as they sent it.

    Candidate 360 quotes lines from the CV with a page or section reference,
    and a recruiter reading a quote will eventually want to see it in place —
    especially now that a scanned CV is read by character recognition, where
    the quoted words are an approximation of what is on the page. Being able
    to open the original is what makes "check the evidence before deciding"
    something a person can actually do.

    Served by evaluation id, never by a path from the request. `storage_path`
    is an opaque key the system wrote; letting a caller name a file is how a
    document endpoint turns into a way to read anything on the disk.
    """
    evaluation = db.get(Evaluation, evaluation_id)
    if evaluation is None:
        raise HTTPException(status_code=404, detail="Assessment not found")

    document = (db.get(CandidateDocument, evaluation.document_id)
                if evaluation.document_id else None)
    if document is None or not document.storage_path:
        raise HTTPException(
            status_code=404,
            detail="The original CV for this assessment is no longer on file.",
        )

    try:
        payload = storage.read(document.storage_path)
    except storage.StorageError:
        # The row survived and the file did not — retention, a purge, a
        # restored database. Say so plainly rather than returning a 500 that
        # reads like the whole screen is broken.
        raise HTTPException(
            status_code=404,
            detail="The original CV for this assessment is no longer on file.",
        ) from None

    filename = _safe_filename(
        getattr(document, "original_filename", "") or "cv",
        "cv",
    )
    extension = (document.extension or "").lstrip(".").lower() or "pdf"
    return Response(
        content=payload,
        media_type=document.content_type or "application/octet-stream",
        headers={
            # inline, not attachment: the point is to look at it next to the
            # assessment, not to collect another copy of a file the recruiter
            # already has.
            "Content-Disposition": f'inline; filename="{filename}.{extension}"',
        },
    )


@router.get("/api/evaluations/{evaluation_id}/report.pdf")
def candidate_report(evaluation_id: str, db: Session = Depends(get_db)):
    """
    The full Candidate 360 as a PDF.

    A print of what the screen shows, including the quoted evidence with its
    page and section references — a PDF is what gets forwarded to a hiring
    manager who never saw the screen, so it carries the disclaimer and the
    provenance rather than only the score.
    """
    inputs = _report_inputs(db, evaluation_id)
    inputs.pop("document", None)

    try:
        pdf = report_builder.build_candidate_report(**inputs)
    except Exception as exc:  # a broken report must not look like a missing one
        raise HTTPException(
            status_code=500,
            detail=f"The report could not be produced: {exc.__class__.__name__}",
        ) from exc

    _record_export(db, {**inputs, "candidate": inputs["candidate"]}, "pdf")

    name = _safe_filename(getattr(inputs["candidate"], "full_name", ""), "candidate")
    return Response(
        content=pdf, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{name}-assessment.pdf"'},
    )


@router.get("/api/evaluations/{evaluation_id}/report.docx")
def candidate_report_docx(evaluation_id: str, db: Session = Depends(get_db)):
    """
    The same Candidate 360 as a Word document.

    The PDF is the record; this is the working copy. A hiring manager who
    wants to add a note, strike a line, or paste a section into their own
    paperwork cannot do any of that to a PDF.
    """
    inputs = _report_inputs(db, evaluation_id)
    document = inputs.pop("document", None)

    try:
        payload = report_docx.build_candidate_report_docx(
            **inputs,
            document_quality=document_quality.describe(document),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"The report could not be produced: {exc.__class__.__name__}",
        ) from exc

    _record_export(db, inputs, "docx")

    name = _safe_filename(getattr(inputs["candidate"], "full_name", ""), "candidate")
    return Response(
        content=payload,
        media_type=(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
        headers={"Content-Disposition": f'attachment; filename="{name}-assessment.docx"'},
    )


# One name per candidate per zip, even when two candidates share a name.
def _dedupe_filename(name: str, seen: dict[str, int]) -> str:
    count = seen.get(name, 0)
    seen[name] = count + 1
    return name if count == 0 else f"{name}-{count + 1}"


def build_shortlist_zip(
    db: Session, campaign: Campaign, format: str = "pdf",
) -> tuple[str, bytes, int] | None:
    """
    Every shortlisted candidate's Candidate 360 report, as one PDF or Word
    zip. Shared by the download route below and the hiring-manager email
    route in `app/api/reports.py` — one implementation, two callers.

    Zipped under one named folder ("Shortlisted Candidates PDF" or
    "...Word") so the files land somewhere recognisable once extracted,
    rather than loose at the top of the archive. Only candidates a recruiter
    has actually shortlisted (`Disposition.SHORTLIST`) are included — the
    same "a person decides" rule `_export_records`'s `decided_only` already
    applies to the spreadsheet export.

    Returns None when nothing is shortlisted, rather than raising — a caller
    that must still act (send an email with no attachment) should not have
    to catch an exception to find that out.
    """
    records = _export_records(db, campaign, decided_only=True)
    shortlisted = [
        record for record in records
        if record["action"] is not None and record["action"].disposition == Disposition.SHORTLIST
    ]
    if not shortlisted:
        return None

    folder = "Shortlisted Candidates PDF" if format == "pdf" else "Shortlisted Candidates Word"
    extension = "pdf" if format == "pdf" else "docx"
    seen: dict[str, int] = {}
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for record in shortlisted:
            evaluation_id = record["evaluation"].id
            inputs = _report_inputs(db, evaluation_id)
            try:
                if format == "pdf":
                    build_inputs = {k: v for k, v in inputs.items() if k != "document"}
                    payload = report_builder.build_candidate_report(**build_inputs)
                else:
                    document = inputs.pop("document", None)
                    payload = report_docx.build_candidate_report_docx(
                        **inputs, document_quality=document_quality.describe(document),
                    )
            except Exception as exc:  # a broken report must not silently vanish from the zip
                raise HTTPException(
                    status_code=500,
                    detail=f"The report could not be produced: {exc.__class__.__name__}",
                ) from exc
            _record_export(db, inputs, format)
            name = _dedupe_filename(
                _safe_filename(getattr(inputs["candidate"], "full_name", ""), "candidate"), seen,
            )
            archive.writestr(f"{folder}/{name}-assessment.{extension}", payload)

    zip_name = _safe_filename(campaign.job_title or campaign.name, "shortlist")
    filename = f"{zip_name}-shortlisted-{extension}.zip"
    return filename, buffer.getvalue(), len(shortlisted)


@router.get("/api/campaigns/{campaign_id}/reports.zip")
def shortlisted_reports_zip(
    campaign_id: str,
    format: str = Query("pdf", pattern="^(pdf|docx)$"),
    actor: str = Query(""),
    db: Session = Depends(get_db),
):
    """
    Download endpoint for `build_shortlist_zip` — the decisions screen's
    per-candidate download links, bundled, so a recruiter with a real
    shortlist does not click ten separate downloads.
    """
    campaign = _require_campaign(db, campaign_id)
    result = build_shortlist_zip(db, campaign, format=format)
    if result is None:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "No candidate has been shortlisted yet. Shortlist "
                           "at least one candidate first.",
                "errors": [],
            },
        )
    filename, payload, count = result

    _audit_export(db, campaign, f"{format}-zip", count, actor)
    return Response(
        content=payload,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# Shortlist export
# ---------------------------------------------------------------------------

def _export_records(db: Session, campaign: Campaign, decided_only: bool) -> list[dict]:
    evaluations = list(db.scalars(
        select(Evaluation)
        .where(
            Evaluation.campaign_id == campaign.id,
            Evaluation.is_current.is_(True),
            Evaluation.status == EvaluationStatus.COMPLETED,
        )
        .order_by(Evaluation.overall_score.desc())
    ).all())

    records: list[dict] = []
    for evaluation in evaluations:
        action = _current_action(db, evaluation.candidate_id)
        if decided_only and (action is None or action.action_type == ActionType.COMMENT):
            continue
        evidence = list(db.scalars(
            select(EvaluationEvidence)
            .where(EvaluationEvidence.evaluation_id == evaluation.id)
            .order_by(EvaluationEvidence.relevance.desc())
            .limit(3)
        ).all())
        records.append({
            "evaluation": evaluation,
            "candidate": db.get(Candidate, evaluation.candidate_id),
            "campaign": campaign,
            "document": (db.get(CandidateDocument, evaluation.document_id)
                         if evaluation.document_id else None),
            "action": action,
            "rubric_version": db.get(RubricVersion, evaluation.rubric_version_id),
            "evidence": evidence,
        })
    return records


def _audit_export(db: Session, campaign: Campaign, fmt: str, count: int, actor: str) -> None:
    disposition_service.record_audit(
        db, AuditAction.EXPORTED,
        campaign_id=campaign.id, entity_type="campaign", entity_id=campaign.id,
        summary=f"{count} candidate record(s) exported as {fmt.upper()}",
        after={"format": fmt, "candidates": count},
        actor=actor,
    )
    db.commit()


@router.get("/api/campaigns/{campaign_id}/export.csv")
def export_csv(
    campaign_id: str,
    decided_only: bool = Query(
        True,
        description=(
            "Only candidates a recruiter has decided on. Exporting an "
            "unreviewed ranking would make the AI's ordering the operative "
            "decision, which this system is explicitly not for."
        ),
    ),
    actor: str = Query(""),
    db: Session = Depends(get_db),
):
    campaign = _require_campaign(db, campaign_id)
    records = _export_records(db, campaign, decided_only)
    if not records:
        raise HTTPException(
            status_code=422,
            detail={
                "message": (
                    "There is nothing to export yet. Record a decision on at "
                    "least one candidate first, or set decided_only=false to "
                    "export the full assessed list."
                ),
                "errors": [],
            },
        )

    payload = ats_export.to_csv(ats_export.build_rows(records))
    _audit_export(db, campaign, "csv", len(records), actor)
    name = _safe_filename(campaign.job_title or campaign.name, "shortlist")
    return Response(
        content=payload, media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}-shortlist.csv"'},
    )


@router.get("/api/campaigns/{campaign_id}/export.xlsx")
def export_xlsx(
    campaign_id: str,
    decided_only: bool = Query(True),
    actor: str = Query(""),
    db: Session = Depends(get_db),
):
    """
    Workbook with the shortlist and the SuccessFactors field mapping on a
    second sheet, so whoever imports it knows which column goes where.
    """
    campaign = _require_campaign(db, campaign_id)
    records = _export_records(db, campaign, decided_only)
    if not records:
        raise HTTPException(
            status_code=422,
            detail={
                "message": (
                    "There is nothing to export yet. Record a decision on at "
                    "least one candidate first, or set decided_only=false to "
                    "export the full assessed list."
                ),
                "errors": [],
            },
        )

    payload = ats_export.to_xlsx(ats_export.build_rows(records), campaign=campaign)
    _audit_export(db, campaign, "xlsx", len(records), actor)
    name = _safe_filename(campaign.job_title or campaign.name, "shortlist")
    return Response(
        content=payload,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{name}-shortlist.xlsx"'},
    )


@router.get("/api/exports/ats/field-mapping")
def field_mapping():
    """
    The SuccessFactors field mapping, as data.

    Exposed so the Decision screen renders the same mapping the export
    actually uses, rather than a hand-maintained copy that can drift.
    """
    return {
        "ats": "SAP SuccessFactors Recruiting",
        "integration": "file",
        "note": (
            "Export is file-based. A live API integration needs a sandbox "
            "tenant, OData credentials and an approved OAuth client, and has "
            "not been agreed. Both routes use this same mapping."
        ),
        "fields": [
            {"our_field": ours, "successfactors_field": theirs, "note": note}
            for ours, theirs, note in ats_export.FIELD_MAP
        ],
    }
