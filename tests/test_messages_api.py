"""
The communication log — B10 / W-E.

What was actually said to a candidate has no record anywhere else in the
product. This module writes one: a template set for the product's own
voice, a render step that never silently drops a placeholder, and a send
step that records a real audit row for a message that is never really
transmitted.

`app/main.py` is owned by the supervisor and does not yet mount
`messages_router` (see SILENCE in the implementer report). Until it does,
these tests build a small standalone app around the router so the router
itself is verified end to end.
"""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import messages as messages_api
from app.api.messages import router as messages_router
from app.core.mail_ref import ref_tag
from app.core.outlook_adapter import SendResult
from app.db.models import AuditAction, AuditEvent, Campaign, Candidate
from app.db.session import get_db


def make_client(db_session):
    app = FastAPI()
    app.include_router(messages_router)

    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    return TestClient(app)


def make_campaign(db_session, **kw):
    campaign = Campaign(
        name=kw.get("name", "Coastal Ops"),
        job_title=kw.get("job_title", "Control Room Operator"),
    )
    db_session.add(campaign)
    db_session.flush()
    return campaign


def make_candidate(db_session, campaign, **kw):
    candidate = Candidate(
        campaign_id=campaign.id,
        full_name=kw.get("full_name", "Haitham Al-Otaibi"),
        email=kw.get("email", "haitham@example.com"),
    )
    db_session.add(candidate)
    db_session.flush()
    return candidate


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

def test_the_template_set_names_its_placeholders(db_session):
    client = make_client(db_session)
    response = client.get("/api/campaigns/any/messages/templates")
    assert response.status_code == 200
    templates = response.json()
    ids = {t["id"] for t in templates}
    assert {
        "SHORTLIST_INVITE", "INTERVIEW_INVITE", "INTERVIEW_REGRET",
        "OFFER_COVER", "DOCUMENT_CHASE", "GENERAL",
    } <= ids
    for t in templates:
        assert "placeholders" in t and isinstance(t["placeholders"], list)
        assert t["subject"] and t["body"]


def test_rendering_fills_the_candidates_own_values(db_session):
    campaign = make_campaign(db_session)
    candidate = make_candidate(db_session, campaign)
    client = make_client(db_session)

    response = client.post(
        f"/api/campaigns/{campaign.id}/messages/templates/SHORTLIST_INVITE/render",
        json={"candidate_id": candidate.id},
    )
    assert response.status_code == 200
    body = response.json()
    assert "Haitham Al-Otaibi" in body["subject"] + body["body"]
    assert "Control Room Operator" in body["subject"] + body["body"]


def test_a_placeholder_nobody_can_resolve_is_left_visible(db_session):
    campaign = make_campaign(db_session)
    candidate = make_candidate(db_session, campaign)
    client = make_client(db_session)

    response = client.post(
        f"/api/campaigns/{campaign.id}/messages/templates/INTERVIEW_INVITE/render",
        json={"candidate_id": candidate.id},
    )
    assert response.status_code == 200
    body = response.json()
    assert "interview_when" in body["unresolved"]
    assert "{interview_when}" in body["body"]


def test_an_unresolved_placeholder_can_be_supplied(db_session):
    campaign = make_campaign(db_session)
    candidate = make_candidate(db_session, campaign)
    client = make_client(db_session)

    response = client.post(
        f"/api/campaigns/{campaign.id}/messages/templates/INTERVIEW_INVITE/render",
        json={"candidate_id": candidate.id, "values": {"interview_when": "Tue 16 Sep, 10:00"}},
    )
    body = response.json()
    assert body["unresolved"] == []
    assert "Tue 16 Sep, 10:00" in body["body"]


def test_an_unknown_template_is_refused(db_session):
    campaign = make_campaign(db_session)
    candidate = make_candidate(db_session, campaign)
    client = make_client(db_session)

    response = client.post(
        f"/api/campaigns/{campaign.id}/messages/templates/NOT_A_TEMPLATE/render",
        json={"candidate_id": candidate.id},
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Sending (recording)
# ---------------------------------------------------------------------------

def test_sending_records_an_audit_row_marked_simulated(db_session):
    campaign = make_campaign(db_session)
    candidate = make_candidate(db_session, campaign)
    client = make_client(db_session)

    response = client.post(
        f"/api/campaigns/{campaign.id}/messages/{candidate.id}/send",
        json={
            "channel": "EMAIL", "recipient": "haitham@example.com",
            "subject": "You are shortlisted", "body": "Come talk to us.",
            "template_id": "SHORTLIST_INVITE", "actor_id": "Fatima Al-Rashid",
        },
    )
    assert response.status_code == 201

    events = db_session.query(AuditEvent).filter_by(action=AuditAction.MESSAGE_SENT).all()
    assert len(events) == 1
    event = events[0]
    assert event.candidate_id == candidate.id
    assert event.campaign_id == campaign.id
    assert event.after["simulated"] is True
    assert event.after["recipient"] == "haitham@example.com"
    assert event.after["channel"] == "EMAIL"
    assert event.after["template_id"] == "SHORTLIST_INVITE"


def test_sending_uses_the_configured_mail_adapter_for_email(db_session, monkeypatch):
    """
    B10: when a real adapter reports a real send, the audit row and the API
    response both say so honestly — simulated flips to False and the
    adapter's own detail string is preserved. The adapter itself is faked
    here; see tests/test_outlook_adapter.py for the adapter's own coverage.
    """
    campaign = make_campaign(db_session)
    candidate = make_candidate(db_session, campaign)
    client = make_client(db_session)

    class _FakeAdapter:
        def send(self, *, to_address, subject, body, cc_address=None):
            return SendResult(sent=True, simulated=False,
                               detail=f"Sent via local Outlook to {to_address}.")

    monkeypatch.setattr(messages_api, "get_mail_adapter", lambda: _FakeAdapter())

    response = client.post(
        f"/api/campaigns/{campaign.id}/messages/{candidate.id}/send",
        json={
            "channel": "EMAIL", "recipient": "haitham@example.com",
            "subject": "You are shortlisted", "body": "Come talk to us.",
            "actor_id": "Fatima Al-Rashid",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["simulated"] is False
    assert "Sent via local Outlook" in body["send_detail"]

    event = db_session.query(AuditEvent).filter_by(action=AuditAction.MESSAGE_SENT).one()
    assert event.after["simulated"] is False
    assert "Sent via local Outlook" in event.after["send_detail"]


def test_an_email_subject_carries_the_reference_tag(db_session, monkeypatch):
    """
    B10: the tag a reply gets matched back on. Both the outbound send and
    the recorded/returned subject must carry it, since the audit row is
    what the product treats as the truth of what was actually sent.
    """
    campaign = make_campaign(db_session)
    candidate = make_candidate(db_session, campaign)
    client = make_client(db_session)

    captured = {}

    class _CapturingAdapter:
        def send(self, *, to_address, subject, body, cc_address=None):
            captured["subject"] = subject
            captured["cc_address"] = cc_address
            return SendResult(sent=True, simulated=False, detail="Sent.")

    monkeypatch.setattr(messages_api, "get_mail_adapter", lambda: _CapturingAdapter())

    response = client.post(
        f"/api/campaigns/{campaign.id}/messages/{candidate.id}/send",
        json={
            "channel": "EMAIL", "recipient": "haitham@example.com",
            "subject": "You are shortlisted", "body": "Come talk to us.",
            "actor_id": "Fatima Al-Rashid",
        },
    )
    assert response.status_code == 201
    expected = "You are shortlisted" + ref_tag(campaign.id, candidate.id)
    assert response.json()["subject"] == expected
    assert captured["subject"] == expected

    event = db_session.query(AuditEvent).filter_by(action=AuditAction.MESSAGE_SENT).one()
    assert event.after["subject"] == expected


def test_an_sms_subject_is_left_untagged(db_session):
    """SMS has no email subject a reply-reader parses, so nothing is appended."""
    campaign = make_campaign(db_session)
    candidate = make_candidate(db_session, campaign)
    client = make_client(db_session)

    response = client.post(
        f"/api/campaigns/{campaign.id}/messages/{candidate.id}/send",
        json={"channel": "SMS", "recipient": "0555", "subject": "Hi",
              "body": "Hi", "actor_id": "Fatima Al-Rashid"},
    )
    assert response.status_code == 201
    assert response.json()["subject"] == "Hi"


def test_a_cc_address_is_threaded_to_the_mail_adapter(db_session, monkeypatch):
    """B10: CC support, mirroring `mail.CC` in the user's own pasted script."""
    campaign = make_campaign(db_session)
    candidate = make_candidate(db_session, campaign)
    client = make_client(db_session)

    captured = {}

    class _CapturingAdapter:
        def send(self, *, to_address, subject, body, cc_address=None):
            captured["cc_address"] = cc_address
            return SendResult(sent=True, simulated=False, detail="Sent.")

    monkeypatch.setattr(messages_api, "get_mail_adapter", lambda: _CapturingAdapter())

    response = client.post(
        f"/api/campaigns/{campaign.id}/messages/{candidate.id}/send",
        json={
            "channel": "EMAIL", "recipient": "haitham@example.com",
            "subject": "Hi", "body": "Come talk to us.",
            "actor_id": "Fatima Al-Rashid", "cc": "recruiter@example.com",
        },
    )
    assert response.status_code == 201
    assert captured["cc_address"] == "recruiter@example.com"

    event = db_session.query(AuditEvent).filter_by(action=AuditAction.MESSAGE_SENT).one()
    assert event.after["cc"] == "recruiter@example.com"


def test_sms_never_uses_the_mail_adapter(db_session, monkeypatch):
    """A non-EMAIL channel has no adapter to call; it must stay simulated
    even when email_backend is configured for real sends."""
    campaign = make_campaign(db_session)
    candidate = make_candidate(db_session, campaign)
    client = make_client(db_session)

    def _fail_if_called():
        raise AssertionError("SMS must never reach the mail adapter")

    monkeypatch.setattr(messages_api, "get_mail_adapter", _fail_if_called)

    response = client.post(
        f"/api/campaigns/{campaign.id}/messages/{candidate.id}/send",
        json={"channel": "SMS", "recipient": "0555", "subject": "Hi",
              "body": "Hi", "actor_id": "Fatima Al-Rashid"},
    )
    assert response.status_code == 201
    assert response.json()["simulated"] is True


def test_a_non_approved_recipient_is_refused_when_backend_is_outlook(db_session, monkeypatch):
    """B10 hardening: a real Outlook backend must not mail an arbitrary
    caller-supplied address. Only the shared allowlist in mail_guard."""
    from app.core import mail_guard
    monkeypatch.setattr(mail_guard.settings, "email_backend", "outlook")
    campaign = make_campaign(db_session)
    candidate = make_candidate(db_session, campaign)
    client = make_client(db_session)

    response = client.post(
        f"/api/campaigns/{campaign.id}/messages/{candidate.id}/send",
        json={
            "channel": "EMAIL", "recipient": "haitham@example.com",
            "subject": "You are shortlisted", "body": "Come talk to us.",
            "actor_id": "Fatima Al-Rashid",
        },
    )
    assert response.status_code == 422
    assert "haitham@example.com" in response.json()["detail"]


def test_a_non_approved_recipient_is_allowed_when_backend_is_simulated(db_session, monkeypatch):
    """The guard must never block a simulated send — demos and tests rely
    on sending to whatever address they are given."""
    from app.core import mail_guard
    monkeypatch.setattr(mail_guard.settings, "email_backend", "simulated")
    campaign = make_campaign(db_session)
    candidate = make_candidate(db_session, campaign)
    client = make_client(db_session)

    response = client.post(
        f"/api/campaigns/{campaign.id}/messages/{candidate.id}/send",
        json={
            "channel": "EMAIL", "recipient": "haitham@example.com",
            "subject": "You are shortlisted", "body": "Come talk to us.",
            "actor_id": "Fatima Al-Rashid",
        },
    )
    assert response.status_code == 201


def test_an_empty_recipient_is_refused_with_a_readable_message(db_session):
    campaign = make_campaign(db_session)
    candidate = make_candidate(db_session, campaign)
    client = make_client(db_session)

    response = client.post(
        f"/api/campaigns/{campaign.id}/messages/{candidate.id}/send",
        json={"channel": "EMAIL", "recipient": "", "subject": "Hi", "body": "Hi",
              "actor_id": "Fatima Al-Rashid"},
    )
    assert response.status_code == 422
    assert "recipient" in response.json()["detail"].lower()


def test_an_empty_body_is_refused_with_a_readable_message(db_session):
    campaign = make_campaign(db_session)
    candidate = make_candidate(db_session, campaign)
    client = make_client(db_session)

    response = client.post(
        f"/api/campaigns/{campaign.id}/messages/{candidate.id}/send",
        json={"channel": "EMAIL", "recipient": "a@b.com", "subject": "Hi", "body": "  ",
              "actor_id": "Fatima Al-Rashid"},
    )
    assert response.status_code == 422
    assert "body" in response.json()["detail"].lower()


def test_sending_to_a_candidate_in_another_campaign_is_refused(db_session):
    campaign = make_campaign(db_session)
    other_campaign = make_campaign(db_session, name="Other")
    candidate = make_candidate(db_session, other_campaign)
    client = make_client(db_session)

    response = client.post(
        f"/api/campaigns/{campaign.id}/messages/{candidate.id}/send",
        json={"channel": "EMAIL", "recipient": "a@b.com", "subject": "Hi", "body": "Hi",
              "actor_id": "Fatima Al-Rashid"},
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Reading the log
# ---------------------------------------------------------------------------

def test_the_campaign_log_reads_newest_first(db_session):
    campaign = make_campaign(db_session)
    candidate = make_candidate(db_session, campaign)
    client = make_client(db_session)

    client.post(
        f"/api/campaigns/{campaign.id}/messages/{candidate.id}/send",
        json={"channel": "EMAIL", "recipient": "a@b.com", "subject": "First",
              "body": "First message", "actor_id": "Fatima Al-Rashid"},
    )
    client.post(
        f"/api/campaigns/{campaign.id}/messages/{candidate.id}/send",
        json={"channel": "SMS", "recipient": "0555", "subject": "Second",
              "body": "Second message", "actor_id": "Fatima Al-Rashid"},
    )

    response = client.get(f"/api/campaigns/{campaign.id}/messages")
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 2
    # "Second" was sent by SMS, which carries no reference tag; "First" was
    # EMAIL, which does (see test_an_email_subject_carries_the_reference_tag).
    assert rows[0]["subject"] == "Second"
    assert rows[1]["subject"] == "First" + ref_tag(campaign.id, candidate.id)
    assert rows[0]["candidate_id"] == candidate.id
    assert rows[0]["actor_id"] == "Fatima Al-Rashid"


def test_a_candidates_thread_reads_oldest_first(db_session):
    campaign = make_campaign(db_session)
    candidate = make_candidate(db_session, campaign)
    client = make_client(db_session)

    client.post(
        f"/api/campaigns/{campaign.id}/messages/{candidate.id}/send",
        json={"channel": "EMAIL", "recipient": "a@b.com", "subject": "First",
              "body": "First message", "actor_id": "Fatima Al-Rashid"},
    )
    client.post(
        f"/api/campaigns/{campaign.id}/messages/{candidate.id}/send",
        json={"channel": "SMS", "recipient": "0555", "subject": "Second",
              "body": "Second message", "actor_id": "Fatima Al-Rashid"},
    )

    response = client.get(f"/api/campaigns/{campaign.id}/messages/{candidate.id}")
    assert response.status_code == 200
    rows = response.json()
    assert [r["subject"] for r in rows] == [
        "First" + ref_tag(campaign.id, candidate.id), "Second",
    ]
