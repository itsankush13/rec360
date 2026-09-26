"""
Shortlist export — CSV, XLSX, and an SAP SuccessFactors field mapping.

The client's ATS is SAP SuccessFactors Recruiting. Whether the handover is a
live API call or a file their team imports has not been decided, and it needs
their HRIS owner: a real integration wants a sandbox tenant, OData
credentials and an OAuth client approved by their IT, which is a
calendar-weeks item rather than a code one.

Both routes need exactly the same thing first — a field-mapped candidate
record. That is what this module produces. If the decision later goes to a
live integration, this mapping is the payload; if it stays file-based, it is
the import. Nothing here is wasted either way, which is why it is worth
building before the decision rather than after.

The mapping below is the one already printed on the Decision screen under
"See the field mapping", so the software and the design agree.

Deliberate choices:

  * **Only dispositioned candidates are exported by default.** Sending an
    unreviewed ranking to an ATS would make the AI's ordering the operative
    decision, which is the thing the client explicitly said must not happen.
  * **The AI recommendation and any recruiter override are separate
    columns.** Collapsing them would lose the fact that a person disagreed,
    which is the single most important thing in the record.
  * **No CV file is attached.** The documents are retained under
    STORAGE_ROOT and a real integration would attach them; a CSV cannot, and
    pretending otherwise in the column set would mislead.
"""
from __future__ import annotations

import csv
import io
from datetime import datetime, timezone

# Our field -> SuccessFactors field. Mirrors the table in web/decisions.html.
FIELD_MAP: list[tuple[str, str, str]] = [
    # (our column, SuccessFactors field, note shown in the mapping sheet)
    ("candidate_name", "Candidate Full Name", ""),
    ("email", "Email", ""),
    ("phone", "Phone", ""),
    ("location", "Address / Location", ""),
    ("requisition_id", "Requisition ID", "The campaign reference"),
    ("requisition_title", "Requisition Title", ""),
    ("recruiter_recommendation", "Recruiter Recommendation",
     "The recruiter's decision, not the AI's"),
    ("ai_assessment", "Candidate Notes",
     "The AI recommendation, recorded alongside the decision"),
    ("overall_score", "Candidate Notes", "Out of 100, against the approved rubric"),
    ("confidence", "Candidate Notes", "How far the assessment can be relied on"),
    ("eligibility", "National ID / Residency Status",
     "Whether the mandatory rules were met"),
    ("years_experience", "Total Years of Experience", ""),
    ("evidence_summary", "Candidate Notes", "What the score was read from"),
    ("assessed_on", "Candidate Notes", ""),
    ("rubric_version", "Candidate Notes", "Which rubric produced this"),
    ("cv_filename", "Attachment", "The file itself is not carried in a CSV"),
]

COLUMNS = [ours for ours, _, _ in FIELD_MAP]

DISPOSITION_WORDS = {
    "SHORTLIST": "Shortlisted", "REJECT": "Not taken forward", "HOLD": "On hold",
    "REQUEST_REVIEW": "Sent for review", "INTERVIEW": "Invited to interview",
}
RECOMMENDATION_WORDS = {
    "STRONG_FIT": "Strong fit", "POTENTIAL_FIT": "Potential fit",
    "REVIEW_REQUIRED": "Review required", "NOT_RECOMMENDED": "Not recommended",
}
ELIGIBILITY_WORDS = {
    "ELIGIBLE": "Meets the mandatory rules",
    "DISQUALIFIED": "Does not meet a mandatory rule",
    "REVIEW_REQUIRED": "Could not be verified from the CV",
}


def _enum(value) -> str:
    return getattr(value, "value", value) or ""


def build_rows(records) -> list[dict]:
    """
    Turn export records into flat rows.

    Each record is a dict with keys: evaluation, candidate, campaign,
    document, action, rubric_version, evidence (a short list of excerpts).
    """
    rows: list[dict] = []
    for record in records:
        evaluation = record["evaluation"]
        candidate = record.get("candidate")
        campaign = record.get("campaign")
        action = record.get("action")
        document = record.get("document")
        version = record.get("rubric_version")

        ai = RECOMMENDATION_WORDS.get(_enum(evaluation.recommendation), "")
        decision = ""
        if action is not None:
            if getattr(action, "overridden_to", None):
                decision = RECOMMENDATION_WORDS.get(_enum(action.overridden_to), "")
            elif getattr(action, "disposition", None):
                decision = DISPOSITION_WORDS.get(_enum(action.disposition), "")

        excerpts = record.get("evidence") or []
        summary = " | ".join(
            f'"{e.excerpt[:140]}"'
            + (f" (CV page {e.page_number})" if e.page_number is not None
               else (f" ({e.section.title()})" if e.section else ""))
            for e in excerpts[:3]
        )

        rows.append({
            "candidate_name": getattr(candidate, "full_name", "") or "",
            "email": getattr(candidate, "email", "") or "",
            "phone": getattr(candidate, "phone", "") or "",
            "location": getattr(candidate, "location", "") or "",
            "requisition_id": getattr(campaign, "id", "") or "",
            "requisition_title": getattr(campaign, "job_title", "")
                                 or getattr(campaign, "name", "") or "",
            "recruiter_recommendation": decision or "Not yet decided",
            "ai_assessment": ai,
            "overall_score": round(float(evaluation.overall_score or 0), 1),
            "confidence": f"{float(evaluation.overall_confidence or 0) * 100:.0f}%",
            "eligibility": ELIGIBILITY_WORDS.get(
                _enum(evaluation.eligibility_status), ""),
            "years_experience": evaluation.experience_years_total,
            "evidence_summary": summary,
            "assessed_on": (evaluation.created_at.strftime("%Y-%m-%d")
                            if getattr(evaluation, "created_at", None) else ""),
            "rubric_version": (f"v{version.version_number}" if version else ""),
            "cv_filename": getattr(document, "original_filename", "") or "",
        })
    return rows


def to_csv(rows: list[dict]) -> bytes:
    """UTF-8 with BOM, because Excel on Windows mangles accented names without it."""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return buffer.getvalue().encode("utf-8-sig")


def to_xlsx(rows: list[dict], *, campaign=None) -> bytes:
    """
    Workbook with two sheets: the shortlist, and the field mapping.

    The mapping sheet ships with the data deliberately — whoever imports this
    into SuccessFactors needs to know which column goes where, and a separate
    document would get separated.
    """
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    maroon = PatternFill("solid", fgColor="971A3E")
    sand = PatternFill("solid", fgColor="F7F3ED")
    header_font = Font(bold=True, color="FFFFFF", size=10)

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Shortlist"

    title = (getattr(campaign, "job_title", None)
             or getattr(campaign, "name", None) or "Shortlist")
    sheet.append([f"{title} — candidate export"])
    sheet.append([
        "AI recommends; a person decides. The recruiter decision column is the "
        "operative one; the AI assessment is recorded beside it."
    ])
    sheet.append([])
    sheet.append([c.replace("_", " ").title() for c in COLUMNS])

    for cell in sheet[4]:
        cell.fill = maroon
        cell.font = header_font
        cell.alignment = Alignment(vertical="center", wrap_text=True)
    sheet["A1"].font = Font(bold=True, size=13, color="6E1030")
    sheet["A2"].font = Font(italic=True, size=9, color="8A817C")

    for row in rows:
        sheet.append([row.get(c, "") for c in COLUMNS])

    widths = {"candidate_name": 26, "email": 28, "evidence_summary": 70,
              "requisition_id": 38, "requisition_title": 26, "location": 20,
              "recruiter_recommendation": 20, "ai_assessment": 18, "eligibility": 30}
    for index, column in enumerate(COLUMNS, start=1):
        sheet.column_dimensions[get_column_letter(index)].width = widths.get(column, 14)
    sheet.freeze_panes = "A5"

    mapping = workbook.create_sheet("Field mapping")
    mapping.append(["Our field", "SAP SuccessFactors field", "Note"])
    for cell in mapping[1]:
        cell.fill = maroon
        cell.font = header_font
    for ours, theirs, note in FIELD_MAP:
        mapping.append([ours.replace("_", " ").title(), theirs, note])
    for index, width in enumerate((28, 34, 52), start=1):
        mapping.column_dimensions[get_column_letter(index)].width = width
    for row in mapping.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")
            cell.fill = sand

    mapping.append([])
    mapping.append([
        "Generated " + datetime.now(timezone.utc).strftime("%d %B %Y, %H:%M UTC")
        + ". The CV file itself is not carried in a spreadsheet; a live "
          "integration would attach it."
    ])

    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()
