"""
Local Outlook reply ingestion — B10, the inbound half.

The outbound side (a parallel, separately-built lane) stamps every outgoing
subject with a tag this module reads back: `" [REF-{campaign_id}]"` for a
campaign-level thread (e.g. the hiring-manager report) or
`" [REF-{campaign_id}:{candidate_id}]"` for a candidate-level thread (e.g. an
interview invite). A reply's subject in Outlook is the original subject with
an "RE:"/"FW:" prefix, so the tag is matched as a substring via
`REF_TAG_RE`, never against the whole subject.

Same opt-in gate as `app.core.outlook_adapter` / `app.core.calendar_adapter`:
`get_inbox_reader()` returns `None` unless `settings.email_backend ==
"outlook"`. Reading replies only makes sense once real sending is on, and a
second setting that could drift out of sync with the send-side flag is
exactly the kind of inconsistent-config trap CLAUDE.md warns about for
`QUEUE_BACKEND` — so this reuses the existing flag rather than adding one.

Same DI shape as the other two adapters: `_dispatch_outlook()` is isolated so
tests substitute a fake COM double (`InboxReader(dispatch=fake)`) with no
pywin32 or real Outlook install involved. Unlike the send-side adapters —
called synchronously from the request thread that dispatched them — this one
is meant to be invoked from the on-demand `/api/replies/ingest` endpoint,
which FastAPI may run on a worker thread with no COM apartment of its own.
Real use (only, never the fake-double test path — see `_read`) is wrapped in
`pythoncom.CoInitialize()` / `CoUninitialize()` for exactly that reason.
"""
from __future__ import annotations

import dataclasses
import logging
import re
from datetime import datetime

from app.core.config import settings

logger = logging.getLogger(__name__)

# The subject-tagging contract: a campaign-only tag, or a campaign:candidate
# pair. Matched as a substring so an "RE: "/"FW: " prefix Outlook adds to a
# reply subject never breaks the match.
REF_TAG_RE = re.compile(r"\[REF-([0-9a-fA-F-]{36})(?::([0-9a-fA-F-]{36}))?\]")

# Best-effort markers for where Outlook's quoted original message begins.
# This is a heuristic for a demo, not a MIME-aware quote parser — see
# `strip_quoted_text`'s docstring for exactly what it does and does not
# handle.
_QUOTE_MARKERS = [
    re.compile(r"\n\s*-{2,}\s*Original Message\s*-{2,}", re.IGNORECASE),
    re.compile(r"\nFrom:\s?.+\n\s*Sent:\s?.+\n\s*To:\s?.+\n\s*Subject:\s?.+", re.IGNORECASE),
    re.compile(r"\nOn .{0,120} wrote:\s*\n", re.IGNORECASE),
    re.compile(r"\n_{5,}\s*\n"),  # Outlook's horizontal rule above the header block
]


def strip_quoted_text(body: str) -> str:
    """
    Best-effort trim of the quoted original message from a reply body.

    Handles: Outlook's "-----Original Message-----" banner; the plain-text
    "From: / Sent: / To: / Subject:" header block Outlook inserts above a
    quoted message; "On <date>, <name> wrote:" (seen when the other party is
    on a non-Outlook client); and a trailing run of '>'-quoted lines.

    Does NOT handle: HTML-only bodies (Outlook's `.Body` is plain text, so
    this is moot for COM-read mail, but would matter for any other source);
    quoted text interleaved with an inline reply rather than appended below
    it; a forwarded thread with multiple nested quote blocks (only the first
    marker found is used as the cut point); or a quoting style particular to
    a mail client other than Outlook/Outlook Web. Where none of the markers
    match, the full body is returned unchanged rather than guessed at.
    """
    if not body:
        return ""
    earliest = len(body)
    for pattern in _QUOTE_MARKERS:
        match = pattern.search(body)
        if match and match.start() < earliest:
            earliest = match.start()
    text = body[:earliest]

    lines = text.splitlines()
    while lines and lines[-1].strip().startswith(">"):
        lines.pop()
    return "\n".join(lines).strip()


@dataclasses.dataclass
class ParsedReply:
    """One inbox item whose subject carried a `[REF-...]` tag."""

    message_id: str
    campaign_id: str
    candidate_id: str | None
    sender_address: str
    received_at: datetime | None
    subject: str
    body: str


def _dispatch_outlook():
    """
    Isolated in its own function, exactly like `outlook_adapter` and
    `calendar_adapter`, so tests substitute a fake COM namespace without
    pywin32 or a real Outlook install being involved.
    """
    import win32com.client
    return win32com.client.Dispatch("Outlook.Application")


class InboxReader:
    """
    Reads the local Outlook Inbox for `[REF-...]`-tagged replies.

    `read_replies()` must never raise — a mailbox read failing must not take
    down whatever called it; failures are logged and an empty list comes
    back, the same contract `SendResult`/`InviteResult` give their callers.
    """

    def __init__(self, dispatch=_dispatch_outlook):
        self._dispatch = dispatch
        # Only the real, default dispatch function touches actual Outlook
        # COM objects. A test's fake double must never require pythoncom or
        # a COM apartment — this flag is how `_read` tells the two apart.
        self._is_real = dispatch is _dispatch_outlook

    def read_replies(self, *, limit: int = 200) -> list[ParsedReply]:
        try:
            return self._read(limit=limit)
        except Exception as exc:
            logger.warning("Reply ingestion failed: %s", exc)
            return []

    def _read(self, *, limit: int) -> list[ParsedReply]:
        if self._is_real:
            import pythoncom
            pythoncom.CoInitialize()
        try:
            outlook = self._dispatch()
            namespace = outlook.GetNamespace("MAPI")
            inbox = namespace.GetDefaultFolder(6)  # olFolderInbox
            results: list[ParsedReply] = []
            seen = 0
            for item in inbox.Items:
                if seen >= limit:
                    break
                seen += 1
                subject = getattr(item, "Subject", "") or ""
                match = REF_TAG_RE.search(subject)
                if not match:
                    continue
                campaign_id, candidate_id = match.group(1), match.group(2)
                message_id = getattr(item, "EntryID", "") or ""
                if not message_id:
                    # No stable id on this item (shouldn't happen for a real
                    # Outlook MailItem, but a fake double might omit it) —
                    # fall back to something that at least distinguishes
                    # this item from another with the same subject.
                    message_id = f"{subject}|{getattr(item, 'ReceivedTime', '')}"
                sender = (
                    getattr(item, "SenderEmailAddress", "")
                    or getattr(item, "SenderName", "")
                    or ""
                )
                body = getattr(item, "Body", "") or ""
                results.append(ParsedReply(
                    message_id=str(message_id),
                    campaign_id=campaign_id,
                    candidate_id=candidate_id,
                    sender_address=str(sender).strip(),
                    received_at=getattr(item, "ReceivedTime", None),
                    subject=subject,
                    body=strip_quoted_text(body),
                ))
            return results
        finally:
            if self._is_real:
                import pythoncom
                pythoncom.CoUninitialize()


def get_inbox_reader() -> InboxReader | None:
    """
    `None` when reply ingestion is not enabled for this environment — the
    same opt-in gate `get_mail_adapter`/`get_calendar_adapter` use. Callers
    treat `None` as "nothing to do", not as an error.
    """
    if settings.email_backend != "outlook":
        return None
    try:
        return InboxReader()
    except Exception as exc:
        logger.warning(
            "email_backend=outlook but the inbox reader could not be built "
            "(%s); reply ingestion is skipped.", exc,
        )
        return None
