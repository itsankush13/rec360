"""
Candidate 360 report — PDF.

`app/core/report_generator.py` already builds PDFs, and the brief says to
reuse rather than rebuild. It is not reused here, for two reasons worth
stating rather than burying:

  * It renders in a dark navy and teal scheme. The client's delivered design
    is maroon on sand, and a report that does not match the screens it came
    from reads as someone else's software.
  * It consumes the legacy `CandidateScore` shape — five hardcoded
    dimensions, no evidence, no eligibility, no confidence. The Candidate 360
    the client specified has sixteen sections, and twelve of them do not
    exist in that shape.

Its reportlab conventions are followed closely; the palette and the data
model are not. The old module stays on disk for the legacy pipeline.

The report is a faithful print of what the screen shows. In particular it
carries the evidence excerpts with their page and section references, the
eligibility findings, the Challenge Agent's concerns, and the statement that
a person decides — because a PDF is what gets forwarded, printed and put in
front of a hiring manager who never saw the screen.
"""
from __future__ import annotations

import io
from datetime import datetime, timezone

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table,
    TableStyle,
)

# The client's palette, taken from web/assets/app.css so the report and the
# screens cannot drift apart.
SAND = colors.HexColor("#F7F3ED")
SAND_2 = colors.HexColor("#EFE8DE")
HAIR = colors.HexColor("#E5DCCE")
MAROON = colors.HexColor("#971A3E")
MAROON_DEEP = colors.HexColor("#6E1030")
MAROON_SOFT = colors.HexColor("#F6E8EC")
GOLD = colors.HexColor("#B8924E")
INK = colors.HexColor("#231F20")
INK_2 = colors.HexColor("#5A5350")
INK_3 = colors.HexColor("#8A817C")

# The four-step ordinal verdict scale. Deliberately not a traffic light —
# the stylesheet says so, and the report honours the same decision.
VERDICT = {
    "STRONG_FIT": ("Strong fit", colors.HexColor("#1F6F52")),
    "POTENTIAL_FIT": ("Potential fit", colors.HexColor("#3E6E8E")),
    "REVIEW_REQUIRED": ("Review required", GOLD),
    "NOT_RECOMMENDED": ("Not recommended", MAROON),
}

OUTCOME_WORDS = {
    "CONFIRMED_MATCH": "Confirmed",
    "PARTIAL_MATCH": "Partial or adjacent match",
    "NOT_DEMONSTRATED": "Not shown in the CV",
    "CONTRADICTORY_EVIDENCE": "CV contradicts this",
    "INSUFFICIENT_EVIDENCE": "Not enough in the CV to judge",
}

NEXT_ACTION_WORDS = {
    "INTERVIEW": "Invite to interview",
    "MANUAL_REVIEW": "Read this assessment before relying on it",
    "REQUEST_EVIDENCE": "Ask the candidate for the missing detail",
    "CONFIRM_ELIGIBILITY": "Confirm the unverified conditions first",
    "REJECT": "Do not take forward",
}

SEVERITY_WORDS = {"HIGH": "Significant", "MEDIUM": "Worth checking",
                  "LOW": "Minor", "INFO": "Note"}


def _styles() -> dict:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("t", parent=base["Title"], fontName="Helvetica-Bold",
                                fontSize=22, leading=26, textColor=colors.white,
                                alignment=TA_LEFT, spaceAfter=2),
        "kicker": ParagraphStyle("k", fontName="Helvetica", fontSize=8.5, leading=12,
                                 textColor=colors.HexColor("#E8C9D3"), spaceAfter=6),
        "lede": ParagraphStyle("l", fontName="Helvetica", fontSize=10, leading=15,
                               textColor=colors.white),
        "h2": ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=12.5, leading=16,
                             textColor=MAROON_DEEP, spaceBefore=16, spaceAfter=6),
        "body": ParagraphStyle("b", fontName="Helvetica", fontSize=9.5, leading=14,
                               textColor=INK_2),
        "small": ParagraphStyle("s", fontName="Helvetica", fontSize=8, leading=11,
                                textColor=INK_3),
        "quote": ParagraphStyle("q", fontName="Helvetica-Oblique", fontSize=9,
                                leading=13.5, textColor=INK,
                                leftIndent=10, spaceAfter=2),
        "cite": ParagraphStyle("c", fontName="Helvetica-Bold", fontSize=7.5, leading=10,
                               textColor=MAROON, leftIndent=10, spaceAfter=8),
        "cell": ParagraphStyle("cl", fontName="Helvetica", fontSize=8.5, leading=11.5,
                               textColor=INK_2, wordWrap="CJK"),
        "cellb": ParagraphStyle("cb", fontName="Helvetica-Bold", fontSize=8.5,
                                leading=11.5, textColor=INK, wordWrap="CJK"),
    }


def _escape(text) -> str:
    return (str(text or "").replace("&", "&amp;")
            .replace("<", "&lt;").replace(">", "&gt;"))


def _pct(value) -> str:
    return f"{float(value or 0):.0f}"


def _banner(story, styles, evaluation, candidate, campaign) -> None:
    label, _ = VERDICT.get(
        getattr(evaluation.recommendation, "value", evaluation.recommendation),
        ("Review required", GOLD),
    )
    band = getattr(evaluation.confidence_band, "value", evaluation.confidence_band)
    name = _escape(getattr(candidate, "full_name", "") or "Candidate")
    role = _escape(getattr(campaign, "job_title", "") or getattr(campaign, "name", ""))
    site = _escape(getattr(campaign, "location", "") or "")

    left = [
        Paragraph(f"{_pct(evaluation.overall_score)}", ParagraphStyle(
            "score", fontName="Helvetica-Bold", fontSize=40, leading=42,
            textColor=colors.white, alignment=1)),
        Paragraph("out of 100", ParagraphStyle(
            "of", fontName="Helvetica", fontSize=7.5, leading=10,
            textColor=colors.HexColor("#E8C9D3"), alignment=1)),
    ]
    right = [
        Paragraph(role.upper() + (f" &nbsp;·&nbsp; {site.upper()}" if site else ""),
                  styles["kicker"]),
        Paragraph(name, styles["title"]),
        Spacer(1, 5),
        Paragraph(
            f"{label} &nbsp;·&nbsp; {_pct(evaluation.mandatory_score)} of 100 on the "
            f"mandatory criteria &nbsp;·&nbsp; {band.lower()} confidence",
            styles["lede"]),
    ]
    table = Table([[left, right]], colWidths=[3.4 * cm, 12.6 * cm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), MAROON),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 14),
        ("RIGHTPADDING", (0, 0), (-1, -1), 14),
        ("TOPPADDING", (0, 0), (-1, -1), 16),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 16),
    ]))
    story.append(table)
    story.append(Spacer(1, 10))


def _kv_row(styles, pairs) -> Table:
    cells, widths = [], []
    for key, value in pairs:
        cells.append([
            Paragraph(_escape(key).upper(), styles["small"]),
            Paragraph(f"<b>{_escape(value)}</b>", styles["cellb"]),
        ])
        widths.append(16.0 / max(1, len(pairs)) * cm)
    table = Table([[c[0] for c in cells], [c[1] for c in cells]], colWidths=widths)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), SAND),
        ("LINEBELOW", (0, 0), (-1, 0), 0, SAND),
        ("BOX", (0, 0), (-1, -1), 0.5, HAIR),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, HAIR),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    return table


def _section(story, styles, heading) -> None:
    story.append(Paragraph(_escape(heading), styles["h2"]))
    story.append(HRFlowable(width="100%", thickness=0.6, color=HAIR,
                            spaceBefore=0, spaceAfter=6))


def build_candidate_report(
    *, evaluation, candidate, campaign, criteria, evidence_by_criterion,
    eligibility_findings, challenge_findings=None, rubric_version=None,
    benchmark=None, action=None,
) -> bytes:
    """
    Render one Candidate 360 as a PDF and return the bytes.

    Takes plain objects rather than a database session so it can be tested
    without one, and so the API layer decides what to load.
    """
    styles = _styles()
    buffer = io.BytesIO()
    document = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=2.5 * cm, rightMargin=2.5 * cm,
        topMargin=1.8 * cm, bottomMargin=2.0 * cm,
        title=f"Candidate assessment — {getattr(candidate, 'full_name', '')}",
        author="Recruitment 360",
    )
    story: list = []

    _banner(story, styles, evaluation, candidate, campaign)

    # The disclaimer sits above everything, not in a footnote. It is the
    # client's first requirement.
    story.append(Paragraph(
        "<b>This is a decision-support assessment, not a hiring decision.</b> "
        "Every score below is traceable to a line in the candidate's CV. A "
        "person decides.",
        ParagraphStyle("dis", fontName="Helvetica", fontSize=8.5, leading=12,
                       textColor=MAROON_DEEP, backColor=MAROON_SOFT,
                       borderPadding=8, spaceAfter=10)))

    eligibility = getattr(evaluation.eligibility_status, "value",
                          evaluation.eligibility_status)
    ELIGIBILITY_WORDS = {
        "ELIGIBLE": "Meets the mandatory rules",
        "DISQUALIFIED": "Does not meet a mandatory rule",
        "REVIEW_REQUIRED": "Could not be verified from the CV",
    }
    story.append(_kv_row(styles, [
        ("Overall", f"{_pct(evaluation.overall_score)} of 100"),
        ("Confidence", f"{float(evaluation.overall_confidence or 0) * 100:.0f}%"),
        ("Eligibility", ELIGIBILITY_WORDS.get(eligibility, eligibility)),
        ("Experience", f"{evaluation.experience_years_total:g} yrs "
                       f"({evaluation.experience_years_relevant:g} relevant)"),
    ]))
    story.append(Spacer(1, 4))

    category_pairs = []
    for label, field in (("Skills", "skills_score"), ("Experience", "experience_score"),
                         ("Education", "education_score"),
                         ("Certifications", "certification_score")):
        value = getattr(evaluation, field, None)
        category_pairs.append((label, "Not assessed" if value is None else _pct(value)))
    story.append(_kv_row(styles, category_pairs))

    # ── recommended next action ──
    action_code = getattr(evaluation, "next_action", None)
    if action_code:
        _section(story, styles, "Recommended next action")
        story.append(Paragraph(
            f"<b>{_escape(NEXT_ACTION_WORDS.get(action_code, action_code))}.</b> "
            f"{_escape(evaluation.next_action_reason)}", styles["body"]))

    if action is not None:
        disposition = getattr(getattr(action, "disposition", None), "value", None)
        if disposition:
            story.append(Spacer(1, 6))
            story.append(Paragraph(
                f"<b>Recruiter decision:</b> {_escape(disposition.replace('_', ' ').title())}"
                + (f" — {_escape(action.reason)}" if getattr(action, "reason", "") else "")
                + (f" (recorded by {_escape(action.actor)})" if getattr(action, "actor", "") else ""),
                styles["body"]))

    # ── narrative ──
    if getattr(evaluation, "narrative", ""):
        _section(story, styles, "Summary")
        story.append(Paragraph(_escape(evaluation.narrative), styles["body"]))

    # ── strengths and gaps ──
    strengths = evaluation.strengths or []
    gaps = evaluation.gaps or []
    if strengths or gaps:
        _section(story, styles, "Strengths, gaps and risks")
        if strengths:
            story.append(Paragraph("<b>What this candidate brings</b>", styles["body"]))
            for item in strengths[:6]:
                story.append(Paragraph(
                    f"• {_escape(item.get('label'))} — scored {_pct(item.get('score'))}",
                    styles["body"]))
            story.append(Spacer(1, 6))
        if gaps:
            story.append(Paragraph("<b>Material gaps and risks</b>", styles["body"]))
            for item in gaps[:6]:
                story.append(Paragraph(
                    f"• {_escape(item.get('label'))} — "
                    f"{_escape(OUTCOME_WORDS.get(item.get('outcome'), item.get('outcome')))}",
                    styles["body"]))

    # ── criterion table ──
    _section(story, styles, "Every criterion, scored against the approved rubric")
    rows = [[
        Paragraph("<b>Requirement</b>", styles["cellb"]),
        Paragraph("<b>Weight</b>", styles["cellb"]),
        Paragraph("<b>Score</b>", styles["cellb"]),
        Paragraph("<b>Finding</b>", styles["cellb"]),
        Paragraph("<b>Confidence</b>", styles["cellb"]),
    ]]
    for criterion in criteria:
        outcome = getattr(criterion.outcome, "value", criterion.outcome)
        rows.append([
            Paragraph(_escape(criterion.label), styles["cell"]),
            Paragraph(f"{criterion.weight:g}", styles["cell"]),
            Paragraph(f"<b>{_pct(criterion.raw_score)}</b>", styles["cellb"]),
            Paragraph(_escape(OUTCOME_WORDS.get(outcome, outcome)), styles["cell"]),
            Paragraph(f"{float(criterion.confidence or 0) * 100:.0f}%", styles["cell"]),
        ])
    table = Table(rows, colWidths=[7.0 * cm, 1.5 * cm, 1.5 * cm, 4.0 * cm, 2.0 * cm],
                  repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), SAND_2),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, SAND]),
        ("GRID", (0, 0), (-1, -1), 0.4, HAIR),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(table)

    # ── evidence ──
    cited = [(c, evidence_by_criterion.get(c.id, [])) for c in criteria]
    cited = [(c, e) for c, e in cited if e]
    if cited:
        _section(story, styles, "Evidence, quoted from the CV")
        story.append(Paragraph(
            "Each quotation below is the text the score was read from, with "
            "where it appears in the CV.", styles["small"]))
        story.append(Spacer(1, 6))
        for criterion, items in cited[:10]:
            for item in items[:2]:
                where = (f"CV page {item.page_number}" if item.page_number is not None
                         else "CV")
                if getattr(item, "section", ""):
                    where += f", {item.section.title()}"
                story.append(KeepTogether([
                    Paragraph(f'"{_escape(item.excerpt)}"', styles["quote"]),
                    Paragraph(
                        f"{_escape(criterion.label)} &nbsp;→&nbsp; {_escape(where)}",
                        styles["cite"]),
                ]))

    # ── eligibility ──
    if eligibility_findings:
        _section(story, styles, "Eligibility")
        for finding in eligibility_findings:
            if finding.indeterminate:
                prefix = "Could not be verified"
            elif finding.triggered:
                prefix = "Not met"
            else:
                prefix = "Met"
            story.append(Paragraph(
                f"<b>{prefix}.</b> {_escape(finding.message)}", styles["body"]))
        story.append(Spacer(1, 4))
        story.append(Paragraph(
            "Eligibility is decided by the campaign's own rules, evaluated "
            "arithmetically and outside the AI. A score cannot overturn it, and "
            "a condition that could not be verified is sent for review rather "
            "than failed.", styles["small"]))

    # ── missing information ──
    missing = evaluation.missing_information or []
    if missing:
        _section(story, styles, "Missing or ambiguous information")
        for item in missing[:8]:
            story.append(Paragraph(f"• {_escape(item)}", styles["body"]))

    # ── questions and interview focus ──
    questions = evaluation.validation_questions or []
    if questions:
        _section(story, styles, "Questions to put to the candidate")
        for q in questions[:8]:
            story.append(Paragraph(f"• {_escape(q.get('question'))}", styles["body"]))
            story.append(Paragraph(f"   {_escape(q.get('why'))}", styles["small"]))

    focus = evaluation.interview_focus or []
    if focus:
        _section(story, styles, "Suggested interview focus")
        for item in focus[:6]:
            story.append(Paragraph(
                f"• <b>{_escape(item.get('area'))}</b> — {_escape(item.get('reason'))}",
                styles["body"]))

    # ── challenge findings ──
    if challenge_findings:
        _section(story, styles, "What the review agent questioned")
        story.append(Paragraph(
            "A second pass reviews this assessment for unsupported conclusions, "
            "missing evidence, contradictions and weighting anomalies. It never "
            "changes a score.", styles["small"]))
        story.append(Spacer(1, 5))
        for finding in challenge_findings[:8]:
            severity = getattr(finding.severity, "value", finding.severity)
            story.append(Paragraph(
                f"<b>{_escape(SEVERITY_WORDS.get(severity, severity))}: "
                f"{_escape(finding.title)}</b>", styles["body"]))
            story.append(Paragraph(_escape(finding.detail), styles["small"]))
            if getattr(finding, "recommendation", ""):
                story.append(Paragraph(
                    f"   → {_escape(finding.recommendation)}", styles["small"]))
            story.append(Spacer(1, 4))

    # ── benchmark ──
    if benchmark and benchmark.get("position"):
        position = benchmark["position"]
        _section(story, styles, "Compared with this campaign")
        story.append(Paragraph(_escape(position.get("statement", "")), styles["body"]))
        stats = benchmark.get("benchmarks") or {}
        if stats:
            story.append(Paragraph(
                f"Scores across {stats.get('candidates_assessed')} assessed "
                f"candidates run from {stats.get('lowest')} to {stats.get('highest')}, "
                f"median {stats.get('median')}.", styles["small"]))

    # ── provenance ──
    story.append(Spacer(1, 14))
    story.append(HRFlowable(width="100%", thickness=0.6, color=HAIR, spaceAfter=6))
    version_note = ""
    if rubric_version is not None:
        version_note = (f"Rubric version {rubric_version.version_number}"
                        + (f", approved by {_escape(rubric_version.approved_by)}"
                           if rubric_version.approved_by else "") + ". ")
    produced_on = (f", {evaluation.created_at:%d %B %Y}"
                   if getattr(evaluation, "created_at", None) else "")
    story.append(Paragraph(
        version_note
        + f"Assessment {evaluation.id} produced by engine "
          f"{evaluation.engine_version}{produced_on}. "
          "Scoring is deterministic: the same CV against the same rubric "
          "produces the same result.",
        styles["small"]))
    story.append(Paragraph(
        f"Generated {datetime.now(timezone.utc):%d %B %Y, %H:%M} UTC.", styles["small"]))

    document.build(story)
    return buffer.getvalue()
