"""
The hiring-manager handoff work queue (W-A, wide pass journey steps 4 & 10).

`GET /api/campaigns/{id}/handoff/queue` answers "who owes what right now" in
one call, grouped the way the screen needs to show it, so the screen does not
make six calls and group them in JavaScript.
"""
from unittest.mock import patch

import pytest

from app.db.models import LifecycleStatus

from tests.test_processing import FAKE_JD_EXTRACTION, PDF_MIME, upload
from tests.test_evaluations import STRONG_CV, make_cv_pdf

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
def shortlisted(client):
    """A campaign with one assessed, shortlisted candidate."""
    with patch("app.services.requirement_service.parse_jd", return_value=FAKE_JD_EXTRACTION):
        campaign_id = client.post("/api/campaigns", json={
            "name": "Handoff", "job_title": "Control Room Operator",
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
    return campaign_id, candidate_id


def test_a_shortlisted_candidate_nobody_has_sent_is_ready_to_send(
    client, shortlisted, people
):
    campaign_id, candidate_id = shortlisted
    client.post(f"/api/campaigns/{campaign_id}/lifecycle/{candidate_id}/enter",
                params={"actor_id": people["recruiter"]["id"]})

    queue = client.get(f"/api/campaigns/{campaign_id}/handoff/queue").json()

    assert queue["total"] == 1
    ready = queue["ready_to_send"]
    assert len(ready) == 1
    assert ready[0]["candidate_id"] == candidate_id
    assert ready[0]["status"] == "SHORTLISTED"
    assert ready[0]["status_label"] == "Shortlisted, not yet sent to the hiring manager"
    assert "days_in_state" in ready[0]
    assert queue["with_manager"] == []
    assert queue["returned"] == []
    assert queue["ready_to_close"] == []


def test_a_candidate_with_the_manager_shows_days_waiting_and_the_owner(
    client, shortlisted, people
):
    campaign_id, candidate_id = shortlisted
    client.post(
        f"/api/campaigns/{campaign_id}/lifecycle/{candidate_id}/send-to-manager",
        json={"actor_id": people["recruiter"]["id"],
              "manager_id": people["manager"]["id"]},
    )

    queue = client.get(f"/api/campaigns/{campaign_id}/handoff/queue").json()

    with_manager = queue["with_manager"]
    assert len(with_manager) == 1
    assert with_manager[0]["owner_name"] == "Aziz Rahman"
    assert with_manager[0]["days_in_state"] >= 0
    assert queue["ready_to_send"] == []


def test_a_returned_candidate_carries_the_managers_question(
    client, shortlisted, people
):
    campaign_id, candidate_id = shortlisted
    client.post(
        f"/api/campaigns/{campaign_id}/lifecycle/{candidate_id}/send-to-manager",
        json={"actor_id": people["recruiter"]["id"],
              "manager_id": people["manager"]["id"]},
    )
    client.post(
        f"/api/campaigns/{campaign_id}/lifecycle/{candidate_id}/review",
        json={"reviewer_id": people["manager"]["id"], "outcome": "QUESTION",
              "reason": "How many hours on the console, and on which unit?"},
    )

    queue = client.get(f"/api/campaigns/{campaign_id}/handoff/queue").json()

    returned = queue["returned"]
    assert len(returned) == 1
    assert returned[0]["question"] == "How many hours on the console, and on which unit?"


def test_an_accepted_offer_is_ready_to_close_as_hired(client, shortlisted, people, db_session):
    from app.services import lifecycle_service

    campaign_id, candidate_id = shortlisted
    client.post(f"/api/campaigns/{campaign_id}/lifecycle/{candidate_id}/enter",
                params={"actor_id": people["recruiter"]["id"]})
    for to_status in (
        LifecycleStatus.WITH_HIRING_MANAGER, LifecycleStatus.INTERVIEW_SCHEDULED,
        LifecycleStatus.FEEDBACK_COMPLETE, LifecycleStatus.PENDING_APPROVAL,
        LifecycleStatus.PENDING_COST_CENTRE, LifecycleStatus.APPROVED,
        LifecycleStatus.OFFER_DRAFTED, LifecycleStatus.OFFER_SENT,
        LifecycleStatus.OFFER_ACCEPTED,
    ):
        lifecycle_service.transition(
            db_session, campaign_id=campaign_id, candidate_id=candidate_id,
            to_status=to_status, actor_id=people["admin"]["id"],
        )

    queue = client.get(f"/api/campaigns/{campaign_id}/handoff/queue").json()

    ready_to_close = queue["ready_to_close"]
    assert len(ready_to_close) == 1
    assert ready_to_close[0]["status"] == "OFFER_ACCEPTED"


def test_an_unknown_campaign_is_refused(client):
    missing = client.get("/api/campaigns/does-not-exist/handoff/queue")
    assert missing.status_code == 404
