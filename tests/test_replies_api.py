"""
B10/B11 — dispatching classified email replies into the domain, and the
on-demand API surface over it (`app/api/replies.py`, `app/services/reply_service.py`).

The Outlook inbox itself is never touched here: `app.services.reply_service`
is unit-tested against a fake `InboxReader` double (same DI shape
`test_outlook_adapter.py`/`test_calendar_adapter.py`/`test_reply_ingestion.py`
use), and the LLM path is never exercised — every reply body here is worded
to hit the classifier's deterministic tier.
"""
from unittest.mock import patch

import pytest
from sqlalchemy import select

from app.db.models import AuditAction, AuditEvent, LifecycleStatus
from app.core.reply_ingestion import ParsedReply
from app.services import reply_service

from tests.test_processing import FAKE_JD_EXTRACTION, PDF_MIME, upload
from tests.test_evaluations import STRONG_CV, make_cv_pdf

UNKNOWN_CAMPAIGN_ID = "99999999-9999-9999-9999-999999999999"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def people(client):
    def make(name, email, role):
        return client.post("/api/users", json={
            "full_name": name, "email": email, "role": role,
        }).json()

    return {
        "recruiter": make("Fatima Al-Rashid", "fatima@example.com", "RECRUITER"),
        "manager": make("Aziz Rahman", "aziz@example.com", "HIRING_MANAGER"),
    }


@pytest.fixture()
def with_manager(client, people):
    """A shortlisted candidate already handed to the hiring manager."""
    with patch("app.services.requirement_service.parse_jd", return_value=FAKE_JD_EXTRACTION):
        campaign_id = client.post("/api/campaigns", json={
            "name": "Replies", "job_title": "Control Room Operator",
            "job_description": "Python and AWS backend engineer.",
        }).json()["id"]
        client.post(f"/api/campaigns/{campaign_id}/requirements/extract", json={})
    client.post(f"/api/campaigns/{campaign_id}/rubric/versions",
                json={"seed_from_requirements": True})
    client.post(f"/api/campaigns/{campaign_id}/rubric/versions/1/submit", json={})
    client.post(f"/api/campaigns/{campaign_id}/rubric/versions/1/approve",
                json={"approved_by": "Fatima Al-Rashid"})
    upload(client, campaign_id, [("haitham.pdf", make_cv_pdf(STRONG_CV), PDF_MIME)])
    client.post(f"/api/campaigns/{campaign_id}/evaluations/runs", json={})

    candidate_id = client.get(f"/api/campaigns/{campaign_id}/candidates").json()[0]["id"]
    client.post(
        f"/api/campaigns/{campaign_id}/candidates/{candidate_id}/disposition",
        json={"disposition": "SHORTLIST", "actor": "Fatima Al-Rashid"},
    )
    client.post(
        f"/api/campaigns/{campaign_id}/lifecycle/{candidate_id}/send-to-manager",
        json={"actor_id": people["recruiter"]["id"], "manager_id": people["manager"]["id"]},
    )
    return campaign_id, candidate_id


def _reply(campaign_id, candidate_id=None, *, body, sender="aziz@example.com",
          message_id="msg-1"):
    return ParsedReply(
        message_id=message_id, campaign_id=campaign_id, candidate_id=candidate_id,
        sender_address=sender, received_at=None,
        subject="RE: Interview", body=body,
    )


def _patch_inbox(replies):
    return patch.object(reply_service, "get_inbox_reader", return_value=_FakeReader(replies))


class _FakeReader:
    def __init__(self, replies):
        self._replies = replies

    def read_replies(self, *, limit=200):
        return self._replies


def _lifecycle_status(db_session, campaign_id, candidate_id):
    from app.services import lifecycle_service
    record = lifecycle_service.current(db_session, campaign_id, candidate_id)
    return record.status if record else None


# ---------------------------------------------------------------------------
# Default (auto-apply off): every reply is a proposed decision only
# ---------------------------------------------------------------------------

def test_ingest_records_a_proposed_decision_by_default(client, db_session, with_manager):
    campaign_id, candidate_id = with_manager
    replies = [_reply(campaign_id, candidate_id, body="Approved, looks good.")]

    with _patch_inbox(replies):
        response = client.post("/api/replies/ingest")

    assert response.status_code == 200
    body = response.json()
    assert body["processed"] == 1
    assert body["replies"][0]["status"] == "proposed"
    assert body["replies"][0]["intent"] == "approve"

    # The candidate has NOT moved — a proposed decision never mutates state.
    assert _lifecycle_status(db_session, campaign_id, candidate_id) == \
        LifecycleStatus.WITH_HIRING_MANAGER.value

    events = list(db_session.scalars(
        select(AuditEvent).where(AuditEvent.action == AuditAction.EMAIL_REPLY_RECEIVED)
    ).all())
    assert len(events) == 1
    assert events[0].after["status"] == "proposed"
    assert events[0].candidate_id == candidate_id


def test_pending_lists_the_proposed_decision(client, with_manager):
    campaign_id, candidate_id = with_manager
    replies = [_reply(campaign_id, candidate_id, body="Approved, looks good.")]
    with _patch_inbox(replies):
        client.post("/api/replies/ingest")

    pending = client.get(f"/api/campaigns/{campaign_id}/replies/pending").json()

    assert len(pending) == 1
    assert pending[0]["candidate_id"] == candidate_id
    assert pending[0]["status"] == "proposed"


def test_applying_a_proposed_decision_moves_the_candidate(client, db_session, with_manager, people):
    campaign_id, candidate_id = with_manager
    replies = [_reply(campaign_id, candidate_id, body="Approved, looks good.")]
    with _patch_inbox(replies):
        client.post("/api/replies/ingest")
    entity_id = client.get(f"/api/campaigns/{campaign_id}/replies/pending").json()[0]["entity_id"]

    response = client.post(
        f"/api/campaigns/{campaign_id}/replies/{entity_id}/apply",
        json={"actor_id": people["manager"]["id"]},
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "manually_applied"
    assert _lifecycle_status(db_session, campaign_id, candidate_id) == \
        LifecycleStatus.INTERVIEW_SCHEDULED.value
    assert client.get(f"/api/campaigns/{campaign_id}/replies/pending").json() == []


def test_applying_an_already_resolved_decision_is_refused(client, with_manager, people):
    campaign_id, candidate_id = with_manager
    replies = [_reply(campaign_id, candidate_id, body="Approved, looks good.")]
    with _patch_inbox(replies):
        client.post("/api/replies/ingest")
    entity_id = client.get(f"/api/campaigns/{campaign_id}/replies/pending").json()[0]["entity_id"]
    client.post(f"/api/campaigns/{campaign_id}/replies/{entity_id}/apply",
               json={"actor_id": people["manager"]["id"]})

    response = client.post(
        f"/api/campaigns/{campaign_id}/replies/{entity_id}/apply",
        json={"actor_id": people["manager"]["id"]},
    )

    assert response.status_code == 422
    assert "already been resolved" in response.json()["detail"]


# ---------------------------------------------------------------------------
# A campaign-level reply names no candidate — never auto-applied, and the
# apply endpoint refuses rather than guessing which candidate it was about.
# ---------------------------------------------------------------------------

def test_a_campaign_level_reply_is_proposed_only_and_cannot_be_applied(client, with_manager):
    campaign_id, _candidate_id = with_manager
    replies = [_reply(campaign_id, candidate_id=None, body="Approved, looks good.")]
    with _patch_inbox(replies):
        client.post("/api/replies/ingest")

    pending = client.get(f"/api/campaigns/{campaign_id}/replies/pending").json()
    assert len(pending) == 1
    assert pending[0]["candidate_id"] is None

    response = client.post(
        f"/api/campaigns/{campaign_id}/replies/{pending[0]['entity_id']}/apply",
        json={"actor_id": "does-not-matter"},
    )
    assert response.status_code == 422
    assert "no single hiring-manager verdict" in response.json()["detail"]


# ---------------------------------------------------------------------------
# Auto-apply, opt-in
# ---------------------------------------------------------------------------

def test_auto_apply_setting_off_by_default():
    from app.core.config import settings
    assert settings.auto_apply_reply_decisions is False


def test_auto_apply_moves_the_candidate_when_the_setting_is_on(
    client, db_session, with_manager, monkeypatch,
):
    monkeypatch.setattr(reply_service.settings, "auto_apply_reply_decisions", True)
    campaign_id, candidate_id = with_manager
    replies = [_reply(campaign_id, candidate_id, body="Approved, looks good.",
                      sender="aziz@example.com")]

    with _patch_inbox(replies):
        response = client.post("/api/replies/ingest")

    assert response.json()["replies"][0]["status"] == "auto_applied"
    assert _lifecycle_status(db_session, campaign_id, candidate_id) == \
        LifecycleStatus.INTERVIEW_SCHEDULED.value
    assert client.get(f"/api/campaigns/{campaign_id}/replies/pending").json() == []


def test_auto_apply_does_not_fire_for_an_unrecognised_sender(
    client, db_session, with_manager, monkeypatch,
):
    """Conservative: a reply from an address with no matching User is never guessed at."""
    monkeypatch.setattr(reply_service.settings, "auto_apply_reply_decisions", True)
    campaign_id, candidate_id = with_manager
    replies = [_reply(campaign_id, candidate_id, body="Approved, looks good.",
                      sender="someone-not-on-file@example.com")]

    with _patch_inbox(replies):
        response = client.post("/api/replies/ingest")

    assert response.json()["replies"][0]["status"] == "proposed"
    assert _lifecycle_status(db_session, campaign_id, candidate_id) == \
        LifecycleStatus.WITH_HIRING_MANAGER.value


def test_auto_apply_never_fires_for_a_schedule_confirmation(
    client, db_session, with_manager, monkeypatch,
):
    """
    No existing service call this module can point at for "confirmed for
    2026-09-20" — proposed only, regardless of the setting.
    """
    monkeypatch.setattr(reply_service.settings, "auto_apply_reply_decisions", True)
    campaign_id, candidate_id = with_manager
    replies = [_reply(campaign_id, candidate_id,
                      body="Confirmed, works for 2026-09-20 10:00.")]

    with _patch_inbox(replies):
        response = client.post("/api/replies/ingest")

    reply = response.json()["replies"][0]
    assert reply["intent"] == "schedule_confirm"
    assert reply["status"] == "proposed"
    assert _lifecycle_status(db_session, campaign_id, candidate_id) == \
        LifecycleStatus.WITH_HIRING_MANAGER.value


# ---------------------------------------------------------------------------
# Idempotency and unknown campaigns
# ---------------------------------------------------------------------------

def test_ingesting_the_same_message_twice_only_records_it_once(client, db_session, with_manager):
    campaign_id, candidate_id = with_manager
    replies = [_reply(campaign_id, candidate_id, body="Approved, looks good.",
                      message_id="dup-1")]

    with _patch_inbox(replies):
        client.post("/api/replies/ingest")
        second = client.post("/api/replies/ingest")

    assert second.json()["processed"] == 0
    events = list(db_session.scalars(
        select(AuditEvent).where(AuditEvent.action == AuditAction.EMAIL_REPLY_RECEIVED)
    ).all())
    assert len(events) == 1


def test_a_reply_naming_an_unknown_campaign_is_skipped(client, with_manager):
    campaign_id, candidate_id = with_manager
    replies = [_reply(UNKNOWN_CAMPAIGN_ID, candidate_id, body="Approved, looks good.")]

    with _patch_inbox(replies):
        response = client.post("/api/replies/ingest")

    assert response.json()["processed"] == 0


def test_ingest_is_a_no_op_when_reply_ingestion_is_not_enabled(client):
    """`get_inbox_reader()` returns None unless email_backend == 'outlook' —
    unpatched here, so this exercises the real gate rather than the fake double."""
    response = client.post("/api/replies/ingest")
    assert response.status_code == 200
    assert response.json() == {"processed": 0, "replies": []}
