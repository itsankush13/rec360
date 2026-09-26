"""
The communication log — B10 / W-E.

Nothing else in the product records what was said to a candidate. This
module gives that first question — "what did we actually tell them?" — an
answer: a small set of templates in the product's own voice, a render step
that never quietly drops a placeholder, and a send step that writes one
real audit row for a message that is never actually transmitted.

**A message does not move the lifecycle.** Sending a note is not a state
change; these endpoints write an audit row only and never call
`app.core.lifecycle.check` or `lifecycle_service.transition`.

**Transmission is opt-in and off by default.** `app.core.outlook_adapter`
decides, from `settings.email_backend`, whether a message is actually sent
through a local Outlook profile or only recorded. Default is "simulated" —
`after.simulated` is `True` and nothing leaves this process, exactly as
before this module could send at all. See `outlook_adapter`'s docstring for
what "outlook" mode has and has not been verified against.

**Every EMAIL subject carries a reference tag.** A separate, parallel piece
of work reads Outlook replies and matches them back to the candidate they
concern; the only thing available to match on is the subject line. Before an
EMAIL is sent or recorded, `app.core.mail_ref.ref_tag` appends
" [REF-{campaign_id}:{candidate_id}]" — see that module for the fixed shape.
SMS and phone notes have no email subject a reply-reader parses, so they are
left untagged.
"""
from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.mail_guard import ensure_approved_mail_recipients
from app.core.mail_ref import ref_tag
from app.core.outlook_adapter import get_mail_adapter
from app.db.models import AuditAction, Campaign, Candidate
from app.db.session import get_db
from app.services.disposition_service import audit_trail, record_audit

router = APIRouter(prefix="/api/campaigns/{campaign_id}/messages", tags=["messages"])


# ---------------------------------------------------------------------------
# Templates — the product's own voice. Placeholders resolved automatically:
# {candidate_name}, {role}, {campaign}. Anything else (like
# {interview_when}) has no automatic source and must be supplied by the
# sender, or it stays visible in the rendered text.
# ---------------------------------------------------------------------------

TEMPLATES = {
    "SHORTLIST_INVITE": {
        "name": "Shortlist invite",
        "subject": "Good news about your application for {role}",
        "body": (
            "Dear {candidate_name},\n\n"
            "Thank you for applying for the {role} position, and for the time "
            "you put into your application. We were glad to receive it.\n\n"
            "I am pleased to tell you that you have been shortlisted. Your "
            "experience stood out against what we are looking for, and we "
            "would like to take your application further.\n\n"
            "What happens next:\n\n"
            "1. A member of the recruitment team will contact you within the "
            "next few working days.\n"
            "2. We will agree a time to speak that suits you, and tell you who "
            "you will be meeting and how long to allow.\n"
            "3. If we need anything further from you before then, we will ask "
            "in good time and explain why it is needed.\n\n"
            "There is nothing you need to do right now. If your phone number "
            "or email address has changed, or if there are days you are not "
            "available, simply reply to this email and let us know.\n\n"
            "Thank you again for your interest in joining us. "
            "Congratulations, and we look forward to speaking with you.\n\n"
            "Kind regards,\n"
            "Recruitment Team\n\n"
            "Your reference: {campaign}"
        ),
    },
    "INTERVIEW_INVITE": {
        "name": "Interview invite",
        "subject": "Your interview for {role} — {interview_when}",
        "body": (
            "Dear {candidate_name},\n\n"
            "Thank you for your patience while we reviewed your application "
            "for the {role} position. We would very much like to meet you.\n\n"
            "Your interview is arranged for {interview_when}. A separate "
            "calendar invitation is on its way to this same email address, so "
            "you can add the time straight to your diary.\n\n"
            "What to expect:\n\n"
            "1. Please allow about 45 minutes.\n"
            "2. We will talk through your experience, the day-to-day work of "
            "the role, and the team you would be joining.\n"
            "3. There is no test and nothing to prepare. Come as you are, and "
            "bring any questions you have for us.\n"
            "4. If the meeting is in person, please arrive about ten minutes "
            "early and bring photo identification for site access.\n\n"
            "Please reply to confirm that the time works for you. If it does "
            "not, tell us which days and times suit you better and we will "
            "rearrange it. Changing the time will not count against you in "
            "any way.\n\n"
            "If anything is unclear, or you need any adjustment to take part "
            "comfortably, reply to this email and we will arrange it.\n\n"
            "We look forward to meeting you.\n\n"
            "Kind regards,\n"
            "Recruitment Team\n\n"
            "Your reference: {campaign}"
        ),
    },
    "INTERVIEW_REGRET": {
        "name": "Interview regret",
        "subject": "Your application for {role}",
        "body": (
            "Dear {candidate_name},\n\n"
            "Thank you for meeting us to discuss the {role} position, and for "
            "the time and thought you gave to the conversation.\n\n"
            "After careful consideration we have decided not to take your "
            "application further on this occasion. This was a close decision "
            "and not an easy one. It reflects how closely each person matched "
            "the specific needs of this particular role, and it is not a "
            "judgement on your ability or your experience more widely.\n\n"
            "If it would help, we are happy to share feedback from your "
            "interview. Just reply to this email and we will arrange a short "
            "call at a time that suits you.\n\n"
            "We would genuinely welcome an application from you for future "
            "openings, and we will keep your details on file so we can let "
            "you know when a suitable role comes up, unless you would prefer "
            "us not to.\n\n"
            "Thank you again for your interest in joining us. We wish you "
            "every success.\n\n"
            "Kind regards,\n"
            "Recruitment Team\n\n"
            "Your reference: {campaign}"
        ),
    },
    "OFFER_COVER": {
        "name": "Offer cover note",
        "subject": "Your offer for {role}",
        "body": (
            "Dear {candidate_name},\n\n"
            "Following your interview, I am delighted to offer you the {role} "
            "position. Everyone who met you was impressed, and we would very "
            "much like you to join us.\n\n"
            "Your formal offer letter is attached to this email. It sets out "
            "the salary, the working pattern, the start date we have in mind, "
            "and the terms that apply.\n\n"
            "What happens next:\n\n"
            "1. Please read the offer letter in full and take the time you "
            "need to consider it.\n"
            "2. If you are happy to accept, reply to this email to confirm.\n"
            "3. We will then agree a start date with you and send joining "
            "instructions, including where to go on your first day and what "
            "to bring.\n\n"
            "If anything in the letter is unclear, or you would like to talk "
            "any part of it through before you decide, reply to this email or "
            "ask us to call you. We are glad to answer questions.\n\n"
            "Congratulations. We very much hope you will accept.\n\n"
            "Kind regards,\n"
            "Recruitment Team\n\n"
            "Your reference: {campaign}"
        ),
    },
    "DOCUMENT_CHASE": {
        "name": "Document chase",
        "subject": "A few documents we still need for your {role} application",
        "body": (
            "Dear {candidate_name},\n\n"
            "Thank you for your application for the {role} position. Your "
            "application is progressing, and we are grateful for the time you "
            "have put into it so far.\n\n"
            "Before we can take it to the next stage, there are a few "
            "documents we still need from you:\n\n"
            "{documents}\n\n"
            "How to send them:\n\n"
            "1. Reply to this email with the documents attached.\n"
            "2. Clear photographs taken on a phone are perfectly fine, as "
            "long as all of the text can be read and the whole page is in "
            "view.\n"
            "3. If a document is not in English or Arabic, please include a "
            "translation if you already have one. If you do not, send the "
            "document anyway and we will advise.\n\n"
            "If any of these will be difficult or slow to obtain, please tell "
            "us rather than delaying your reply. There is often an acceptable "
            "alternative, and we would rather help you find it.\n\n"
            "If you have already sent some of these, please accept our "
            "apologies and ignore that part of this note. Our messages may "
            "simply have crossed.\n\n"
            "Thank you for your help.\n\n"
            "Kind regards,\n"
            "Recruitment Team\n\n"
            "Your reference: {campaign}"
        ),
    },
    "GENERAL": {
        "name": "General note",
        "subject": "About your application for {role}",
        "body": (
            "Dear {candidate_name},\n\n"
            "{message}\n\n"
            "If you have any questions about this, or about your application "
            "for the {role} position more generally, simply reply to this "
            "email and we will come back to you.\n\n"
            "Kind regards,\n"
            "Recruitment Team\n\n"
            "Your reference: {campaign}"
        ),
    },
}


def _placeholders(text: str) -> list[str]:
    import re
    return re.findall(r"\{(\w+)\}", text)


# ---------------------------------------------------------------------------
# Shapes
# ---------------------------------------------------------------------------

class RenderIn(BaseModel):
    candidate_id: str
    values: dict[str, str] = Field(default_factory=dict)


class RenderOut(BaseModel):
    subject: str
    body: str
    unresolved: list[str]


class SendIn(BaseModel):
    channel: Literal["EMAIL", "SMS", "PHONE_NOTE"]
    recipient: str
    subject: str
    body: str
    actor_id: str
    template_id: str | None = None
    # B10: CC on an EMAIL send, threaded straight through to the mail
    # adapter. Meaningless for SMS/PHONE_NOTE, which have no adapter to CC.
    cc: str | None = None


class MessageOut(BaseModel):
    candidate_id: str
    channel: str
    recipient: str
    subject: str
    body: str
    template_id: str | None
    actor_id: str
    created_at: str
    simulated: bool = True
    send_detail: Optional[str] = None


def _fail(detail: str) -> HTTPException:
    return HTTPException(status_code=422, detail=detail)


def _require_campaign(db: Session, campaign_id: str) -> Campaign:
    campaign = db.get(Campaign, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign


def _require_candidate(db: Session, campaign_id: str, candidate_id: str) -> Candidate:
    candidate = db.get(Candidate, candidate_id)
    if candidate is None or candidate.campaign_id != campaign_id:
        raise _fail(f"Candidate '{candidate_id}' is not in campaign '{campaign_id}'.")
    return candidate


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

@router.get("/templates")
def list_templates(campaign_id: str):
    return [
        {
            "id": template_id,
            "name": t["name"],
            "subject": t["subject"],
            "body": t["body"],
            "placeholders": sorted(set(
                _placeholders(t["subject"]) + _placeholders(t["body"])
            )),
        }
        for template_id, t in TEMPLATES.items()
    ]


@router.post("/templates/{template_id}/render", response_model=RenderOut)
def render_template(campaign_id: str, template_id: str, payload: RenderIn,
                    db: Session = Depends(get_db)):
    template = TEMPLATES.get(template_id)
    if template is None:
        raise HTTPException(status_code=404, detail=f"No template named '{template_id}'.")

    campaign = _require_campaign(db, campaign_id)
    candidate = _require_candidate(db, campaign_id, payload.candidate_id)

    known = {
        "candidate_name": candidate.full_name,
        "role": campaign.job_title,
        "campaign": campaign.name,
    }
    known.update(payload.values)

    names = sorted(set(_placeholders(template["subject"]) + _placeholders(template["body"])))
    unresolved = [n for n in names if not (known.get(n) or "").strip()]

    class _Leave(dict):
        def __missing__(self, key):
            return "{" + key + "}"

    fill = _Leave({k: v for k, v in known.items() if k not in unresolved})
    subject = template["subject"].format_map(fill)
    body = template["body"].format_map(fill)
    return RenderOut(subject=subject, body=body, unresolved=unresolved)


# ---------------------------------------------------------------------------
# Sending (recording)
# ---------------------------------------------------------------------------

@router.post("/{candidate_id}/send", response_model=MessageOut, status_code=201)
def send_message(campaign_id: str, candidate_id: str, payload: SendIn,
                 db: Session = Depends(get_db)):
    _require_campaign(db, campaign_id)
    _require_candidate(db, campaign_id, candidate_id)

    if not payload.recipient.strip():
        raise _fail("A message needs a recipient to send to.")
    if not payload.body.strip():
        raise _fail("A message needs a body — it cannot be sent empty.")

    # An EMAIL's subject carries the reference tag a reply gets matched back
    # on (see the module docstring and app.core.mail_ref). SMS/PHONE_NOTE
    # have no email subject for that reader to look at, so they are recorded
    # exactly as composed.
    subject = (
        payload.subject + ref_tag(campaign_id, candidate_id)
        if payload.channel == "EMAIL"
        else payload.subject
    )

    # Only EMAIL has an adapter today; SMS/PHONE_NOTE stay simulated-only.
    if payload.channel == "EMAIL":
        ensure_approved_mail_recipients(to_address=payload.recipient, cc_address=payload.cc)
    transmission = (
        get_mail_adapter().send(
            to_address=payload.recipient, subject=subject, body=payload.body,
            cc_address=payload.cc,
        )
        if payload.channel == "EMAIL"
        else None
    )
    simulated = transmission.simulated if transmission else True
    send_detail = transmission.detail if transmission else None

    after = {
        "channel": payload.channel,
        "recipient": payload.recipient,
        "subject": subject,
        "body": payload.body,
        "template_id": payload.template_id,
        "cc": payload.cc,
        "simulated": simulated,
        "send_detail": send_detail,
    }
    summary = f"Message sent by {payload.channel.lower()}: {payload.subject}"
    if transmission is not None and not transmission.simulated:
        summary += " (sent via local Outlook)"
    event = record_audit(
        db, AuditAction.MESSAGE_SENT,
        campaign_id=campaign_id, candidate_id=candidate_id,
        entity_type="candidate", entity_id=candidate_id,
        summary=summary,
        after=after, actor=payload.actor_id,
    )
    db.commit()
    return MessageOut(
        candidate_id=candidate_id, channel=payload.channel,
        recipient=payload.recipient, subject=subject, body=payload.body,
        template_id=payload.template_id, actor_id=payload.actor_id,
        created_at=event.created_at.isoformat() if event.created_at else "",
        simulated=simulated, send_detail=send_detail,
    )


# ---------------------------------------------------------------------------
# Reading the log
# ---------------------------------------------------------------------------

def _as_message(event) -> MessageOut:
    after = event.after or {}
    return MessageOut(
        candidate_id=event.candidate_id or "",
        channel=after.get("channel", ""),
        recipient=after.get("recipient", ""),
        subject=after.get("subject", ""),
        body=after.get("body", ""),
        template_id=after.get("template_id"),
        actor_id=event.actor,
        created_at=event.created_at.isoformat() if event.created_at else "",
        simulated=after.get("simulated", True),
        send_detail=after.get("send_detail"),
    )


@router.get("", response_model=list[MessageOut])
def campaign_log(campaign_id: str, db: Session = Depends(get_db)):
    """The campaign's message log, newest first."""
    _require_campaign(db, campaign_id)
    events = audit_trail(db, campaign_id, action=AuditAction.MESSAGE_SENT)
    return [_as_message(e) for e in events]


@router.get("/{candidate_id}", response_model=list[MessageOut])
def candidate_thread(campaign_id: str, candidate_id: str, db: Session = Depends(get_db)):
    """One candidate's thread, oldest first, so it reads as a conversation."""
    _require_campaign(db, campaign_id)
    events = audit_trail(
        db, campaign_id, action=AuditAction.MESSAGE_SENT, candidate_id=candidate_id,
        limit=1000,
    )
    return [_as_message(e) for e in reversed(events)]
