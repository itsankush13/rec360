"""
B10 — the local Outlook reply reader.

Same fake-COM-double pattern as `test_outlook_adapter.py` /
`test_calendar_adapter.py`: nothing here touches pywin32's real COM layer or
a live Outlook profile. `InboxReader` takes its dispatch function as a
constructor argument precisely so a fake `Outlook.Application` double can
stand in for `GetNamespace("MAPI").GetDefaultFolder(6).Items`.
"""
from datetime import datetime

from app.core import reply_ingestion
from app.core.reply_ingestion import (
    REF_TAG_RE,
    InboxReader,
    get_inbox_reader,
    strip_quoted_text,
)

CAMPAIGN_ID = "11111111-1111-1111-1111-111111111111"
CANDIDATE_ID = "22222222-2222-2222-2222-222222222222"


# ---------------------------------------------------------------------------
# The subject-tagging contract
# ---------------------------------------------------------------------------

def test_ref_tag_matches_a_campaign_and_candidate_tag_as_a_substring():
    subject = f"RE: Interview round 1: Jane Doe [REF-{CAMPAIGN_ID}:{CANDIDATE_ID}]"
    match = REF_TAG_RE.search(subject)
    assert match is not None
    assert match.group(1) == CAMPAIGN_ID
    assert match.group(2) == CANDIDATE_ID


def test_ref_tag_matches_a_campaign_only_tag():
    subject = f"RE: Hiring manager report — Q3 [REF-{CAMPAIGN_ID}]"
    match = REF_TAG_RE.search(subject)
    assert match is not None
    assert match.group(1) == CAMPAIGN_ID
    assert match.group(2) is None


def test_ref_tag_does_not_match_an_untagged_subject():
    assert REF_TAG_RE.search("RE: Let's catch up") is None


# ---------------------------------------------------------------------------
# Quote stripping (best-effort — see the module docstring for what this
# does and does not handle)
# ---------------------------------------------------------------------------

def test_strip_quoted_text_removes_the_original_message_banner():
    body = (
        "Approved, let's proceed.\n\n"
        "-----Original Message-----\n"
        "From: recruiter@example.com\n"
        "Sent: Monday\n"
        "To: manager@example.com\n"
        "Subject: Interview request\n"
        "Please review this candidate."
    )
    assert strip_quoted_text(body) == "Approved, let's proceed."


def test_strip_quoted_text_removes_a_from_sent_to_subject_block():
    body = (
        "Sounds good to me.\n\n"
        "From: someone@example.com\n"
        "Sent: Tuesday, 10:00 AM\n"
        "To: recruiter@example.com\n"
        "Subject: RE: Interview\n"
        "Original content here."
    )
    assert strip_quoted_text(body) == "Sounds good to me."


def test_strip_quoted_text_removes_an_on_wrote_block():
    body = "Let's go with Tuesday.\n\nOn Mon, Jan 5, 2026, Fatima wrote:\n> Can we schedule?"
    assert strip_quoted_text(body) == "Let's go with Tuesday."


def test_strip_quoted_text_removes_trailing_quote_marks():
    body = "No further questions.\n> Previous message line one\n> Previous message line two"
    assert strip_quoted_text(body) == "No further questions."


def test_strip_quoted_text_returns_the_body_unchanged_when_no_marker_is_found():
    body = "Just a plain reply with no quoting at all."
    assert strip_quoted_text(body) == body


def test_strip_quoted_text_handles_an_empty_body():
    assert strip_quoted_text("") == ""


# ---------------------------------------------------------------------------
# Fake COM double
# ---------------------------------------------------------------------------

class _FakeMailItem:
    def __init__(self, subject, body="", sender="manager@example.com",
                entry_id="entry-1", received=None):
        self.Subject = subject
        self.Body = body
        self.SenderEmailAddress = sender
        self.EntryID = entry_id
        self.ReceivedTime = received or datetime(2026, 9, 13, 9, 0)


class _FakeInbox:
    def __init__(self, items):
        self.Items = items


class _FakeNamespace:
    def __init__(self, inbox):
        self._inbox = inbox

    def GetDefaultFolder(self, which):
        assert which == 6  # olFolderInbox
        return self._inbox


class _FakeOutlookApplication:
    def __init__(self, items):
        self._namespace = _FakeNamespace(_FakeInbox(items))

    def GetNamespace(self, kind):
        assert kind == "MAPI"
        return self._namespace


def test_reader_extracts_campaign_and_candidate_and_strips_the_ref_tag_body():
    items = [_FakeMailItem(
        subject=f"RE: Interview round 1 [REF-{CAMPAIGN_ID}:{CANDIDATE_ID}]",
        body="Approved, let's go ahead.\n\n-----Original Message-----\nSubject: x",
        sender="aziz@example.com",
    )]
    reader = InboxReader(dispatch=lambda: _FakeOutlookApplication(items))

    replies = reader.read_replies()

    assert len(replies) == 1
    reply = replies[0]
    assert reply.campaign_id == CAMPAIGN_ID
    assert reply.candidate_id == CANDIDATE_ID
    assert reply.sender_address == "aziz@example.com"
    assert reply.body == "Approved, let's go ahead."
    assert reply.message_id == "entry-1"


def test_reader_skips_items_whose_subject_has_no_ref_tag():
    items = [
        _FakeMailItem(subject="RE: Interview round 1 [REF-" + CAMPAIGN_ID + "]"),
        _FakeMailItem(subject="Unrelated newsletter"),
    ]
    reader = InboxReader(dispatch=lambda: _FakeOutlookApplication(items))

    replies = reader.read_replies()

    assert len(replies) == 1
    assert replies[0].candidate_id is None  # campaign-only tag


def test_reader_never_raises_when_the_com_call_fails():
    def _broken_dispatch():
        raise RuntimeError("Outlook is not installed")

    reader = InboxReader(dispatch=_broken_dispatch)
    assert reader.read_replies() == []


def test_reader_respects_the_limit():
    items = [
        _FakeMailItem(subject=f"RE: x [REF-{CAMPAIGN_ID}]", entry_id=f"id-{i}")
        for i in range(5)
    ]
    reader = InboxReader(dispatch=lambda: _FakeOutlookApplication(items))
    assert len(reader.read_replies(limit=2)) == 2


# ---------------------------------------------------------------------------
# Opt-in gate — same shape as get_mail_adapter/get_calendar_adapter
# ---------------------------------------------------------------------------

def test_get_inbox_reader_is_none_by_default(monkeypatch):
    monkeypatch.setattr(reply_ingestion.settings, "email_backend", "simulated")
    assert get_inbox_reader() is None


def test_get_inbox_reader_builds_a_reader_when_outlook_is_configured(monkeypatch):
    monkeypatch.setattr(reply_ingestion.settings, "email_backend", "outlook")
    reader = get_inbox_reader()
    assert isinstance(reader, InboxReader)


def test_get_inbox_reader_falls_back_to_none_when_the_adapter_cannot_be_built(monkeypatch):
    monkeypatch.setattr(reply_ingestion.settings, "email_backend", "outlook")

    class _Broken:
        def __init__(self):
            raise RuntimeError("pywin32 not installed")

    monkeypatch.setattr(reply_ingestion, "InboxReader", _Broken)
    assert get_inbox_reader() is None
