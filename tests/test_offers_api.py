"""
The offer: drafted, sent, and the candidate's answer.

Journey steps 8 and 9. Real state through `lifecycle_service.transition`,
real audit rows through `disposition_service.record_audit`. B12: draft/revise
render an approved offer letter, and send reuses B10's `MailAdapter` —
simulated by default (an honest audit row, nothing transmitted), a real
local-Outlook send only when `settings.email_backend == "outlook"`.
"""
from datetime import date, timedelta
from unittest.mock import patch

import pytest

from app.api import offers as offers_api
from app.core.outlook_adapter import SendResult
from app.db.models import AuditAction, AuditEvent
from sqlalchemy import select

from tests.test_processing import FAKE_JD_EXTRACTION, PDF_MIME, upload
from tests.test_evaluations import STRONG_CV, make_cv_pdf


FUTURE_START = (date.today() + timedelta(days=30)).isoformat()
FUTURE_EXPIRY = (date.today() + timedelta(days=10)).isoformat()


@pytest.fixture()
def people(client):
    def make(name, email, role):
        return client.post("/api/users", json={
            "full_name": name, "email": email, "role": role,
        }).json()

    return {
        "recruiter": make("Fatima Al-Rashid", "fatima@example.com", "RECRUITER"),
        "manager": make("Aziz Rahman", "aziz@example.com", "HIRING_MANAGER"),
        "admin": make("Sara Khan", "sara@example.com", "ADMIN"),
    }


@pytest.fixture()
def approved(client, people):
    """A campaign with one candidate walked all the way to APPROVED."""
    with patch("app.services.requirement_service.parse_jd", return_value=FAKE_JD_EXTRACTION):
        campaign_id = client.post("/api/campaigns", json={
            "name": "Offers", "job_title": "Control Room Operator",
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
    client.post(
        f"/api/campaigns/{campaign_id}/lifecycle/{candidate_id}/review",
        json={"reviewer_id": people["manager"]["id"], "outcome": "PROCEED"},
    )
    client.post(
        f"/api/campaigns/{campaign_id}/lifecycle/{candidate_id}/transition",
        json={"to_status": "FEEDBACK_COMPLETE", "actor_id": people["manager"]["id"]},
    )
    client.post(
        f"/api/campaigns/{campaign_id}/lifecycle/{candidate_id}/transition",
        json={"to_status": "PENDING_APPROVAL", "actor_id": people["recruiter"]["id"]},
    )
    client.post(
        f"/api/campaigns/{campaign_id}/lifecycle/{candidate_id}/transition",
        json={"to_status": "PENDING_COST_CENTRE", "actor_id": people["admin"]["id"]},
    )
    client.post(
        f"/api/campaigns/{campaign_id}/lifecycle/{candidate_id}/transition",
        json={"to_status": "APPROVED", "actor_id": people["admin"]["id"]},
    )
    return campaign_id, candidate_id


def _draft_payload(actor_id, **overrides):
    payload = {
        "actor_id": actor_id,
        "base_salary": 12000,
        "currency": "QAR",
        "grade": "G7",
        "start_date": FUTURE_START,
        "expiry_date": FUTURE_EXPIRY,
        "allowances": {"housing": 1500, "transport": 500},
        "notes": "Strong console hours.",
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# Drafting
# ---------------------------------------------------------------------------

def test_an_approved_candidate_gets_an_offer_drafted(client, approved, people):
    campaign_id, candidate_id = approved
    draft = client.post(
        f"/api/campaigns/{campaign_id}/offers/{candidate_id}/draft",
        json=_draft_payload(people["recruiter"]["id"]),
    )
    assert draft.status_code == 201
    body = draft.json()
    assert body["status"] == "OFFER_DRAFTED"
    assert body["total_package"] == 12000 + 1500 + 500

    # B12: the draft response carries the rendered letter — this is HR's
    # review copy before anything is sent.
    assert "Control Room Operator" in body["letter"]
    assert "QAR 14,000.00" in body["letter"]
    assert "Housing" in body["letter"]

    now = client.get(f"/api/campaigns/{campaign_id}/lifecycle/{candidate_id}").json()
    assert now["status"] == "OFFER_DRAFTED"


def test_a_negative_salary_is_refused_in_plain_words(client, approved, people):
    campaign_id, candidate_id = approved
    refused = client.post(
        f"/api/campaigns/{campaign_id}/offers/{candidate_id}/draft",
        json=_draft_payload(people["recruiter"]["id"], base_salary=-500),
    )
    assert refused.status_code == 422
    assert "positive" in refused.json()["detail"]


def test_a_start_date_in_the_past_is_refused(client, approved, people):
    campaign_id, candidate_id = approved
    refused = client.post(
        f"/api/campaigns/{campaign_id}/offers/{candidate_id}/draft",
        json=_draft_payload(
            people["recruiter"]["id"],
            start_date=(date.today() - timedelta(days=1)).isoformat(),
        ),
    )
    assert refused.status_code == 422
    assert "future" in refused.json()["detail"]


def test_an_expiry_after_the_start_date_is_refused(client, approved, people):
    campaign_id, candidate_id = approved
    refused = client.post(
        f"/api/campaigns/{campaign_id}/offers/{candidate_id}/draft",
        json=_draft_payload(
            people["recruiter"]["id"],
            start_date=FUTURE_EXPIRY, expiry_date=FUTURE_START,
        ),
    )
    assert refused.status_code == 422
    assert "expire before" in refused.json()["detail"]


def test_the_draft_writes_an_audit_row_with_the_package(
    client, approved, people, db_session
):
    campaign_id, candidate_id = approved
    client.post(
        f"/api/campaigns/{campaign_id}/offers/{candidate_id}/draft",
        json=_draft_payload(people["recruiter"]["id"]),
    )
    event = db_session.scalars(
        select(AuditEvent).where(AuditEvent.action == AuditAction.OFFER_DRAFTED)
    ).first()
    assert event is not None
    assert event.after["total_package"] == 14000
    assert event.after["base_salary"] == 12000


# ---------------------------------------------------------------------------
# Revise
# ---------------------------------------------------------------------------

def test_a_revision_records_a_fresh_draft_and_names_what_changed(
    client, approved, people
):
    campaign_id, candidate_id = approved
    first = client.post(
        f"/api/campaigns/{campaign_id}/offers/{candidate_id}/draft",
        json=_draft_payload(people["recruiter"]["id"]),
    ).json()

    revised = client.post(
        f"/api/campaigns/{campaign_id}/offers/{candidate_id}/revise",
        json=_draft_payload(people["recruiter"]["id"], base_salary=13000),
    )
    assert revised.status_code == 200
    body = revised.json()
    assert body["base_salary"] == 13000
    assert body["changed"]["base_salary"] == {"old": 12000, "new": 13000}
    assert body["revision_of"]
    assert "QAR 13,000.00" in body["letter"]

    # No state change — an offer that is silently overwritten never happens,
    # but nor does a revision move the candidate anywhere.
    now = client.get(f"/api/campaigns/{campaign_id}/lifecycle/{candidate_id}").json()
    assert now["status"] == "OFFER_DRAFTED"


def test_a_revision_needs_an_existing_draft(client, approved, people):
    campaign_id, candidate_id = approved
    refused = client.post(
        f"/api/campaigns/{campaign_id}/offers/{candidate_id}/revise",
        json=_draft_payload(people["recruiter"]["id"]),
    )
    assert refused.status_code == 422
    assert "drafted offer to revise" in refused.json()["detail"]


# ---------------------------------------------------------------------------
# Send
# ---------------------------------------------------------------------------

def _drafted(client, campaign_id, candidate_id, people):
    return client.post(
        f"/api/campaigns/{campaign_id}/offers/{candidate_id}/draft",
        json=_draft_payload(people["recruiter"]["id"]),
    )


def test_sending_the_offer_moves_the_candidate_and_names_the_recipient(
    client, approved, people
):
    campaign_id, candidate_id = approved
    _drafted(client, campaign_id, candidate_id, people)

    sent = client.post(
        f"/api/campaigns/{campaign_id}/offers/{candidate_id}/send",
        json={"actor_id": people["recruiter"]["id"]},
    )
    assert sent.status_code == 200
    body = sent.json()
    assert body["status"] == "OFFER_SENT"
    assert "@" in body["recipient_email"]

    now = client.get(f"/api/campaigns/{campaign_id}/lifecycle/{candidate_id}").json()
    assert now["status"] == "OFFER_SENT"


def test_the_send_is_simulated_by_default_only_audited(
    client, approved, people, db_session
):
    campaign_id, candidate_id = approved
    _drafted(client, campaign_id, candidate_id, people)
    sent = client.post(
        f"/api/campaigns/{campaign_id}/offers/{candidate_id}/send",
        json={"actor_id": people["recruiter"]["id"]},
    )
    assert sent.json()["simulated"] is True

    event = db_session.scalars(
        select(AuditEvent).where(AuditEvent.action == AuditAction.OFFER_SENT)
    ).first()
    assert event is not None
    assert "@" in event.after["recipient_email"]
    assert event.after["simulated"] is True


def test_sending_uses_the_configured_mail_adapter_and_the_rendered_letter(
    client, approved, people, db_session, monkeypatch
):
    """B12: when a real adapter reports a real send, the audit row and the
    API response both say so honestly, and the letter body actually sent is
    the one rendered at draft time. The adapter itself is faked here; see
    tests/test_outlook_adapter.py for the adapter's own coverage."""
    campaign_id, candidate_id = approved
    draft = _drafted(client, campaign_id, candidate_id, people).json()

    sent_bodies = []

    class _FakeAdapter:
        def send(self, *, to_address, subject, body):
            sent_bodies.append(body)
            return SendResult(sent=True, simulated=False,
                               detail=f"Sent via local Outlook to {to_address}.")

    monkeypatch.setattr(offers_api, "get_mail_adapter", lambda: _FakeAdapter())

    sent = client.post(
        f"/api/campaigns/{campaign_id}/offers/{candidate_id}/send",
        json={"actor_id": people["recruiter"]["id"]},
    )
    assert sent.status_code == 200
    body = sent.json()
    assert body["simulated"] is False
    assert "Sent via local Outlook" in body["send_detail"]
    assert sent_bodies == [draft["letter"]]

    event = db_session.scalars(
        select(AuditEvent).where(AuditEvent.action == AuditAction.OFFER_SENT)
    ).first()
    assert event.after["simulated"] is False
    assert "Sent via local Outlook" in event.after["send_detail"]


def test_a_draft_cannot_be_sent_before_it_exists(client, approved, people):
    campaign_id, candidate_id = approved
    refused = client.post(
        f"/api/campaigns/{campaign_id}/offers/{candidate_id}/send",
        json={"actor_id": people["recruiter"]["id"]},
    )
    assert refused.status_code == 422


# ---------------------------------------------------------------------------
# Response
# ---------------------------------------------------------------------------

def _sent(client, campaign_id, candidate_id, people):
    _drafted(client, campaign_id, candidate_id, people)
    return client.post(
        f"/api/campaigns/{campaign_id}/offers/{candidate_id}/send",
        json={"actor_id": people["recruiter"]["id"]},
    )


def test_an_acceptance_moves_the_candidate_to_accepted(client, approved, people):
    campaign_id, candidate_id = approved
    _sent(client, campaign_id, candidate_id, people)

    response = client.post(
        f"/api/campaigns/{campaign_id}/offers/{candidate_id}/response",
        json={"actor_id": people["recruiter"]["id"], "response": "ACCEPTED"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "OFFER_ACCEPTED"


def test_a_decline_without_a_reason_surfaces_the_state_machines_refusal(
    client, approved, people
):
    campaign_id, candidate_id = approved
    _sent(client, campaign_id, candidate_id, people)

    refused = client.post(
        f"/api/campaigns/{campaign_id}/offers/{candidate_id}/response",
        json={"actor_id": people["recruiter"]["id"], "response": "DECLINED",
              "reason": "", "reason_code": "COMPENSATION"},
    )
    assert refused.status_code == 422
    assert "needs a reason" in refused.json()["detail"]


def test_a_decline_without_a_coded_reason_is_refused(client, approved, people):
    campaign_id, candidate_id = approved
    _sent(client, campaign_id, candidate_id, people)

    refused = client.post(
        f"/api/campaigns/{campaign_id}/offers/{candidate_id}/response",
        json={"actor_id": people["recruiter"]["id"], "response": "DECLINED",
              "reason": "Took a counter-offer."},
    )
    assert refused.status_code == 422
    assert "reason code" in refused.json()["detail"]


def test_a_decline_with_a_coded_reason_is_recorded(
    client, approved, people, db_session
):
    campaign_id, candidate_id = approved
    _sent(client, campaign_id, candidate_id, people)

    declined = client.post(
        f"/api/campaigns/{campaign_id}/offers/{candidate_id}/response",
        json={"actor_id": people["recruiter"]["id"], "response": "DECLINED",
              "reason": "Took a counter-offer.", "reason_code": "COUNTER_OFFER"},
    )
    assert declined.status_code == 200
    assert declined.json()["status"] == "OFFER_DECLINED"

    event = db_session.scalars(
        select(AuditEvent).where(AuditEvent.action == AuditAction.OFFER_RESPONSE_RECORDED)
    ).first()
    assert event.after["reason_code"] == "COUNTER_OFFER"


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------

def test_the_campaign_level_read_shows_every_offer(client, approved, people):
    campaign_id, candidate_id = approved
    _sent(client, campaign_id, candidate_id, people)

    offers = client.get(f"/api/campaigns/{campaign_id}/offers").json()
    assert len(offers) == 1
    row = offers[0]
    assert row["candidate_id"] == candidate_id
    assert row["status"] == "OFFER_SENT"
    assert row["total_package"] == 14000
    assert row["days_since_sent"] is not None


def test_the_candidate_level_read_shows_history_oldest_first(
    client, approved, people
):
    campaign_id, candidate_id = approved
    _drafted(client, campaign_id, candidate_id, people)
    client.post(
        f"/api/campaigns/{campaign_id}/offers/{candidate_id}/revise",
        json=_draft_payload(people["recruiter"]["id"], base_salary=13000),
    )

    history = client.get(
        f"/api/campaigns/{campaign_id}/offers/{candidate_id}"
    ).json()
    assert history["candidate_id"] == candidate_id
    actions = [e["action"] for e in history["events"]]
    assert actions == ["OFFER_DRAFTED", "OFFER_DRAFTED"]
    assert history["events"][0]["after"]["base_salary"] == 12000
    assert history["events"][1]["after"]["base_salary"] == 13000


def test_an_explicit_recipient_overrides_the_candidates_own_address(
    client, approved, people
):
    """A demo candidate's CV-extracted address is never an approved real
    recipient, so the offer send accepts a chosen address the way comms.html
    already does. Blank keeps the candidate's own address."""
    campaign_id, candidate_id = approved
    _drafted(client, campaign_id, candidate_id, people)

    sent = client.post(
        f"/api/campaigns/{campaign_id}/offers/{candidate_id}/send",
        json={
            "actor_id": people["recruiter"]["id"],
            "recipient": "daipayan.r@protivitiglobal.in",
        },
    )
    assert sent.status_code == 200
    assert sent.json()["recipient_email"] == "daipayan.r@protivitiglobal.in"


def test_omitting_the_recipient_still_uses_the_candidates_address(
    client, approved, people
):
    campaign_id, candidate_id = approved
    _drafted(client, campaign_id, candidate_id, people)

    sent = client.post(
        f"/api/campaigns/{campaign_id}/offers/{candidate_id}/send",
        json={"actor_id": people["recruiter"]["id"]},
    )
    assert sent.status_code == 200
    candidate = client.get(
        f"/api/campaigns/{campaign_id}/candidates"
    ).json()
    rows = candidate if isinstance(candidate, list) else candidate.get("items", [])
    own = [r for r in rows if r["id"] == candidate_id][0]["email"]
    assert sent.json()["recipient_email"] == own


def test_a_rejected_recipient_leaves_the_candidate_not_sent(
    client, approved, people, monkeypatch
):
    """The allowlist used to run after the lifecycle transition, so a blocked
    recipient still left the candidate recorded as OFFER_SENT with no letter
    ever sent. The record must never claim a send that did not happen."""
    from app.core.config import settings

    campaign_id, candidate_id = approved
    _drafted(client, campaign_id, candidate_id, people)
    monkeypatch.setattr(settings, "email_backend", "outlook")

    blocked = client.post(
        f"/api/campaigns/{campaign_id}/offers/{candidate_id}/send",
        json={
            "actor_id": people["recruiter"]["id"],
            "recipient": "stranger@nowhere.example",
        },
    )
    assert blocked.status_code == 422

    now = client.get(f"/api/campaigns/{campaign_id}/lifecycle/{candidate_id}").json()
    assert now["status"] == "OFFER_DRAFTED"
