"""
Emailing the shortlist report to the hiring manager — B10 (outbound half).

`app/api/exports.py` already turns a campaign's decided candidates into a
CSV or an XLSX workbook for download; `web/decisions.html` currently says
"download it, then attach it to your email" — there is no path that
actually sends anything to the hiring manager. This module is that path: it
reuses `exports._export_records` and `app.core.ats_export.build_rows` (the
exact same rows the CSV/XLSX download builds, per that module's own rule
that both formats "must not load it two different ways") to build a formal,
pre-written message — a plain-text body plus an HTML version carrying a
bulleted per-candidate summary table — and sends it through
`app.core.outlook_adapter.get_mail_adapter` the same way `app/api/messages.py`
sends a candidate message.

**`Campaign.hiring_manager` is a free-text name, not an email address.**
Checked against actual usage before writing this: `web/new-campaign.html`
labels the field "Name of the hiring manager" and stores values like
"Priya Nair" (see `tests/test_campaigns.py`); nothing in the schema or the
UI ever puts an email address in it. Adding an email column would be a
migration this task does not need, so the recipient (and optional CC) is
supplied by the caller on each send rather than read off the campaign.

**Recorded through the existing `AuditAction.SENT_TO_HIRING_MANAGER`.**
That action already exists and already has a label in `web/audit.html`
("Sent to the hiring manager") — but it was already in use for a different
thing: `app.services.lifecycle_service.send_to_hiring_manager` writes it
when a candidate is handed to a named `User` with the hiring-manager role
for review (`entity_type="candidate_lifecycle"`). This module writes the
same action for a different event — a whole-campaign report actually
emailed to an external address — with `entity_type="campaign"` so the two
are distinguishable in `AuditEvent.entity_type` despite sharing one action
value. Reusing the value (rather than adding a new one) was this task's
explicit instruction; see `docs/DECISIONS.md` (B10) for the reasoning.

**Same opt-in transmission rule as `messages.py`.** Nothing here bypasses
`settings.email_backend`; the default "simulated" adapter records the send
and transmits nothing, exactly like every other outbound path in this
product until someone opts in.
"""
from __future__ import annotations

import html
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.exports import _export_records, build_shortlist_zip
from app.core import ats_export
from app.core.lifecycle import TransitionError
from app.core.mail_guard import ensure_approved_mail_recipients
from app.core.mail_ref import ref_tag
from app.core.outlook_adapter import get_mail_adapter
from app.db.models import AuditAction, Campaign, Disposition, Recommendation, User, UserRole
from app.db.session import get_db
from app.services import lifecycle_service
from app.services.disposition_service import record_audit
from app.services.lifecycle_service import LifecycleError

router = APIRouter(prefix="/api/campaigns/{campaign_id}/reports", tags=["reports"])


def _require_campaign(db: Session, campaign_id: str) -> Campaign:
    campaign = db.get(Campaign, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign


def _report_body(campaign: Campaign, rows: list[dict]) -> str:
    """
    A plain-text summary a hiring manager can read straight in an email
    client — the same fields the CSV/XLSX export carries, condensed to one
    line per candidate rather than a spreadsheet, because a mail body is not
    read the way a workbook is opened.
    """
    title = campaign.job_title or campaign.name or "the role"
    manager = campaign.hiring_manager or "Hiring Manager"
    lines = [
        f"Dear {manager},",
        "",
        f"Please find below the shortlist summary for the {title} requisition, "
        "prepared by the recruitment team. Each candidate has been assessed "
        "against the approved rubric; the recruiter's decision is the "
        "operative recommendation, with the AI assessment shown alongside it "
        "for reference only.",
        "",
    ]
    for index, row in enumerate(rows, start=1):
        lines.append(
            f"{index}. {row['candidate_name']} — "
            f"{row['recruiter_recommendation']} "
            f"(AI: {row['ai_assessment'] or 'not assessed'}, "
            f"score {row['overall_score']}/100)"
        )
    lines.append("")
    lines.append(f"{len(rows)} candidate(s) in this report.")
    lines.append("")
    lines.append(
        "Please let us know if you have any questions, or if you would like "
        "to proceed to the next stage for any of the candidates listed above."
    )
    lines.append("")
    lines.append("Best regards,")
    lines.append("Recruitment Team")
    return "\n".join(lines)


def _sentences(text: str | None, limit: int = 3) -> list[str]:
    """Split a narrative/rationale paragraph into short, readable points."""
    text = (text or "").strip()
    if not text:
        return []
    parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+", text) if p.strip()]
    return parts[:limit] or [text]


def _labels(items: list[dict] | None, limit: int = 4) -> list[str]:
    """Pull the `label` out of a strengths/gaps JSON list, in order."""
    out = []
    for item in (items or [])[:limit]:
        label = (item or {}).get("label")
        if label:
            out.append(str(label))
    return out


def _bullets_html(items: list[str], empty_text: str | None = None) -> str:
    if not items:
        if empty_text:
            return f"<span style=\"color:#8A817C;\">{html.escape(empty_text)}</span>"
        return "<span style=\"color:#8A817C;\">&mdash;</span>"
    lis = "".join(f"<li>{html.escape(item)}</li>" for item in items)
    return f"<ul style=\"margin:0;padding-left:18px;\">{lis}</ul>"


# Overall Feedback reads as a hiring recommendation to the hiring manager —
# why the company should (or shouldn't) move forward with this candidate —
# not a restatement of the recruiter/AI labels already visible elsewhere on
# the row (recruiter decision lives in the row's own disposition; the AI
# label is folded into "Why This Score").
_FEEDBACK_BY_RECOMMENDATION = {
    Recommendation.STRONG_FIT:
        "A strong match for this role, backed by clear, direct evidence across "
        "the criteria that matter most for it — worth prioritising.",
    Recommendation.POTENTIAL_FIT:
        "A workable match worth taking further — there is enough confirmed "
        "evidence here to justify moving this candidate forward.",
    Recommendation.REVIEW_REQUIRED:
        "The evidence on file is mixed or not yet complete enough to call "
        "either way — worth a closer look before deciding.",
    Recommendation.NOT_RECOMMENDED:
        "Based on the evidence gathered so far, this does not look like a "
        "good match for the role.",
}


def _feedback_bullets(evaluation, strengths: list[str]) -> list[str]:
    bullets = [_FEEDBACK_BY_RECOMMENDATION.get(
        evaluation.recommendation,
        "There is not yet enough evidence on file to call this one way or the other.",
    )]
    if strengths:
        bullets.append(f"Particularly strong on {', '.join(strengths[:2])}.")
    return bullets


_TD_STYLE = "padding:10px 12px;border:1px solid #E3DDD4;vertical-align:top;font-size:13px;"
_TH_STYLE = (
    "padding:10px 12px;border:1px solid #6E1030;background:#971A3E;color:#FFFFFF;"
    "font-size:12px;text-align:left;"
)


def _summary_table_html(rows: list[dict], records: list[dict]) -> str:
    """
    The same candidates as `_report_body`, as an HTML table a hiring manager
    can scan — one row per candidate, each qualitative column broken into
    bullet points (rather than a wall of prose) for readability, mirroring
    the shortlist screen's own score/strength/weakness/feedback breakdown.
    """
    header_cells = "".join(
        f'<th style="{_TH_STYLE}">{label}</th>'
        for label in (
            "Candidate", "Overall Score (out of 100)", "Why This Score",
            "Strength", "Weakness", "Overall Feedback",
        )
    )
    body_rows = []
    for row, record in zip(rows, records):
        evaluation = record["evaluation"]
        why = _sentences(evaluation.narrative or evaluation.ai_rationale_summary)
        strengths = _labels(evaluation.strengths)
        weaknesses = _labels(evaluation.gaps)
        feedback = _feedback_bullets(evaluation, strengths)
        body_rows.append(
            "<tr>"
            f'<td style="{_TD_STYLE}font-weight:600;">{html.escape(row["candidate_name"])}</td>'
            f'<td style="{_TD_STYLE}">{row["overall_score"]}</td>'
            f'<td style="{_TD_STYLE}">{_bullets_html(why)}</td>'
            f'<td style="{_TD_STYLE}">{_bullets_html(strengths)}</td>'
            f'<td style="{_TD_STYLE}">{_bullets_html(weaknesses, "No significant weaknesses identified — no candidate is perfect; probe further at interview.")}</td>'
            f'<td style="{_TD_STYLE}">{_bullets_html(feedback)}</td>'
            "</tr>"
        )
    return (
        '<table style="border-collapse:collapse;width:100%;font-family:Calibri,Segoe UI,Arial,'
        'sans-serif;">'
        f"<thead><tr>{header_cells}</tr></thead>"
        f"<tbody>{''.join(body_rows)}</tbody>"
        "</table>"
    )


def _report_html_body(campaign: Campaign, rows: list[dict], records: list[dict]) -> str:
    """
    A formal, pre-written email to the hiring manager: greeting, context,
    the candidate summary table (bulleted for readability), and a closing
    note about the attached assessment reports.
    """
    title = html.escape(campaign.job_title or campaign.name or "the role")
    manager = html.escape(campaign.hiring_manager or "Hiring Manager")
    font = "font-family:Calibri,Segoe UI,Arial,sans-serif;font-size:13px;color:#1F1B18;"
    return f"""
<div style="{font}line-height:1.5;">
  <p>Dear {manager},</p>
  <p>
    Please find below the shortlist summary for the <b>{title}</b> requisition,
    prepared by the recruitment team. Each candidate has been assessed against
    the approved rubric; the recruiter's decision is the operative
    recommendation, with the AI assessment shown alongside it for reference
    only.
  </p>
  {_summary_table_html(rows, records)}
  <p>
    The full assessment report for each shortlisted candidate is attached to
    this email as a single zip file, for your detailed review.
  </p>
  <p>
    Please let us know if you have any questions, or if you would like to
    proceed to the next stage for any of the candidates listed above.
  </p>
  <p>
    Best regards,<br/>
    Recruitment Team
  </p>
</div>
""".strip()


class EmailReportIn(BaseModel):
    recipient: str
    cc: str | None = None
    actor_id: str = ""
    # Mirrors export.csv/export.xlsx's own default: sending the AI's
    # unreviewed ranking as if it were "the shortlist" would make that
    # ranking the operative decision, which this product is explicitly not
    # for.
    decided_only: bool = True


class EmailReportOut(BaseModel):
    campaign_id: str
    recipient: str
    cc: str | None
    subject: str
    candidates: int
    simulated: bool
    send_detail: str | None
    attachment_filename: str | None
    attached_reports: int
    # This email is now also the handoff trigger (see `_handoff_to_manager`
    # below): how many of the reported candidates actually moved to
    # "with the hiring manager" in the lifecycle, and to whom. 0/None when
    # `recipient` does not match a known hiring manager's account — the
    # email still sends either way.
    moved_to_manager: int = 0
    manager_name: str | None = None


# B01 item 4 / X58-style gap: this email used to be a download-and-attach
# formality with no effect on the lifecycle, so a candidate could sit in
# handoff.html's "Ready to send" forever even after the manager had actually
# been emailed. Sending the report now IS the handoff — the candidates it
# reports on move to WITH_HIRING_MANAGER, owned by whoever the recipient
# address resolves to, exactly as if someone had clicked handoff.html's own
# "Send to hiring manager" for each of them. Only a `User` with the hiring
# manager (or admin) role can own a lifecycle row, so a recipient address
# that is not one of theirs still gets the email — nothing here blocks
# sending an informal copy to someone outside the system — but moves no one.
def _resolve_actor_id(db: Session, actor_id: str) -> str | None:
    """
    `EmailReportIn.actor_id` is, in every caller today, the signed-in
    person's *name* (`web/decisions.html` sends `window.__r360ActorName()`,
    matching every other free-text `actor` field on this page) — but
    `lifecycle_service.transition` needs a real `User.id`, belonging to
    someone whose role is actually allowed to move a candidate to
    `WITH_HIRING_MANAGER` (recruiter or admin — never the hiring manager
    themselves, per `app/core/lifecycle.ALLOWED_ROLES`). Try, in order: a
    real id passed through as-is, a name matched against a known account,
    then any recruiter/admin account as a last resort, so this send is
    never blocked by that pre-existing name/id mismatch. `None` only when
    no such account exists at all.
    """
    if actor_id:
        if db.get(User, actor_id) is not None:
            return actor_id
        by_name = db.scalars(select(User).where(User.full_name == actor_id)).first()
        if by_name is not None:
            return by_name.id
    fallback = db.scalars(
        select(User).where(User.role.in_((UserRole.RECRUITER, UserRole.ADMIN)))
    ).first()
    return fallback.id if fallback else None


def _handoff_to_manager(
    db: Session, *, campaign_id: str, records: list[dict], recipient: str,
    actor_id: str,
) -> tuple[User | None, int]:
    manager = db.scalars(
        select(User).where(
            User.email == recipient,
            User.role.in_((UserRole.HIRING_MANAGER, UserRole.ADMIN)),
        )
    ).first()
    if manager is None:
        return None, 0

    resolved_actor_id = _resolve_actor_id(db, actor_id)
    if resolved_actor_id is None:
        return manager, 0

    # Only a recruiter's SHORTLIST/INTERVIEW decision is eligible to enter
    # the lifecycle at all (`lifecycle_service.enter`'s own gate) — a HOLD or
    # REJECT included in a `decided_only=false` report must not be handed to
    # a manager for review.
    eligible_ids = {
        record["candidate"].id for record in records
        if record["action"] is not None
        and record["action"].disposition in (Disposition.SHORTLIST, Disposition.INTERVIEW)
    }
    moved = 0
    for candidate_id in eligible_ids:
        try:
            lifecycle_service.send_to_hiring_manager(
                db, campaign_id=campaign_id, candidate_id=candidate_id,
                actor_id=resolved_actor_id, manager_id=manager.id,
                note=f"Sent with the shortlist report to {recipient}.",
            )
            moved += 1
        except (LifecycleError, TransitionError):
            # Already with this or another manager, already past that stage,
            # or some other illegal-transition reason — the email still
            # reports on this candidate, it just does not move again.
            continue
    return manager, moved


@router.post("/email-to-hiring-manager", response_model=EmailReportOut, status_code=201)
def email_shortlist_to_hiring_manager(
    campaign_id: str, payload: EmailReportIn, db: Session = Depends(get_db),
):
    campaign = _require_campaign(db, campaign_id)

    if not payload.recipient.strip():
        raise HTTPException(
            status_code=422,
            detail="A hiring-manager report needs a recipient email address.",
        )

    records = _export_records(db, campaign, payload.decided_only)
    if not records:
        raise HTTPException(
            status_code=422,
            detail={
                "message": (
                    "There is nothing to report yet. Record a decision on at "
                    "least one candidate first, or set decided_only=false to "
                    "report the full assessed list."
                ),
                "errors": [],
            },
        )
    rows = ats_export.build_rows(records)

    title = campaign.job_title or campaign.name or "Shortlist"
    subject = f"Shortlist report: {title}" + ref_tag(campaign_id)
    body = _report_body(campaign, rows)

    # Attach the shortlisted candidates' Candidate 360 PDFs as one zip. Not
    # every decided candidate is shortlisted, so this can honestly come back
    # empty — the email still sends, just with no attachment.
    zip_result = build_shortlist_zip(db, campaign, format="pdf")
    attachments = None
    attachment_filename: str | None = None
    attached_reports = 0
    if zip_result is not None:
        attachment_filename, zip_bytes, attached_reports = zip_result
        attachments = [(attachment_filename, zip_bytes)]
        body += (
            "\n\nThe full assessment report for each shortlisted candidate "
            "is attached as a zip."
        )
    html_body = _report_html_body(campaign, rows, records)

    ensure_approved_mail_recipients(to_address=payload.recipient, cc_address=payload.cc)
    transmission = get_mail_adapter().send(
        to_address=payload.recipient, cc_address=payload.cc,
        subject=subject, body=body, attachments=attachments,
        html_body=html_body,
    )

    manager, moved_to_manager = _handoff_to_manager(
        db, campaign_id=campaign_id, records=records,
        recipient=payload.recipient, actor_id=payload.actor_id,
    )

    summary = (
        f"Shortlist report for {title} sent to the hiring manager "
        f"({len(rows)} candidate(s))"
    )
    if not transmission.simulated:
        summary += " (sent via local Outlook)"
    if moved_to_manager:
        summary += f"; {moved_to_manager} moved to {manager.full_name} for review"

    record_audit(
        db, AuditAction.SENT_TO_HIRING_MANAGER,
        campaign_id=campaign_id, entity_type="campaign", entity_id=campaign_id,
        summary=summary,
        after={
            "recipient": payload.recipient,
            "cc": payload.cc,
            "candidates": len(rows),
            "decided_only": payload.decided_only,
            "simulated": transmission.simulated,
            "send_detail": transmission.detail,
            "attached": attachments is not None,
            "attached_reports": attached_reports,
            "moved_to_manager": moved_to_manager,
        },
        actor=payload.actor_id,
    )
    db.commit()

    return EmailReportOut(
        campaign_id=campaign_id, recipient=payload.recipient, cc=payload.cc,
        subject=subject, candidates=len(rows),
        simulated=transmission.simulated, send_detail=transmission.detail,
        attachment_filename=attachment_filename, attached_reports=attached_reports,
        moved_to_manager=moved_to_manager,
        manager_name=manager.full_name if manager else None,
    )
