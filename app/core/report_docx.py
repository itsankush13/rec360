"""
The Candidate 360 as a Word document.

Why this exists alongside `report_builder.py`, which already renders the same
assessment as a PDF: a hiring manager who wants to add a note, strike a line
or paste a section into their own paperwork cannot do any of that to a PDF.
The PDF is the record; the Word file is the working copy.

The content is deliberately the same in both, in the same order, so that two
people looking at two formats are looking at the same assessment. If you
change what one says, change the other.

The theme follows the client's palette, as the PDF does: maroon headings on
white, with the four-step verdict scale. Colour is defined once here rather
than inherited, because python-docx has no stylesheet to point at.
"""
from __future__ import annotations

import io

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt, RGBColor

MAROON = RGBColor(0x97, 0x1A, 0x3E)
INK = RGBColor(0x2B, 0x26, 0x24)
MUTED = RGBColor(0x6B, 0x62, 0x5C)


def _pct(value) -> str:
    return "Not assessed" if value is None else f"{round(float(value))} out of 100"


def _heading(document, text: str) -> None:
    paragraph = document.add_paragraph()
    run = paragraph.add_run(text.upper())
    run.bold = True
    run.font.size = Pt(9)
    run.font.color.rgb = MAROON
    paragraph.paragraph_format.space_before = Pt(16)
    paragraph.paragraph_format.space_after = Pt(4)


def _body(document, text: str, *, muted: bool = False, size: float = 10.5):
    paragraph = document.add_paragraph()
    run = paragraph.add_run(text)
    run.font.size = Pt(size)
    run.font.color.rgb = MUTED if muted else INK
    paragraph.paragraph_format.space_after = Pt(6)
    return paragraph


def _facts(document, pairs) -> None:
    table = document.add_table(rows=0, cols=2)
    table.style = "Table Grid"
    for label, value in pairs:
        if value in (None, ""):
            continue
        cells = table.add_row().cells
        left = cells[0].paragraphs[0].add_run(str(label))
        left.bold = True
        left.font.size = Pt(9.5)
        right = cells[1].paragraphs[0].add_run(str(value))
        right.font.size = Pt(9.5)


def build_candidate_report_docx(
    *, evaluation, candidate, campaign, criteria, evidence_by_criterion,
    eligibility_findings, challenge_findings=None, rubric_version=None,
    benchmark=None, action=None, document_quality=None,
) -> bytes:
    """
    Render one Candidate 360 as a Word document and return the bytes.

    Takes plain objects rather than a database session, exactly as the PDF
    builder does, so it can be tested without one and so the API layer
    decides what to load.
    """
    document = Document()
    normal = document.styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(10.5)

    name = getattr(candidate, "full_name", "") or "Candidate"
    title = document.add_paragraph()
    run = title.add_run(name)
    run.bold = True
    run.font.size = Pt(20)
    run.font.color.rgb = MAROON
    title.paragraph_format.space_after = Pt(2)

    role = getattr(campaign, "job_title", "") or getattr(campaign, "name", "")
    _body(document, f"Assessed for {role}" if role else "Candidate assessment",
          muted=True, size=10)

    # The disclaimer sits above everything, not in a footnote. It is the
    # client's first requirement, and this is the copy most likely to be
    # forwarded to somebody who never saw the screen.
    warning = document.add_paragraph()
    warning_run = warning.add_run(
        "This is a decision-support assessment, not a hiring decision. "
        "Every score below is traceable to a line in the candidate's CV. "
        "A person makes the decision."
    )
    warning_run.bold = True
    warning_run.font.size = Pt(10)
    warning.paragraph_format.space_before = Pt(10)
    warning.paragraph_format.space_after = Pt(10)

    _heading(document, "Recommendation")
    recommendation = getattr(evaluation, "recommendation", None)
    _facts(document, [
        ("Recommendation", getattr(recommendation, "value", recommendation) or "Not assessed"),
        ("Overall score", _pct(getattr(evaluation, "overall_score", None))),
        ("Confidence", _pct(
            (getattr(evaluation, "overall_confidence", None) or 0) * 100
            if getattr(evaluation, "overall_confidence", None) is not None else None
        )),
        ("Eligibility", getattr(
            getattr(evaluation, "eligibility_status", None), "value", None
        ) or "Not assessed"),
        ("Rubric version", getattr(rubric_version, "version_number", None)),
    ])

    if document_quality:
        _heading(document, "How this CV was read")
        _body(document, document_quality.get("summary", ""))
        _body(document, document_quality.get("effect_on_assessment", ""), muted=True, size=9.5)

    if getattr(evaluation, "next_action_reason", ""):
        _heading(document, "Recommended next step")
        _body(document, evaluation.next_action_reason)

    strengths = getattr(evaluation, "strengths", None) or []
    if strengths:
        _heading(document, "Strengths")
        for item in strengths:
            document.add_paragraph(
                item if isinstance(item, str) else item.get("text", ""),
                style="List Bullet",
            )

    gaps = getattr(evaluation, "gaps", None) or []
    if gaps:
        _heading(document, "Material gaps and risks")
        for item in gaps:
            document.add_paragraph(
                item if isinstance(item, str) else item.get("text", ""),
                style="List Bullet",
            )

    if eligibility_findings:
        _heading(document, "Eligibility checks")
        for finding in eligibility_findings:
            _body(document, "· " + (getattr(finding, "summary", "") or ""), size=10)

    _heading(document, "Scores by criterion, with evidence")
    for criterion in criteria or []:
        label = getattr(criterion, "label", "") or getattr(criterion, "name", "")
        line = document.add_paragraph()
        head = line.add_run(f"{label} — {_pct(getattr(criterion, 'raw_score', None))}")
        head.bold = True
        head.font.size = Pt(10.5)
        line.paragraph_format.space_before = Pt(10)
        line.paragraph_format.space_after = Pt(2)

        if getattr(criterion, "rationale", ""):
            _body(document, criterion.rationale, size=10)

        for item in (evidence_by_criterion or {}).get(
            getattr(criterion, "id", None), []
        ):
            quote = getattr(item, "quote", "") or getattr(item, "text", "")
            page = getattr(item, "page_number", None)
            section = getattr(item, "section", "") or ""
            where = (f"page {page}" if page else section) or "in the CV"
            _body(document, f"“{quote}” — {where}", muted=True, size=9.5)

    if challenge_findings:
        _heading(document, "Challenge findings")
        for finding in challenge_findings:
            _body(document, "· " + (getattr(finding, "summary", "") or ""), size=10)

    missing = getattr(evaluation, "missing_information", None) or []
    if missing:
        _heading(document, "Missing or ambiguous information")
        for item in missing:
            document.add_paragraph(
                item if isinstance(item, str) else item.get("text", ""),
                style="List Bullet",
            )

    if action is not None:
        _heading(document, "Recruiter decision on file")
        _facts(document, [
            ("Decision", getattr(getattr(action, "disposition", None), "value", None)),
            ("By", getattr(action, "actor", "")),
            ("Reason", getattr(action, "reason", "")),
        ])

    footer = document.add_paragraph()
    footer_run = footer.add_run(
        "Scores come from the approved rubric for this campaign. "
        "The system recommends; a person decides."
    )
    footer_run.font.size = Pt(8.5)
    footer_run.font.color.rgb = MUTED
    footer.alignment = WD_ALIGN_PARAGRAPH.LEFT
    footer.paragraph_format.space_before = Pt(18)

    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()
